"""Normal hospital itinerary and joint-MILP input, separate from old scenario."""
from pathlib import Path
from copy import deepcopy
import json
ROOT=Path(__file__).resolve().parents[1]
def config():return json.loads((ROOT/'config/hospital_execution/scenario.json').read_text())
def normal_tasks():
 tasks={};routes={}
 for rid,sequence in [('r1',['DL','PW2','TL','PW1','DL']),('r3',['DR','PW3','PR','TR','PW7','DR']),('r2',['G1','DL','G1','DR','G1'])]:
  route=[]
  for k,anchor in enumerate(sequence):
   jid=f'{rid}_N{k}';role='patrol' if rid!='r2' else ['routine_pickup','routine_drop','routine_pickup','routine_drop','routine_ready'][k];duration=5. if rid!='r2' else [15.,10.,15.,10.,1.][k]
   task=dict(kind='normal',anchor=anchor,duration=duration,capabilities=['move'],release=0.,deadline=2000.,resources=[anchor] if anchor in ['G1','DL','DR'] else [],dependencies=route[-1:],service_role=role,nominal_owner=rid)
   if rid=='r2' and k<4:task.update(cargo_group='W' if k<2 else 'E',cargo_role='pickup' if k%2==0 else 'drop')
   tasks[jid]=task;route.append(jid)
  routes[rid]=route
 return tasks,routes

def problem(sources,reference,completed,protocol_view,now,stage):
 c=config();tasks,_=normal_tasks();p=dict(time=round(now,2),horizon=c['horizon'],buffer=1.,weights=deepcopy(c['weights']),robots={},tasks={},events={},known_finishes={j:r['service_finished'] for j,r in completed.items()},fixed_resources=[],reference=deepcopy(reference),travel_times=c['tables']['event'],cargo_pairs=[])
 for rid,anchor in sources.items():
  p['robots'][rid]=dict(position=c['anchors'][anchor][:2],home=c['anchors'][c['homes'][rid]][:2],source_anchor=anchor,home_anchor=c['homes'][rid],ready=now+5.,energy=1.,capacity=1.,minimum=0.,speed=.22,move_rate=0.,idle_rate=0.,capabilities=c['capabilities'][rid])
 if stage=='response_plan':
  for jid,t in tasks.items():
   if jid not in completed:p['tasks'][jid]=deepcopy(t)
  if all(j in p['tasks'] for j in ['r2_N2','r2_N3']):p['cargo_pairs'].append(['r2_N2','r2_N3'])
 else:p['reference']=dict(owners={},starts={},routes={r:[] for r in sources})
 for t in protocol_view['completed_facts']:p['known_finishes']['E1_'+t['role']]=t['finished_at']
 for t in protocol_view['tasks']:
  role=t['role'];anchor={'verify':'V1','monitor':'M1','pickup':'G1','deliver':'H1'}[role];jid='E1_'+role
  assert t['target']['xy']==c['anchors'][anchor][:2]
  item=dict(kind=role,anchor=anchor,duration=None if role=='monitor' else 3.,release=now,deadline=2200.,capabilities=t['capabilities'],resources=['G1'] if role=='pickup' else [],dependencies=['E1_'+x.split(':')[1] for x in t['completion_dependencies']],protocol_task_id=t['task_id'],protocol_revision=t['revision'],service_role=role)
  if role=='verify':item['start_deadline']=now+90.
  if role=='monitor':item.update(minimum_duration=2.,start_deadline=now+120.)
  p['tasks'][jid]=item
 for jid,t in p['tasks'].items():t.update(location=c['anchors'][t['anchor']][:2],energy_rate=0.)
 if stage=='response_plan':
  p['events']['E1']=dict(monitor='E1_monitor',pickup='E1_pickup',deliver='E1_deliver',observed_at=15.);p['cargo_pairs'].append(['E1_pickup','E1_deliver'])
 p['_scope_note']='verification-only assignment with routine backlog held' if stage=='verify_plan' else 'joint routine/event allocation and scheduling; idle actual sources, custody pair constraints'
 return p
