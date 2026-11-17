"""Isolated extension of the unchanged independent backend."""
from time import perf_counter
import clinic_milp_backend as b
from aligned_contract import tau,validate,impact_scope
Original=b.Model
class Model(Original):
 def _build(self):
  super()._build();p=self.p;M=5*p['horizon']+20
  for j,t in p['tasks'].items():
   if t['kind']=='monitor' and t.get('deadline') is not None:self.row('monitor_finish_deadline_'+j,{f'f_{j}':-1},-t['deadline'])
  for a,d in p.get('cargo_pairs',[]):
   for r in p['robots']:self.eq('cargo_'+r+a,{b.xk(r,a):1,b.xk(r,d):-1})
   self.eq('direct_'+a,{b.ak(r,a,d):1 for r in p['robots']},1.)
  for key,u,v,r in self.pairs:
   a,z=p['tasks'][u],p['tasks'][v]
   self.ge(key+'_full_u',{f's_{v}':1,f's_{u}':-1},a['duration']+a.get('egress',0.)+z.get('approach',0.)+p['buffer'],key,M)
   self.row(key+'_full_v',{f's_{u}':1,f's_{v}':-1,key:M},z['duration']+z.get('egress',0.)+a.get('approach',0.)+p['buffer'])
  for n,lock in enumerate(p.get('blocked_resources',[])):
   for j,t in p['tasks'].items():
    if lock['resource'] not in t['resources']:continue
    key=self.var('block_'+str(n)+j,0,1,binary=True)
    self.ge(key+'_after',{f's_{j}':1},lock['finish']+p['buffer']+t['approach'],key,M)
    self.row(key+'_before',{f's_{j}':-1,key:M},t['duration']+t['egress']+p['buffer']-lock['start'])
b.Model=Model;b.tau=tau;b.validate=validate

class ScopedSolver(b.Solver):
 """Accept only independently validated incumbents; retain the proof status."""
 def solve(self,p,scope,kind,deadline):
  if kind!='monolithic':return super().solve(p,scope,kind,deadline)
  import re,os
  from pathlib import Path
  begin=perf_counter();self.counter+=1;folder=Path(self.out).resolve()/f'budgeted_{self.counter:03d}';folder.mkdir(parents=True,exist_ok=True);tpl=b.Model(p);model,v=tpl.pulp_model(scope);z={k:b.pulp.LpVariable(k,*tpl.bounds[k]) for k in tpl.outer}
  for row in tpl.rows:
   if any(k in tpl.outer for k in row.coefficients):model+=sum(c*(z[k] if k in z else v[k]) for k,c in row.coefficients.items())>=row.rhs,row.name
  model+=tpl.constant+sum(c*(z[k] if k in z else v[k]) for k,c in tpl.cost.items());log=folder/'cbc.log';previous=Path.cwd()
  if deadline<=perf_counter():return dict(status='UNKNOWN_BUDGET',scope=scope,kind=kind,timing=dict(total=perf_counter()-begin))
  try:
   os.chdir(folder);model.solve(b.pulp.PULP_CBC_CMD(msg=False,threads=0,gapRel=0,gapAbs=0,timeLimit=max(.1,deadline-perf_counter()),keepFiles=True,options=['randomSeed 1','randomCbcSeed 1'],logPath=str(log)))
  finally:os.chdir(previous)
  raw=log.read_text();result=dict(status='INFEASIBLE' if model.status==b.pulp.LpStatusInfeasible and 'infeasible' in raw.lower() else 'UNKNOWN_BUDGET',scope=scope,kind=kind,cbc_logs=[str(log)],timing=dict(total=perf_counter()-begin));values={k:x.value() for k,x in {**v,**z}.items()}
  if all(x is not None for x in values.values()):
   try:
    plan=b.reconstruct(p,values);cost=float(b.pulp.value(model.objective));audit=validate(p,plan,scope,cost)
    if audit['passed']:result.update(status='OPTIMAL' if ('Result - Optimal solution found' in raw or 'Optimal objective' in raw) and model.sol_status==b.pulp.LpSolutionOptimal else 'FEASIBLE_BUDGET',plan=plan,objective=cost,validation=audit)
   except (KeyError,RuntimeError,StopIteration):pass
  bounds=re.findall(r'Lower bound:\s+([-+0-9.eE]+)',raw)
  if bounds:result.update(best_bound=float(bounds[-1])+tpl.constant,cbc_bound_without_constant=float(bounds[-1]),objective_constant=tpl.constant)
  if result.get('objective') is not None and result.get('best_bound') is not None:result['relative_gap']=max(0.,(result['objective']-result['best_bound'])/max(1.,abs(result['objective'])))
  result['timing']['total']=perf_counter()-begin;return result

def solve(p,policy,out,budget=25.,kind='monolithic'):
 begin=perf_counter();solver=ScopedSolver(out);impact=impact_scope(p) if policy=='local_impact' else None
 if policy=='full_replan':scopes=[dict(free=list(p['tasks']),freeze_time=False)]
 elif policy=='local_impact':
  scopes=[dict(free=impact['free'],freeze_time=True)]
  remaining=sorted(set(p['tasks'])-set(impact['free']),key=lambda j:p['reference']['starts'][j]);free=set(impact['free'])
  for j in remaining:free.add(j);scopes.append(dict(free=sorted(free),freeze_time=True))
  scopes.append(dict(free=list(p['tasks']),freeze_time=False))
 else:scopes=b.policy_stages(p,'local_repair' if policy=='local_repair' else 'retained_milp')
 attempts=[]
 for scope in scopes:
  q=solver.solve(p,scope,kind,begin+budget);attempts.append(q)
  if q['status'] in ['OPTIMAL','FEASIBLE_BUDGET']:
   return dict(policy=policy,status=q['status'],plan=q['plan'],objective=q['objective'],validation=q['validation'],best_bound=q.get('best_bound'),relative_gap=q.get('relative_gap'),attempts=attempts,impact=impact,scope_expansions=len(attempts)-1,planning_seconds=perf_counter()-begin)
  if q['status']!='INFEASIBLE':break
 return dict(policy=policy,status=attempts[-1]['status'],attempts=attempts,impact=impact,planning_seconds=perf_counter()-begin)
if __name__=='__main__':
 import argparse,json
 from pathlib import Path
 a=argparse.ArgumentParser();a.add_argument('input',type=Path);a.add_argument('output',type=Path);a.add_argument('--policy',default='retained_milp');v=a.parse_args();import hashlib
 sources=[Path(__file__),Path(__file__).with_name('aligned_contract.py'),Path(__file__).with_name('clinic_milp_backend.py')];(v.output.parent/'solver_source_manifest.json').write_text(json.dumps({str(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in sources},indent=2));r=solve(json.loads(v.input.read_text()),v.policy,v.output.parent/'solver');v.output.write_text(json.dumps(r,indent=2));print(r['status'],r.get('objective'))
