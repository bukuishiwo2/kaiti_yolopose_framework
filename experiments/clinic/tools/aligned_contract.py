"""Shared phase-aware time contract; no ROS or solver dependency."""
from pathlib import Path
import types
base=types.ModuleType('aligned_base_check');exec((Path(__file__).parent/'clinic_plan_check.py').read_text(),base.__dict__)
def tau(p,i,u,v):
 a=p['robots'][i]['source_anchor'] if u=='src' else p['tasks'][u].get('clear_anchor',p['tasks'][u]['anchor'])
 b=p['robots'][i]['home_anchor'] if v=='end' else p['tasks'][v].get('entry_anchor',p['tasks'][v]['anchor'])
 return (0. if u=='src' else p['tasks'][u].get('egress',0.))+float(p['travel_times'][a][b])+(0. if v=='end' else p['tasks'][v].get('approach',0.))
base.tau=tau

def occupancy(p,plan,j):
 t=p['tasks'][j];return [plan['starts'][j]-t.get('approach',0.),plan['finishes'][j]+t.get('egress',0.)]

def validate(p,plan,scope,claimed=None):
 v=base.validate(p,plan,scope,claimed);errors=v['errors']
 def ck(name,ok):
  v['checks']+=1
  if not ok:errors.append(dict(name=name,residual=1.))
 for j,t in p['tasks'].items():
  if t['kind']=='monitor' and t.get('deadline') is not None:ck('monitor_finish_deadline_'+j,plan['finishes'][j]<=t['deadline']+1e-5)
 for pick,drop in p.get('cargo_pairs',[]):
  route=plan['routes'][plan['owners'][pick]];ck('custody_'+pick,plan['owners'][pick]==plan['owners'][drop] and route.index(drop)==route.index(pick)+1)
 jobs=list(p['tasks'])
 for n,a in enumerate(jobs):
  for b in jobs[n+1:]:
   if set(p['tasks'][a]['resources'])&set(p['tasks'][b]['resources']):
    x,y=occupancy(p,plan,a),occupancy(p,plan,b);ck('full_occupancy_'+a+b,max(y[0]-x[1],x[0]-y[1])>=p['buffer']-1e-5)
 for lock in p.get('blocked_resources',[]):
  for j,t in p['tasks'].items():
   if lock['resource'] in t['resources']:
    x=occupancy(p,plan,j);ck('availability_'+j,x[1]+p['buffer']<=lock['start']+1e-5 or x[0]>=lock['finish']+p['buffer']-1e-5)
 v['passed']=not errors;return v

def impact_scope(p):
 """Actual-source failures and changed occupation intervals, then explicit forward closure."""
 ref=p['reference'];seeds={j:['new_task'] for j in p['tasks'] if j not in ref['owners']};edges={j:set() for j in p['tasks']}
 for rid,route in ref['routes'].items():
  route=[j for j in route if j in edges]
  if route:
   j=route[0];arrival=p['robots'][rid]['ready']+tau(p,rid,'src',j)
   if arrival>ref['starts'][j]+1e-5:seeds[j]=['actual_ready_or_source_infeasible']
  for u,v in zip(route,route[1:]):edges[u].add(v)
 for j,t in p['tasks'].items():
  for dep in t['dependencies']:
   if dep in edges:edges[dep].add(j)
  if j in ref['owners'] and not set(t['capabilities']).issubset(p['robots'][ref['owners'][j]]['capabilities']):seeds.setdefault(j,[]).append('owner_unavailable')
  for lock in p.get('blocked_resources',[]):
   if lock['resource'] in t['resources'] and j in ref['starts']:
    lo=ref['starts'][j]-t.get('approach',0.);hi=ref['finishes'][j]+t.get('egress',0.)
    if lo<lock['finish']+p['buffer'] and hi+p['buffer']>lock['start']:seeds.setdefault(j,[]).append('resource_availability_overlap')
 for resource in {r for t in p['tasks'].values() for r in t['resources']}:
  q=sorted([j for j,t in p['tasks'].items() if resource in t['resources'] and j in ref['starts']],key=lambda j:ref['starts'][j])
  for a,b in zip(q,q[1:]):edges[a].add(b)
 for a,b in p.get('cargo_pairs',[]):edges[a].add(b);edges[b].add(a)
 free=set(seeds);queue=list(free)
 while queue:
  for j in edges[queue.pop()]:
   if j not in free:free.add(j);queue.append(j)
 return dict(seeds=seeds,edges={j:sorted(q) for j,q in edges.items() if q},free=sorted(free),preserved=sorted(set(p['tasks'])-free))

def worker_ready_ack(ack,run_id,task_id,task,robot,ros_time):
 seen=ack.get('tasks',{}).get(task_id,{})
 return ack.get('run_id')==run_id and ros_time-ack.get('received_at',-100.)<5. and seen.get('state')=='READY' and seen.get('revision')==task['revision'] and seen.get('attempt')==task['attempt'] and seen.get('owner')==robot
