"""Fail-closed checks using installed Nav2/ROS interfaces; never an alternative navigator."""
from pathlib import Path
import json
import os
import math
import time
import xml.etree.ElementTree as ET
import numpy as np
import yaml
from PIL import Image
from .config import ROOT, PROFILE, profile, scenario, nav2_parameters, source_manifest

def static_check():
    checks = []
    def check(name, passed, detail=None):
        checks.append(dict(name=name, passed=bool(passed), detail=detail))
    cfg = scenario()
    for key in ['scenario', 'nav2_template', 'static_map', 'collision_map', 'world', 'ros_setup', 'rmf_setup']:
        path = Path(profile()[key])
        if not path.is_absolute(): path = ROOT / path
        check('file:' + key, path.is_file(), str(path))
    for package in ['nav2_bringup', 'nav2_bt_navigator', 'nav2_behaviors', 'ros_gz_bridge', 'robot_state_publisher', 'turtlebot4_description', 'ros_gz_sim', 'controller_manager']:
        check('installed:' + package, (Path('/opt/ros/humble/share') / package / 'package.xml').is_file())
    navmap = yaml.safe_load((ROOT / profile()['static_map']).read_text())
    image = (ROOT / profile()['static_map']).parent / navmap['image']
    pixels = np.asarray(Image.open(image))
    check('static_map:image', pixels.ndim == 2)
    check('static_sampling:metadata', navmap['resolution'] == .05 and navmap['origin'] == [0., -50., 0.] and pixels.shape == (1000,1200), 'Existing evidence helper is calibrated to this immutable Clinic raster; other metadata must fail.')
    for robot in cfg['robots']:
        params = nav2_parameters(robot, resolve=True)
        for kind in ['local_costmap', 'global_costmap']:
            p = params[kind][kind]['ros__parameters']
            check(robot + ':' + kind + ':publish_rate', p.get('publish_frequency',0)>0)
            check(robot + ':' + kind + ':sim_time', p.get('use_sim_time') is True)
            check(robot + ':' + kind + ':frame', p['robot_base_frame'] == 'base_link')
            for layer in p['plugins']:
                plugin = p.get(layer, {})
                for source in plugin.get('observation_sources', '').split():
                    topic = plugin[source].get('topic')
                    check(robot + ':' + kind + ':' + layer + ':scan', topic == '/' + robot + '/scan', topic)
                    check(robot + ':' + kind + ':' + layer + ':mark_clear', plugin[source].get('marking') and plugin[source].get('clearing'))
        x,y,yaw = cfg['robots'][robot]['start']
        check(robot + ':start', all(math.isfinite(v) for v in [x,y,yaw]))
        check(robot + ':urdf', (ROOT/'config/three_tb4'/f'{robot}.urdf').is_file())
    for name, xyz in cfg['anchors'].items():
        x,y = xyz[:2]; col = int((x-navmap['origin'][0])/navmap['resolution']); row=pixels.shape[0]-1-int((y-navmap['origin'][1])/navmap['resolution'])
        check('anchor:' + name + ':free', 0<=row<pixels.shape[0] and 0<=col<pixels.shape[1] and pixels[row,col]>=200)
    slots = ['CPW2','CPW2B','CPW2C']
    check('PW2:separate_clear_slots', min(math.dist(cfg['anchors'][u][:2],cfg['anchors'][v][:2]) for i,u in enumerate(slots) for v in slots[i+1:]) >= .75)
    tree = Path('/opt/ros/humble/share/nav2_bt_navigator/behavior_trees/navigate_to_pose_w_replanning_and_recovery.xml')
    tags = {n.tag for n in ET.parse(tree).iter()}
    check('upstream:recovery_available', {'FollowPath','ClearEntireCostmap','Spin','Wait'} <= tags)
    return dict(passed=all(c['passed'] for c in checks), checks=checks, source_hashes=source_manifest(), scope='Static only: not actual Nav2 reachability, sensor causality or robot interaction acceptance.')

def runtime_check(timeout=90., pulse=False):
    import rclpy
    from rclpy.node import Node
    from rclpy.executors import SingleThreadedExecutor
    from rclpy.action import get_action_names_and_types
    from rclpy.parameter import Parameter
    from rclpy.time import Time
    from rclpy.qos import qos_profile_sensor_data, qos_check_compatible, QoSCompatibility
    from lifecycle_msgs.srv import GetState
    from rcl_interfaces.srv import GetParameters
    from nav2_msgs.msg import Costmap
    from nav2_msgs.srv import ClearEntireCostmap
    from sensor_msgs.msg import LaserScan
    from std_msgs.msg import String
    from tf2_ros import Buffer, TransformListener
    from shared_resource import STATE_QOS
    from bed_local_evidence import static_sampling_mask, local_delta
    cfg=scenario();mask=static_sampling_mask(ROOT/'config/hospital_aligned/semantic_navigation.pgm')
    class RobotCheck(Node):
        def __init__(self, rid):
            super().__init__('clinic_runtime_preflight',namespace=rid,use_global_arguments=False,
                cli_args=['--ros-args','-r',f'/tf:=/{rid}/tf','-r',f'/tf_static:=/{rid}/tf_static'],parameter_overrides=[Parameter('use_sim_time',value=True)])
            self.rid=rid;self.scan=None;self.maps={};self.samples={'scan':0,'local_costmap':0,'global_costmap':0};self.received={};self.gate_clients={};self.futures={};self.gate_results={};self.requested_at={};self.metrics={};self.buf=Buffer();self.tf=TransformListener(self.buf,self)
            params=nav2_parameters(rid,resolve=True);self.max_age={k:max(1.,3./params[k][k]['ros__parameters']['publish_frequency']) for k in ['local_costmap','global_costmap']};self.max_age['scan']=.5
            self.create_subscription(LaserScan,'scan',self.scan_cb,qos_profile_sensor_data)
            for kind in ['local_costmap','global_costmap']:
                self.create_subscription(Costmap,kind+'/costmap_raw',lambda m,k=kind:self.map_cb(k,m),10)
            for name in ['controller_server','planner_server','behavior_server','bt_navigator']:
                self.gate_clients[name]=self.create_client(GetState,name+'/get_state')
            for kind in ['local_costmap','global_costmap']:
                key=kind+':params';self.gate_clients[key]=self.create_client(GetParameters,kind+'/'+kind+'/get_parameters')
        def now(self): return self.get_clock().now().nanoseconds*1e-9
        def scan_cb(self,m): self.scan=m;self.samples['scan']+=1;self.received['scan']=self.now()
        def map_cb(self,k,m): self.maps[k]=m;self.samples[k]+=1;self.received[k]=self.now()
        def values(self):
            checks={};now=self.now();checks['clock_advancing']=now>1.
            for k in self.samples:
                limit=self.max_age[k]
                self.metrics['age:'+k]=now-self.received.get(k,-1e9)
                checks[k+':messages']=self.samples[k]>=2 and 0<=now-self.received.get(k,-1e9)<limit
            if self.scan:
                stamp=self.scan.header.stamp.sec+self.scan.header.stamp.nanosec*1e-9
                self.metrics['scan_stamp_age']=now-stamp;checks['scan:stamp']=0<=now-stamp<.5;checks['scan:frame']=self.scan.header.frame_id=='rplidar_link';checks['scan:ranges']=bool(np.any(np.isfinite(self.scan.ranges)))
            for frame in ['base_link','rplidar_link']:
                try:
                    t=self.buf.lookup_transform('map',frame,Time());age=now-(t.header.stamp.sec+t.header.stamp.nanosec*1e-9);self.metrics['tf_age:'+frame]=age;checks['tf:'+frame]=0<=age<.5
                except Exception:checks['tf:'+frame]=False
            pubs=self.get_publishers_info_by_topic('/'+self.rid+'/scan');subs=self.get_subscriptions_info_by_topic('/'+self.rid+'/scan')
            for kind in ['local_costmap','global_costmap']:
                endpoints=[s for s in subs if s.node_name==kind and s.node_namespace=='/'+self.rid+'/'+kind]
                checks[kind+':scan_endpoint']=bool(pubs and endpoints)
                checks[kind+':qos']=bool(endpoints and pubs) and all(qos_check_compatible(p.qos_profile,s.qos_profile)[0]!=QoSCompatibility.ERROR for p in pubs for s in endpoints)
            services=dict(self.get_service_names_and_types())
            for kind in ['local_costmap','global_costmap']:
                checks[kind+':clear_service']='nav2_msgs/srv/ClearEntireCostmap' in services.get('/'+self.rid+'/'+kind+'/clear_entirely_'+kind,[])
            actions=dict(get_action_names_and_types(self))
            for name,typ in [('compute_path_to_pose','nav2_msgs/action/ComputePathToPose'),('follow_path','nav2_msgs/action/FollowPath'),('spin','nav2_msgs/action/Spin')]:
                checks['action:'+name]=typ in actions.get('/'+self.rid+'/'+name,[])
            wall=time.monotonic()
            for key,client in self.gate_clients.items():
                f=self.futures.get(key)
                if f is not None and f.done():
                    response=f.result();valid=False
                    if response is not None:
                        valid=(response.values[0].string_value=='/'+self.rid+'/scan' and response.values[1].bool_value) if key.endswith(':params') else response.current_state.id==3
                    self.gate_results[key]=(valid,wall);self.futures.pop(key)
                if key not in self.futures and client.service_is_ready() and wall-self.requested_at.get(key,-999.)>=.5:
                    if key.endswith(':params'):
                        req=GetParameters.Request();req.names=['obstacle_layer.scan.topic','use_sim_time']
                    else:req=GetState.Request()
                    self.futures[key]=client.call_async(req);self.requested_at[key]=wall
                valid,at=self.gate_results.get(key,(False,-999.));checks['live:'+key]=valid and wall-at<2.
            return checks
        def occupancy(self):
            counts={}
            for kind,m in self.maps.items():
                try:t=self.buf.lookup_transform('map',m.header.frame_id,Time())
                except Exception:continue
                q=t.transform.rotation;yaw=math.atan2(2*(q.w*q.z+q.x*q.y),1-2*(q.y*q.y+q.z*q.z));meta=m.metadata
                grid=np.asarray(m.data).reshape(meta.size_y,meta.size_x);ox,oy=meta.origin.position.x,meta.origin.position.y
                if kind=='global_costmap' and m.header.frame_id=='map':
                    cx,cy=cfg['bed_experiment']['short_center'];res=meta.resolution;x0=max(0,int((cx-1.2-ox)/res));x1=min(meta.size_x,int((cx+1.2-ox)/res)+2);y0=max(0,int((cy-1.2-oy)/res));y1=min(meta.size_y,int((cy+1.2-oy)/res)+2);grid=grid[y0:y1,x0:x1];ox+=x0*res;oy+=y0*res
                counts[kind]=local_delta(grid,[ox,oy],meta.resolution,[t.transform.translation.x,t.transform.translation.y,yaw],cfg['bed_experiment']['short_center'],mask)
            hits=0
            if self.scan:
                try:
                    t=self.buf.lookup_transform('map','rplidar_link',Time());q=t.transform.rotation;yaw=math.atan2(2*(q.w*q.z+q.x*q.y),1-2*(q.y*q.y+q.z*q.z));a=self.scan.angle_min+np.arange(len(self.scan.ranges))*self.scan.angle_increment+yaw;rr=np.asarray(self.scan.ranges);cx,cy=cfg['bed_experiment']['short_center'];valid=np.isfinite(rr)&(rr>.45)&(rr<10.);hits=int(np.sum(valid&((t.transform.translation.x+rr*np.cos(a)-cx)**2+(t.transform.translation.y+rr*np.sin(a)-cy)**2<1.17**2)))
                except Exception:pass
            return dict(at=self.now(),hits=hits,costmaps=counts)
    rclpy.init();ex=SingleThreadedExecutor();nodes=[RobotCheck(r) for r in cfg['robots']]
    for n in nodes:ex.add_node(n)
    begin=time.monotonic();report={};stable=None;last_evaluation=-999.
    try:
        while time.monotonic()-begin<timeout:
            ex.spin_once(timeout_sec=.03)
            if time.monotonic()-last_evaluation<.1:continue
            last_evaluation=time.monotonic()
            report={n.rid:n.values() for n in nodes}
            if all(all(v.values()) for v in report.values()):
                if stable is None:stable=time.monotonic()
                if time.monotonic()-stable>=1.:break
            else:stable=None
        passed=bool(stable is not None and time.monotonic()-stable>=1.)
        result=dict(passed=passed,environment=dict(domain=os.environ.get('ROS_DOMAIN_ID'),partition=os.environ.get('IGN_PARTITION')),checked_wall=time.time(),robots=report,measurements={n.rid:dict(metrics=n.metrics,samples=n.samples,allowed_message_age=n.max_age) for n in nodes},wall_seconds=time.monotonic()-begin,scope='Real messages, resolved live parameters, TF, QoS, lifecycle/action/service endpoints; no motion or avoidance claim.')
        if passed and pulse:
            n=next(n for n in nodes if n.rid=='r2');events=[];obs=[]
            n.create_subscription(String,'/clinic_bed/physical_truth',lambda m:events.append(json.loads(m.data)),STATE_QOS)
            pub=n.create_publisher(String,'/clinic_bed/scenario_trigger',10);deadline=time.monotonic()+10.
            while pub.get_subscription_count()==0 and time.monotonic()<deadline:ex.spin_once(timeout_sec=.05)
            if not pub.get_subscription_count():return dict(passed=False,error='Scenario driver subscriber unavailable',runtime=result)
            baseline=n.occupancy()
            if baseline['hits']>=3 or any(baseline['costmaps'].get(k,{}).get('new',999)>0 for k in ['local_costmap','global_costmap']):return dict(passed=False,error='Corridor baseline is occupied; no injection',runtime=result)
            clears=[n.create_client(ClearEntireCostmap,k+'/clear_entirely_'+k) for k in ['local_costmap','global_costmap']]
            pub.publish(String(data=json.dumps(dict(phase='short'))));deadline=time.monotonic()+60.;clear_since=None;detected=False;laser_clear_since=None;last_clear=-999.;pending=[];recovery=[];last_sample=-999.;ack_at=None
            while time.monotonic()<deadline:
                ex.spin_once(timeout_sec=.03)
                if time.monotonic()-last_sample<.1:continue
                last_sample=time.monotonic();v=n.occupancy();obs.append(v)
                if pending and all(f.done() for f in pending):
                    if any(f.result() is None for f in pending):raise RuntimeError('Standard Nav2 clear response missing')
                    pending=[];ack_at=n.now();recovery[-1]['ack_at']=ack_at
                detected|=v['hits']>=4 and all(v['costmaps'].get(k,{}).get('new',0)>=4 for k in ['local_costmap','global_costmap'])
                removed=any(e['action']=='removed' for e in events)
                if removed and v['hits']<3:
                    if laser_clear_since is None:laser_clear_since=n.now()
                    if n.now()-laser_clear_since>=2. and n.now()-last_clear>=15. and not pending and any(v['costmaps'].get(k,{}).get('new',0)>0 for k in ['local_costmap','global_costmap']) and all(c.service_is_ready() for c in clears):
                        last_clear=n.now();pending=[c.call_async(ClearEntireCostmap.Request()) for c in clears];recovery.append(dict(requested_at=n.now(),reason='Laser clear, native maps retain occupancy; standard Nav2 ClearEntireCostmap both, then reobserve'))
                else:laser_clear_since=None
                clear=removed and not pending and v['hits']<3 and all(v['costmaps'].get(k,{}).get('new',999)==0 and (ack_at is None or n.received[k]>=ack_at) for k in ['local_costmap','global_costmap'])
                if clear:
                    if clear_since is None:clear_since=n.now()
                    if n.now()-clear_since>=1.:break
                else:clear_since=None
            result['sensor_pulse']=dict(passed=detected and clear_since is not None and n.now()-clear_since>=1.,baseline=baseline,events=events,observations=obs,recovery=recovery,scope='Stationary R2, one physical short bed pulse; real scan AND both costmap deltas; no MILP, navigation obstacle recovery, or full loop proof.')
            result['passed'] &= result['sensor_pulse']['passed']
            deadline=time.monotonic()+8.;stable=None
            while time.monotonic()<deadline:
                ex.spin_once(timeout_sec=.03)
                if time.monotonic()-last_evaluation<.1:continue
                last_evaluation=time.monotonic()
                report={n.rid:n.values() for n in nodes}
                if all(all(v.values()) for v in report.values()):
                    if stable is None:stable=time.monotonic()
                    if time.monotonic()-stable>=1.:break
                else:stable=None
            result['robots']=report;result['passed'] &= stable is not None and time.monotonic()-stable>=1.
        result['checked_wall']=time.time()
        return result
    finally:
        for n in nodes:ex.remove_node(n);n.destroy_node()
        ex.shutdown();rclpy.try_shutdown()
