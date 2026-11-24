"""Frozen capability cases, not B0/B1/B2/B3 performance comparisons.

The E1 source is an actual active-monitor snapshot. E2 positive/terminal facts
are explicitly controlled offline semantic assumptions, not observed new model
outputs or actual ACKs. Region B and new concurrency remain unqualified for
physical execution. Existing response limits and allocation weights are kept.
"""
import argparse
from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import event_model as model
import prepare_active as prepare
from solve_model import read, write
from kaiti_task_sim.clinic_visual import compile_tasks, registered_space
import dense_tasks


def positive_second(seed):
    p = prepare.prepare(seed)
    config = read(Path(read(seed)['sources']['runtime_configuration']['path']))
    event_id = 'E2'
    # This is a declared counterfactual review result at the saved state, not
    # an inference that verify success automatically established a fall.
    candidate_at = p['time']-10.
    confirmation = p['time']
    verified_at = p['time']-1.
    p['known_finishes']['E2_verify'] = verified_at
    p['semantic_fixture_facts'] = dict(E2_verify=dict(
        event_id='E2', role='verify', end=verified_at,
        source='CONTROLLED_OFFLINE_ASSUMED_VERIFY_AND_EXPLICIT_REVIEW',
        evidence_id='fixture-E2-verify-review', actual_execution=False))
    space = registered_space(config, 'B')
    view = dict(tasks=[])
    for role in ('monitor', 'pickup', 'deliver'):
        xy = config['anchors']['G1'][:2] if role == 'pickup' else space['service_points'][role]
        view['tasks'].append(dict(
            task_id=event_id+':'+role, role=role, revision=1, attempt=1,
            capabilities=['move', 'camera' if role == 'monitor' else 'carry'],
            completion_dependencies=[event_id+(':'+ 'pickup' if role == 'deliver' else ':verify')],
            target=dict(frame='map', xy=xy, space_revision=1)))
    compiled = compile_tasks(view, confirmation, config, 'B', dense_tasks.phases)
    for old_job, task in compiled.items():
        role = task['kind']
        job = event_id+'_'+role
        task.update(event_id=event_id, protocol_task_id=event_id+':'+role,
                    execution_authorized=False,
                    dependencies=[event_id+('_pickup' if role == 'deliver' else '_verify')])
        if role in {'pickup', 'deliver'}:
            task['cargo_group'] = event_id
        p['tasks'][job] = task
        p['allowed_robots'][job] = list(p['robots'])
    p['cargo_pairs'].append(['E2_pickup', 'E2_deliver'])
    p['event_index']['E2'] = dict(
        event_id=event_id, phase='CONFIRMED',
        tasks=dict(verify='E2_verify', monitor='E2_monitor',
                   pickup='E2_pickup', deliver='E2_deliver'),
        candidate_at=candidate_at, confirmed_at=confirmation,
        verification_source=dict(
            source='CONTROLLED_OFFLINE_ASSUMED_EXPLICIT_REVIEW',
            evidence_id='fixture-E2-positive-review', event_id='E2',
            actual_execution=False),
        position_valid=True, position_source='video_source_registered',
        handover_required=True,
        source_note='Counterfactual positive branch only; no new observation or verdict is claimed.')
    p['third_role_policies'].append(dict(
        event_id='E2', normal_task='C0_r1_W3',
        source='EXPLICIT_OFFLINE_EVENT_CONTINUITY_POLICY'))
    p['case_assumptions'] = dict(
        event_origins=dict(E1='OBSERVED_HISTORICAL_ACTIVE_EVENT',
                           E2='CONTROLLED_COUNTERFACTUAL_POSITIVE_BRANCH'),
        second_event_spatial_status='MODEL_ONLY_REGION_B_NOT_PHYSICALLY_QUALIFIED',
        third_role_policy='E1 original C0_r3_W2 retained; E2 explicitly uses the first named R1 suffix C0_r1_W3. No deployed multi-event policy is claimed.',
        actual_execution_authorized=False)
    return p


def cases(seed):
    active = prepare.prepare(seed)
    active['case_id'] = 'A1_active_E1_only'
    active['expected_status'] = 'PASS'
    candidate = prepare.prepare(seed, candidate=True)
    candidate['case_id'] = 'A2_active_E1_E2_candidate_verify_only'
    candidate['expected_status'] = 'PASS'
    concurrent = positive_second(seed)
    concurrent['case_id'] = 'A3_two_positive_monitor_intervals_overlap'
    concurrent['required_monitor_overlap'] = [['E1', 'E2']]
    concurrent['expected_status'] = 'PASS'
    station = deepcopy(concurrent)
    station['case_id'] = 'A4_shared_G1_existing_reservation'
    station['blocked_resources'].append(dict(
        resource='G1', start=station['time'], finish=station['time']+120.,
        source='CONTROLLED_OFFLINE_EXISTING_RESERVATION'))
    station['expected_status'] = 'PASS'
    insufficient = deepcopy(concurrent)
    insufficient['case_id'] = 'A5_one_camera_cannot_cover_two_overlapping_monitors'
    insufficient['robots']['r3']['capabilities'].remove('camera')
    insufficient['expected_status'] = 'INFEASIBLE'
    insufficient['case_assumptions']['capacity_change'] = (
        'Only r1 retains camera. Positive interval overlap is required as a '
        'structural concurrency test; no response deadline or weight is changed.')
    unknown = deepcopy(concurrent)
    unknown['case_id'] = 'A6_unknown_obstruction_requires_new_contract'
    unknown['issued_bindings']['E1_pickup']['state'] = 'BED_WAIT'
    unknown['expected_status'] = 'BLOCKED'
    return [active, candidate, concurrent, station, insufficient, unknown,
            sequential_after_actual_closure(seed)]


def sequential_after_actual_closure(seed):
    """Use a separate historical successful run, not a fabricated E1 release."""
    runroot = Path(os.environ.get('CLINIC_POSITIVE_RUN',
        '/home/yhc/clinic_planning_ws/verification/visual_positive_2026-11-18_c1/positive_02'))
    trace = runroot/'trace.jsonl'
    terminal, handover, completed = None, None, {}
    with trace.open() as stream:
        for number, line in enumerate(stream, 1):
            record = __import__('json').loads(line)
            phase = record.get('phase')
            if phase == 'job_completed' and record.get('record'):
                item = record['record']
                completed[item['job_id']] = deepcopy(item)
            elif phase == 'scripted_handover_ack' and record.get('event_id') == 'E1':
                handover = dict(event_id='E1', role='handover',
                                evidence_id='actual-trace-line:'+str(number),
                                source_line=number, source=record.get('source'))
            elif phase == 'online_commitment_check':
                check = record.get('check', {})
                if (check.get('protocol', {}).get('event') or {}).get('lifecycle') == 'COMPLETED':
                    terminal = deepcopy(check)
                    terminal['_source_line'] = number
    if terminal is None or handover is None or not all(
            state['job'] is None and state['cargo'] is None
            for state in terminal['states'].values()):
        raise ValueError('Sequential case needs an actual terminal idle state and own handover.')
    p = positive_second(seed)
    p['time'] = terminal['at']
    p['state_version'] = terminal['plan_revision']
    old = read(runroot/'02_response/problem.json')
    for job in old['tasks']:
        if job not in completed:
            raise ValueError('An old obligation would be omitted in sequential fixture: '+job)
    config = read(Path(read(seed)['sources']['runtime_configuration']['path']))
    p['tasks'] = {j:t for j, t in p['tasks'].items() if j.startswith('E2_')}
    shift = p['time']-p['event_index']['E2']['confirmed_at']
    for task in p['tasks'].values():
        task['release'] += shift
        if task.get('start_deadline') is not None:
            task['start_deadline'] += shift
    p['event_index']['E2']['confirmed_at'] += shift
    p['event_index']['E2']['candidate_at'] += shift
    p['active_bindings'], p['issued_bindings'], p['resource_leases'] = {}, {}, []
    p['hard_owners'], p['blocked_resources'], p['fixed_resources'] = {}, [], []
    p['third_role_policies'] = []
    p['reference'] = dict(owners={}, starts={}, finishes={},
                          routes={r:[] for r in p['robots']})
    p['known_finishes'] = {j:item['end'] for j, item in completed.items()}
    p['actual_known_finishes'] = deepcopy(p['known_finishes'])
    p['known_finishes']['E2_verify'] = p['time']-1.
    p['actual_history'] = {j:{
        key:item.get(key) for key in ('task_id', 'robot', 'job_id', 'status',
                                     'service_started', 'service_finished', 'end')}
        for j, item in completed.items()}
    p['preserved_protocol_snapshot'] = deepcopy(terminal['protocol'])
    # Keep actual identity/state fields, not unbounded navigation diagnostics
    # containing JSON-incompatible endpoint_error=Infinity. Full raw evidence
    # remains in the hash-bound historical trace; no planning scalar is changed.
    p['actual_snapshot'] = deepcopy(terminal['states'])
    for state in p['actual_snapshot'].values():
        record = state.get('record') or {}
        state['record'] = {key:deepcopy(record.get(key)) for key in (
            'task_id', 'job_id', 'robot', 'role', 'target', 'anchor', 'status',
            'begin', 'end', 'service_started', 'service_finished',
            'sent_revision', 'attempt', 'plan_revision')}
    receipts = {}
    for role in ('verify', 'monitor', 'pickup', 'deliver'):
        task = terminal['protocol']['tasks']['E1:'+role]
        if task['state'] != 'SUCCEEDED':
            raise ValueError('Actual event closure is incomplete.')
        receipts[role] = dict(
            event_id='E1', role=role, evidence_id='actual-protocol:E1:'+role,
            execution_revision=task['execution_revision'], attempt=task['attempt'],
            source_line=terminal['_source_line'])
    receipts['handover'] = handover
    p['event_index']['E1'] = dict(
        event_id='E1', phase='COMPLETED',
        tasks=dict(verify='E1_verify', monitor='E1_monitor',
                   pickup='E1_pickup', deliver='E1_deliver'),
        terminal_evidence=dict(
            event_id='E1', source='ACTUAL_HISTORICAL_PROTOCOL_AND_RECEIVER_TRACE',
            evidence_id='positive_02-terminal:'+str(terminal['_source_line']),
            role_receipts=receipts))
    for robot, state in terminal['states'].items():
        anchor = state['anchor']
        p['robots'][robot].update(source_anchor=anchor, ready=p['time'],
                                  position=config['anchors'][anchor][:2])
    p['allowed_robots'] = {j:list(p['robots']) for j in p['tasks']}
    p['cargo_pairs'] = [['E2_pickup', 'E2_deliver']]
    p['case_id'] = 'A7_actual_closed_E1_then_counterfactual_E2'
    p['expected_status'] = 'PASS'
    p['sequential_source'] = dict(
        trace=str(trace), trace_sha256=prepare.sha(trace),
        source_line=terminal['_source_line'],
        source_original_problem=str(runroot/'02_response/problem.json'),
        source_original_problem_sha256=prepare.sha(runroot/'02_response/problem.json'),
        scope='Independent positive_02 terminal state, not a temporal continuation of the bed_before_pickup_04 cases.')
    p['case_assumptions'] = dict(
        event_origins=dict(E1='ACTUAL_COMPLETED_POSITIVE_02',
                           E2='CONTROLLED_OFFLINE_POSITIVE_BRANCH_AFTER_E1'),
        no_actual_obligation_removed=True, new_execution_authorized=False)
    return p


def generate(seed, output):
    output.mkdir(parents=True, exist_ok=False)
    fixtures = cases(seed)
    for p in fixtures:
        folder = output/p['case_id']
        folder.mkdir()
        write(folder/'problem.json', p)
        write(folder/'preflight.json', model.preflight(p))
    sources = [HERE/name for name in (
        'event_model.py', 'prepare_active.py', 'solve_model.py',
        'capability_cases.py', 'event_registry.py')]
    sources += [model.WORKSPACE/'tools'/name for name in (
        'aligned_solver.py', 'aligned_contract.py', 'clinic_milp_backend.py',
        'clinic_plan_check.py')]
    write(output/'protocol.json', dict(
        frozen_before_solves=True, fixture_seed=str(seed),
        fixture_seed_sha256=prepare.sha(seed),
        source_manifest={str(p):prepare.sha(p) for p in sources},
        cases={p['case_id']:dict(
            input_sha256=model.digest(p), expected_status=p['expected_status'])
            for p in fixtures},
        budget_seconds=25., solver='UNCHANGED_CBC', solver_seed=17,
        response_limits_changed=False, objective_weights=model.FROZEN_WEIGHTS,
        method_comparison='NOT_RUN_B0_B1_B2_B3_NOT_ALL_ADAPTED',
        interpretation='Capability and independently checked feasibility only; no speed ranking, actual E2 execution, or algorithm superiority claim.'))
    print('Frozen', len(fixtures), 'capability inputs')


def run(output):
    protocol = read(output/'protocol.json')
    for path, expected in protocol['source_manifest'].items():
        if prepare.sha(Path(path)) != expected:
            raise RuntimeError('Frozen source changed: '+path)
    for name, expected in protocol['cases'].items():
        problem = output/name/'problem.json'
        if model.digest(read(problem)) != expected['input_sha256']:
            raise RuntimeError('Frozen input changed: '+name)
        result_dir = output/name/'solve'
        if result_dir.exists():
            raise FileExistsError(str(result_dir))
        process = subprocess.run([
            sys.executable, str(HERE/'solve_model.py'), 'solve',
            '--source', str(problem), '--output', str(result_dir),
            '--budget', str(protocol['budget_seconds'])],
            text=True, capture_output=True, timeout=60.)
        (output/name/'worker.log').write_text(process.stdout+process.stderr)
        if process.returncode:
            raise RuntimeError(process.stderr[-2000:])
        result = read(result_dir/'result.json')
        print(name, result['status'], 'expected', expected['expected_status'], flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['generate', 'run'])
    parser.add_argument('--seed', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.mode == 'generate':
        generate(args.seed, args.output)
    else:
        run(args.output)
