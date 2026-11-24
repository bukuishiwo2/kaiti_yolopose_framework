#!/usr/bin/env python3
"""Independent task-level ablation; unchanged deployed Clinic MILP/impact code.

Synthetic travel is NOT a Clinic navigation certificate. No ROS or robot action.
The deployed bed wrapper and a seed-gate-free diagnostic are separate policies.
"""
import argparse
from copy import deepcopy
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import random
import re
import signal
import statistics
import subprocess
import sys
import time

P=Path(__file__).resolve().parents[1]
W=Path('/home/yhc/clinic_planning_ws')
sys.path.insert(0,str(W/'tools'))
import prefix_solver as native
import bed_contract as contract

POLICIES=('fixed_structure','fixed_owner','full_warm','local_current','local_no_seed_gate')
FAMILIES=('T','L','P','G')
OK={'OPTIMAL','FEASIBLE_BUDGET'}


def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2))


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def make_case(family,seed,count):
    """Predefined mechanisms, not selected after seeing solver outcomes."""
    assert family in FAMILIES and count%3==0 and count>=6
    rng=random.Random(seed);m=count//3
    coupled_duration=float(rng.randint(3,6))+.01*(seed%97)
    anchors={f'H{i}':float(i*4) for i in range(3)}
    if family=='G':anchors={a:0. for a in anchors}
    travel={a:{b:abs(x-y) for b,y in anchors.items()} for a,x in anchors.items()}
    for row in travel.values():row.update({f'END_r{i}':0. for i in range(3)})
    robots={f'r{i}':dict(position=[anchors[f'H{i}'],0.],home=[anchors[f'H{i}'],0.],
        source_anchor=f'H{i}',home_anchor=f'END_r{i}',ready=0.,energy=1.,capacity=1.,minimum=0.,
        speed=1.,move_rate=0.,idle_rate=0.,capabilities=['move',f'lane{i}']+(['lift'] if i<2 else [])) for i in range(3)}
    p=dict(time=0.,horizon=600.,buffer=1.,weights=deepcopy(native.a.b.WEIGHTS),robots=robots,
        tasks={},events={},cargo_pairs=[],known_finishes={},fixed_resources=[],blocked_resources=[],
        travel_times=travel,start_tolerance=2.,reference=dict(owners={},starts={},finishes={},routes={r:[] for r in robots},ends={},energy_end={r:1. for r in robots}))
    ref=p['reference']
    for k in range(m):
        for i in range(3):
            j=f'N{i}_{k}';rid=f'r{i}';prev=f'N{i}_{k-1}'
            deps=[prev] if k else []
            if family=='P' and i:deps.append(f'N{i-1}_{k}')
            duration=coupled_duration if family=='G' else float(rng.randint(3,6))
            # Unaffected tasks remain genuinely exchangeable. Unique lane
            # abilities would presolve away full assignment search and give a
            # misleading scope-size benchmark.
            capabilities=['move']
            if i==0 and (family=='G' or family=='L' and k==m-1):capabilities=['move','lift']
            task=dict(kind='normal',anchor=f'H{i}',entry_anchor=f'H{i}',clear_anchor=f'H{i}',
                location=[anchors[f'H{i}'],0.],duration=duration,approach=0.,egress=0.,release=0.,deadline=500.,
                resources=[],dependencies=deps,capabilities=capabilities,energy_rate=0.,nominal_owner=rid)
            p['tasks'][j]=task
            start=max([1.]+[ref['finishes'][d]+1. for d in deps])
            if k:start=max(start,ref['finishes'][prev]+1.)
            ref['owners'][j]=rid;ref['starts'][j]=start;ref['finishes'][j]=start+duration;ref['routes'][rid].append(j)
    if family=='G':
        for k in range(m):p['tasks'][f'N0_{k}']['deadline']=ref['finishes'][f'N0_{k}']+2.
    for rid,route in ref['routes'].items():ref['ends'][rid]=ref['finishes'][route[-1]]
    target=f'N0_{m-1}' if family in {'T','L'} else 'N0_0'
    if family in {'T','P'}:p['tasks'][target]['resources']=['DISTURBED_STATION']
    p['hard_owners']={'N2_0':'r2'}
    # Encode the lock in the *native* capability contract as well, so the
    # unchanged legacy wrapper sees exactly the same feasible owner set.
    p['robots']['r2']['capabilities'].append('protected_r2')
    p['tasks']['N2_0']['capabilities'].append('protected_r2')
    p['commitment_basis']='synthetic immutable projected suffix source/ready + fixed future owner; not service ACKs'
    p['external_commitments']={r:dict(execution_token=f'fixture:{family}:{seed}:{count}:{r}',source_anchor=v['source_anchor'],ready=v['ready']) for r,v in robots.items()}
    baseline=deepcopy(p)
    if family in {'T','P'}:
        start=ref['starts'][target];p['blocked_resources']=[dict(resource='DISTURBED_STATION',start=max(0.,start-1.),finish=start+float(rng.randint(9,18)),change_id='observed_resource_outage_fixture')]
    else:p['robots']['r0']['capabilities'].remove('lift')
    scope=dict(free=list(p['tasks']),freeze_time=False)
    good=validate(baseline,ref,scope);bad=validate(p,ref,scope)
    assert good['passed'] and not bad['passed'],(good,bad)
    design=dict(schema='repair-mechanism/v1',family=family,seed=seed,tasks=count,synthetic=True,
        independent_instance=True,rolling_snapshot=False,target=target,
        expected={'T':'retiming sufficient; tail impact small','L':'at least one reassignment necessary by capability loss',
            'P':'temporal propagation broad; reassignment unnecessary','G':'backup robot coupling; initial local window infeasible, expansion/fallback needed'}[family],
        baseline_validation=good,old_invalid=bad,impact=contract.impact_scope(p),
        construction='fixed generator before measured solves; no outcome-based filtering',
        physical_navigation_qualified=False)
    return baseline,p,design


def validate(p,plan,scope,objective=None,policy=None):
    q=contract.validate(p,plan,scope,objective)
    extra=[]
    for j,r in p.get('hard_owners',{}).items():
        if plan['owners'].get(j)!=r:extra.append(dict(name='hard_owner_'+j,residual=1.))
    if policy in {'fixed_owner','fixed_structure'}:
        for j,r in p['reference']['owners'].items():
            if plan['owners'][j]!=r:extra.append(dict(name='baseline_owner_'+j,residual=1.))
    if policy=='fixed_structure':
        if plan['routes']!=p['reference']['routes']:extra.append(dict(name='baseline_routes',residual=1.))
        for resource in {r for t in p['tasks'].values() for r in t['resources']}:
            order=sorted([j for j,t in p['tasks'].items() if resource in t['resources']],key=lambda j:p['reference']['starts'][j])
            if sorted(order,key=lambda j:plan['starts'][j])!=order:extra.append(dict(name='baseline_resource_order',residual=1.))
    q['errors']+=extra;q['checks']+=len(p.get('hard_owners',{}));q['passed']=not q['errors']
    return q


def solve_once(p,scope,policy,out,deadline,warm=None):
    """Use unchanged PrefixModel, objective, reconstruction, independent validator."""
    out.mkdir(parents=True,exist_ok=False);begin=time.perf_counter();b=native.a.b
    tpl=native.PrefixModel(p);model,v=tpl.pulp_model(scope)
    z={k:b.pulp.LpVariable(k,*tpl.bounds[k]) for k in tpl.outer}
    for row in tpl.rows:
        if any(k in tpl.outer for k in row.coefficients):model+=sum(c*(z[k] if k in z else v[k]) for k,c in row.coefficients.items())>=row.rhs,row.name
    model+=tpl.constant+sum(c*(z[k] if k in z else v[k]) for k,c in tpl.cost.items())
    for j,r in p.get('hard_owners',{}).items():model+=v[b.xk(r,j)]==1
    if policy=='fixed_owner':
        for j,r in p['reference']['owners'].items():model+=v[b.xk(r,j)]==1
    if policy=='fixed_structure':
        for resource in {r for t in p['tasks'].values() for r in t['resources']}:
            order=sorted([j for j,t in p['tasks'].items() if resource in t['resources']],key=lambda j:p['reference']['starts'][j])
            for a,c in zip(order,order[1:]):model+=v['s_'+c]>=v['s_'+a]+p['tasks'][a]['duration']+p['tasks'][a]['egress']+p['tasks'][c]['approach']+p['buffer']
    variables=model.variables();use_warm=bool(warm and set(warm)=={x.name for x in variables})
    if use_warm:
        for x in variables:
            value=warm[x.name]
            if x.lowBound is not None and value<x.lowBound and x.lowBound-value<1e-6:value=x.lowBound
            if x.upBound is not None and value>x.upBound and value-x.upBound<1e-6:value=x.upBound
            x.setInitialValue(value)
    if time.perf_counter()>=deadline:return dict(status='UNKNOWN_BUDGET',scope=scope)
    log=(out/'cbc.log').resolve();previous=Path.cwd()
    try:
        os.chdir(out)
        model.solve(b.pulp.PULP_CBC_CMD(msg=False,threads=1,timeLimit=max(.001,deadline-time.perf_counter()),gapRel=0,gapAbs=0,
            keepFiles=True,warmStart=use_warm,options=['randomSeed 1','randomCbcSeed 1'],logPath=str(log)))
    finally:os.chdir(previous)
    raw=log.read_text();q=dict(status='INFEASIBLE' if model.status==b.pulp.LpStatusInfeasible and 'infeasible' in raw.lower() else 'UNKNOWN_BUDGET',
        scope=deepcopy(scope),elapsed=time.perf_counter()-begin,cbc_log=str(log),warm_offered=use_warm,
        mip_start_accepted='MIPStart provided solution with cost' in raw,
        variables=len(variables),binary_variables=sum(x.name in tpl.binary for x in variables),
        free_binary_bounds=sum(x.name in tpl.binary and x.lowBound!=x.upBound for x in variables),constraints=len(model.constraints))
    values={k:x.value() for k,x in {**v,**z}.items()}
    if all(x is not None for x in values.values()):
        try:
            plan=b.reconstruct(p,values);obj=float(b.pulp.value(model.objective));check=validate(p,plan,scope,obj,policy)
            if check['passed']:q.update(status='OPTIMAL' if ('Result - Optimal solution found' in raw or 'Optimal objective' in raw) and model.sol_status==b.pulp.LpSolutionOptimal else 'FEASIBLE_BUDGET',plan=plan,objective=obj,validation=check,_warm={x.name:x.value() for x in variables})
        except (KeyError,RuntimeError,StopIteration,ValueError):pass
    internal=re.findall(r'Integer solution of .*?\(([0-9.]+) seconds\)',raw)
    q['cbc_internal_first_incumbent_seconds']=float(internal[0]) if internal else None
    processed=re.findall(r'processed model has (\d+) rows, (\d+) columns \((\d+) integer.*?(\d+) of which binary',raw)
    if processed:q['cbc_processed']=dict(zip(['rows','columns','integer','binary'],map(int,processed[-1])))
    nodes=re.findall(r'Enumerated nodes:\s+(\d+)',raw)
    q['cbc_enumerated_nodes']=int(nodes[-1]) if nodes else None
    available=set(scope['free']) if policy not in {'fixed_structure','fixed_owner','seed'} else set()
    q['eligible_assignment_alternatives']=sum(max(0,sum(set(t['capabilities']).issubset(r['capabilities']) for r in p['robots'].values())-1)
        for j,t in p['tasks'].items() if j in available and j not in p.get('hard_owners',{}))
    return q


def worker(args):
    import psutil
    p=json.loads(args.input.read_text());out=args.output.parent;policy=args.policy
    # Bound original wrapper's CBC threads without modifying deployed source.
    command=native.a.b.pulp.PULP_CBC_CMD
    def single_thread(*a,**kw):kw['threads']=1;return command(*a,**kw)
    native.a.b.pulp.PULP_CBC_CMD=single_thread
    begin=time.perf_counter();deadline=begin+args.budget;attempts=[];incumbents=[];first=None;warm=None
    impact=contract.impact_scope(p);initial=dict(free=impact['free'],freeze_time=True)
    full=dict(free=list(p['tasks']),freeze_time=False)
    def capture(q,scope=None):
        nonlocal first
        if q.get('plan'):
            check=validate(p,q['plan'],scope or q['scope'],q['objective'],policy)
            at=time.perf_counter()-begin
            if check['passed'] and at<=args.budget:
                if first is None:first=dict(seconds=at,objective=q['objective'],definition='complete independently validated plan available to wrapper; not CBC internal timestamp')
                row=deepcopy(q);row['validation']=check;row['available_at']=at;incumbents.append(row)
    def alarm(signum,frame):raise TimeoutError('common total worker budget')
    signal.signal(signal.SIGALRM,alarm);signal.setitimer(signal.ITIMER_REAL,args.budget)
    result={}
    try:
        if policy=='local_current':
            import bed_solver
            original=native.a.ScopedSolver.solve
            def observed(self,*a,**kw):
                q=original(self,*a,**kw);capture(q,initial);return q
            native.a.ScopedSolver.solve=observed
            result=bed_solver.solve(p,'local_impact',out/'legacy',args.budget)
            capture(result)
            attempts=result.get('attempts',[])
        elif policy in {'fixed_structure','fixed_owner'}:
            scope=dict(free=[] if policy=='fixed_structure' else list(p['tasks']),freeze_time=False)
            result=solve_once(p,scope,policy,out/'solve',deadline);capture(result);attempts=[result]
        else:
            # Same fixed-owner/old-route seed for both search methods, <=20% of
            # total budget. Failure is evidence, never a search admission gate.
            seed=solve_once(p,dict(free=[],freeze_time=False),'seed',out/'seed',min(deadline,begin+args.budget*.2))
            attempts.append(seed)
            seed_valid=bool(seed.get('plan') and validate(p,seed['plan'],initial if policy=='local_no_seed_gate' else full,seed['objective'])['passed'])
            if seed_valid:capture(seed,initial if policy=='local_no_seed_gate' else full);warm=seed.get('_warm')
            scopes=[full] if policy=='full_warm' else [initial]
            if policy=='local_no_seed_gate':
                free=set(impact['free'])
                # Existing prefix/aligned expansion order, not a new selector.
                for j in sorted(set(p['tasks'])-free,key=lambda j:p['reference']['starts'][j]):
                    free.add(j);scopes.append(dict(free=sorted(free),freeze_time=True))
                scopes.append(full)
            for idx,scope in enumerate(scopes):
                q=solve_once(p,scope,'search',out/f'search_{idx:02d}',deadline,warm)
                attempts.append(q);capture(q)
                if q['status'] in OK or q['status']!='INFEASIBLE':break
            result=attempts[-1]
    except TimeoutError:
        for child in psutil.Process().children(recursive=True):
            try:child.kill()
            except psutil.NoSuchProcess:pass
        result=dict(status='UNKNOWN_BUDGET',deadline_hit=True)
    finally:signal.setitimer(signal.ITIMER_REAL,0.)
    if incumbents:
        best=min(incumbents,key=lambda q:q['objective'])
        if result.get('status') not in OK or result.get('objective',math.inf)>best['objective']+1e-6:
            result={**best,'status':'FEASIBLE_BUDGET','incumbent_fallback':True}
    else:
        # Legacy seed infeasibility does NOT prove the local/full search domain
        # infeasible. Keep native status separately to avoid a false proof.
        if policy=='local_current' and result.get('status')=='INFEASIBLE':
            result=dict(native_status='INFEASIBLE',status='SEED_INFEASIBLE_SEARCH_NOT_RUN',seed_gate=True)
    def clean(q):return {k:v for k,v in q.items() if k!='_warm'}
    result=clean(result);result.update(policy=policy,worker_seconds=time.perf_counter()-begin,first_validated=first,
        attempts=[clean(q) for q in attempts],impact=impact,budget=args.budget,threads=1,
        source_input_sha256=sha(args.input),scope_expansions=max(0,len([q for q in attempts if 'scope' in q])-2))
    write(args.output,result)


def describe(values):
    if not values:return None
    ordered=sorted(values);return dict(n=len(values),median=statistics.median(values),mean=statistics.mean(values),p95=ordered[max(0,math.ceil(.95*len(ordered))-1)])


def run(args):
    args.out.mkdir(parents=True,exist_ok=False)
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    schedule=[];cases=[]
    for n in args.sizes:
        for family in FAMILIES:
            for seed in args.seeds:
                case=f'{family}_n{n}_s{seed}';folder=args.out/case
                before,p,design=make_case(family,seed,n)
                write(folder/'baseline.json',before);write(folder/'problem.json',p);write(folder/'design.json',design)
                cases.append(dict(id=case,family=family,seed=seed,tasks=n,path=str(folder)))
    order_rng=random.Random(args.schedule_seed);order_rng.shuffle(cases)
    method_order=list(POLICIES);order_rng.shuffle(method_order)
    for idx,case in enumerate(cases):
        slot=idx%len(POLICIES);policies=method_order[slot:]+method_order[:slot]
        schedule.append(dict(id=case['id'],policies=policies))
    manifest=dict(protocol='independent paired task-level benchmark; one snapshot per independently generated case',
        families=list(FAMILIES),sizes=args.sizes,seeds=args.seeds,budget=args.budget,policies=list(POLICIES),
        schedule=schedule,cases=cases,schedule_seed=args.schedule_seed,physical_execution=False,selection_before_solves=True,
        notes=['fixed_structure fixes owners, robot and old resource order; availability disjunctions remain, not advertised as pure LP',
            'fixed_owner fixes ownership only and may reorder routes/resources: stronger than simple retiming',
            'local_current is deployed bed_solver unmodified; local_no_seed_gate is a separate offline diagnostic adapter with existing closure/window/expansion rules',
            'scope bounds count is not presolved CBC search size; failed/unknown runs retained'],
        environment=dict(python=platform.python_version(),platform=platform.platform(),cpu_affinity=sorted(os.sched_getaffinity(0)),load=os.getloadavg()))
    write(args.out/'manifest.json',manifest)
    sources=[Path(__file__)]+[W/'tools'/f for f in ['bed_solver.py','bed_contract.py','prefix_solver.py','prefix_contract.py','aligned_solver.py','aligned_contract.py','clinic_milp_backend.py','clinic_plan_check.py']]
    write(args.out/'source_manifest.json',{str(f):sha(f) for f in sources})
    for idx,f in enumerate(sources):
        dest=args.out/'sources'/f'{idx:02d}_{f.name}';dest.parent.mkdir(exist_ok=True);dest.write_bytes(f.read_bytes())
    rows=[]
    for case,block in zip(cases,schedule):
        folder=Path(case['path']);p=json.loads((folder/'problem.json').read_text())
        for slot,policy in enumerate(block['policies']):
            dest=folder/policy;dest.mkdir();begin=time.perf_counter()
            with (dest/'worker.log').open('w') as log:
                proc=subprocess.run([sys.executable,str(Path(__file__).resolve()),'--worker','--input',str(folder/'problem.json'),
                    '--output',str(dest/'result.json'),'--policy',policy,'--budget',str(args.budget)],stdout=log,stderr=subprocess.STDOUT,
                    timeout=args.budget+20,env={**os.environ,'OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1','MKL_NUM_THREADS':'1'})
            q=json.loads((dest/'result.json').read_text()) if (dest/'result.json').exists() else dict(status='ERROR_NO_RESULT')
            usable=q.get('status') in OK
            check=validate(p,q['plan'],q['scope'],q['objective'],policy) if usable else None
            row=dict(**case,policy=policy,slot=slot,budget=args.budget,input_sha256=sha(folder/'problem.json'),
                status=q['status'],exit=proc.returncode,valid=bool(usable and check['passed']),validation=check,
                process_seconds=time.perf_counter()-begin,worker_seconds=q.get('worker_seconds'),first_validated=q.get('first_validated'),
                result=str(dest/'result.json'),objective=q.get('objective'),initial_free=len(contract.impact_scope(p)['free']),
                final_free=len(q.get('scope',{}).get('free',[])) if usable else None,
                scope_expansions=q.get('scope_expansions'),
                commitment_violations=sum(e['name'].startswith('hard_owner') for e in (check or {}).get('errors',[])))
            if usable:row.update(owner_changes=sum(q['plan']['owners'][j]!=r for j,r in p['reference']['owners'].items()),
                shifted_tasks=sum(abs(q['plan']['starts'][j]-t)>1e-5 for j,t in p['reference']['starts'].items()),
                total_start_shift=sum(abs(q['plan']['starts'][j]-t) for j,t in p['reference']['starts'].items()),planned_route_finish=max(q['plan']['ends'].values()))
            rows.append(row);write(args.out/'rows.json',rows)
            write(args.out/'status.json',dict(state='RUNNING',completed=len(rows),total=len(cases)*len(POLICIES)))
            print(case['id'],policy,q['status'],'valid',row['valid'],flush=True)
            if proc.returncode or q['status'].startswith('ERROR') or usable and not row['valid']:
                write(args.out/'failure.json',row);return 1
    stats={}
    for family in FAMILIES:
        stats[family]={}
        for policy in POLICIES:
            subset=[r for r in rows if r['family']==family and r['policy']==policy];valid=[r for r in subset if r['valid']]
            stats[family][policy]=dict(instances=len(subset),successes=len(valid),success_rate=len(valid)/len(subset),
                statuses={s:sum(r['status']==s for r in subset) for s in sorted({r['status'] for r in subset})},
                first_validated_seconds=describe([r['first_validated']['seconds'] for r in valid if r['first_validated']]),
                process_seconds=describe([r['process_seconds'] for r in subset]),worker_seconds=describe([r['worker_seconds'] for r in subset]),
                owner_changes=describe([r['owner_changes'] for r in valid]),initial_free_ratio=describe([r['initial_free']/r['tasks'] for r in subset]),
                final_free_ratio=describe([r['final_free']/r['tasks'] for r in valid]),commitment_violations=sum(r['commitment_violations'] for r in subset))
    write(args.out/'summary.json',dict(passed=all(r['exit']==0 and (not r['valid'] or r['validation']['passed']) for r in rows),
        instances=len(cases),runs=len(rows),stats=stats,physical_execution=False,
        caution='benchmark execution/validation PASS is not all-method recovery PASS; no physical completion times; no academic novelty claim'))
    write(args.out/'status.json',dict(state='COMPLETE',completed=len(rows),total=len(rows)))
    return 0


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--worker',action='store_true')
    ap.add_argument('--input',type=Path);ap.add_argument('--output',type=Path);ap.add_argument('--policy',choices=POLICIES)
    ap.add_argument('--out',type=Path);ap.add_argument('--budget',type=float,default=5.)
    ap.add_argument('--sizes',type=int,nargs='+',default=[6,12]);ap.add_argument('--seeds',type=int,nargs='+',default=[7,19,43])
    ap.add_argument('--schedule-seed',type=int,default=20261118)
    a=ap.parse_args()
    if a.budget<=0:ap.error('positive common budget required')
    if len(set(a.seeds))!=len(a.seeds):ap.error('independent seeds must be unique')
    raise SystemExit(worker(a) if a.worker else run(a))
