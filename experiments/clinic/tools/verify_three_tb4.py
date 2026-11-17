#!/usr/bin/env python3
"""Three namespaced physical Nav2 clients; routine services and FIFO shared area."""
import argparse
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import shutil
import time
import yaml
import rclpy
from rclpy.node import Node
from rclpy.parameter import Parameter
from rclpy.executors import SingleThreadedExecutor
from rclpy.time import Time
from rclpy.action import ActionClient
from rclpy.qos import qos_profile_sensor_data
from std_msgs.msg import String
from nav_msgs.msg import Odometry
from sensor_msgs.msg import LaserScan
from tf2_msgs.msg import TFMessage
from tf2_ros import Buffer,TransformListener,TransformException
from nav2_msgs.action import NavigateToPose
from lifecycle_msgs.srv import GetState
from controller_manager_msgs.srv import ListControllers
from shared_resource import STATE_QOS

ROOT=Path(__file__).resolve().parents[1]


class Robot(Node):
    def __init__(self,rid,coordinator):
        super().__init__('verification_client',namespace=rid,use_global_arguments=False,cli_args=['--ros-args','-r',f'/tf:=/{rid}/tf','-r',f'/tf_static:=/{rid}/tf_static'],parameter_overrides=[Parameter('use_sim_time',value=True)])
        self.rid=rid;self.c=coordinator;self.action=ActionClient(self,NavigateToPose,'navigate_to_pose')
        self.buffer=Buffer();self.listener=TransformListener(self.buffer,self)
        self.odom=None;self.odom_at=None;self.scan_at=None;self.scan_count=0;self.odom_count=0;self.cmd_count=0;self.edges=set();self.phases={};self.state='IDLE';self.record=None;self.nav_handle=None;self.phase_wall=time.monotonic();self.futures={};self.lifecycle={}
        self.create_subscription(Odometry,'odom',self.odometry,qos_profile_sensor_data)
        self.create_subscription(LaserScan,'scan',self.scan,qos_profile_sensor_data)
        self.create_subscription(TFMessage,'tf',self.tf,100)
        self.create_subscription(String,'experiment/service_feedback',self.feedback,10)
        self.pub=self.create_publisher(String,'experiment/service_request',10)
        for name in ['amcl','controller_server','planner_server','bt_navigator']:
            self.lifecycle[name]=self.create_client(GetState,name+'/get_state')
        self.controllers=self.create_client(ListControllers,'controller_manager/list_controllers')
    def now(self):return self.c.now()
    def odometry(self,msg):self.odom=msg;self.odom_at=self.now();self.odom_count+=1
    def scan(self,msg):self.scan_at=self.now();self.scan_count+=1
    def tf(self,msg):
        for t in msg.transforms:self.edges.add((t.header.frame_id,t.child_frame_id))
    def feedback(self,msg):
        data=json.loads(msg.data);self.phases[data['task_id'],data['phase']]=data;self.c.log('service_feedback',robot=self.rid,feedback=data)
    def pose(self):
        try:t=self.buffer.lookup_transform('map','base_link',Time())
        except TransformException:return None
        q=t.transform.rotation
        return dict(x=t.transform.translation.x,y=t.transform.translation.y,yaw=math.atan2(2*(q.w*q.z+q.x*q.y),1-2*(q.y*q.y+q.z*q.z)),tf_age=self.now()-(t.header.stamp.sec+t.header.stamp.nanosec*1e-9))
    def ready(self):
        if not (self.action.server_is_ready() and self.odom is not None and self.scan_count>2 and self.odom_count>2 and self.pose() is not None and {('map','odom'),('odom','base_link')}.issubset(self.edges)):return False
        good=True
        for name,client in self.lifecycle.items():
            key='life_'+name
            if key not in self.futures or self.futures[key].done():
                if key in self.futures and self.futures[key].done() and self.futures[key].result() is not None and self.futures[key].result().current_state.id==3:continue
                if client.service_is_ready():self.futures[key]=client.call_async(GetState.Request())
                good=False
            else:good=False
        if not self.controllers.service_is_ready():return False
        if 'controllers' not in self.futures:self.futures['controllers']=self.controllers.call_async(ListControllers.Request());return False
        f=self.futures['controllers']
        if not f.done():return False
        states={x.name:x.state for x in f.result().controller}
        if any(states.get(k)!='active' for k in ['joint_state_broadcaster','diffdrive_controller']):self.futures.pop('controllers');return False
        return good
    def guard(self,target):
        p=self.pose()
        if p is None or self.odom is None:return False,p
        d=dict(p,position_error=math.hypot(p['x']-target['x'],p['y']-target['y']),yaw_error=abs(math.atan2(math.sin(p['yaw']-target['yaw']),math.cos(p['yaw']-target['yaw']))),speed=math.hypot(self.odom.twist.twist.linear.x,self.odom.twist.twist.linear.y),angular_speed=abs(self.odom.twist.twist.angular.z),odom_age=self.now()-self.odom_at,scan_age=self.now()-self.scan_at if self.scan_at is not None else 1e9)
        return d['position_error']<=.20 and d['yaw_error']<=.30 and d['speed']<.04 and d['angular_speed']<.06 and max(d['tf_age'],d['odom_age'],d['scan_age'])<.5,d
    def navigate(self,target,kind):
        if self.state not in ['IDLE','NORMAL_DONE','SHARED_DONE']:raise RuntimeError(self.rid+' busy at dispatch')
        tid=f'{self.c.run_id}:{self.rid}:{kind}'
        self.record=dict(task_id=tid,robot=self.rid,kind=kind,target=target,begin=self.now(),wall_begin=time.monotonic());self.c.records.append(self.record)
        self.c.log('navigation_requested',**self.record)
        goal=NavigateToPose.Goal();goal.pose.header.frame_id='map';goal.pose.header.stamp=self.get_clock().now().to_msg();goal.pose.pose.position.x=target['x'];goal.pose.pose.position.y=target['y'];goal.pose.pose.orientation.z=math.sin(target['yaw']/2);goal.pose.pose.orientation.w=math.cos(target['yaw']/2)
        self.goal_future=self.action.send_goal_async(goal);self.state='NAV_ACK';self.phase_wall=time.monotonic()
    def fail(self,reason):
        self.record.update(status=reason,end=self.now());self.state='FAILED';self.c.failed=reason;self.c.log('task_failed',**self.record)
        if self.nav_handle:self.nav_handle.cancel_goal_async()
    def step(self):
        if self.state=='NAV_ACK':
            if self.goal_future.done():
                self.nav_handle=self.goal_future.result()
                if not self.nav_handle.accepted:self.fail('NAV_REJECTED');return
                self.result_future=self.nav_handle.get_result_async();self.record['accepted']=self.now();self.state='NAVIGATING'
            elif time.monotonic()-self.phase_wall>15:self.fail('NAV_ACK_TIMEOUT')
        elif self.state=='NAVIGATING':
            if self.result_future.done():
                status=self.result_future.result().status;self.record.update(nav_status=status,nav_end=self.now())
                self.c.log('navigation_result',robot=self.rid,task_id=self.record['task_id'],status=status)
                if status!=4:self.fail('NAV_FAILED');return
                self.state='STABILIZING';self.stable=None;self.stable_wall=None;self.phase_at=self.now();self.phase_wall=time.monotonic()
            elif self.now()-self.record['begin']>150 or time.monotonic()-self.phase_wall>300:self.fail('NAV_TIMEOUT')
        elif self.state=='STABILIZING':
            ok,d=self.guard(self.record['target']);wall=time.monotonic()
            self.c.log('guard_sample',robot=self.rid,task_id=self.record['task_id'],detail=d,effective_ready=ok)
            if ok:
                if self.stable is None:self.stable=self.now();self.stable_wall=wall
                if self.now()-self.stable>=.7:
                    self.record.update(stable_at=self.now(),stable_since=self.stable,stable_since_wall=self.stable_wall,arrival=d,arrival_ground_truth=self.c.truth.get(self.rid))
                    self.c.log('arrival_stable',**self.record)
                    if self.record['kind']=='exit':self.complete('EXIT_DONE');return
                    req=dict(task_id=self.record['task_id'],attempt=1,target=self.record['target'],duration=3. if self.record['kind']=='shared' else 1.5,lease_id=self.c.lease_id(self.rid) if self.record['kind']=='shared' else None)
                    self.pub.publish(String(data=json.dumps(req)));self.record['start_requested']=self.now();self.state='START_WAIT';self.phase_at=self.now();self.phase_wall=time.monotonic();self.c.log('service_requested',robot=self.rid,request=req)
            else:self.stable=None;self.stable_wall=None
            if self.now()-self.phase_at>5 or time.monotonic()-self.phase_wall>30:self.fail('ARRIVAL_NOT_STABLE')
        elif self.state=='START_WAIT':
            tid=self.record['task_id']
            if (tid,'started') in self.phases:self.record['service_started']=self.phases[tid,'started']['at'];self.state='SERVICE_RUNNING';self.phase_at=self.now();self.phase_wall=time.monotonic()
            elif (tid,'rejected') in self.phases:self.fail('SERVICE_REJECTED')
            elif self.now()-self.phase_at>4 or time.monotonic()-self.phase_wall>30:self.fail('START_TIMEOUT')
        elif self.state=='SERVICE_RUNNING':
            tid=self.record['task_id']
            if (tid,'succeeded') in self.phases:
                self.record['service_finished']=self.phases[tid,'succeeded']['at'];self.complete('NORMAL_DONE' if self.record['kind']=='normal' else 'SHARED_DONE')
            elif (tid,'failed') in self.phases:self.fail('SERVICE_FAILED')
            elif self.now()-self.phase_at>7 or time.monotonic()-self.phase_wall>40:self.fail('SERVICE_TIMEOUT')
    def complete(self,state):
        self.record.update(status='SUCCEEDED',end=self.now(),ground_truth=self.c.truth.get(self.rid));self.state=state;self.c.log('task_completed',robot=self.rid,record=self.record)


class Coordinator(Node):
    def __init__(self,out):
        super().__init__('three_tb4_verification',parameter_overrides=[Parameter('use_sim_time',value=True)])
        self.out=out;self.run_id=out.name;self.config=yaml.safe_load((ROOT/'config/three_tb4/scenario.yaml').read_text());self.records=[];self.truth={};self.truth_samples=[];self.resource={};self.resource_events=[];self.failed=None;self.events=[];self.file=(out/'trace.jsonl').open('w');self.peers={}
        self.pub=self.create_publisher(String,'/clinic_three/resource_request',10)
        self.create_subscription(String,'/clinic_three/resource_state',self.resource_cb,STATE_QOS)
        self.create_subscription(TFMessage,'/world/clinic_l1_three/dynamic_pose/info',self.truth_cb,100)
    def now(self):return self.get_clock().now().nanoseconds*1e-9
    def log(self,phase,**data):
        item=dict(at=self.now(),wall=time.monotonic(),phase=phase,**data);self.events.append(item);self.file.write(json.dumps(item)+'\n');self.file.flush()
        if phase not in ['pose_sample','guard_sample']:print(json.dumps(item),flush=True)
    def resource_cb(self,msg):
        self.resource=json.loads(msg.data);self.resource_events.append(self.resource);self.log('resource_feedback',resource=self.resource)
    def truth_cb(self,msg):
        data={}
        for t in msg.transforms:
            if t.child_frame_id in self.config['robots']:
                q=t.transform.rotation;data[t.child_frame_id]=dict(x=t.transform.translation.x,y=t.transform.translation.y,z=t.transform.translation.z,yaw=math.atan2(2*(q.w*q.z+q.x*q.y),1-2*(q.y*q.y+q.z*q.z)))
        if data:self.truth.update(data);self.truth_samples.append(dict(at=self.now(),poses=data))
    def lease_id(self,rid):return f'{self.run_id}:{rid}:shared'
    def request(self,rid,action,probe=False):
        req=dict(robot=rid,action=action,lease_id=self.lease_id(rid),probe=probe);self.pub.publish(String(data=json.dumps(req)));self.log('resource_request',request=req)
    def graph_audit(self):
        evidence={};checks={}
        for rid,robot in self.peers.items():
            data={}
            for topic in ['tf','tf_static','scan','odom','cmd_vel','experiment/service_feedback']:
                ps=self.get_publishers_info_by_topic(f'/{rid}/{topic}');data[topic]=[dict(namespace=p.node_namespace,node=p.node_name) for p in ps];checks[f'{rid}_{topic}_scoped']=bool(ps) and all(p.node_namespace==f'/{rid}' for p in ps)
            checks[rid+'_tf_edges']={('map','odom'),('odom','base_link')}.issubset(robot.edges)
            checks[rid+'_scan_odom_received']=robot.scan_count>2 and robot.odom_count>2
            evidence[rid]=dict(publishers=data,tf_edges=sorted(robot.edges),pose=robot.pose(),truth=self.truth.get(rid))
        checks['no_global_tf']=len(self.get_publishers_info_by_topic('/tf'))==0 and len(self.get_publishers_info_by_topic('/tf_static'))==0
        checks['no_global_cmd_vel']=len(self.get_publishers_info_by_topic('/cmd_vel'))==0
        return dict(passed=all(checks.values()),checks=checks,evidence=evidence)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path);args=parser.parse_args();out=args.out or ROOT/'runs'/('three_tb4_'+datetime.now().strftime('%Y%m%d_%H%M%S'));out.mkdir(parents=True,exist_ok=False)
    source=out/'source';source.mkdir();hashes={}
    for p in list((ROOT/'tools').glob('*.py'))+list((ROOT/'launch').glob('*three*.py'))+list((ROOT/'config/three_tb4').glob('*'))+[ROOT/'maps/clinic_l1.yaml',ROOT/'maps/clinic_l1.pgm',ROOT/'worlds/clinic_l1_three.sdf']:
        dst=source/p.relative_to(ROOT);dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,dst);hashes[str(p.relative_to(ROOT))]=hashlib.sha256(p.read_bytes()).hexdigest()
    (out/'source_manifest.json').write_text(json.dumps(hashes,indent=2))
    rclpy.init();c=Coordinator(out);executor=SingleThreadedExecutor();executor.add_node(c)
    for rid in c.config['robots']:r=Robot(rid,c);c.peers[rid]=r;executor.add_node(r)
    begin=time.monotonic();stage='READY';normal_started=set();shared_started=set();exit_started=set();release_sent=set();release_probe=set();lease_probe_sent=False;last_sample=-1.;isolation_start=None;graph=None
    try:
        while time.monotonic()-begin<800 and not c.failed:
            executor.spin_once(timeout_sec=.02)
            for robot in c.peers.values():robot.step()
            if c.now()-last_sample>=.2:
                c.log('pose_sample',poses={rid:r.pose() for rid,r in c.peers.items()},truth=c.truth);last_sample=c.now()
            if stage=='READY':
                if all(r.ready() for r in c.peers.values()) and len(c.truth)==3:
                    graph=c.graph_audit();(out/'namespace_audit.json').write_text(json.dumps(graph,indent=2))
                    if not graph['passed']:c.failed='namespace_audit_failed';break
                    if any(math.hypot(c.truth[rid]['x']-cfg['start'][0],c.truth[rid]['y']-cfg['start'][1])>.25 for rid,cfg in c.config['robots'].items()):
                        c.failed='initial_poses_not_reset_restart_experiment';c.log('reset_required',truth=c.truth);break
                    c.log('ready',truth=c.truth);c.initial_truth=json.loads(json.dumps(c.truth));isolation_start=c.now();c.initial_at=c.now()
                    c.peers['r1'].navigate(c.config['robots']['r1']['private'],'normal');normal_started.add('r1');stage='NORMAL'
                elif time.monotonic()-begin>240:c.failed='readiness_timeout';break
            elif stage=='NORMAL':
                if c.now()-isolation_start>=4:
                    if len(normal_started)==1:
                        c.isolation_end=json.loads(json.dumps(c.truth));c.log('command_isolation_end',initial=c.initial_truth,final=c.truth)
                    for rid in ['r2','r3']:
                        if rid not in normal_started:c.peers[rid].navigate(c.config['robots'][rid]['private'],'normal');normal_started.add(rid)
                if all(r.state=='NORMAL_DONE' for r in c.peers.values()):
                    for rid in c.peers:c.request(rid,'acquire')
                    stage='SHARED'
            elif stage=='SHARED':
                owner=c.resource.get('owner')
                if owner and owner not in shared_started:
                    c.peers[owner].navigate(c.config['shared'],'shared');shared_started.add(owner)
                if owner=='r1' and not lease_probe_sent:
                    probe=dict(task_id=f'{c.run_id}:r2:lease_negative',attempt=1,target=c.config['shared'],duration=1.5,lease_id=c.lease_id('r2'))
                    c.peers['r2'].pub.publish(String(data=json.dumps(probe)));c.log('unauthorized_service_probe',robot='r2',request=probe);lease_probe_sent=True
                for rid,r in c.peers.items():
                    if r.state=='SHARED_DONE' and rid not in release_probe:c.request(rid,'release',True);release_probe.add(rid)
                    denied=any(e['phase']=='release_denied' and e.get('request',{}).get('robot')==rid and e.get('reason')=='owner_not_confirmed_clear' for e in c.resource_events)
                    if r.state=='SHARED_DONE' and denied and rid not in exit_started:r.navigate(c.config['robots'][rid]['private'],'exit');exit_started.add(rid)
                    if r.state=='EXIT_DONE' and rid not in release_sent:c.request(rid,'release');release_sent.add(rid)
                released={e.get('request',{}).get('robot') for e in c.resource_events if e['phase']=='released'}
                if released==set(c.peers) and c.resource.get('owner') is None:stage='DONE';break
        if stage!='DONE' and not c.failed:c.failed='overall_wall_timeout'
    except Exception as e:c.failed=repr(e);raise
    finally:
        for r in c.peers.values():
            if c.failed and r.nav_handle:r.nav_handle.cancel_goal_async()
        result=dict(passed=stage=='DONE' and not c.failed,stage=stage,failure=c.failed,records=c.records,resource_events=c.resource_events,truth_samples=c.truth_samples,initial_truth=getattr(c,'initial_truth',None),isolation_end=getattr(c,'isolation_end',None),namespace_audit=graph,wall_seconds=time.monotonic()-begin)
        (out/'result.json').write_text(json.dumps(result,indent=2));print('RESULT',out,result['passed'],c.failed,flush=True);c.file.close()
        for r in list(c.peers.values())+[c]:executor.remove_node(r);r.destroy_node()
        executor.shutdown();rclpy.shutdown()
    return 0 if result['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
