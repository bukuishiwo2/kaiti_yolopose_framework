#!/usr/bin/env python3
"""Frozen factorial experiment plus genuine accepted-reference event insertion."""
import argparse
from copy import deepcopy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
sys.path.insert(0,str(HERE));import adapter as ca
spec=importlib.util.spec_from_file_location('old_benchmark',ROOT/'scripts/benchmark_clinic_assignment.py');old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
write=old.write;read=old.read;sha=old.sha;finite=old.json_finite
W=ca.base.WORKSPACE
RUNS=('dense_loop_a13','unified_bed_local_r1')
PROFILES=('observed','r1_hold','g1_reservation','routine_window','role_restricted')


def extract(run,out):
    root=W/'runs'/run;p0=read(root/'00_normal/problem.json');result=read(root/'00_normal/result.json')
    accepted=None;excerpts=[];nread=0
    with (root/'trace.jsonl').open() as f:
        for n,line in enumerate(f,1):
            q=json.loads(line);nread=n
            if q['phase']=='plan_committed' and q.get('stage')=='normal':
                assert accepted is None;accepted=q
            if q['phase'] in ('plan_committed','planning_requested','navigation_requested','job_completed','fall_event_injected'):
                excerpts.append(dict(line=n,line_sha256=__import__('hashlib').sha256(line.encode()).hexdigest(),record=finite(q)))
            if q['phase']=='planning_requested' and q.get('stage')=='response':break
            if n>5000:raise RuntimeError('bounded provenance scan exceeded before response snapshot')
    assert accepted and accepted['plan']==result['plan'],'saved solver plan is not proved accepted'
    _,contract=ca.native();audit=contract.validate(p0,accepted['plan'],dict(free=list(p0['tasks']),freeze_time=False))
    assert audit['passed'],audit
    observed_event=next(v['record'] for v in excerpts if v['record']['phase']=='fall_event_injected')
    files=[root/'00_normal/problem.json',root/'00_normal/result.json',root/'01_verify/problem.json',root/'02_response/problem.json',root/'trace.jsonl',root/'runtime_scenario.json']
    prov=dict(schema='accepted-reference-provenance/v1',run=run,reference_kind='HISTORICALLY_OBSERVED_PLAN_COMMIT',
        accepted_at=accepted['episode_time'],accepted_trace_line=next(v['line'] for v in excerpts if v['record']['phase']=='plan_committed' and v['record'].get('stage')=='normal'),
        accepted_plan=accepted['plan'],initial_full_validation=audit,
        historical_event_at=observed_event['episode_time'],historical_event_origin='legacy scripted event, NOT visual inference',
        new_event_origin='OFFLINE_SEMANTIC_GRAPH_SPLICE_FROM_VALIDATED_VISUAL_ROLE_TEMPLATE; no fresh fall observation or verdict claimed',
        bounded_trace_lines_read=nread,source_sha256={str(f):sha(f) for f in files},
        related_snapshots={stage:str(root/stage/'problem.json') for stage in ('01_verify','02_response')})
    # Identity comparison above is after finite() copied the excerpt; locate by phase.
    prov['accepted_trace_line']=next(v['line'] for v in excerpts if v['record']['phase']=='plan_committed' and v['record'].get('stage')=='normal')
    write(out/run/'provenance.json',prov);write(out/run/'trace_excerpt.json',excerpts)
    return prov


def make_case(run,prov,stage,variant='observed',reference_cost=True):
    root=W/'runs'/run;source=read(root/stage/'problem.json');p0=read(root/'00_normal/problem.json');p=deepcopy(source);full=prov['accepted_plan']
    active={j for pre in source['prefixes'].values() for j in pre['jobs']};completed=set(source['actual_known_finishes'])
    pending=set(p0['tasks'])-active-completed
    assert not active&pending
    p['tasks']={j:deepcopy(p0['tasks'][j]) for j in p0['tasks'] if j in pending}
    visual=read(old.SOURCE/('01_verify' if stage=='01_verify' else '02_response')/'problem.json')
    roles=['verify'] if stage=='01_verify' else ['deliver','monitor','pickup']
    for role in roles:
        j='E1_'+role;t=deepcopy(visual['tasks'][j]);t['release']=source['time']
        if t.get('start_deadline') is not None:t['start_deadline']=source['time']+360.
        t['execution_authorized']=False;p['tasks'][j]=t
    ref=dict(owners={j:full['owners'][j] for j in p0['tasks'] if j in pending},
        starts={j:full['starts'][j] for j in p0['tasks'] if j in pending},
        finishes={j:full['finishes'][j] for j in p0['tasks'] if j in pending},
        routes={r:[j for j in route if j in pending] for r,route in full['routes'].items()})
    p['accepted_reference']=deepcopy(ref);p['reference']=deepcopy(ref) if reference_cost else dict(owners={},starts={},routes={r:[] for r in p['robots']})
    p['reference_cost_enabled']=reference_cost
    p['nominal_owners']=deepcopy(ref['owners']);p['original_nominal_owners']={j:p0['tasks'][j]['nominal_owner'] for j in pending}
    p['static_owners']={**ref['owners'],**{j:('r1' if t['kind'] in ('verify','monitor') else 'r2') for j,t in p['tasks'].items() if t['kind']!='normal'}}
    p['hard_owners']={};p['allowed_robots']={j:list(p['robots']) for j in p['tasks']}
    p['assignment_weights']=deepcopy(ca.WEIGHTS);p['weights']={k:0. for k in source['weights']}
    p['weights'].update(normal_delay=.1,owner=2.,shift=.05,travel=.1)
    p['immutable_projection']={r:{k:v[k] for k in ('source_anchor','ready')} for r,v in source['robots'].items()}
    p['physical_certificate']=read(old.SOURCE/'certificate.json');p['region']='A'
    p['events']={} if stage=='01_verify' else dict(E1=dict(monitor='E1_monitor',pickup='E1_pickup',deliver='E1_deliver',observed_at=prov['historical_event_at']))
    p['cargo_pairs']=[] if stage=='01_verify' else [['E1_pickup','E1_deliver']]
    p['clocks']=dict(candidate_at=prov['historical_event_at'],confirmed_at=None if stage=='01_verify' else source['time'],
        actual_verify_started_at=None if stage=='01_verify' else source['snapshot_states']['r3']['record']['service_started'],
        task_planning_release={j:t['release'] for j,t in p['tasks'].items() if t['kind']!='normal'},
        confirmed_at_provenance='counterfactual explicit-review acceptance assumed at saved response snapshot; NOT a historical explicit fall verdict')
    if stage!='01_verify':p['necessary_normal']='C0_r3_W2';assert p['necessary_normal'] in pending
    else:p.pop('necessary_normal',None)
    parameters={}
    if variant=='r1_hold':
        p['robots']['r1']['ready']+=160.
        parameters['counterfactual_irrevocable_r1_source_hold_seconds']=160.
    elif variant=='g1_reservation':
        lock=dict(resource='G1',start=p['time'],finish=p['time']+240.,source='offline registered service reservation assumption')
        p['blocked_resources'].append(lock);parameters['additional_G1_reservation']=lock
    elif variant=='routine_window':
        j='C0_r3_W3';due=max(p['time']+240.,ref['finishes'][j]+90.)
        p['tasks'][j]['deadline']=due;parameters['counterfactual_hard_routine_window']={j:due}
    elif variant=='role_restricted':
        for j,t in p['tasks'].items():
            if t['kind']!='normal':p['allowed_robots'][j]=[p['static_owners'][j]]
        parameters['roles']='prior A certificate role-owner restriction as model sensitivity only; no full source-config/timing qualification'
    elif variant!='observed':raise ValueError(variant)
    for t in p['tasks'].values():t['execution_authorized']=False
    p['case_id']=f'{run}__{stage}__{variant}'+('' if reference_cost else '__reference_erased')
    p['sample_unit']=dict(source_episode=run,stage=stage,variant=variant,independent_physical_trial=False,rolling_snapshot=False,
        reference_kind='HISTORICALLY_OBSERVED_PLAN_COMMIT',scenario_kind='SAVED_STATE_PLUS_COUNTERFACTUAL_EVENT_INSERTION')
    p['scenario_parameters']=parameters;p['physical_execution_authorized']=False
    p['source_path']=str(root/stage/'problem.json');p['source_sha256']=sha(Path(p['source_path']))
    p['accepted_provenance_sha256']=ca.digest(prov)
    p['task_partition']=dict(completed=sorted(completed&set(p0['tasks'])),issued_prefix=sorted(active&set(p0['tasks'])),unissued_suffix=sorted(pending),
        active_states={r:dict(job=v['job'],state=v['state'],record_task_id=v['record'].get('task_id'),leg=v.get('leg')) for r,v in source['snapshot_states'].items()})
    p['legal_business_policy']='legacy third-role continuity required; T=0 variants are OFFLINE_POLICY_RELAXATION_ONLY'
    return finite(p)


def generate(out,dev=False):
    out.mkdir(parents=True,exist_ok=False);cases=[];manifest={};runs=RUNS[:1] if dev else RUNS
    for run in runs:
        prov=extract(run,out/'sources')
        variants=('observed','r1_hold') if dev else PROFILES
        for variant in variants:
            p=make_case(run,prov,'02_response',variant);p['methods']=list(ca.METHODS);cases.append(p)
        p=make_case(run,prov,'01_verify');p['methods']=['B0','B1','F10','F11'];cases.append(p)
        if not dev:
            for variant in ('observed','g1_reservation'):
                p=make_case(run,prov,'02_response',variant,False);p['methods']=['F10','F11'];cases.append(p)
    for p in cases:write(out/'cases'/p['case_id']/'problem.json',p)
    sources=[HERE/'adapter.py',HERE/'run.py',ROOT/'src/kaiti_task_sim/clinic_assignment.py',ROOT/'scripts/benchmark_clinic_assignment.py']+[W/'tools'/f for f in ['aligned_solver.py','aligned_contract.py','clinic_milp_backend.py','clinic_plan_check.py']]
    protocol=dict(schema='accepted-insert-factorial/v1',frozen_before_solves=True,budget_seconds=5.,solver_seed=17,
        methods=dict(B0='fixed accepted owners and static emergency roles; required third policy',B1='earliest service bundle insertion, accepted ordinary owners/order, required third policy',
            F00='third OFF, limited normal domain',F01='third OFF, joint normal domain',F10='third ON, limited normal domain (B2)',F11='third ON, joint normal domain (legal B3)'),
        third_policy_status='REQUIRED_IN_CURRENT_EXECUTOR; OFF cells exclusively offline business-policy counterfactuals',
        fixed_factors=['tasks','clocks','robot snapshot','capability','spatial domain','hard prefix','resource','objective','weights','CBC seed/threads','five-second algorithm budget'],
        objective_weights=ca.WEIGHTS,reference_erasure='separate diagnostic only; removes owner/shift reference costs, reports true accepted changes against preserved accepted_reference; not a same-objective superiority comparison',
        generation='two preselected historical runs x five deterministic response conditions; two verify stages; four reference-erased diagnostics; no outcome selection',
        variants=list(PROFILES),population='shared episodes/accepted plans and states, not IID scenes; verify/response are separate conditional-stage comparisons, not a new closed-loop replay',
        new_mechanism='NOT_IMPLEMENTED_PENDING_EVIDENCE',physical_execution='NOT_RUN',
        source_manifest={str(f):sha(f) for f in sources},cases={p['case_id']:ca.digest(p) for p in cases})
    write(out/'protocol.json',protocol);print('generated',len(cases),'cases',sum(len(p['methods']) for p in cases),'calls')


def worker(inp,out,method):
    p=read(inp);old.ca=ca;q=old.solve_worker(p,method,out,5.,17)
    q['factor_profile']=ca.profile(method);q['business_policy_class']='OFFLINE_POLICY_RELAXATION_ONLY' if not ca.profile(method)['third'] else 'REQUIRED_BUSINESS_POLICY_PRESERVED'
    q['physical_execution_authorized']=False;write(out/'result.json',q)


def run(out):
    protocol=read(out/'protocol.json')
    for path,s in protocol['source_manifest'].items():assert sha(Path(path))==s,('source drift',path)
    for index,(name,expected) in enumerate(protocol['cases'].items()):
        folder=out/'cases'/name;p=read(folder/'problem.json');assert ca.digest(p)==expected
        methods=p['methods'];order=methods[index%len(methods):]+methods[:index%len(methods)]
        for method in order:
            target=folder/method
            if target.exists():raise RuntimeError('will not overwrite '+str(target))
            env=dict(os.environ,OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1')
            child=subprocess.run([sys.executable,str(HERE/'run.py'),'worker','--input',str(folder/'problem.json'),'--output',str(target),'--method',method],env=env,capture_output=True,text=True,timeout=20.,start_new_session=True)
            target.mkdir(exist_ok=True);(target/'worker.log').write_text(child.stdout+child.stderr)
            if child.returncode:raise RuntimeError(f'{name}/{method}: '+child.stderr[-2000:])
        print(name,[(m,read(folder/m/'result.json')['status']) for m in methods],flush=True)

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('mode',choices=['generate','run','worker']);a.add_argument('--output',type=Path,required=True);a.add_argument('--input',type=Path);a.add_argument('--method',choices=ca.METHODS);a.add_argument('--dev',action='store_true');v=a.parse_args()
    if v.mode=='generate':generate(v.output,v.dev)
    elif v.mode=='run':run(v.output)
    else:worker(v.input,v.output,v.method)
