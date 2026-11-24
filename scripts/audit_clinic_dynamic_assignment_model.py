#!/usr/bin/env python3
"""Audit saved real Clinic allocation inputs without solving or starting ROS.

Sensitivity probes identify effective model inputs, not algorithm performance.
The original model, objectives, qualification guards and evidence stay untouched.
"""
import argparse
from copy import deepcopy
import hashlib
import itertools
import json
from pathlib import Path
import sys


PROJECT = Path(__file__).resolve().parents[1]
DEFAULT_WORKSPACE = Path('/home/yhc/clinic_planning_ws')
DEFAULT_EVIDENCE = DEFAULT_WORKSPACE / 'verification/visual_bed_2026-11-18_d1/bed_before_pickup_04'


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,allow_nan=False).encode()).hexdigest()


def write(path,value):
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n')


def model_snapshot(model_class,problem,scope):
    """Canonicalize native model rows, all variable domains and objective parts."""
    template=model_class(problem)
    model,_=template.pulp_model(scope)
    content=dict(bounds=template.bounds,binary=sorted(template.binary),outer=sorted(template.outer),
        native_rows=[dict(name=r.name,coefficients=r.coefficients,rhs=r.rhs) for r in template.rows],
        pulp_rows={name:dict(coefficients={v.name:float(c) for v,c in row.items()},
            constant=float(row.constant),sense=row.sense) for name,row in model.constraints.items()},
        pulp_variables={v.name:dict(low=v.lowBound,high=v.upBound,category=v.cat) for v in model.variables()})
    return dict(structure_sha256=digest(content),cost_sha256=digest(template.cost),
        constant=template.constant,variables=len(template.bounds),native_rows=len(template.rows),
        pulp_rows=len(model.constraints),cost=template.cost,
        variable_names=sorted(template.bounds))


def capability_role_options(problem,qualified=None):
    """Capability-only domain; not a schedule/route feasibility certificate."""
    roles=['monitor','pickup','deliver']
    domains={role:[r for r,v in problem['robots'].items()
        if set(problem['tasks']['E1_'+role]['capabilities']).issubset(v['capabilities'])
        and (qualified is None or r in qualified.get(role,[]))] for role in roles}
    options=[dict(zip(roles,assignment)) for assignment in itertools.product(*(domains[k] for k in roles))
        if assignment[1]==assignment[2] and assignment[0]!=assignment[1]]
    return dict(domains=domains,combinations=options,scope='capability and role relations only, not temporal/geometry feasibility')


def run(workspace,evidence,out):
    out.mkdir(parents=True,exist_ok=False)
    sys.path[:0]=[str(PROJECT/'src'),str(workspace/'tools')]
    # Imports modify only this audit process's model bindings, as native workers do.
    import dense_solver
    import bed_initial_solver
    import bed_contract
    import dense_tasks
    from dense_validate import validate as validate_dense
    from bed_validate import validate as validate_response
    from kaiti_task_sim.clinic_visual import VisualEventBridge,compile_tasks

    paths=[workspace/'tools'/name for name in ['clinic_milp_backend.py','clinic_plan_check.py',
        'aligned_solver.py','aligned_contract.py','dense_solver.py','dense_tasks.py','dense_validate.py',
        'bed_initial_solver.py','bed_validate.py','prefix_contract.py']]
    paths += [PROJECT/'src/kaiti_task_sim/clinic_visual.py',PROJECT/'src/kaiti_task_sim/event_protocol.py',Path(__file__)]
    before={str(path):hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}
    write(out/'source_hashes.json',before)
    checks={};inventory={};loaded={}
    for phase in ['00_normal','01_verify','02_response']:
        folder=evidence/phase;p=json.loads((folder/'problem.json').read_text());q=json.loads((folder/'result.json').read_text())
        validate=validate_response if phase=='02_response' else validate_dense
        v=validate(p,q['plan'],q['scope'],q['objective']);checks[phase+'_saved_plan_valid']=v['passed']
        cls=bed_initial_solver.Model if phase=='02_response' else dense_solver.DenseModel
        snapshot=model_snapshot(cls,p,q['scope']);write(out/(phase+'_model.json'),snapshot)
        inventory[phase]=dict(time=p['time'],stage=p['stage'],weights=p['weights'],
            task_count=len(p['tasks']),free=q['scope']['free'],owners=q['plan']['owners'],
            references=p['reference']['owners'],reference_starts=p['reference']['starts'],
            robot_sources={r:{k:v.get(k) for k in ['ready','source_anchor','capabilities']} for r,v in p['robots'].items()},
            objective=q['objective'],objective_parts=v['objective_parts'],validation=v,
            events=p['events'],input=str(folder/'problem.json'),input_sha256=hashlib.sha256((folder/'problem.json').read_bytes()).hexdigest())
        loaded[phase]=(p,q,cls,snapshot)

    p,q,cls,original=loaded['02_response'];probes=[]
    def probe(name,modify,expected):
        changed=deepcopy(p);modify(changed);s=model_snapshot(cls,changed,q['scope'])
        observed=dict(structure_changed=s['structure_sha256']!=original['structure_sha256'],
            objective_coefficients_changed=s['cost_sha256']!=original['cost_sha256'],
            objective_constant_delta=s['constant']-original['constant'])
        passed=all(abs(observed[k]-v)<1e-7 if isinstance(v,float) else observed[k]==v for k,v in expected.items())
        checks['probe_'+name]=passed
        probes.append(dict(name=name,expected=expected,observed=observed,passed=passed,
            interpretation='model-input sensitivity, not a solve or a physical counterfactual'))
    no_effect=dict(structure_changed=False,objective_coefficients_changed=False,objective_constant_delta=0.)
    probe('priority_urgency_metadata',lambda v:(v['events']['E1'].update(priority=999,urgency='critical'),
        v['tasks']['E1_monitor'].update(priority=999)),no_effect)
    probe('confidence_metadata',lambda v:v['events']['E1'].update(confidence=.01),no_effect)
    probe('workload_scalar_metadata',lambda v:v['robots']['r1'].update(workload=999),no_effect)
    probe('raw_position_without_anchor_update',lambda v:v['robots']['r1'].update(position=[-999.,-999.]),no_effect)
    probe('event_time_only',lambda v:v['events']['E1'].update(observed_at=p['events']['E1']['observed_at']+10.),
        dict(structure_changed=False,objective_coefficients_changed=False,objective_constant_delta=-20.*p['weights']['response']))
    probe('response_weight',lambda v:v['weights'].update(response=2*p['weights']['response']),dict(objective_coefficients_changed=True))
    probe('projected_ready',lambda v:v['robots']['r1'].update(ready=p['robots']['r1']['ready']+10.),dict(structure_changed=True))
    probe('source_anchor',lambda v:v['robots']['r1'].update(source_anchor='DL'),dict(structure_changed=True))
    probe('capability',lambda v:v['robots']['r1'].update(capabilities=['move']),dict(structure_changed=True))
    probe('known_dependency',lambda v:v['tasks']['C0_r1_W2'].update(dependencies=[]),dict(structure_changed=True))
    probe('resource_unavailability',lambda v:v['blocked_resources'].append(dict(resource='G1',start=0.,finish=1000.)),dict(structure_changed=True))
    checks['no_explicit_makespan_variable']=not any('cmax' in name.lower() or 'makespan' in name.lower() for name in original['variable_names'])
    checks['zero_energy_rates_in_saved_response']=all(v['move_rate']==v['idle_rate']==0. for v in p['robots'].values()) and all(t['energy_rate']==0. for t in p['tasks'].values())
    checks['normal_stage_assignment_frozen']=not loaded['00_normal'][1]['scope']['free']
    checks['response_not_all_normal_owners_free']=len(set(q['scope']['free'])&set(p['reference']['owners']))<len(p['reference']['owners'])
    checks['saved_response_normal_reference_is_release']=all(p['reference']['starts'][j]==p['tasks'][j]['release']
        for j in p['reference']['owners'] if p['tasks'][j]['kind']=='normal')
    parts=inventory['02_response']['objective_parts']
    checks['saved_response_shift_duplicates_release_wait']=abs(parts['shift']*p['weights']['normal_delay']-
        parts['normal_delay']*p['weights']['shift'])<1e-7
    cert=json.loads((evidence/'certificate.json').read_text())
    role_domains=dict(capability=capability_role_options(p),qualified=capability_role_options(p,cert['qualified_robots']))
    checks['capability_options_three_qualified_one']=len(role_domains['capability']['combinations'])==3 and len(role_domains['qualified']['combinations'])==1

    config=bed_contract.config();bridge=VisualEventBridge(config,source_id='audit-only')
    transition=bridge.observe(dict(sample_id='audit-candidate',source_id='audit-only',source_at=1.,
        score=.9,stable=True,window_ready=True),1.)
    view=bridge.protocol.planning_view();early=compile_tasks(view,1.,config,'A',dense_tasks.phases,cert)
    late=compile_tasks(view,2.,config,'A',dense_tasks.phases,cert)
    changed_cert=deepcopy(cert);changed_cert['qualified_robots']={role:['r3'] for role in cert['qualified_robots']}
    different_domain=compile_tasks(view,1.,config,'A',dense_tasks.phases,changed_cert)
    checks['candidate_only_creates_verify']=set(early)=={'E1_verify'}
    checks['certificate_owner_domain_not_compiled']=early==different_domain
    checks['compile_now_rebases_release_and_deadline']=late['E1_verify']['release']-early['E1_verify']['release']==1. and late['E1_verify']['start_deadline']-early['E1_verify']['start_deadline']==1.
    compilation=dict(candidate_decision=transition['decision'],early=early,later_same_view=late,
        robot_qualification_only_change=different_domain,scope='isolated model/compile probe, no images or execution ACKs')

    known=loaded['01_verify'][0];plan=loaded['01_verify'][1]['plan'];event=p['events']['E1']['observed_at']
    clocks=dict(candidate_at=event,verify_planning_at=known['time'],verify_task_release=known['tasks']['E1_verify']['release'],
        verify_plan_start=plan['starts']['E1_verify'],verify_response_as_implemented=plan['starts']['E1_verify']-known['time'],
        verify_response_from_candidate=plan['starts']['E1_verify']-event,
        response_planning_at=p['time'],monitor_release=p['tasks']['E1_monitor']['release'],
        response_formula='(monitor_start - event.observed_at) + (delivery_finish - event.observed_at)',
        verify_formula='verify_start - problem.time',completion_formula='sum(robot_route_end - robot.ready), weight return=.01; not makespan')
    checks['sources_unchanged']=all(hashlib.sha256(Path(path).read_bytes()).hexdigest()==h for path,h in before.items())
    write(out/'inventory.json',inventory);write(out/'sensitivity_probes.json',probes)
    write(out/'role_domains.json',role_domains);write(out/'compile_probes.json',compilation);write(out/'clock_contract.json',clocks)
    result=dict(passed=all(checks.values()),checks=checks,evidence=str(evidence),checks_count=len(checks),
        saved_plans_revalidated=3,sensitivity_probes=len(probes),new_solver_calls=0,ros_or_gazebo_started=False,
        meaning='PASS means audit findings reproduced, not all model capabilities present',
        performance_advantage='NOT_ESTABLISHED',novelty='NOT_ESTABLISHED')
    write(out/'summary.json',result);print(json.dumps(result,ensure_ascii=False));return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace',type=Path,default=DEFAULT_WORKSPACE)
    parser.add_argument('--evidence',type=Path,default=DEFAULT_EVIDENCE)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    raise SystemExit(0 if run(args.workspace,args.evidence,args.out)['passed'] else 1)
