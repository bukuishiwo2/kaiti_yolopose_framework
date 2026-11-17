#!/usr/bin/env python3
"""Real Gazebo/Nav2 one-cycle routine and scripted event acceptance."""
import argparse,json,math,time,hashlib,shutil,subprocess,sys
from copy import deepcopy
from pathlib import Path
import rclpy
from rclpy.node import Node
from rclpy.parameter import Parameter
from rclpy.executors import SingleThreadedExecutor
from std_msgs.msg import String
from tf2_msgs.msg import TFMessage
from nav2_msgs.action import NavigateToPose,Spin
from rclpy.action import ActionClient
from nav2_msgs.msg import Costmap
from verify_three_tb4 import Robot,Coordinator
from shared_resource import STATE_QOS
from aligned_tasks import ROOT,config,normal_tasks,problem
from aligned_contract import validate,tau,occupancy,worker_ready_ack

PROJECT=Path('/home/yhc/kaiti_yolopose_framework');sys.path.insert(0,str(PROJECT/'src'))
from kaiti_task_sim.event_protocol import EventTaskProtocol
class Bot(Robot):
 def __init__(self,rid,c):
  super().__init__(rid,c);self.heading_action=ActionClient(self,Spin,'spin');self.near_since=None;self.handoff_requested=False;self.anchor=c.cfg['starts'][rid];self.job=None;self.state='IDLE';self.leases={};self.cargo=None;self.finished=False;self.leg='service';self.saved_service={};self.protocol_ack={};self.create_subscription(String,'experiment/protocol_ack',self.ack_cb,STATE_QOS);self.costmap_ready=False;self.create_subscription(Costmap,'global_costmap/costmap_raw',self.map_cb,10)
 def ack_cb(self,m):self.protocol_ack=json.loads(m.data)
 def map_cb(self,m):self.costmap_ready=m.metadata.size_x>0 and m.metadata.size_y>0
 def ready(self):return super().ready() and self.costmap_ready and (self.c.args.arrival=='nav2' or self.heading_action.wait_for_server(timeout_sec=0.))
 def feedback(self,m):
  data=json.loads(m.data);self.phases[data['task_id'],data['phase']]=data;self.c.log('service_feedback',robot=self.rid,feedback=data)
  if data.get('protocol_task_id') and data['phase'] in ['started','succeeded','cancelled']:
   rec=self.c.commands[data['task_id']]
   if data['task_revision']!=rec['sent_revision']:self.c.failed='TOKEN_MISMATCH';return
   msg=dict(schema='event-task/v1',kind='feedback',message_id='fb:'+data['task_id']+':'+data['phase'],event_id='E1',task_id=data['protocol_task_id'],task_revision=data['task_revision'],attempt=data['attempt'],robot_id=self.rid,phase=data['phase'],at=max(self.c.elapsed(),self.c.protocol.now))
   if rec['job_id']=='E1_verify' and data['phase']=='succeeded':msg['result']='fall'
   self.c.protocol_apply(msg)
 def dispatch(self,jid,exit=False):
  c=self.c;t=c.tasks[jid] if not exit else dict(anchor=c.cfg['homes'][self.rid],kind='exit',duration=0.,service_role='exit');p=c.cfg['anchors'][t['anchor']];self.job=jid;self.record=dict(task_id=f'{c.run_id}:{jid}:{self.rid}',job_id=jid,robot=self.rid,role=t['service_role'],target=dict(x=p[0],y=p[1],yaw=p[2]),anchor=t['anchor'],begin=c.elapsed(),exit=exit,status='RUNNING',plan_revision=c.plan_revision)
  c.records.append(self.record);c.commands[self.record['task_id']]=self.record;c.log('navigation_requested',record=self.record);self.record['navigation_attempts']=[];self.service_target=deepcopy(self.record['target']);self.leg='service' if exit or not t.get('resources') else 'entry';self.record['target']=self.target(t['entry_anchor']) if self.leg=='entry' else self.service_target;self.send_navigation()
 def target(self,anchor):
  x,y,yaw=self.c.cfg['anchors'][anchor];return dict(x=x,y=y,yaw=yaw)
 def send_navigation(self):
  self.near_since=None;self.handoff_requested=False;p=self.record['target'];self.record['navigation_attempts'].append(dict(begin=self.c.elapsed(),reason='initial' if not self.record['navigation_attempts'] else 'stopped_pose_outside_service_guard'));g=NavigateToPose.Goal();g.pose.header.frame_id='map';g.pose.header.stamp=self.get_clock().now().to_msg();g.pose.pose.position.x=p['x'];g.pose.pose.position.y=p['y'];g.pose.pose.orientation.z=math.sin(p['yaw']/2);g.pose.pose.orientation.w=math.cos(p['yaw']/2);self.goal_future=self.action.send_goal_async(g);self.state='NAV_ACK';self.phase_wall=time.monotonic();self.stable=None;self.record['navigation_attempts'][-1]['leg']=self.leg
 def begin_heading(self):
  t=self.c.elapsed();pose=self.pose();delta=math.atan2(math.sin(self.record['target']['yaw']-pose['yaw']),math.cos(self.record['target']['yaw']-pose['yaw']));att=self.record['navigation_attempts'][-1];att['heading_alignment']=dict(begin=t,target_yaw_delta=delta,skip=abs(delta)<=.08)
  if abs(delta)<=.08:
   att['heading_alignment'].update(status=4,end=t);self.state='STABILIZING';self.phase_at=t;self.stable=None;return
  goal=Spin.Goal();goal.target_yaw=float(delta);goal.time_allowance.sec=30;self.heading_future=self.heading_action.send_goal_async(goal);self.state='HEADING_ACK';self.phase_at=t;self.phase_wall=time.monotonic();self.c.log('heading_alignment_requested',robot=self.rid,job=self.job,leg=self.leg,delta=delta)
 def fail(self,reason):
  self.record.update(status=reason,end=self.c.elapsed());self.c.failed=reason;self.state='FAILED';self.c.log('execution_failed',record=self.record)
  if self.nav_handle:self.nav_handle.cancel_goal_async()
 def finish(self):
  if not self.record['exit'] and self.c.tasks[self.job].get('resources') and self.leg=='service':
   self.saved_service={k:deepcopy(self.record[k]) for k in ['target','nav_status','nav_end','stable_at','stable_since','arrival','arrival_ground_truth']};self.leg='clear';self.record['target']=self.target(self.c.tasks[self.job]['clear_anchor']);self.record['clear_departure']=self.c.elapsed();self.send_navigation();return
  c=self.c;rec=self.record;rec.update(status='SUCCEEDED',end=max(c.elapsed(),rec.get('service_finished',c.elapsed())),ground_truth=c.truth.get(self.rid));self.anchor=c.tasks[self.job].get('clear_anchor',rec['anchor']) if not rec['exit'] else rec['anchor'];rec['final_anchor']=self.anchor;c.log('job_completed',record=rec)
  if rec['exit']:self.finished=True
  else:
   c.completed[self.job]=rec;t=c.tasks[self.job]
   if t.get('cargo_role')=='pickup':self.cargo=t['cargo_group']
   if t.get('cargo_role')=='drop':
    if self.cargo!=t['cargo_group']:c.failed='ORDINARY_CUSTODY_MISMATCH'
    self.cargo=None
  self.job=None;self.state='IDLE'
 def step(self):
  c=self.c;t=c.elapsed()
  if self.state=='LEASE_WAIT':
   start=c.plan['starts'].get(self.job,0.)-c.tasks[self.job].get('approach',0.) if c.plan else 0.
   if t>=start and c.acquire(self,self.job):self.leg='service';self.record['lease_granted_at']=t;self.record['target']=deepcopy(self.service_target);self.send_navigation()
   return
  if self.state=='RELEASE_WAIT':
   res=c.tasks[self.job]['resources'][0];lease=self.leases[res]['lease_id']
   if c.resource.get('owners',{}).get(res,{}).get('lease_id')!=lease:
    self.record['lease_released_at']=t;self.leases.pop(res,None);self.leg='done';self.finish()
   return
  if self.state=='NAV_ACK':
   if self.goal_future.done():
    self.nav_handle=self.goal_future.result()
    if not self.nav_handle.accepted:self.fail('NAV_REJECTED');return
    self.result_future=self.nav_handle.get_result_async();self.state='NAVIGATING'
   elif time.monotonic()-self.phase_wall>20:self.fail('NAV_ACK_TIMEOUT')
  elif self.state=='NAVIGATING':
   if self.result_future.done():
    status=self.result_future.result().status;self.record.update(nav_status=status,nav_end=t);self.record['navigation_attempts'][-1].update(status=status,end=t)
    if status==5 and self.handoff_requested:
     self.state='HANDOFF_STOP';self.phase_at=t;return
    if status!=4:self.fail('NAV_FAILED');return
    self.state='STABILIZING';self.stable=None;self.phase_at=t;self.phase_wall=time.monotonic()
   else:
    if c.args.arrival=='pose_handoff' and not self.handoff_requested:
     _,detail=self.guard(self.record['target']);near=bool(detail and detail['position_error']<=.12 and max(detail['tf_age'],detail['odom_age'],detail['scan_age'])<.5)
     if near:
      if self.near_since is None:self.near_since=t
      if t-self.near_since>=.7:
       self.handoff_requested=True;att=self.record['navigation_attempts'][-1];att['handoff']=dict(requested_at=t,near_since=self.near_since,detail=detail,reason='position reached; transfer final yaw to Nav2 Spin');self.nav_handle.cancel_goal_async();c.log('navigation_pose_handoff',robot=self.rid,job=self.job,leg=self.leg,detail=detail)
     else:self.near_since=None
    if t-self.record['navigation_attempts'][-1]['begin']>500 or time.monotonic()-self.phase_wall>900:self.fail('NAV_TIMEOUT')
  elif self.state=='HANDOFF_STOP':
   _,detail=self.guard(self.record['target'])
   if detail and detail['speed']<.02 and detail['angular_speed']<.04 and max(detail['tf_age'],detail['odom_age'],detail['scan_age'])<.5:self.begin_heading()
   elif t-self.phase_at>5:self.fail('HANDOFF_STOP_TIMEOUT')
  elif self.state=='HEADING_ACK':
   if self.heading_future.done():
    handle=self.heading_future.result()
    if not handle.accepted:self.fail('HEADING_REJECTED');return
    self.heading_result=handle.get_result_async();self.state='HEADING_ACTIVE'
   elif t-self.phase_at>5:self.fail('HEADING_ACK_TIMEOUT')
  elif self.state=='HEADING_ACTIVE':
   if self.heading_result.done():
    status=self.heading_result.result().status;self.record['navigation_attempts'][-1]['heading_alignment'].update(status=status,end=t)
    if status!=4:self.fail('HEADING_FAILED');return
    self.state='STABILIZING';self.phase_at=t;self.stable=None
   elif t-self.phase_at>35:self.fail('HEADING_TIMEOUT')
  elif self.state=='STABILIZING':
   ok,d=self.guard(self.record['target']);c.log('guard_sample',task_id=self.record['task_id'],robot=self.rid,detail=d,effective_ready=ok)
   if ok:
    if self.stable is None:self.stable=t
    if t-self.stable>=.7:
     self.record['navigation_attempts'][-1]['arrival_guard_passed']=True
     self.record.update(stable_at=t,stable_since=self.stable,arrival=d,arrival_ground_truth=c.truth.get(self.rid));self.state='WAIT_START'
     if self.leg=='entry':
      self.record.update(gate_arrival=t,gate_anchor=c.tasks[self.job]['entry_anchor'],gate_ground_truth=c.truth.get(self.rid));self.anchor=c.tasks[self.job]['entry_anchor'];self.state='LEASE_WAIT';return
     if self.leg=='clear':
      self.record.update(clear_at=t,clear_ground_truth=c.truth.get(self.rid),clear_anchor=c.tasks[self.job]['clear_anchor']);self.record.update(self.saved_service);res=c.tasks[self.job]['resources'][0];lease=self.leases[res]['lease_id'];c.pub.publish(String(data=json.dumps(dict(action='release',robot=self.rid,resource=res,lease_id=lease))));self.state='RELEASE_WAIT';return
     if self.record['exit']:self.finish();return
   else:self.stable=None
   if not ok and d and t-self.phase_at>=3 and d['speed']<.04 and d['angular_speed']<.06 and max(d['tf_age'],d['odom_age'],d['scan_age'])<.5 and (d['position_error']>.20 or d['yaw_error']>.30) and sum(a.get('leg')==self.leg for a in self.record['navigation_attempts'])<3:
    c.log('bounded_arrival_retry',robot=self.rid,task_id=self.record['task_id'],detail=d,attempt=len(self.record['navigation_attempts'])+1);self.send_navigation();return
   if t-self.phase_at>12:self.fail('ARRIVAL_NOT_STABLE')
  elif self.state=='WAIT_START':
   spec=c.tasks[self.job];proto=c.protocol.tasks.get(spec.get('protocol_task_id'));start=c.plan['starts'].get(self.job,0.) if c.plan else 0.
   if t<start or (proto and proto['state']!='READY') or any(dep not in c.completed for dep in spec.get('dependencies',[])):return
   if proto:
    if not worker_ready_ack(self.protocol_ack,c.run_id,spec['protocol_task_id'],proto,self.rid,self.now()):
     self.record.setdefault('protocol_ack_wait_since',t)
     if t-self.record['protocol_ack_wait_since']>5:self.fail('PROTOCOL_ACK_TIMEOUT')
     return
    self.record['protocol_ack_at']=t;self.record['protocol_ack_snapshot']=deepcopy(self.protocol_ack)
   if not self.guard(self.record['target'])[0]:self.fail('ARRIVAL_GUARD_LOST');return
   res=spec['resources'][0] if spec.get('resources') else None;lease=self.leases.get(res,{})
   req=dict(task_id=self.record['task_id'],attempt=proto['attempt'] if proto else 1,target=self.record['target'],duration=spec['duration'] or 10000.,role=spec['service_role'],protocol_task_id=spec.get('protocol_task_id'),task_revision=proto['revision'] if proto else None,plan_revision=c.plan_revision,resource=res,lease_id=lease.get('lease_id'),cargo_role=spec.get('cargo_role'),cargo_group=spec.get('cargo_group'))
   self.record.update(start_requested=t,sent_revision=req['task_revision']);self.pub.publish(String(data=json.dumps(req)));self.state='START_WAIT';self.phase_at=t;c.log('service_requested',robot=self.rid,request=req)
  elif self.state=='START_WAIT':
   tid=self.record['task_id']
   if (tid,'started') in self.phases:self.record['service_started']=self.phases[tid,'started']['at']-c.epoch;self.state='SERVICE_RUNNING';self.phase_at=t
   elif (tid,'rejected') in self.phases:self.fail('SERVICE_REJECTED')
   elif t-self.phase_at>5:self.fail('START_ACK_TIMEOUT')
  elif self.state=='SERVICE_RUNNING':
   tid=self.record['task_id'];spec=c.tasks[self.job]
   if (tid,'failed') in self.phases:self.fail('SERVICE_FAILED');return
   if (tid,'succeeded') in self.phases:self.record['service_finished']=self.phases[tid,'succeeded']['at']-c.epoch;self.finish();return
   if spec['kind']=='monitor':
    if c.protocol.tasks.get('E1:deliver',{}).get('state')=='SUCCEEDED' and not self.record.get('finish_requested'):
     self.record['finish_requested']=t;self.pub.publish(String(data=json.dumps(dict(task_id=tid,attempt=1,command='finish_monitor'))))
    if t-self.phase_at>1000:self.fail('MONITOR_TIMEOUT')
   elif t-self.phase_at>spec['duration']+10:self.fail('SERVICE_TIMEOUT')
class Episode(Node):
 def __init__(self,out,args):
  super().__init__('hospital_execution',parameter_overrides=[Parameter('use_sim_time',value=True)]);self.out=out;self.run_id=out.name;self.args=args;self.cfg=config();self.tasks,self.routes=normal_tasks();self.records=[];self.commands={};self.completed={};self.truth={};self.truth_samples=[];self.last_truth=-1.;self.epoch=None;self.peers={};self.failed=None;self.finished=False;self.resource={'owners':{}};self.resource_events=[];self.file=(out/'trace.jsonl').open('w');self.protocol=EventTaskProtocol(supply=self.cfg['anchors']['G1'][:2]);self.protocol_records=[];self.plan=None;self.plan_revision=0;self.planning=None;self.planning_records=[];self.planned_owners={};self.phase='ROUTINE';self.last_refresh=-10.;self.counter=0;self.requested=set();self.release_pending=set();self.reference=None;self.health={};self.health_samples=[];self.changes=[];self.change_requested=False;self.blocks=[];self.invalidations=[];self.deviations=[];self.feedback_pending=False;self.feedback_repairs=0;self.egress_updates={};self.resume_phase=None
  self.hold_pub=self.create_publisher(String,'/clinic_aligned/hold_request',10);self.create_subscription(String,'/clinic_aligned/health',self.health_cb,STATE_QOS)
  if args.reference:
   ref=json.loads(args.reference.read_text());self.reference=dict(owners={j:r['robot'] for j,r in ref['completed'].items()},starts={j:r['service_started'] for j,r in ref['completed'].items()},routes={rid:[q['job_id'] for q in sorted(ref['records'],key=lambda q:q['begin']) if q['robot']==rid and not q['exit']] for rid in self.cfg['robots']}); (out/'reference_plan.json').write_text(json.dumps(dict(reference_file=str(args.reference.resolve()),sha256=hashlib.sha256(args.reference.read_bytes()).hexdigest(),accepted=ref['passed'],plan=self.reference),indent=2));assert ref['passed'] and ref['mode']=='normal'
  self.pub=self.create_publisher(String,'/clinic_three/resource_request',10);self.proto_pub=self.create_publisher(String,'/clinic_fall/protocol_state',STATE_QOS);self.create_subscription(String,'/clinic_three/resource_state',self.resource_cb,STATE_QOS);self.create_subscription(TFMessage,'/world/clinic_l1_three/dynamic_pose/info',self.truth_cb,100)
 def health_cb(self,m):
  self.health=json.loads(m.data);self.health_samples.append(deepcopy(self.health))
 def inject_change(self):
  now=self.elapsed();self.change_requested=True
  visits=[j for j,t in self.tasks.items() if j in self.plan['starts'] and 'DR' in t['resources']];j=min(visits,key=lambda j:self.plan['starts'][j]);lo,hi=occupancy(dict(tasks=self.tasks),self.plan,j);self.blocks=[dict(resource='DR',start=max(now+5.,lo-2.),finish=hi+90.,change_id='DR_external_booking')]
  planned_ready=json.loads((self.out/'response_plan/problem.json').read_text())['robots']['r3']['ready'];hold_until=max(now,planned_ready)+30.
  self.hold_pub.publish(String(data=json.dumps(dict(robot='r3',until=self.epoch+hold_until,change_id='r3_execution_hold'))))
  b=self.blocks[0];self.pub.publish(String(data=json.dumps(dict(action='block',resource='DR',start=self.epoch+b['start'],finish=self.epoch+b['finish'],change_id=b['change_id']))));self.changes.append(dict(at=now,kind='execution_hold_and_resource_availability',robot_hold_until=hold_until,original_available_at=planned_ready,availability_shift=30.,blocked=b));self.log('dynamic_change_requested',change=self.changes[-1]);self.phase='CHANGE_ACK'
 def now(self):return self.get_clock().now().nanoseconds*1e-9
 def elapsed(self):return self.now()-self.epoch if self.epoch is not None else -1.
 def log(self,phase,**kw):
  row=dict(at=self.now(),episode_time=self.elapsed(),wall=time.monotonic(),phase=phase,**kw);self.file.write(json.dumps(row)+'\n');self.file.flush()
  if phase not in ['guard_sample','pose_sample']:print(json.dumps(row),flush=True)
  if phase=='job_completed' and not kw['record']['exit'] and self.plan and kw['record']['job_id'] in self.plan['finishes']:
   q=kw['record'];j=q['job_id'];estimate=self.plan['finishes'][j]+self.tasks[j].get('egress',0.);late=q['end']-estimate
   if late>5.:
    d=dict(at=self.elapsed(),job=j,robot=q['robot'],planned_clear=estimate,actual_clear=q['end'],delay=late);self.deviations.append(d)
    if self.tasks[j]['resources']:
     resource=self.tasks[j]['resources'][0];self.egress_updates[resource]=max(self.egress_updates.get(resource,0.),q['clear_at']-q['service_finished']+5.)
    if (self.phase=='ROUTINE' and self.args.mode=='normal') or (self.phase=='RESPONSE' and self.protocol.event and self.protocol.event['lifecycle']=='COMPLETED'):self.feedback_pending=True

 def truth_cb(self,m):
  for t in m.transforms:
   if t.child_frame_id in self.cfg['robots']:
    q=t.transform.rotation;self.truth[t.child_frame_id]=dict(x=t.transform.translation.x,y=t.transform.translation.y,z=t.transform.translation.z,yaw=math.atan2(2*(q.w*q.z+q.x*q.y),1-2*(q.y*q.y+q.z*q.z)))
  if self.now()-self.last_truth>=.1 and len(self.truth)==3:self.truth_samples.append(dict(at=self.now(),poses=deepcopy(self.truth)));self.last_truth=self.now()
 def resource_cb(self,m):self.resource=json.loads(m.data);self.resource_events.append(deepcopy(self.resource));self.log('resource_feedback',resource=self.resource)
 def publish(self):
  s=self.protocol.snapshot();s.update(planned_owners=self.planned_owners,published_ros_time=self.now(),run_id=self.run_id);self.proto_pub.publish(String(data=json.dumps(s)))
 def protocol_apply(self,m):
  out=self.protocol.apply(m);self.protocol_records.append(dict(message=m,output=out));self.log('protocol_transition',message=m,decision=out['decision'],operations=out['operations']);self.publish()
 def observe(self):
  self.counter+=1;t=max(self.elapsed(),self.protocol.now);e=self.cfg['event'];space=dict(valid=True,frame='map',event_xy=e['center'],service_points={r:self.cfg['anchors'][e['services'][r]][:2] for r in ['verify','monitor']});space['service_points']['deliver']=self.cfg['anchors'][e['services']['event_handoff']][:2]
  self.protocol_apply(dict(schema='event-task/v1',kind='observation',message_id='obs-'+str(self.counter),event_id='E1',at=t,source_at=self.elapsed(),status='confirmed',space=space));self.last_refresh=self.elapsed()
 def release(self,bot):pass
 def acquire(self,bot,jid):
  task=self.tasks[jid]
  if not task.get('resources'):return True
  res=task['resources'][0];lease=f'{self.run_id}:{jid}:{bot.rid}';owner=self.resource.get('owners',{}).get(res,{})
  if owner.get('lease_id')==lease:bot.leases[res]=dict(lease_id=lease,job=jid);return True
  if lease not in self.requested:self.requested.add(lease);self.pub.publish(String(data=json.dumps(dict(action='acquire',robot=bot.rid,resource=res,lease_id=lease,entry_anchor=task['entry_anchor'],expected_hold=task['approach']+task['duration']+task['egress']))))
  return False
 def submit(self,stage):
  assert all(b.state=='IDLE' and not b.cargo for b in self.peers.values());now=self.elapsed();ref=(deepcopy(self.plan) if 'repair' in stage else self.reference) or dict(owners={},starts={},routes={r:[] for r in self.peers});ref=deepcopy(ref)
  if stage=='normal_plan':ref=dict(owners={j:t['nominal_owner'] for j,t in self.tasks.items()},starts={j:0. for j in self.tasks},routes=deepcopy(self.routes))
  ref['owners']={j:r for j,r in ref['owners'].items() if j not in self.completed};ref['starts']={j:t for j,t in ref['starts'].items() if j in ref['owners']};ref['routes']={r:[j for j in q if j not in self.completed] for r,q in ref['routes'].items()};p=problem({r:b.anchor for r,b in self.peers.items()},ref,self.completed,self.protocol.planning_view(),now,'response_plan' if 'repair' in stage else stage)
  if 'repair' in stage:
   p['tasks']={j:deepcopy(self.tasks[j]) for j in p['tasks']};p['blocked_resources']=deepcopy(self.blocks);p['cargo_pairs']=[pair for pair in p['cargo_pairs'] if all(j in p['tasks'] for j in pair)]
   if not all('E1_'+j in p['tasks'] for j in ['monitor','pickup','deliver']):p['events']={}
   for t in p['tasks'].values():
    if t['resources']:t['egress']=max(t['egress'],self.egress_updates.get(t['resources'][0],0.))
   for rid,v in p['robots'].items():v['ready']=max(now+3.,self.health.get('robots',{}).get(rid,{}).get('until',0.)-self.epoch)
   incumbent=deepcopy(self.plan);incumbent['routes']={r:[j for j in q if j in p['tasks']] for r,q in incumbent['routes'].items()}
   for field in ['owners','starts','finishes']:incumbent[field]={j:v for j,v in incumbent[field].items() if j in p['tasks']}
   oldcheck=validate(p,incumbent,dict(free=list(p['tasks']),freeze_time=False));self.invalidations.append(dict(at=now,stage=stage,incumbent=incumbent,old_plan_validation=oldcheck));self.log('incumbent_invalidated',validation=oldcheck)
  for rid,robot in p['robots'].items():
   if self.peers[rid].finished:robot['capabilities']=[]
  folder=self.out/stage;folder.mkdir();inp=folder/'problem.json';inp.write_text(json.dumps(p,indent=2));output=folder/'result.json';f=(folder/'worker.log').open('w');proc=subprocess.Popen([str(PROJECT/'.venv/bin/python'),str(ROOT/'tools/aligned_solver.py'),str(inp),str(output),'--policy','local_impact' if 'repair' in stage else 'retained_milp' if stage=='normal_plan' else self.args.policy],stdout=f,stderr=subprocess.STDOUT);self.planning=dict(stage=stage,problem=p,process=proc,log=f,output=output,wall=time.monotonic(),at=now,revision=self.protocol.world_revision);self.phase='PLANNING';self.log('planning_requested',stage=stage,sources={r:b.anchor for r,b in self.peers.items()})
 def poll(self):
  q=self.planning
  if not q:return
  if q['process'].poll() is None:
   if time.monotonic()-q['wall']>45:self.failed='PLANNING_TIMEOUT'
   return
  q['log'].close();result=json.loads(q['output'].read_text()) if q['output'].exists() else {'status':'PROCESS_FAILED'}
  if result['status'] not in ['OPTIMAL','FEASIBLE_BUDGET']:self.failed='MILP_'+result['status'];return
  p=deepcopy(q['problem']);p['time']=self.elapsed()
  for v in p['robots'].values():v['ready']=max(v['ready'],self.elapsed())
  input_check=validate(q['problem'],result['plan'],result['attempts'][-1]['scope'],result['objective']);check=validate(p,result['plan'],result['attempts'][-1]['scope'])
  check['input_objective_valid']=input_check['passed'];check['passed'] &= input_check['passed']
  for a,b in p.get('cargo_pairs',[]):
   route=result['plan']['routes'][result['plan']['owners'][a]];check['passed'] &= result['plan']['owners'][a]==result['plan']['owners'][b] and route.index(b)==route.index(a)+1
  if not check['passed'] or self.protocol.world_revision!=q['revision']:self.failed='INVALID_OR_STALE_PLAN';return
  entry=dict(stage=q['stage'],requested_at=q['at'],returned_at=self.elapsed(),end_to_end_wall=time.monotonic()-q['wall'],solver=result,commit_validation=check);self.planning_records.append(entry);self.plan=result['plan'];self.plan_revision+=1;self.tasks.update(q['problem']['tasks']);self.planned_owners.update({t['protocol_task_id']:self.plan['owners'][j] for j,t in self.tasks.items() if j in self.plan['owners'] and t.get('protocol_task_id')});self.phase=(self.resume_phase or 'ROUTINE') if q['stage'].startswith('feedback_repair') else 'ROUTINE' if q['stage']=='normal_plan' else 'VERIFY' if q['stage']=='verify_plan' else 'RESPONSE';self.log('plan_committed',stage=q['stage'],plan=self.plan,objective=result['objective']);self.publish();self.planning=None
 def dispatch(self,bot):
  if bot.state!='IDLE' or bot.finished or self.planning or self.phase=='CHANGE_ACK':return
  if self.now()<self.health.get('robots',{}).get(bot.rid,{}).get('until',0.):return
  if self.phase in ['ROUTINE','QUIESCE','FEEDBACK_QUIESCE']:
   queue=[j for j in (self.plan['routes'][bot.rid] if self.plan else self.routes[bot.rid]) if j not in self.completed]
   if self.phase in ['QUIESCE','FEEDBACK_QUIESCE'] and not bot.cargo:
    clear_points={v['clear'] for v in self.cfg['resource_phases'].values()}
    if bot.anchor in clear_points and queue and not self.tasks[queue[0]]['resources']:
     key=(self.phase,bot.anchor,queue[0])
     if getattr(bot,'clearance_key',None)!=key:bot.clearance_key=key;self.log('quiescence_clearance',robot=bot.rid,anchor=bot.anchor,next_job=queue[0])
    else:return
  else:queue=[j for j in self.plan['routes'][bot.rid] if j not in self.completed]
  if not queue:
   if self.phase=='VERIFY':return
   bot.dispatch('EXIT_'+bot.rid,True);return
  jid=queue[0]
  if self.plan and self.phase in ['ROUTINE','QUIESCE','FEEDBACK_QUIESCE','VERIFY','RESPONSE']:
   dt=self.cfg['tables']['normal' if self.args.mode=='normal' else 'event'][bot.anchor][self.tasks[jid]['entry_anchor']]+self.tasks[jid]['approach']
   if self.elapsed()<self.plan['starts'][jid]-dt:return
  bot.dispatch(jid)

def main():
 p=argparse.ArgumentParser();p.add_argument('--arrival',choices=['nav2','pose_handoff'],default='nav2');p.add_argument('--parking',choices=['original','separate_bays'],default='original');p.add_argument('--localization',choices=['amcl','reference'],default='amcl');p.add_argument('--mode',choices=['normal','event'],required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--reference',type=Path);p.add_argument('--changes',choices=['none','hold_resource'],default='none');p.add_argument('--policy',default='retained_milp',choices=['retained_milp','full_replan','local_repair']);a=p.parse_args();a.out.mkdir(parents=True,exist_ok=False)
 if a.mode=='event' and not a.reference:raise ValueError('Event run needs the accepted normal run as reference')
 import aligned_tasks
 aligned_tasks.PARKING_VARIANT=a.parking;(a.out/'runtime_scenario.json').write_text(json.dumps(config(),indent=2))
 source=a.out/'source';source.mkdir();files=list((ROOT/'config/hospital_aligned').glob('*'))+[ROOT/'tools'/n for n in ['run_aligned_episode.py','aligned_tasks.py','aligned_solver.py','aligned_contract.py','aligned_resources.py','aligned_keepout.py','aligned_health.py','aligned_service_worker.py','hospital_service_worker.py','clinic_milp_backend.py']]+[PROJECT/'src/kaiti_task_sim/event_protocol.py'];hashes={}
 if a.localization=='reference':files+=list((ROOT/'config/hospital_reference').glob('*'))+[ROOT/'tools/aligned_reference_tf.py']
 for f in files:
  rel=f.relative_to(ROOT) if f.is_relative_to(ROOT) else Path('protocol_reference.py');dest=source/rel;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(f,dest);hashes[str(rel)]=hashlib.sha256(f.read_bytes()).hexdigest()
 (a.out/'source_manifest.json').write_text(json.dumps(hashes,indent=2));rclpy.init();c=Episode(a.out,a);ex=SingleThreadedExecutor();ex.add_node(c)
 for rid in c.cfg['robots']:b=Bot(rid,c);c.peers[rid]=b;ex.add_node(b)
 begin=time.monotonic();ready=False;lastpose=-1.
 try:
  while time.monotonic()-begin<3000 and not c.failed:
   ex.spin_once(timeout_sec=.02)
   if not ready:
    if all(b.ready() for b in c.peers.values()) and len(c.truth)==3:
     graph=Coordinator.graph_audit(c);(a.out/'namespace_audit.json').write_text(json.dumps(graph,indent=2));assert graph['passed'];c.epoch=c.now()+1.;ready=True;c.publish();c.log('episode_ready',mode=a.mode);c.submit('normal_plan')
    elif time.monotonic()-begin>240:c.failed='READY_TIMEOUT'
    continue
   if c.elapsed()<0:continue
   for b in c.peers.values():b.step();c.release(b)
   if c.elapsed()-lastpose>=.2:c.log('pose_sample',poses={r:b.pose() for r,b in c.peers.items()},truth=c.truth);lastpose=c.elapsed()
   if a.mode=='event':
    if c.phase=='ROUTINE' and c.elapsed()>=c.cfg['fall_at']:c.observe();c.phase='QUIESCE';c.log('fall_event_injected',active_jobs={r:b.job for r,b in c.peers.items()},states={r:b.state for r,b in c.peers.items()})
    if c.protocol.event and c.elapsed()-c.last_refresh>=2:c.observe()
    if c.phase=='QUIESCE' and all(b.state=='IDLE' and not b.cargo for b in c.peers.values()):c.log('commitment_barrier_reached');c.submit('verify_plan')
    if c.phase=='VERIFY' and 'E1_verify' in c.completed and all(b.state=='IDLE' for b in c.peers.values()):c.submit('response_plan')
   if c.feedback_pending and len(c.completed)<16+(4 if a.mode=='event' else 0) and not c.planning and c.phase in ['ROUTINE','RESPONSE'] and c.feedback_repairs<3:
    c.resume_phase=c.phase;c.phase='FEEDBACK_QUIESCE';c.feedback_pending=False;c.log('execution_delay_detected',deviation=c.deviations[-1])
   if c.phase=='FEEDBACK_QUIESCE' and all(b.state=='IDLE' and not b.cargo for b in c.peers.values()):
    c.feedback_repairs+=1;c.log('feedback_repair_barrier',sources={r:b.anchor for r,b in c.peers.items()});c.submit('feedback_repair_'+str(c.feedback_repairs))
   c.poll()
   if a.mode=='event' and a.changes=='hold_resource' and c.phase=='RESPONSE' and not c.change_requested:c.inject_change()
   if c.phase=='CHANGE_ACK' and c.health.get('robots',{}).get('r3',{}).get('change_id')=='r3_execution_hold' and any(b['change_id']=='DR_external_booking' for b in c.resource.get('blocked',[])):
    c.log('execution_change_feedback',health=c.health,resource=c.resource);c.submit('repair_plan')
   if c.failed:break
   for b in c.peers.values():c.dispatch(b)
   goal=16+(4 if a.mode=='event' else 0)
   if len(c.completed)==goal and all(b.finished for b in c.peers.values()) and not c.resource.get('owners') and (a.mode=='normal' or c.protocol.event['lifecycle']=='COMPLETED'):c.finished=True;break
  if not c.finished and not c.failed:c.failed='EPISODE_TIMEOUT'
 except KeyboardInterrupt:c.failed='USER_INTERRUPTED'
 except Exception as e:c.failed=repr(e);raise
 finally:
  if c.planning and c.planning['process'].poll() is None:c.planning['process'].kill()
  if c.failed:
   for b in c.peers.values():
    if b.nav_handle:b.nav_handle.cancel_goal_async()
  result=dict(arrival=a.arrival,parking=a.parking,localization=a.localization,passed=c.finished and not c.failed,failure=c.failed,mode=a.mode,changes_mode=a.changes,policy=a.policy,records=c.records,completed=c.completed,protocol=c.protocol.snapshot(),protocol_records=c.protocol_records,planning_records=c.planning_records,truth_samples=c.truth_samples,resource_events=c.resource_events,changes=c.changes,health_samples=c.health_samples,invalidations=c.invalidations,deviations=c.deviations,feedback_repairs=c.feedback_repairs,epoch=c.epoch,wall_seconds=time.monotonic()-begin);(a.out/'result.json').write_text(json.dumps(result,indent=2));c.file.close();print('RESULT',a.out,result['passed'],c.failed,flush=True)
  for b in list(c.peers.values())+[c]:ex.remove_node(b);b.destroy_node()
  ex.shutdown();rclpy.shutdown()
 return 0 if result['passed'] else 1
if __name__=='__main__':raise SystemExit(main())
