"""Independent warm-start wrapper; reuse the original MILP and impact closure.

Both policies first retime the same retained ownership/routes. The incumbent is
then offered to a genuine CBC search over the selected scope, within one budget.
"""
import argparse,json,re,os
from pathlib import Path
from time import perf_counter
import prefix_solver as old
from bed_contract import validate,impact_scope
b=old.a.b
old.a.validate=validate;b.validate=validate;old.validate=validate


def solve(p,policy,out,budget=25.):
 begin=perf_counter();deadline=begin+budget;out=Path(out);out.mkdir(parents=True,exist_ok=True)
 impact=impact_scope(p);scope=dict(free=impact['free'] if policy=='local_impact' else list(p['tasks']),freeze_time=policy=='local_impact')
 # The shared retiming seed also respects the local policy's retained start window.
 held=set(p['reference']['owners'])-set(impact['free'])
 class SeedModel(old.PrefixModel):
  def pulp_model(self,s):
   model,v=super().pulp_model(s)
   for j in held:
    start=p['reference']['starts'][j];window=p.get('start_tolerance',0.)
    model+=v['s_'+j]>=start-window;model+=v['s_'+j]<=start+window
   return model,v
 b.Model=SeedModel
 seed=old.a.ScopedSolver(out/'seed').solve(p,dict(free=[],freeze_time=False),'monolithic',min(deadline,begin+5.))
 b.Model=old.PrefixModel
 if seed['status'] not in ['OPTIMAL','FEASIBLE_BUDGET']:
  return dict(policy=policy,status=seed['status'],attempts=[seed],impact=impact,planning_seconds=perf_counter()-begin,scope=scope)
 seed_scope_check=validate(p,seed['plan'],scope,seed['objective']);assert seed_scope_check['passed'],seed_scope_check
 source=Path(seed['cbc_logs'][-1]).parent/'independent_des-pulp.sol';raw={}
 for line in source.read_text().splitlines():
  parts=line.split()
  if len(parts)>=3 and re.fullmatch(r'X\d+',parts[1]):raw[int(parts[1][1:])]=float(parts[2])
 tpl=b.Model(p);model,v=tpl.pulp_model(scope);z={k:b.pulp.LpVariable(k,*tpl.bounds[k]) for k in tpl.outer}
 for row in tpl.rows:
  if any(k in tpl.outer for k in row.coefficients):model+=sum(c*(z[k] if k in z else v[k]) for k,c in row.coefficients.items())>=row.rhs,row.name
 model+=tpl.constant+sum(c*(z[k] if k in z else v[k]) for k,c in tpl.cost.items())
 variables=model.variables();assert len(variables)==len(raw)
 values={x.name:raw[i] for i,x in enumerate(variables)}
 # CBC text output can contain signed round-off at a bound. Normalize only
 # within 1e-7, then recheck every original row before offering MIPStart.
 for variable in variables:
  value=values[variable.name]
  if variable.lowBound is not None and value<variable.lowBound:
   assert variable.lowBound-value<=1e-7,(variable.name,value,variable.lowBound)
   values[variable.name]=variable.lowBound
  if variable.upBound is not None and value>variable.upBound:
   assert value-variable.upBound<=1e-7,(variable.name,value,variable.upBound)
   values[variable.name]=variable.upBound
 assert max(max(0.,row.rhs-sum(c*values[k] for k,c in row.coefficients.items())) for row in tpl.rows)<1e-5
 for variable in variables:variable.setInitialValue(values[variable.name])
 seed_time=perf_counter()-begin;directory=(out/'search').resolve();directory.mkdir();log=directory/'cbc.log';previous=Path.cwd()
 try:
  os.chdir(directory);model.solve(b.pulp.PULP_CBC_CMD(msg=False,threads=0,gapRel=0,gapAbs=0,timeLimit=max(.1,deadline-perf_counter()),warmStart=True,keepFiles=True,options=['randomSeed 1','randomCbcSeed 1'],logPath=str(log)))
 finally:os.chdir(previous)
 raw_log=log.read_text();plan=b.reconstruct(p,{k:x.value() for k,x in {**v,**z}.items()});cost=float(b.pulp.value(model.objective));check=validate(p,plan,scope,cost)
 accepted='MIPStart provided solution with cost' in raw_log
 result=dict(policy=policy,status='FEASIBLE_BUDGET',plan=seed['plan'],objective=seed['objective'],validation=seed_scope_check,attempts=[dict(scope=scope,kind='monolithic_warm',cbc_logs=[str(log)])],impact=impact,scope=scope,scope_expansions=0,mip_start_accepted=accepted,seed_seconds=seed_time,seed_objective=seed['objective'],seed_scope=seed['scope'],seed_status=seed['status'],seed_attempt=seed)
 if check['passed'] and cost<=seed['objective']+1e-5:result.update(plan=plan,objective=cost,validation=check,status='OPTIMAL' if 'Result - Optimal solution found' in raw_log and model.sol_status==b.pulp.LpSolutionOptimal else 'FEASIBLE_BUDGET')
 else:result['incumbent_fallback']=True
 bounds=re.findall(r'Lower bound:\s+([-+0-9.eE]+)',raw_log)
 if bounds:result['best_bound']=float(bounds[-1])+tpl.constant
 result['planning_seconds']=perf_counter()-begin;return result

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('input',type=Path);p.add_argument('output',type=Path);p.add_argument('--policy',choices=['local_impact','full_warm'],required=True);p.add_argument('--budget',type=float,default=25.);a=p.parse_args();problem=json.loads(a.input.read_text());result=solve(problem,a.policy,a.output.parent/(a.output.stem+'_solver'),a.budget);a.output.write_text(json.dumps(result,indent=2));print(result['status'],result.get('objective'))
