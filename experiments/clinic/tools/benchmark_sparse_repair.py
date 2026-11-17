"""Independent seeded sparse-impact paired study; frozen bed_solver is reused verbatim.
First feasible means a complete validated incumbent available to the wrapper,
not CBC's internal discovery timestamp or a plan committed to real robots.
"""
from pathlib import Path
import argparse,copy,hashlib,json,random,statistics,subprocess,sys,time,traceback
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from bed_contract import validate,impact_scope
from aligned_contract import tau

def write(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,indent=2))
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def instance(base,seed,n,kind):
 rng=random.Random(seed);p=copy.deepcopy(base);p.update(tasks={},events={},cargo_pairs=[],blocked_resources=[],fixed_resources=[],reference=dict(owners={},starts={},finishes={},routes={r:[] for r in base['robots']},ends={},energy_end={r:1. for r in base['robots']}))
 p['horizon']=5000.;p['time']=base['time'];p['offline_case']=dict(seed=seed,tasks_per_robot=n,disturbance=kind,synthetic=True)
 # Active monitor/custody metadata is retained; suffix tasks depend on projected releases.
 for rid,rob in p['robots'].items():
  prev='src';end=rob['ready']+40.;route=p['reference']['routes'][rid]
  for k in range(n):
   j=f'N_{rid}_{k}';anchor=rng.choice(['PW1','PW2','TL','DL','G1']);deps=route[-1:]
   # Shared resource spans robots, but forward edges end before the disturbed tail.
   resource='COMMON' if k==0 else f'LANE_{rid}'
   t=dict(kind='normal',anchor=anchor,entry_anchor=anchor,clear_anchor=anchor,location=[0.,0.],duration=float(rng.randint(3,8)),approach=0.,egress=0.,release=p['time'],deadline=4500.,resources=[resource],dependencies=deps,capabilities=['move'],energy_rate=0.,nominal_owner=rid)
   p['tasks'][j]=t;start=end+tau(p,rid,prev,j)+rng.randint(4,10)
   if k==0:start+=list(p['robots']).index(rid)*240.
   # Resource COMMON serial admission; later route resources are per-robot.
   for other,ot in p['tasks'].items():
    if other!=j and resource in ot['resources'] and other in p['reference']['finishes']:start=max(start,p['reference']['finishes'][other]+p['buffer']+5.)
   p['reference']['owners'][j]=rid;p['reference']['starts'][j]=round(start,2);end=round(start+t['duration'],2);p['reference']['finishes'][j]=end;route.append(j);prev=j
  p['reference']['ends'][rid]=end+tau(p,rid,prev,'end')
 # Both kinds cause a real model violation, with no future disturbance supplied to baseline.
 baseline=copy.deepcopy(p);check=validate(baseline,baseline['reference'],dict(free=list(p['tasks']),freeze_time=False));assert check['passed'],check
 if kind=='tail_resource':
  j=p['reference']['routes']['r2'][-1];resource='TAIL_BLOCK';p['tasks'][j]['resources']=[resource];s=p['reference']['starts'][j];p['blocked_resources']=[dict(resource=resource,start=s-1.,finish=s+rng.randint(20,65),change_id='observed_bed_extension')]
 else:
  j=p['reference']['routes']['r3'][0];p['robots']['r3']['ready']=p['reference']['starts'][j]+rng.randint(20,60)
  # Projected prefix release and its source are adjusted consistently.
  if 'r3' in p.get('active_commitments',{}):
   for key in ['active_commitments','prefixes']:
    p[key]['r3']['ready']=p['robots']['r3']['ready'];p[key]['r3']['schedule'][0]['clear_forecast']=p['robots']['r3']['ready'];p[key]['r3']['schedule'][0]['service_finish_forecast']=p['robots']['r3']['ready']
   p['known_finishes']['E1_monitor']=p['robots']['r3']['ready'];p['committed_finishes']['E1_monitor']=p['robots']['r3']['ready'];p['coverage_projection']['monitor_release']=p['robots']['r3']['ready']
 impact=impact_scope(p);assert 0<len(impact['free'])/len(p['tasks'])<=1/3+1e-6
 invalid=validate(p,p['reference'],dict(free=list(p['tasks']),freeze_time=False));assert not invalid['passed']
 return p,dict(baseline=check,old_plan_invalid=invalid,impact=impact)

def worker(args):
 import bed_solver as solver
 import signal,psutil
 p=json.loads(args.input.read_text());start=time.perf_counter();first=[];seeds=[];original=solver.old.a.ScopedSolver.solve
 def observed(self,*a,**kw):
  r=original(self,*a,**kw)
  if not first and r.get('plan') and validate(p,r['plan'],r['scope'],r['objective'])['passed']:
   seeds.append(copy.deepcopy(r))
   first.append(dict(seconds=time.perf_counter()-start,objective=r['objective'],definition='validated seed available to wrapper, includes model/solve/verification',plan_sha256=hashlib.sha256(json.dumps(r['plan'],sort_keys=True).encode()).hexdigest()))
  return r
 solver.old.a.ScopedSolver.solve=observed
 def deadline(signum,frame):raise TimeoutError('Independent equal wall deadline')
 signal.signal(signal.SIGALRM,deadline);signal.setitimer(signal.ITIMER_REAL,args.budget)
 try:
  r=solver.solve(p,args.policy,args.output.parent/'solver',args.budget);r['first_feasible']=first[0] if first else None;r['worker_wall']=time.perf_counter()-start;write(args.output,r)
 except TimeoutError:
  for child in psutil.Process().children(recursive=True):
   try:child.kill()
   except psutil.NoSuchProcess:pass
  if not seeds:r=dict(status='NO_FEASIBLE_INCUMBENT')
  else:
   s=seeds[0];impact=impact_scope(p);scope=dict(free=impact['free'] if args.policy=='local_impact' else list(p['tasks']),freeze_time=args.policy=='local_impact');check=validate(p,s['plan'],scope,s['objective']);assert check['passed']
   r=dict(status='FEASIBLE_BUDGET',plan=s['plan'],objective=s['objective'],scope=scope,validation=check,planning_seconds=time.perf_counter()-start,deadline_fallback=True,mip_start_accepted=any('MIPStart provided solution with cost' in x.read_text(errors='replace') for x in (args.output.parent/'solver/search').glob('*.log')))
  r.update(first_feasible=first[0] if first else None,worker_wall=time.perf_counter()-start);write(args.output,r)
 except Exception as e:
  write(args.output,dict(status='ERROR',error=repr(e),traceback=traceback.format_exc(),first_feasible=first[0] if first else None,worker_wall=time.perf_counter()-start));raise
 finally:signal.setitimer(signal.ITIMER_REAL,0.)

def main(a):
 if a.worker:return worker(a)
 a.out.mkdir(parents=True,exist_ok=False);base=json.loads(a.source.read_text());rows=[]
 manifest={str(x):digest(x) for x in [Path(__file__),ROOT/'tools/bed_solver.py',ROOT/'tools/bed_contract.py',ROOT/'tools/prefix_solver.py',ROOT/'tools/prefix_contract.py',ROOT/'tools/aligned_contract.py',ROOT/'tools/clinic_milp_backend.py']};write(a.out/'source_manifest.json',manifest)
 (a.out/'sources').mkdir()
 for n,src in enumerate(manifest):(a.out/'sources'/f'{n}_{Path(src).name}').write_bytes(Path(src).read_bytes())
 for case in range(a.cases):
  seed=2026111700+case;n=[3,4,5][case%3];kind=['tail_resource','source_delay'][case%2];p,design=instance(base,seed,n,kind);folder=a.out/f'case_{case:02d}';write(folder/'design.json',design)
  for policy in (['local_impact','full_warm'] if case%2==0 else ['full_warm','local_impact']):
   dst=folder/policy;write(dst/'problem.json',p);begin=time.perf_counter()
   with (dst/'worker.log').open('w') as log:
    proc=subprocess.run([sys.executable,str(Path(__file__)),'--worker','--input',str(dst/'problem.json'),'--output',str(dst/'result.json'),'--policy',policy,'--budget',str(a.budget)],stdout=log,stderr=subprocess.STDOUT,timeout=a.budget+30.)
   r=json.loads((dst/'result.json').read_text());usable=r.get('status') in ['OPTIMAL','FEASIBLE_BUDGET'];check=validate(p,r['plan'],r['scope'],r['objective']) if usable else dict(passed=False)
   row=dict(case=case,seed=seed,kind=kind,tasks=len(p['tasks']),free=len(design['impact']['free']),policy=policy,budget=a.budget,input_sha256=digest(dst/'problem.json'),exit=proc.returncode,status=r['status'],passed=usable and check['passed'],first_feasible=r.get('first_feasible'),solver_seconds=r.get('planning_seconds'),process_wall=time.perf_counter()-begin,validation=check,mip_start=r.get('mip_start_accepted'),hard_wall_deadline=True,deadline_fallback=r.get('deadline_fallback',False))
   if usable:row.update(objective=r['objective'],owner_changes=sum(r['plan']['owners'][j]!=rid for j,rid in p['reference']['owners'].items()),start_shift=sum(abs(r['plan']['starts'][j]-s) for j,s in p['reference']['starts'].items()),adjacency_cost=check['objective_parts']['adjacency'])
   rows.append(row);write(a.out/'rows.json',rows);write(a.out/'status.json',dict(state='RUNNING',completed=len(rows),total=2*a.cases));print(f'CASE {case:02d} {policy} {row["status"]} valid={row["passed"]}',flush=True)
   if proc.returncode!=0 or not row['passed']:
    write(a.out/'failure.json',dict(case=case,policy=policy,row=row,action='STOP; diagnose before any further pair'));return 1
  pair=rows[-2:];assert pair[0]['input_sha256']==pair[1]['input_sha256'];assert pair[0]['first_feasible']['plan_sha256']==pair[1]['first_feasible']['plan_sha256']
 stats={}
 for pol in ['local_impact','full_warm']:
  rr=[r for r in rows if r['policy']==pol];stats[pol]=dict(cases=len(rr),recovered=sum(r['passed'] for r in rr),median_first_feasible=statistics.median(r['first_feasible']['seconds'] for r in rr),median_solver_seconds=statistics.median(r['solver_seconds'] for r in rr),median_process_wall=statistics.median(r['process_wall'] for r in rr),mean_owner_changes=statistics.mean(r['owner_changes'] for r in rr),mean_start_shift=statistics.mean(r['start_shift'] for r in rr))
 write(a.out/'summary.json',dict(passed=all(r['passed'] for r in rows),rows=rows,stats=stats,source_snapshot=str(a.source),source_sha256=digest(a.source),synthetic=True,notes=['Independent synthetic sparse-impact task snapshots using frozen Clinic travel priors; not physical stability trials.','First feasible is validated common seed availability, not CBC internal first discovery.','No energy/charge claims; active monitor/custody are projected external commitments.','Independent5s wall deadline; child solve is killed and validated seed returned on expiry; bookkeeping overhead recorded.']))
 write(a.out/'status.json',dict(state='COMPLETE',passed=True,completed=len(rows)));return 0
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--worker',action='store_true');p.add_argument('--input',type=Path);p.add_argument('--output',type=Path);p.add_argument('--policy');p.add_argument('--out',type=Path);p.add_argument('--source',type=Path,default=ROOT/'runs/unified_bed_local_r1/03_active_repair/problem.json');p.add_argument('--budget',type=float,default=5.);p.add_argument('--cases',type=int,default=12);a=p.parse_args();raise SystemExit(main(a))
