#!/usr/bin/env python3
"""Independent patrol/incident/recovery/two-period physical Clinic acceptance."""
from pathlib import Path
from copy import deepcopy
from types import SimpleNamespace
import argparse,json,hashlib,shutil,subprocess,time,sys,math
import numpy as np
import rclpy
from rclpy.executors import SingleThreadedExecutor
from std_msgs.msg import String
import run_aligned_episode as old
import dense_tasks as dt
from dense_validate import validate as model_validate
ROOT=dt.ROOT;PROJECT=old.PROJECT
old.config=dt.config;old.normal_tasks=dt.normal_tasks

def navigation_budget(cfg,spec,leg,anchor,direct):
 target=spec['entry_anchor'] if leg=='entry' else spec['clear_anchor'] if leg=='clear' else spec['anchor']
 source=spec['anchor'] if leg=='clear' else anchor
 prior=max(0.,(cfg['tables']['event'][source][target]-12.)*.22)
 limit=max(8.,1.5*prior+2.)
 if leg in ['service','clear'] and spec['resources']:limit=min(limit,max(8.,2*direct+2.))
 return limit,prior

class Bot(old.Bot):
 def __init__(self,rid,c):
  super().__init__(rid,c)
  from nav2_msgs.action import ComputePathToPose,FollowPath
  from rclpy.action import ActionClient
  self.path_action=ActionClient(self,ComputePathToPose,'compute_path_to_pose');self.follow_action=ActionClient(self,FollowPath,'follow_path');self.path_wait_since=None
 def ready(self):return super().ready() and self.path_action.server_is_ready() and self.follow_action.server_is_ready()
 def send_navigation(self):
  from nav2_msgs.action import ComputePathToPose
  self.near_since=None;self.handoff_requested=False;t=self.c.elapsed();g=ComputePathToPose.Goal();g.use_start=False;g.planner_id='GridBased';g.goal.header.frame_id='map';g.goal.header.stamp=self.get_clock().now().to_msg();p=self.record['target'];g.goal.pose.position.x=p['x'];g.goal.pose.position.y=p['y'];g.goal.pose.orientation.z=math.sin(p['yaw']/2);g.goal.pose.orientation.w=math.cos(p['yaw']/2);self.path_future=self.path_action.send_goal_async(g);self.state='PATH_ACK';self.phase_at=t;self.phase_wall=time.monotonic()
 def start_follow(self):
  from nav2_msgs.action import FollowPath
  self.c.reserve_motion(self);g=FollowPath.Goal();g.path=self.approved_path;g.controller_id='FollowPath';g.goal_checker_id='general_goal_checker';self.record['navigation_attempts'].append(dict(begin=self.c.elapsed(),reason='approved_once_path',leg=self.leg,nav_kind='Nav2 ComputePathToPose + FollowPath',approved_length=self.approved_length));self.goal_future=self.follow_action.send_goal_async(g);self.state='NAV_ACK';self.phase_wall=time.monotonic();self.stable=None;self.path_wait_since=None
 def step(self):
  t=self.c.elapsed()
  if self.state=='PATH_ACK':
   if self.path_future.done():
    h=self.path_future.result()
    if not h.accepted:self.fail('PATH_REJECTED');return
    self.path_result=h.get_result_async();self.state='PATH_RESULT'
   elif t-self.phase_at>15:self.fail('PATH_ACK_TIMEOUT')
   return
  if self.state=='PATH_RESULT':
   if not self.path_result.done():
    if t-self.phase_at>20:self.fail('PATH_RESULT_TIMEOUT')
    return
   result=self.path_result.result();path=result.result.path;pts=[(p.pose.position.x,p.pose.position.y) for p in path.poses];length=sum(math.dist(x,y) for x,y in zip(pts,pts[1:]));pose=self.pose();direct=math.hypot(self.record['target']['x']-pose['x'],self.record['target']['y']-pose['y']);local=self.leg in ['service','clear'] and bool(self.c.tasks[self.job]['resources']);limit,prior=navigation_budget(self.c.cfg,self.c.tasks[self.job],self.leg,self.anchor,direct);endpoint_error=math.dist(pts[-1],(self.record['target']['x'],self.record['target']['y'])) if pts else float('inf');ok=result.status==4 and len(pts)>1 and length<=limit and endpoint_error<=.12
   self.record.setdefault('path_checks',[]).append(dict(at=t,leg=self.leg,status=result.status,length=length,direct=direct,short_leg=local,limit=limit,static_prior_length=prior,endpoint_error=endpoint_error,accepted=ok));self.c.log('navigation_path_checked',robot=self.rid,job=self.job,leg=self.leg,length=length,accepted=ok,short_leg=local)
   if not ok:
    if self.path_wait_since is None:self.path_wait_since=t
    self.c.release_unentered_neck(self.rid,self.job,'invalid_path_wait')
    allowance=min(self.c.cfg['path_wait_timeout_seconds'],self.c.tasks[self.job].get('start_deadline',self.c.tasks[self.job]['deadline'])-self.path_wait_since)
    if t-self.path_wait_since>allowance:self.fail('PATH_WAIT_TIMEOUT');return
    self.state='PATH_WAIT';self.retry_at=t+3.;return
   self.approved_path=path;self.approved_length=length;self.approved_at=t;self.path_crosses_neck=any(19.8<=x<=23.7 and -18.8<=y<=-12.8 for x,y in pts);self.state='PATH_ADMISSION'
  if self.state=='PATH_ADMISSION':
   if self.path_crosses_neck and not self.c.request_neck(self,self.job,force=True):return
   if not self.c.motion_admitted(self):return
   if t-self.approved_at>3:self.send_navigation();return
   self.start_follow();return
  if self.state=='PATH_WAIT':
   if t>=self.retry_at:self.send_navigation()
   return
  if self.state=='NAVIGATING' and self.result_future.done():
   status=self.result_future.result().status
   if status not in [4,5] and sum(x['leg']==self.leg for x in self.record['navigation_attempts'])<3:
    self.record['navigation_attempts'][-1].update(status=status,end=t,recovery=dict(reason='controller_abort_wait_then_replan',wait_seconds=3.));self.c.log('controller_recovery_wait',robot=self.rid,job=self.job,leg=self.leg,status=status);self.state='PATH_WAIT';self.retry_at=t+3.;return
  if self.state=='SERVICE_RUNNING' and self.c.tasks[self.job]['kind']=='monitor':
   c=self.c;now=c.elapsed();tid=self.record['task_id']
   if (tid,'failed') in self.phases:self.fail('SERVICE_FAILED');return
   if (tid,'succeeded') in self.phases:self.record['service_finished']=self.phases[tid,'succeeded']['at']-c.epoch;self.finish();return
   if c.handover_ack and not self.record.get('finish_requested'):
    self.record['finish_requested']=now;self.pub.publish(String(data=json.dumps(dict(task_id=tid,attempt=1,command='finish_monitor'))));c.log('monitor_stop_requested_after_handover',robot=self.rid,job=self.job)
   if now-self.phase_at>1100:self.fail('MONITOR_TIMEOUT')
   return
  super().step()

class Episode(old.Episode):
 def __init__(self,out,args):
  super().__init__(out,args);self.phase='PATROL';self.queues={r:[] for r in self.cfg['robots']};self.event_at=None;self.incident_closed_at=None;self.handover_ack=False;self.released_cycles={0};self.cycle_releases=[];self.ledger={j:dict(state='READY',release=t['release'],cycle=t['cycle_id'],nominal_owner=t['nominal_owner']) for j,t in self.tasks.items()};self.deferred=[];self.neck_owner=None;self.neck_entered=False;self.neck_wait=[];self.neck_events=[];self.admissions={};self.next_neck_check=0.;self.normal_complete_logged=False;self.cycle1_planned=False;self.motion_paths={};self.motion_waits=set();self.peer_signature=None;self.next_peer_publish=0.;self.peer_pub=self.create_publisher(String,'/clinic_dense/execution_state',old.STATE_QOS)
 def acquire(self,bot,jid):
  task=self.tasks[jid]
  if not task.get('resources'):return True
  res=task['resources'][0];lease=f'{self.run_id}:{jid}:{bot.rid}';owner=self.resource.get('owners',{}).get(res,{})
  if owner.get('lease_id')==lease:bot.leases[res]=dict(lease_id=lease,job=jid);return True
  if lease not in self.requested:
   self.requested.add(lease);self.pub.publish(String(data=json.dumps(dict(action='acquire',robot=bot.rid,resource=res,lease_id=lease,entry_anchor=task['entry_anchor'],clear_anchor=task['clear_anchor'],expected_hold=task['approach']+task['duration']+task['egress']))))
  return False
 def states(self):return {r:dict(job=b.job,state=b.state,anchor=b.anchor,cargo=b.cargo,record=deepcopy(b.record or {}),pose=b.pose(),leg=b.leg) for r,b in self.peers.items()}
 def normal_pending(self):return [j for j,t in self.tasks.items() if t['kind']=='normal' and j not in self.completed]
 def submit_dense(self,stage):
  assert self.planning is None;now=self.elapsed();states=self.states();active={b.job for b in self.peers.values() if b.job};variants=[]
  if stage=='verify':selected=[['E1_verify']]
  elif stage=='response':
   candidates=[]
   for rid in self.peers:
    q=sorted([j for j in self.normal_pending() if j not in active and self.tasks[j]['nominal_owner']==rid],key=lambda j:(self.tasks[j]['cycle_id'],self.tasks[j]['waypoint']))
    if q:candidates.append(q[0])
   assert candidates,'Need a real routine backlog job for third-robot cooperation'
   selected=[['E1_monitor','E1_pickup','E1_deliver',j] for j in candidates]
  else:selected=[[j for j in self.normal_pending() if j not in active]]
  if not selected[0]:self.phase='RESUME' if stage=='resume' else 'PATROL';return
  for jobs in selected:variants.append(dt.problem(self.cfg,self.tasks,jobs,self.completed,states,self.plan or dict(starts={}),now,self.event_at,stage))
  folder=self.out/f'{len(self.planning_records):02d}_{stage}';folder.mkdir();req=folder/'request.json';req.write_text(json.dumps(dict(variants=variants),indent=2));log=(folder/'worker.log').open('w');output=folder/'result.json';proc=subprocess.Popen([str(PROJECT/'.venv/bin/python'),str(ROOT/'tools/dense_solver.py'),str(req),str(output)],stdout=log,stderr=subprocess.STDOUT)
  self.planning=dict(stage=stage,folder=folder,output=output,process=proc,log=log,at=now,wall=time.monotonic(),states=states);self.log('planning_requested',stage=stage,active_prefix=sorted(active),candidates=len(variants),pending_normal=self.normal_pending())
 def poll_dense(self):
  q=self.planning
  if not q:return
  if q['process'].poll() is None:
   if time.monotonic()-q['wall']>40:self.failed='DENSE_SOLVER_TIMEOUT'
   return
  q['log'].close();r=json.loads(q['output'].read_text()) if q['output'].exists() else dict(status='MISSING_RESULT')
  if r['status'] not in ['OPTIMAL','FEASIBLE_BUDGET']:self.failed='MILP_'+r['status'];return
  p=r['selected_problem'];scope=r['scope'];check=model_validate(p,r['plan'],scope,r['objective']);assert check['passed'],check
  for rid,s in q['states'].items():
   if s['job'] and self.peers[rid].job not in [s['job'],None]:raise RuntimeError('Snapshot fence changed issued action')
  if min(v['ready'] for v in p['robots'].values())<self.elapsed()-1e-6:self.failed='STALE_PLANNING_WINDOW';return
  for j,t in p['tasks'].items():
   if t['kind']=='normal' and p['stage']=='response':assert r['plan']['owners'][j] not in [r['plan']['owners']['E1_monitor'],r['plan']['owners']['E1_pickup']]
  (q['folder']/'problem.json').write_text(json.dumps(p,indent=2));entry=dict(stage=q['stage'],requested_at=q['at'],returned_at=self.elapsed(),end_to_end_wall=time.monotonic()-q['wall'],problem_path=str(q['folder']/'problem.json'),solver=deepcopy(r),commit_validation=check);self.planning_records.append(entry)
  if self.plan is None:self.plan=deepcopy(r['plan'])
  else:
   for field in ['owners','starts','finishes']:self.plan[field].update(deepcopy(r['plan'][field]))
   self.plan['routes']=deepcopy(r['plan']['routes']);self.plan['ends']=deepcopy(r['plan']['ends'])
  self.queues=deepcopy(r['plan']['routes']);self.neck_wait=[];self.plan_revision+=1
  if q['stage']=='cycle1':self.cycle1_planned=True
  self.planned_owners.update({t['protocol_task_id']:r['plan']['owners'][j] for j,t in p['tasks'].items() if t.get('protocol_task_id')});self.publish();self.phase={'verify':'VERIFY','response':'RESPONSE','resume':'RESUME'}.get(q['stage'],'PATROL');self.log('plan_committed',stage=q['stage'],plan=deepcopy(r['plan']),prefixes=p['prefixes'],normal_selected=[j for j,t in p['tasks'].items() if t['kind']=='normal'],objective=r['objective']);self.planning=None
 def update_motion(self):
  for rid in list(self.motion_paths):
   if self.peers[rid].state not in ['NAV_ACK','NAVIGATING']:
    del self.motion_paths[rid];self.log('motion_path_released',robot=rid)
  if self.elapsed()<self.next_peer_publish:return
  self.next_peer_publish=self.elapsed()+.2
  peers={r:dict(stationary=b.state not in ['NAV_ACK','NAVIGATING'],x=round(self.truth[r]['x'],1),y=round(self.truth[r]['y'],1)) for r,b in self.peers.items() if r in self.truth}
  signature=json.dumps({r:p if p['stationary'] else dict(stationary=False) for r,p in peers.items()},sort_keys=True)
  if signature!=self.peer_signature:self.peer_signature=signature;self.peer_pub.publish(String(data=json.dumps(peers)))
 def motion_admitted(self,b):
  pts=np.array([(p.pose.position.x,p.pose.position.y) for p in b.approved_path.poses][::4]+[(b.approved_path.poses[-1].pose.position.x,b.approved_path.poses[-1].pose.position.y)])
  for rid,other in self.motion_paths.items():
   if rid==b.rid:continue
   pose=self.truth.get(rid)
   if not pose:continue
   i=max(0,int(np.argmin(np.linalg.norm(other-np.array([pose['x'],pose['y']]),axis=1)))-1);remaining=other[i:]
   if np.min(np.linalg.norm(pts[:,None,:]-remaining[None,:,:],axis=2))<.75:
    key=(b.rid,b.job,b.leg,rid)
    if key not in self.motion_waits:self.motion_waits.add(key);self.log('motion_path_wait',robot=b.rid,job=b.job,leg=b.leg,conflict_robot=rid)
    return False
  return True
 def reserve_motion(self,b):
  pts=[(p.pose.position.x,p.pose.position.y) for p in b.approved_path.poses];self.motion_paths[b.rid]=np.array(pts[::4]+[pts[-1]]);self.log('motion_path_admitted',robot=b.rid,job=b.job,leg=b.leg,length=b.approved_length)
 def release_unentered_neck(self,rid,j,reason):
  if self.neck_owner==(rid,j) and not self.neck_entered:
   self.neck_events.append(dict(at=self.elapsed(),action='release',robot=rid,job=j,entered=False,reason=reason));self.log('corridor_released',robot=rid,job=j,reason=reason);self.neck_owner=None
  self.neck_wait=[key for key in self.neck_wait if key!=(rid,j)]
 def request_neck(self,b,j,force=False):
  source=self.cfg['anchors'][b.anchor];target=self.cfg['anchors'][self.tasks[j]['entry_anchor']]
  lower=lambda p:p[0]>=19.8 and p[1]<-13.
  needed=(lower(source)!=lower(target)) or self.tasks[j]['entry_anchor']=='ADL'
  if not needed and not force:return True
  key=(b.rid,j)
  if self.neck_owner==key:return True
  if key not in self.neck_wait:self.neck_wait.append(key);self.log('corridor_queued',robot=b.rid,job=j)
  if self.neck_owner is None and self.neck_wait[0]==key:
   self.neck_owner=key;self.neck_wait.pop(0);self.neck_entered=False;dest=self.cfg['anchors'][self.tasks[j]['anchor']];self.neck_exit='south' if dest[0]>=19.8 and dest[1]<-18.8 else 'north' if dest[1]>-13. else 'west';row=dict(at=self.elapsed(),action='grant',robot=b.rid,job=j);self.neck_events.append(row);self.log('corridor_granted',**{k:v for k,v in row.items() if k!='at'})
  return self.neck_owner==key
 def update_neck(self):
  if self.elapsed()<self.next_neck_check:return
  self.next_neck_check=self.elapsed()+.1
  if not self.neck_owner:return
  rid,j=self.neck_owner;p=self.truth.get(rid)
  if not p:return
  inside=19.8<=p['x']<=23.7 and -18.8<=p['y']<=-12.8
  if inside:self.neck_entered=True
  outside=(p['y']<-19.1 if self.neck_exit=='south' else p['y']>-12.5 if self.neck_exit=='north' else p['x']<19.5)
  if (self.neck_entered and outside) or j in self.completed:
   self.neck_events.append(dict(at=self.elapsed(),action='release',robot=rid,job=j,entered=self.neck_entered,pose=deepcopy(p)));self.log('corridor_released',robot=rid,job=j,pose=p);self.neck_owner=None
 def dispatch_dense(self,b):
  if b.state!='IDLE' or self.planning:return
  q=[j for j in self.queues.get(b.rid,[]) if j not in self.completed]
  if not q:return
  j=q[0];spec=self.tasks[j]
  if any(dep not in self.completed for dep in spec['dependencies']):return
  dtm=self.cfg['tables']['event'][b.anchor][spec['entry_anchor']]+spec['approach']
  if self.elapsed()<self.plan['starts'][j]-dtm:return
  for resource in spec['resources']:
   holder=self.admissions.get(resource)
   if holder and holder[1] not in self.completed and holder!=(b.rid,j):return
  for resource in spec['resources']:self.admissions[resource]=(b.rid,j)
  if j in self.ledger:self.ledger[j]['state']='RUNNING';self.ledger[j]['actual_owner']=b.rid;self.ledger[j]['dispatched_at']=self.elapsed()
  b.dispatch(j)
 def inject_event(self):
  self.event_at=self.elapsed();active={b.job for b in self.peers.values() if b.job};self.deferred=[j for j in self.normal_pending() if j not in active]
  for j in self.deferred:self.ledger[j]['state']='DEFERRED'
  self.observe();self.tasks.update(dt.event_tasks(self.protocol.planning_view(),self.elapsed()));self.phase='VERIFY';self.log('fall_event_injected',event_id='E1',priority=100,active_jobs={r:b.job for r,b in self.peers.items()},states={r:b.state for r,b in self.peers.items()},deferred=self.deferred);self.submit_dense('verify')
 def tick(self):
  now=self.elapsed();self.update_motion();self.update_neck()
  if self.event_at is None:
   first=all(f'C0_{r}_W1' in self.completed for r in self.peers);moving=sum(b.state=='NAVIGATING' for b in self.peers.values())
   if first and moving>=2:self.inject_event()
   elif now>550:self.failed='EVENT_TRIGGER_NOT_REACHED';return
  if self.protocol.event and now-self.last_refresh>=2:self.observe()
  self.poll_dense()
  if self.failed:return
  if self.phase=='VERIFY' and 'E1_verify' in self.completed and not self.planning:
   self.tasks.update(dt.event_tasks(self.protocol.planning_view(),now));self.submit_dense('response')
  if self.phase=='RESPONSE' and 'E1_deliver' in self.completed and not self.handover_ack and now-self.completed['E1_deliver']['end']>=3.:
   self.handover_ack=True;self.log('scripted_handover_ack',event_id='E1',source='scenario service receiver, not visual/clinical inference')
  if self.incident_closed_at is None and self.protocol.event and self.protocol.event['lifecycle']=='COMPLETED' and all('E1_'+r in self.completed for r in ['verify','monitor','pickup','deliver']):
   assert self.handover_ack;self.incident_closed_at=now;remaining=self.normal_pending();self.log('incident_closed',event_id='E1',remaining_normal=remaining,deferred_at_event=self.deferred)
   for j in remaining:self.ledger[j]['state']='READY'
   if not self.planning:self.submit_dense('resume')
  if 1 not in self.released_cycles and now>=self.cfg['period_seconds']:
   tasks,routes=dt.cycle_tasks(1);self.tasks.update(tasks);self.routes.update(routes)
   for j,t in tasks.items():self.ledger[j]=dict(state='READY',release=t['release'],cycle=1,nominal_owner=t['nominal_owner'])
   self.released_cycles.add(1);self.cycle_releases.append(dict(cycle=1,nominal_release=self.cfg['period_seconds'],actual_release=now,jobs=sorted(tasks)));self.log('periodic_release',cycle=1,nominal_release=self.cfg['period_seconds'],jobs=sorted(tasks))
   if self.incident_closed_at is not None and not self.planning:self.submit_dense('cycle1')
  if 1 in self.released_cycles and self.incident_closed_at is not None and not self.cycle1_planned and not self.planning:self.submit_dense('cycle1')
  for j in self.ledger:
   if j in self.completed:self.ledger[j]['state']='SUCCEEDED'
  for b in self.peers.values():self.dispatch_dense(b)
  expected={j for j,t in self.tasks.items() if t['kind']=='normal'}|{'E1_'+r for r in ['verify','monitor','pickup','deliver']}
  if self.released_cycles=={0,1} and expected.issubset(self.completed) and all(b.state=='IDLE' for b in self.peers.values()) and not self.resource.get('owners') and self.incident_closed_at is not None:
   assert next(x for x in self.cycle_releases if x['cycle']==1)['actual_release']>self.incident_closed_at,'Next period was not demonstrated after event closure';self.finished=True

def main():
 p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);args=p.parse_args();args.arrival='pose_handoff';args.parking='dense_cycle';args.localization='reference';args.mode='event';args.reference=None;args.policy='milp';args.changes='none';args.out.mkdir(parents=True,exist_ok=False);(args.out/'runtime_scenario.json').write_text(json.dumps(dt.config(),indent=2));source=args.out/'source';files=list((ROOT/'config/hospital_dense').glob('*'))+[ROOT/'tools'/n for n in ['dense_tasks.py','dense_solver.py','dense_validate.py','run_dense_episode.py','run_aligned_episode.py','aligned_solver.py','aligned_contract.py','clinic_milp_backend.py','aligned_service_worker.py','aligned_resources.py','aligned_keepout.py','aligned_reference_tf.py','bootstrap_dense_tb4.py','spawn_dense_tb4.py','dense_resources.py','dense_keepout.py','dense_reference_tf.py']]+[ROOT/'launch/clinic_l1_dense.launch.py',ROOT/'run_clinic_dense.sh',ROOT/'run_dense_episode.sh',PROJECT/'src/kaiti_task_sim/event_protocol.py'];manifest={}
 for f in files:
  rel=f.relative_to(ROOT) if f.is_relative_to(ROOT) else Path('protocol_reference.py');dst=source/rel;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(f,dst);manifest[str(f)]=hashlib.sha256(f.read_bytes()).hexdigest()
 (args.out/'source_manifest.json').write_text(json.dumps(manifest,indent=2));rclpy.init();c=Episode(args.out,args);ex=SingleThreadedExecutor();ex.add_node(c)
 for rid in c.cfg['robots']:b=Bot(rid,c);c.peers[rid]=b;ex.add_node(b)
 begin=time.monotonic();ready=False;last=-1.;last_step=-1.
 try:
  while time.monotonic()-begin<3600 and not c.failed and not c.finished:
   ex.spin_once(timeout_sec=.02)
   if not ready:
    if all(b.ready() for b in c.peers.values()) and len(c.truth)==3:
     audit=old.Coordinator.graph_audit(c);(args.out/'namespace_audit.json').write_text(json.dumps(audit,indent=2));assert audit['passed'];c.epoch=c.now()+1.;ready=True;c.publish();c.log('episode_ready',mode='dense_patrol_incident_two_periods')
    elif time.monotonic()-begin>240:c.failed='READY_TIMEOUT'
    continue
   if c.elapsed()<0:continue
   # Drain high-rate ROS/TF callbacks between bounded 20 Hz state-machine updates.
   if c.elapsed()-last_step<.05:continue
   last_step=c.elapsed()
   if c.plan is None and c.planning is None:
    c.cycle_releases.append(dict(cycle=0,nominal_release=0.,actual_release=c.elapsed(),jobs=sorted(c.tasks)));c.log('periodic_release',cycle=0,nominal_release=0.,jobs=sorted(c.tasks));c.submit_dense('normal')
   for b in c.peers.values():b.step()
   if c.elapsed()-last>=.2:c.log('pose_sample',poses={r:b.pose() for r,b in c.peers.items()},truth=c.truth);last=c.elapsed()
   c.tick()
  if not c.finished and not c.failed:c.failed='EPISODE_TIMEOUT'
 except KeyboardInterrupt:c.failed='USER_INTERRUPTED'
 except Exception as error:c.failed=repr(error);c.log('controller_exception',error=repr(error));raise
 finally:
  if c.planning and c.planning['process'].poll() is None:c.planning['process'].terminate()
  if c.failed:
   for b in c.peers.values():
    if b.nav_handle:b.nav_handle.cancel_goal_async()
  result=dict(passed=c.finished and not c.failed,failure=c.failed,records=c.records,completed=c.completed,tasks=c.tasks,ledger=c.ledger,protocol=c.protocol.snapshot(),protocol_records=c.protocol_records,planning_records=c.planning_records,truth_samples=c.truth_samples,resource_events=c.resource_events,neck_events=c.neck_events,cycle_releases=c.cycle_releases,event_at=c.event_at,incident_closed_at=c.incident_closed_at,handover_ack=c.handover_ack,deferred_at_event=c.deferred,epoch=c.epoch,wall_seconds=time.monotonic()-begin,localization='gazebo_reference_pose',arrival='pose_handoff',disturbances='none; no beds or people',obstacle_policy=c.cfg['obstacle_policy']);(args.out/'result.json').write_text(json.dumps(result,indent=2));c.file.close();print('RESULT',args.out,result['passed'],c.failed,flush=True)
  for b in list(c.peers.values())+[c]:ex.remove_node(b);b.destroy_node()
  ex.shutdown();rclpy.shutdown()
 return 0 if result['passed'] else 1
if __name__=='__main__':raise SystemExit(main())
