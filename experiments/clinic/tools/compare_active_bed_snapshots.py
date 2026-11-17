"""Same immutable actual snapshot and separately labeled seeded ETA perturbations."""
from pathlib import Path
import argparse,json,hashlib,subprocess,time,random
from bed_contract import validate
ROOT=Path(__file__).resolve().parents[1];p=argparse.ArgumentParser();p.add_argument('--name',required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--rounds',type=int,default=3);p.add_argument('--seeds',type=int,default=10);a=p.parse_args();a.out.mkdir(exist_ok=False);rows=[];status=a.out/'status.json';status.write_text(json.dumps(dict(state='WAITING_FOR_REAL_SNAPSHOT')))
while True:
 files=sorted((ROOT/'runs'/a.name).glob('*_active_repair/problem.json'))
 if files:break
 state=ROOT/'verification/active_bed_2026-11-16'/a.name/'status.json'
 if state.exists() and json.loads(state.read_text())['status']=='FAILED':raise RuntimeError('Physical run failed before captured repair')
 time.sleep(2)
original=files[0];base=json.loads(original.read_text());cases=[]
for n in range(a.rounds):cases.append((f'actual_repeat_{n}',base,n,'same actual captured snapshot'))
for seed in range(a.seeds):
 q=json.loads(json.dumps(base));extra=round(random.Random(20261116+seed).uniform(0,15),2);cov=q['coverage_projection'];cov['delivery_finish']+=extra;cov['monitor_release']+=extra
 for rid,pre in q['active_commitments'].items():
  pre['ready']+=extra;pre['schedule'][0]['clear_forecast']+=extra;pre['schedule'][0]['service_finish_forecast']+=extra;q['robots'][rid]['ready']+=extra
  j=pre['jobs'][0];q['known_finishes'][j]+=extra;q['committed_finishes'][j]+=extra
 # Prefix dictionary is serialized separately after load; keep the same joint promise.
 for rid,pre in q['active_commitments'].items():q['prefixes'][rid]=pre
 q['offline_synthetic_eta_perturbation']=dict(seed=20261116+seed,extra=extra);cases.append((f'synthetic_{seed:02d}',q,seed,'offline synthetic ETA uncertainty, not Gazebo stability trial'))
for label,problem,n,scope_note in cases:
 for policy in (['local_impact','full_warm'] if n%2==0 else ['full_warm','local_impact']):
  folder=a.out/label/policy;folder.mkdir(parents=True);inp=folder/'problem.json';inp.write_text(json.dumps(problem,indent=2));out=folder/'result.json';begin=time.perf_counter();code=subprocess.run(['/home/yhc/kaiti_yolopose_framework/.venv/bin/python',str(ROOT/'tools/bed_solver.py'),str(inp),str(out),'--policy',policy],stdout=(folder/'worker.log').open('w'),stderr=subprocess.STDOUT).returncode;r=json.loads(out.read_text()) if out.exists() else dict(status='PROCESS_FAILED');usable=code==0 and r['status'] in ['OPTIMAL','FEASIBLE_BUDGET'];check=validate(problem,r['plan'],r['scope'],r['objective']) if usable else dict(passed=False);row=dict(case=label,kind=scope_note,policy=policy,status=r['status'],passed=usable and check['passed'],wall=time.perf_counter()-begin,objective=r.get('objective'),scope=r.get('scope'),suffix_jobs=len(problem['tasks']),mip_start_accepted=r.get('mip_start_accepted'),input_sha256=hashlib.sha256(inp.read_bytes()).hexdigest(),validation=check)
  if usable:
   row.update(owner_changes=sum(r['plan']['owners'][j]!=v for j,v in problem['reference']['owners'].items()),absolute_start_shift=sum(abs(r['plan']['starts'][j]-v) for j,v in problem['reference']['starts'].items()))
  rows.append(row);status.write_text(json.dumps(dict(state='RUNNING',completed=len(rows),total=2*len(cases)),indent=2));(a.out/'results_partial.json').write_text(json.dumps(rows,indent=2));print(label,policy,row['status'],row.get('objective'),round(row['wall'],3),flush=True)
summary=dict(passed=all(x['passed'] for x in rows),source=str(original),source_sha256=hashlib.sha256(original.read_bytes()).hexdigest(),rows=rows,actual_pairs=a.rounds,synthetic_pairs=a.seeds,note='Each pair has identical problem/weights/hard commitments. Synthetic ETA cases are not 10 physical seeds. FEASIBLE_BUDGET is no optimality proof; all failures retained. Both25s budgets include a common retained-route retiming seed capped at5s, followed by genuine scoped CBC warm-start search.')
(a.out/'summary.json').write_text(json.dumps(summary,indent=2));status.write_text(json.dumps(dict(state='COMPLETE',passed=summary['passed'],completed=len(rows)),indent=2))
