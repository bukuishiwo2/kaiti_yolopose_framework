"""Offline mode/release-state and complete MILP witness gate, no ROS/Gazebo.
Witnesses transform frozen accepted snapshots; this is a feasibility gate,
not a simulated-navigation success or a new optimality claim.
"""
from pathlib import Path
import argparse,copy,hashlib,json,sys
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'tools')]
from support.clinic_runtime.experiment_modes import load_spec,select_cycle,release_time
from support.clinic_runtime.audits import validate
import dense_tasks as dt

def main(a):
 a.out.mkdir(exist_ok=False,parents=True);rows=[]
 for name in ['benchmark','standard','fast']:
  spec=load_spec(name);cfg=json.loads((ROOT/spec['base_scenario']).read_text());cfg['period_seconds']=spec['nominal_next_release'];dt.config=lambda:copy.deepcopy(cfg)
  tasks={};routes={}
  for k in [0,1]:
   ts,rs=select_cycle(*dt.cycle_tasks(k),k,spec);tasks.update(ts);routes[k]=rs
  assert len(tasks)==spec['expected_normal_services'];assert all(dep in tasks for t in tasks.values() for dep in t['dependencies'])
  for closed in [None,300.,630.,710.]:
   release=release_time(spec,closed)
   if name!='benchmark':assert (release==float('inf')) if closed is None else release>=closed+15.
  # Transform only future cycle tasks/releases; initial poses/service/ACK/navigation unchanged.
  for stage in ['00_normal','01_verify','02_response','03_active_repair']:
   src=ROOT/'runs/unified_bed_local_r1'/stage;p=json.loads((src/'problem.json').read_text());r=json.loads((src/'result.json').read_text());plan=copy.deepcopy(r['plan']);keep={j for j in p['tasks'] if not j.startswith('C1_') or j in tasks}
   p['tasks']={j:t for j,t in p['tasks'].items() if j in keep}
   for j,t in p['tasks'].items():
    if j.startswith('C1_'):t['release']=spec['nominal_next_release']
   for obj in [p['reference'],plan]:
    for key in ['owners','starts','finishes']:
     if key in obj:obj[key]={j:v for j,v in obj[key].items() if j in keep}
    obj['routes']={rid:[j for j in q if j in keep] for rid,q in obj['routes'].items()}
   scope=copy.deepcopy(r['scope']);scope['free']=[j for j in scope['free'] if j in keep]
   v=validate(p,plan,scope,None);assert v['passed'],(name,stage,v['errors'])
   cost=sum(v['objective_parts'].values());v=validate(p,plan,scope,cost);assert v['passed']
   dst=a.out/name/stage;dst.mkdir(parents=True);(dst/'witness.json').write_text(json.dumps(dict(problem=p,plan=plan,scope=scope,objective=cost,validation=v),indent=2))
   rows.append(dict(mode=name,stage=stage,passed=True,checks=v['checks'],tasks=len(p['tasks'])))
 (a.out/'summary.json').write_text(json.dumps(dict(passed=True,source_hashes={str(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in [ROOT/'support/clinic_runtime/experiment_modes.py',ROOT/'support/clinic_runtime/episode.py',ROOT/'support/clinic_runtime/audits.py']+list((ROOT/'config/clinic_modes').glob('*.json'))},milp_witnesses=rows,release_state_checks=12,task_and_dependency_checks=True,notes=['Transformed accepted snapshot witnesses, not yet actual mode navigation','Benchmark witness retains original release and task set','Fast/Standard may exceed requested target; no shortened service or simulated ACK']),indent=2));print('MODE_OFFLINE_GATE PASS',len(rows),'MILP witnesses')
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);main(p.parse_args())
