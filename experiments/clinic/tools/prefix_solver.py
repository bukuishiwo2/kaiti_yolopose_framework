"""Independent prefix-aware MILP; the old aligned backend files remain unchanged."""
import json,re,os,hashlib,argparse
from pathlib import Path
from time import perf_counter
import aligned_solver as a
from prefix_contract import validate,impact_scope

class PrefixModel(a.Model):
    def pulp_model(self,scope):
        window=self.p.get('start_tolerance',0.) if scope['freeze_time'] else 0.
        effective=dict(scope,freeze_time=False) if window else scope
        model,variables=super().pulp_model(effective)
        if window:
            for j in set(self.p['reference']['owners'])-set(scope['free']):
                start=self.p['reference']['starts'][j]
                model+=variables['s_'+j]>=start-window
                model+=variables['s_'+j]<=start+window
        return model,variables

a.b.Model=PrefixModel;a.b.validate=validate;a.validate=validate;a.impact_scope=impact_scope

def full_warm(p,out,budget=25.):
    """Actually construct a feasible local seed then search all suffix variables.

    Total budget includes construction and warm-start model setup. Prefix promises
    are identical to local repair and cannot be reassigned in either strategy.
    """
    begin=perf_counter();deadline=begin+budget;out=Path(out);out.mkdir(parents=True,exist_ok=True)
    local=a.solve(p,'local_impact',out/'seed',budget)
    if local['status'] not in ['OPTIMAL','FEASIBLE_BUDGET']:return local
    seed_time=perf_counter()-begin;scope=dict(free=list(p['tasks']),freeze_time=False)
    source=Path(local['attempts'][-1]['cbc_logs'][-1]).parent/'independent_des-pulp.sol';raw={}
    for line in source.read_text().splitlines():
        parts=line.split()
        if len(parts)>=3 and re.fullmatch(r'X\d+',parts[1]):raw[int(parts[1][1:])]=float(parts[2])
    tpl=a.b.Model(p);model,v=tpl.pulp_model(scope);z={k:a.b.pulp.LpVariable(k,*tpl.bounds[k]) for k in tpl.outer}
    for row in tpl.rows:
        if any(k in tpl.outer for k in row.coefficients):model+=sum(c*(z[k] if k in z else v[k]) for k,c in row.coefficients.items())>=row.rhs,row.name
    model+=tpl.constant+sum(c*(z[k] if k in z else v[k]) for k,c in tpl.cost.items())
    variables=model.variables();assert len(variables)==len(raw) and set(raw)==set(range(len(variables)))
    values={x.name:raw[i] for i,x in enumerate(variables)}
    assert max(max(0.,row.rhs-sum(c*values[k] for k,c in row.coefficients.items())) for row in tpl.rows)<1e-5
    seed=a.b.reconstruct(p,values);assert validate(p,seed,scope,local['objective'])['passed']
    for variable in variables:variable.setInitialValue(values[variable.name])
    directory=(out/'full').resolve();directory.mkdir();log=directory/'cbc.log';previous=Path.cwd()
    if perf_counter()<deadline:
        try:
            os.chdir(directory);model.solve(a.b.pulp.PULP_CBC_CMD(msg=False,threads=0,gapRel=0,gapAbs=0,timeLimit=max(.1,deadline-perf_counter()),warmStart=True,keepFiles=True,options=['randomSeed 1','randomCbcSeed 1'],logPath=str(log)))
        finally:os.chdir(previous)
        raw_log=log.read_text();plan=a.b.reconstruct(p,{k:x.value() for k,x in {**v,**z}.items()});cost=float(a.b.pulp.value(model.objective));check=validate(p,plan,scope,cost)
        if check['passed'] and cost<=local['objective']+1e-5:
            status='OPTIMAL' if 'Result - Optimal solution found' in raw_log and model.sol_status==a.b.pulp.LpSolutionOptimal else 'FEASIBLE_BUDGET'
            result=dict(policy='full_warm',status=status,plan=plan,objective=cost,validation=check,attempts=[dict(scope=scope,kind='monolithic_warm',cbc_logs=[str(log)])],scope_expansions=0,impact=local['impact'],mip_start_accepted='MIPStart provided solution with cost' in raw_log,seed_seconds=seed_time,seed_objective=local['objective'],seed_scope=local['attempts'][-1]['scope'],seed_status=local['status'])
            bounds=re.findall(r'Lower bound:\s+([-+0-9.eE]+)',raw_log)
            if bounds:result['best_bound']=float(bounds[-1])+tpl.constant
            result['planning_seconds']=perf_counter()-begin;return result
    # A feasible seed is a full-domain incumbent, never a proof of global optimality.
    return dict(policy='full_warm',status='FEASIBLE_BUDGET',plan=seed,objective=local['objective'],validation=validate(p,seed,scope,local['objective']),attempts=[dict(scope=scope,kind='seed_fallback')],impact=local['impact'],seed_seconds=seed_time,seed_objective=local['objective'],seed_scope=local['attempts'][-1]['scope'],planning_seconds=perf_counter()-begin,mip_start_accepted=False)

def solve(p,policy,out,budget=25.):
    return full_warm(p,out,budget) if policy=='full_warm' else a.solve(p,policy,out,budget)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('input',type=Path);parser.add_argument('output',type=Path);parser.add_argument('--policy',default='local_impact');args=parser.parse_args()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    sources=[Path(__file__),Path(__file__).with_name('prefix_contract.py'),Path(__file__).with_name('aligned_solver.py'),Path(__file__).with_name('aligned_contract.py')]
    (args.output.parent/'solver_source_manifest.json').write_text(json.dumps({str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},indent=2))
    result=solve(json.loads(args.input.read_text()),args.policy,args.output.parent/'solver');args.output.write_text(json.dumps(result,indent=2));print(result['status'],result.get('objective'))
