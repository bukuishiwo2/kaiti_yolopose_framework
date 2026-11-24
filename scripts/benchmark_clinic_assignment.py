#!/usr/bin/env python3
"""Frozen, offline-only four-policy allocation experiment. Never imports ROS.

All modifications to observed snapshots are explicit counterfactual parameters.
No failed strategy is replaced by another strategy's final answer.
"""
import argparse
from copy import deepcopy
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import random
import re
import signal
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from kaiti_task_sim import clinic_assignment as ca
W=ca.WORKSPACE
SOURCE=W/'verification/visual_bed_2026-11-18_d1/bed_before_pickup_04'
FAMILIES=('busy','ready','monitor_load','resource','load_count','hard','region')
OK={'OPTIMAL','FEASIBLE_BUDGET','FEASIBLE_CONSTRUCTIVE'}

def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n')

def read(path):return json.loads(path.read_text())
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def json_finite(value):
    """Saved failed path diagnostics use Infinity; encode as null, not evidence loss."""
    if isinstance(value,dict):return {k:json_finite(v) for k,v in value.items()}
    if isinstance(value,list):return [json_finite(v) for v in value]
    if isinstance(value,float) and not math.isfinite(value):return None
    return value

def make_case(family,level,seed):
    stage='01_verify' if family=='busy' or family=='control_verify' else 'repair_00' if family=='hard' else '02_response'
    original=read(SOURCE/stage/'problem.json');p=deepcopy(original)
    response=read(SOURCE/'02_response/problem.json')
    p['assignment_weights']=deepcopy(ca.WEIGHTS)
    p['weights']={k:0. for k in p['weights']}
    p['weights'].update(normal_delay=ca.WEIGHTS['normal_wait'],owner=ca.WEIGHTS['owner'],shift=ca.WEIGHTS['shift'],travel=ca.WEIGHTS['travel'])
    p['immutable_projection']={r:{k:v[k] for k in ('source_anchor','ready')} for r,v in original['robots'].items()}
    p['physical_certificate']=read(SOURCE/'certificate.json');p['region']='A';p['hard_owners']={}
    p['clocks']=dict(candidate_at=43.87,confirmed_at=None if stage=='01_verify' else 172.26,
        actual_verify_started_at=None if stage=='01_verify' else 169.27,
        task_planning_release={j:t['release'] for j,t in p['tasks'].items() if t['kind']!='normal'})
    if stage=='01_verify' and family!='control_verify':
        p['tasks'].update({j:deepcopy(t) for j,t in response['tasks'].items() if t['kind']=='normal'})
        for pre in original['prefixes'].values():
            for item in pre['schedule']:p['known_finishes'][item['job']]=item['service_finish_forecast']
    p['nominal_owners']={j:t['nominal_owner'] for j,t in p['tasks'].items() if t['kind']=='normal'}
    if family=='hard':
        # Only this saved suffix has a real accepted schedule, not release=0 fallbacks.
        p['nominal_owners']=deepcopy(p['reference']['owners'])
    else:p['reference']=dict(owners={},starts={},routes={r:[] for r in p['robots']})
    p['allowed_robots']={j:list(p['robots']) for j in p['tasks']}
    p['static_owners']={**p['nominal_owners'],**{j:('r1' if t['kind'] in ('verify','monitor') else 'r2') for j,t in p['tasks'].items() if t['kind']!='normal'}}
    params={};rng=random.Random(seed)
    if not family.startswith('control'):
        for j,t in p['tasks'].items():
            if t['kind']=='normal':t['duration']+=float(rng.randint(0,3))
        params['duration_jitter']='Random(seed).randint(0,3), normal tasks in saved order; same across levels'
    if family=='busy':
        extra=(0.,160.)[level];p['robots']['r1']['ready']+=extra;params['r1_prefix_extension']=extra
    elif family=='ready':
        p['robots']['r1']['ready']+=160.;extra=(0.,230.)[level];p['robots']['r3']['ready']+=extra
        params.update(r1_prefix_extension=160.,r3_prefix_extension=extra)
    elif family=='monitor_load':
        value=(4.,240.)[level];p['tasks']['C0_r1_W3']['duration']=value;params['C0_r1_W3_duration']=value
    elif family=='resource':
        delay=(80.,300.)[level];p['blocked_resources'].append(dict(resource='G1',start=p['time'],finish=p['time']+delay,source='counterfactual_registered_resource_outage'))
        params['G1_outage_seconds']=delay
    elif family=='load_count':
        if level:
            for r in p['robots']:
                j='LOAD_'+r;t=deepcopy(p['tasks'][f'C0_{r}_W3']);t['dependencies']=[f'C0_{r}_W3'];t['duration']=30.
                p['tasks'][j]=t;p['nominal_owners'][j]=r;p['static_owners'][j]=r;p['allowed_robots'][j]=list(p['robots'])
        params['normal_task_count']=6+3*level
    elif family=='hard':
        target='C0_r3_W3';p['hard_owners'][target]='r3';params['future_hard_owner']={target:'r3'}
        if level:p['robots']['r3']['capabilities'].remove('move')
        params['hard_owner_capability_lost']=bool(level)
    elif family=='region':
        p['region']=('A','B')[level];params['registered_region']=p['region']
        if level:
            ca.native();import bed_contract;import dense_tasks
            from kaiti_task_sim.clinic_visual import region_registry
            config=bed_contract.config();mapping=region_registry(config)['B']['anchors']
            for j,t in list(p['tasks'].items()):
                if t['kind'] not in mapping:continue
                a=mapping[t['kind']];t=deepcopy(t);t.update(anchor=a,resources=[a] if a in config['resource_phases'] else [],region='B',execution_authorized=False)
                p['tasks'][j]=dense_tasks.phases(t,config)
    elif family.startswith('control'):
        for j,t in p['tasks'].items():p['allowed_robots'][j]=[p['static_owners'][j]]
    else:raise ValueError(family)
    for t in p['tasks'].values():t['execution_authorized']=False
    p['case_id']=f'{family}_l{level}_s{seed}'
    p['scenario_parameters']=params
    p['input_kind']='saved snapshot control' if family.startswith('control') else 'explicit counterfactual derived from saved snapshot'
    p['source_path']=str(SOURCE/stage/'problem.json');p['source_sha256']=sha(Path(p['source_path']))
    p['sample_unit']=dict(source_episode='bed_before_pickup_04',family=family,level=level,seed=seed,
        independent_physical_trial=False,rolling_repair_sample=False,
        note='paired deterministic fixtures; shared source, levels and seeds are dependent, not IID robot trials')
    p['accepted_reference_basis']='saved repair_00 accepted suffix plan' if family=='hard' else 'none; nominal owner is not an accepted plan'
    p['physical_execution_authorized']=False
    p['serialization_note']='Nonfinite diagnostic endpoint_error serialized as null; original source SHA/path preserves raw evidence. No optimizer input uses it.'
    return json_finite(p)


def generate(out,seeds,budget):
    out.mkdir(parents=True,exist_ok=False)
    cases=[make_case(f,l,s) for f in FAMILIES for s in seeds for l in (0,1)]
    cases += [make_case('control_verify',0,0),make_case('control_response',0,0)]
    source_files=[Path(__file__),ROOT/'src/kaiti_task_sim/clinic_assignment.py']+[W/'tools'/n for n in ('aligned_solver.py','aligned_contract.py','clinic_milp_backend.py','clinic_plan_check.py')]
    protocol=dict(schema='clinic-allocation-experiment/v1',created_before_measured_solves=True,
        seeds=seeds,levels=[0,1],families=list(FAMILIES),budget_seconds=budget,policies=list(ca.POLICIES),
        objective_weights=ca.WEIGHTS,objective='4*stage_response + .1*(Cmax-now) + .1*sum(normal_start-release) + 2*accepted_owner_changes + .05*accepted_absolute_shift + .1*phase_travel',
        no_due_dates='normal_wait is waiting, never tardiness; saved hard deadlines remain hard',
        B0='all static owners fixed, route order and resource timing optimized',
        B1='earliest-service feasible bundle insertion; fixed normal owners; all eligible emergency pairs/slots; deterministic resource order; no MILP fallback',
        B2='legacy restricted owner domain + necessary_normal third-role policy; new shared timing/objective adapter, not byte-identical deployed solver',
        B3='joint legal suffix ownership and scheduling; immutable projected prefixes and hard owners',
        fairness='same per-case tasks, physical constraints, costs and wall budget; policy restrictions differ explicitly; common greedy construction for MIPStart under own restrictions',
        first_feasible='first fully validated usable incumbent, including common construction; CBC internal first integer logged separately',
        hardware=dict(python=sys.version,cpu_count=os.cpu_count(),affinity_cpu=min(os.sched_getaffinity(0))),
        qualification='counterfactual capability/map feasible is not new Nav2/concurrency qualification; never dispatch',
        population='28 dependent counterfactual fixtures + 2 saved-input controls with two seeds; no inferential generalization or physical success-rate claims',
        outcome_filtering=False,source_manifest={str(f):sha(f) for f in source_files})
    for p in cases:write(out/'cases'/p['case_id']/'problem.json',p)
    protocol['cases']={p['case_id']:ca.digest(p) for p in cases}
    write(out/'protocol.json',protocol)
    return cases


def solve_worker(p,policy,out,budget,seed):
    out.mkdir(parents=True,exist_ok=False);begin=time.perf_counter();deadline=begin+budget
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    result=dict(policy=policy,input_sha256=ca.digest(p),status='UNKNOWN_BUDGET',budget_seconds=budget,first_feasible_seconds=None)
    checkpoint=out/'incumbent.json'
    def save(q,origin):
        if not q.get('plan'):return
        audit=ca.validate(p,q['plan'],policy,q['objective'])
        if not audit['passed']:return
        if not result.get('plan') or q['objective']<result['objective']-1e-6:
            if result['first_feasible_seconds'] is None:result['first_feasible_seconds']=time.perf_counter()-begin
            result.update(plan=q['plan'],objective=q['objective'],validation=audit,status=q['status'],incumbent_origin=origin)
            write(checkpoint,result)
    def alarm(signum,frame):raise TimeoutError('common wall budget expired')
    signal.signal(signal.SIGALRM,alarm);signal.setitimer(signal.ITIMER_REAL,budget)
    solver_begin=None
    try:
        q=ca.greedy(p,policy,deadline);result['construction']={k:v for k,v in q.items() if k not in ('plan','validation')}
        save(q,'own_policy_constructive_seed')
        if policy!='B1' and time.perf_counter()<deadline:
            tpl,m,variables=ca.model(p,policy)
            result['model_size']=dict(variables=len(m.variables()),constraints=len(m.constraints),binary=len(tpl.binary))
            warm=False
            if q.get('plan'):
                values,residual=ca.warm_values(p,tpl,m,q['plan']);result['mipstart_max_residual']=residual
                if residual<1e-5:
                    for v in m.variables():v.setInitialValue(values[v.name])
                    warm=True
            a,_=ca.native();b=a.b;log=out/'cbc.log';solver_begin=time.perf_counter()
            solver=b.pulp.PULP_CBC_CMD(msg=False,threads=1,gapRel=0,gapAbs=0,
                timeLimit=max(.01,deadline-time.perf_counter()-.15),warmStart=warm,keepFiles=True,
                options=[f'randomSeed {seed}',f'randomCbcSeed {seed}','timeMode elapsed'],logPath=str(log))
            previous=Path.cwd()
            try:os.chdir(out);m.solve(solver)
            finally:os.chdir(previous)
            result['solver_seconds']=time.perf_counter()-solver_begin;raw=log.read_text()
            result['cbc_first_integer_seconds']=None
            found=re.search(r'Cbc0012I Integer solution .*?\(([0-9.]+) seconds\)',raw)
            if found:result['cbc_first_integer_seconds']=float(found.group(1))
            values={k:v.value() for k,v in variables.items()}
            if all(v is not None for v in values.values()):
                try:
                    plan=b.reconstruct(p,values);cost=float(b.pulp.value(m.objective))
                    audit=ca.validate(p,plan,policy,cost)
                    result['final_solver_validation']=audit
                    if audit['passed']:
                        status='OPTIMAL' if 'Result - Optimal solution found' in raw and m.sol_status==b.pulp.LpSolutionOptimal else 'FEASIBLE_BUDGET'
                        save(dict(plan=plan,objective=cost,status=status),'cbc')
                        if status=='OPTIMAL':result['status']='OPTIMAL'
                except (RuntimeError,StopIteration,KeyError,ValueError) as e:result['reconstruction_error']=repr(e)
            if not result.get('plan') and m.status==b.pulp.LpStatusInfeasible and 'infeasible' in raw.lower():result['status']='INFEASIBLE'
            bounds=re.findall(r'Lower bound:\s+([-+0-9.eE]+)',raw)
            if bounds:result['best_bound']=float(bounds[-1])+tpl.constant
        elif policy=='B1' and not q.get('plan'):result['status']=q['status']
    except TimeoutError:
        result['budget_exhausted']=True
        # CBC is a worker child; parent process timeout cleanup is separate.
        import psutil
        for child in psutil.Process().children(recursive=True):
            try:child.kill()
            except psutil.NoSuchProcess:pass
    finally:signal.setitimer(signal.ITIMER_REAL,0.)
    if result.get('plan'):
        if policy!='B1' and result['status']!='OPTIMAL':result['status']='FEASIBLE_BUDGET'
        result['metrics']=ca.metrics(p,result['plan'])
    result['total_seconds']=time.perf_counter()-begin
    result['solver_seconds']=result.get('solver_seconds',0. if solver_begin is None else time.perf_counter()-solver_begin)
    write(out/'result.json',result)
    return result


def run(out):
    protocol=read(out/'protocol.json');budget=protocol['budget_seconds']
    for index,(case_id,expected) in enumerate(protocol['cases'].items()):
        folder=out/'cases'/case_id;p=read(folder/'problem.json');assert ca.digest(p)==expected
        order=ca.POLICIES[index%4:]+ca.POLICIES[:index%4]
        for policy in order:
            target=folder/policy
            if target.exists():raise RuntimeError('existing evidence directory: '+str(target))
            env=dict(os.environ,OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1')
            cmd=[sys.executable,str(Path(__file__).resolve()),'worker','--input',str(folder/'problem.json'),'--output',str(target),'--policy',policy,'--budget',str(budget),'--solver-seed','17']
            begin=time.perf_counter()
            try:
                child=subprocess.run(cmd,env=env,capture_output=True,text=True,timeout=budget+15,start_new_session=True)
                (target/'worker.log').write_text(child.stdout+child.stderr)
                if child.returncode:raise RuntimeError(f'{case_id}/{policy}: {child.stderr[-1800:]}')
            except subprocess.TimeoutExpired as e:raise RuntimeError('worker supervisor timeout; stop and diagnose') from e
            result=read(target/'result.json');result['supervisor_wall_seconds']=time.perf_counter()-begin;write(target/'result.json',result)
        print(case_id,[(m,read(folder/m/'result.json')['status']) for m in ca.POLICIES],flush=True)


def main():
    a=argparse.ArgumentParser();a.add_argument('mode',choices=['generate','run','worker']);a.add_argument('--output',type=Path,required=True);a.add_argument('--input',type=Path);a.add_argument('--policy',choices=ca.POLICIES);a.add_argument('--budget',type=float,default=5.);a.add_argument('--seeds',type=int,nargs='+',default=[113,229]);a.add_argument('--solver-seed',type=int,default=17)
    v=a.parse_args()
    if v.mode=='generate':generate(v.output,v.seeds,v.budget)
    elif v.mode=='run':run(v.output)
    else:solve_worker(read(v.input),v.policy,v.output,v.budget,v.solver_seed)
if __name__=='__main__':main()
