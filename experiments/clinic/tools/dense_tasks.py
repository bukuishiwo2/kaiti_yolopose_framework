"""Independent finite two-cycle patrol ledger and pre-response MILP snapshots."""
from pathlib import Path
from copy import deepcopy
import json,math
ROOT=Path(__file__).resolve().parents[1]
def config():return json.loads((ROOT/'config/hospital_dense/scenario.json').read_text())
def cycle_tasks(cycle):
 c=config();tasks={};routes={r:[] for r in c['robots']}
 for rid,seq in c['patrol_routes'].items():
  for k,anchor in enumerate(seq):
   j=f'C{cycle}_{rid}_W{k+1}';dep=routes[rid][-1:] or ([f'C{cycle-1}_{rid}_W3'] if cycle else []);t=dict(kind='normal',anchor=anchor,duration=4.,capabilities=['move'],release=cycle*c['period_seconds'],deadline=2200.,resources=[anchor] if anchor in ['DL','G1','PW2','TL','PW1'] else [],dependencies=dep,service_role='patrol',nominal_owner=rid,cycle_id=cycle,waypoint=k+1,energy_rate=0.)
   tasks[j]=phases(t,c);routes[rid].append(j)
 return tasks,routes
def normal_tasks():return cycle_tasks(0)
def phases(t,c):
 t=deepcopy(t);t.update(location=c['anchors'][t['anchor']][:2],entry_anchor=t['anchor'],clear_anchor=t['anchor'],approach=0.,egress=0.)
 if t['resources']:
  v=c['resource_phases'][t['resources'][0]];clear=c.get('normal_clear_overrides',{}).get(t.get('nominal_owner'),{}).get(t['anchor'],v['clear']);t.update(entry_anchor=v['entry'],clear_anchor=clear,approach=v['approach'],egress=max(v['egress'],c['tables']['event'][t['anchor']][clear]))
 return t
def event_tasks(view,now):
 c=config();out={}
 for t in view['tasks']:
  role=t['role'];j='E1_'+role;a={'verify':'V1','monitor':'M1','pickup':'G1','deliver':'H1'}[role];item=dict(kind=role,anchor=a,duration=None if role=='monitor' else {'verify':3.,'pickup':8.,'deliver':6.}[role],release=now,deadline=1800.,capabilities=t['capabilities'],resources=['G1'] if role=='pickup' else [],dependencies=['E1_'+v.split(':')[1] for v in t['completion_dependencies']],protocol_task_id=t['task_id'],protocol_revision=t['revision'],service_role=role,energy_rate=0.)
  if role=='monitor':item.update(minimum_duration=2.,start_deadline=now+360.)
  if role=='verify':item['start_deadline']=now+360.
  out[j]=phases(item,c)
 return out

def snapshot(c,tasks,plan,completed,states,now):
 prefixes={};sources={};known={j:q['end'] for j,q in completed.items()};locks=[];locked=set()
 for rid,s in states.items():
  j=s['job'];anchor=s['anchor'];ready=now+35.;schedule=[]
  if j:
   t=tasks[j];assert t['kind']!='monitor','No active-monitor replanning claimed by this no-disturbance loop';assert s['record']['job_id']==j
   rec=s['record'];start=max(plan['starts'][j],now+1.)
   if rec.get('service_started') is not None:start=rec['service_started']
   elif s['state'] in ['NAVIGATING','NAV_ACK','STABILIZING','HANDOFF_STOP','HEADING_ACK','HEADING_ACTIVE']:
    target=rec['target'];pose=s['pose'];remaining=math.hypot(target['x']-pose['x'],target['y']-pose['y'])/.22+12.
    if s['leg']=='entry':remaining+=t['approach']
    start=max(start,now+remaining)
   finish=rec.get('service_finished',max(start+t['duration']+1.,now+1.));finish=math.ceil(finish*100-1e-8)/100.;clear=math.ceil(max(finish+t['egress']+8.,now+8.)*100-1e-8)/100.;anchor=t['clear_anchor'];ready=max(ready,clear);locked.add(j);known[j]=clear
   schedule=[dict(job=j,owner=rid,service_finish_forecast=finish,clear_forecast=clear,clear_anchor=anchor)]
   for resource in t['resources']:locks.append(dict(resource=resource,start=rec.get('lease_granted_at',min(plan['starts'][j],start)-t['approach']),finish=clear,job=j))
  assert not s['cargo'],'This loop submits only before event pickup or after completed incident'
  sources[rid]=dict(source_anchor=anchor,ready=math.ceil(ready*100-1e-8)/100.);prefixes[rid]=dict(jobs=[j] if j else [],schedule=schedule,actual_job=j,record_task_id=s.get('record',{}).get('task_id') if j else None)
 return sources,known,locks,locked,prefixes

def problem(c,tasks,selected,completed,states,plan,now,event_at,stage):
 sources,known,locks,locked,prefixes=snapshot(c,tasks,plan,completed,states,now);selected=set(selected)-set(completed)-locked
 p=dict(time=now,horizon=c['horizon'],buffer=c['resource_buffer'],weights=deepcopy(c['weights']),robots={},tasks={j:deepcopy(tasks[j]) for j in sorted(selected)},events={},known_finishes=known,fixed_resources=[],blocked_resources=locks,reference=dict(owners={},starts={},routes={r:[] for r in c['robots']}),travel_times=deepcopy(c['tables']['event']),cargo_pairs=[],prefixes=prefixes,snapshot_states=states,stage=stage,actual_known_finishes={j:q['end'] for j,q in completed.items()})
 p['weights'].update(response=4.,shift=.05)
 for rid,src in sources.items():
  a=src['source_anchor'];p['robots'][rid]=dict(position=c['anchors'][a][:2],home=c['anchors'][a][:2],source_anchor=a,home_anchor=a,ready=src['ready'],energy=1.,capacity=1.,minimum=0.,speed=.22,move_rate=0.,idle_rate=0.,capabilities=c['capabilities'][rid])
 for rid in p['robots']:
  endpoint='END_'+rid;p['robots'][rid]['home_anchor']=endpoint
  for row in p['travel_times'].values():row[endpoint]=0.
 p['route_end_semantics']='open route: release at last physical clear, no virtual return navigation'
 for j,t in p['tasks'].items():
  for dep in t['dependencies']:assert dep in selected or dep in known,(j,dep)
  if t['kind']=='normal':
   rid=t['nominal_owner'];p['reference']['owners'][j]=rid;p['reference']['starts'][j]=plan['starts'].get(j,t['release']);p['reference']['routes'][rid].append(j)
 for rid in p['reference']['routes']:p['reference']['routes'][rid].sort(key=lambda j:(p['tasks'][j]['cycle_id'],p['tasks'][j]['waypoint']))
 if stage=='response':
  p['events']={'E1':dict(monitor='E1_monitor',pickup='E1_pickup',deliver='E1_deliver',observed_at=event_at)};p['cargo_pairs']=[['E1_pickup','E1_deliver']]
 return p
