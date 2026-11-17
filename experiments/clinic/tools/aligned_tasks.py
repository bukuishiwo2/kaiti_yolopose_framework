from pathlib import Path
import json
from copy import deepcopy
import hospital_tasks as old
ROOT=old.ROOT
PARKING_VARIANT='original'
def config():
 c=json.loads((ROOT/'config/hospital_aligned/scenario.json').read_text())
 if PARKING_VARIANT=='separate_bays':c['homes'].update(r2='PDR',r3='PR')
 return c
def normal_tasks():return old.normal_tasks()
def add_phases(p):
 c=config()
 for j,t in p['tasks'].items():
  t.update(entry_anchor=t['anchor'],clear_anchor=t['anchor'],approach=0.,egress=0.)
  if t['resources']:
   r=t['resources'][0];v=c['resource_phases'][r];bootstrap=j.endswith('_N0');t.update(entry_anchor=r if bootstrap else v['entry'],clear_anchor=v['clear'],approach=0. if bootstrap else v['approach'],egress=v['egress'])
 p['buffer']=c['resource_buffer'];p['blocked_resources']=[]
 return p

def problem(sources,reference,completed,protocol_view,now,stage):
 c=config();old.config=config
 if stage=='normal_plan':
  p=old.problem(sources,reference,completed,dict(tasks=[],completed_facts=[]),now,'response_plan');p['events']={};p['cargo_pairs']=[['r2_N0','r2_N1'],['r2_N2','r2_N3']]
 else:p=old.problem(sources,reference,completed,protocol_view,now,stage)
 p['travel_times']=c['tables']['normal' if stage=='normal_plan' else 'event']
 p['planning_guard_seconds']=30. if stage=='response_plan' else 12.
 for rid,v in p['robots'].items():v['ready']=now+p['planning_guard_seconds']
 if not any('E1_'+j in p['tasks'] for j in ['monitor','pickup','deliver']):p['events']={}
 p['cargo_pairs']=[pair for pair in p['cargo_pairs'] if all(j in p['tasks'] for j in pair)]
 return add_phases(p)
