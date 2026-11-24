"""Compile the hash-bound historical active monitor without inventing ACKs.

The optional second event is an explicitly labelled model candidate and releases
VERIFY only. Positive response branches require a later, separately represented
explicit verdict; this compiler does not manufacture one.
"""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT/'src'))
import event_model as indexed
from kaiti_task_sim.clinic_visual import compile_tasks, registered_space
import dense_tasks


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write(chr(10))


def prepare(seed_path, candidate=False):
    seed = read(seed_path)
    for source in seed['sources'].values():
        if sha(Path(source['path'])) != source['sha256']:
            raise ValueError('Historical source changed: '+source['path'])
    snapshot = seed['snapshot']
    config = read(Path(seed['sources']['runtime_configuration']['path']))
    p = deepcopy(seed['original_pre_monitor_problem'])
    p['time'] = snapshot['at']
    p['state_version'] = snapshot['plan_revision']
    p['original_runtime_weights'] = deepcopy(p['weights'])
    p['objective_contract'] = 'UNCHANGED_INDEPENDENT_DYNAMIC_ASSIGNMENT_CONTRACT_2026-11-18'
    p['weights'] = {
        'travel':.1, 'normal_delay':.1, 'response':0., 'wait':0.,
        'energy':0., 'owner':2., 'shift':.05, 'adjacency':0., 'return':0.}
    p['assignment_weights'] = deepcopy(indexed.FROZEN_WEIGHTS)
    completed = snapshot['completed_actual_records']
    p['tasks'] = {
        job:deepcopy(task) for job, task in snapshot['tasks'].items()
        if job not in completed}
    p['known_finishes'] = {}
    for job, record in completed.items():
        if not isinstance(record.get('end'), (float, int)):
            raise ValueError('Actual completion time missing: '+job)
        p['known_finishes'][job] = record['end']
    p['actual_known_finishes'] = deepcopy(p['known_finishes'])
    p['actual_history'] = deepcopy(completed)
    p['preserved_protocol_snapshot'] = deepcopy(snapshot['protocol'])
    p['actual_snapshot'] = deepcopy(snapshot['states'])
    p['source_seed'] = dict(path=str(seed_path), sha256=sha(seed_path))
    p['active_bindings'], p['issued_bindings'] = {}, {}
    p['hard_owners'] = {}
    p['allowed_robots'] = {job:list(p['robots']) for job in p['tasks']}
    p['cargo_pairs'] = [['E1_pickup', 'E1_deliver']]
    for job, task in p['tasks'].items():
        task['execution_authorized'] = False
        if job.startswith('E1_'):
            task['event_id'] = 'E1'
    binding = deepcopy(seed['semantic_bindings']['active_monitor'])
    binding.update(mode='monitor_continuation',
                   actual_started_at=binding.pop('actual_started_at'),
                   record_task_id=binding['actual_record_task_id'],
                   original_start_deadline=p['tasks']['E1_monitor'].get('start_deadline'),
                   original_finish_deadline=p['tasks']['E1_monitor']['deadline'],
                   original_minimum_duration=p['tasks']['E1_monitor']['minimum_duration'])
    monitor_task = p['tasks']['E1_monitor']
    monitor_task['minimum_duration'] = max(
        0., monitor_task['minimum_duration']-(p['time']-binding['actual_started_at']))
    monitor_task['start_deadline'] = None
    p['active_bindings']['E1_monitor'] = binding
    p['hard_owners']['E1_monitor'] = binding['owner']
    for robot, state in snapshot['states'].items():
        anchor = monitor_task['anchor'] if robot == binding['owner'] else state['anchor']
        if anchor not in p['travel_times']:
            raise ValueError('No frozen travel prior for actual source anchor: '+anchor)
        p['robots'][robot].update(
            source_anchor=anchor, ready=p['time'],
            position=deepcopy(config['anchors'][anchor][:2]))
        job = state.get('job')
        if job and job != 'E1_monitor':
            if job not in p['tasks']:
                raise ValueError('Issued task omitted from remaining graph: '+job)
            record = state.get('record') or {}
            p['issued_bindings'][job] = dict(
                owner=robot, state=state['state'],
                record_task_id=record.get('task_id'), goal=deepcopy(record.get('target')),
                plan_revision=record.get('plan_revision'),
                sent_revision=record.get('sent_revision'),
                note='Navigation identity and goal retained; absent service token fields are not fabricated.')
            p['hard_owners'][job] = robot
    original_plan = snapshot['accepted_plan']
    soft = set(p['tasks'])-set(p['active_bindings'])
    p['reference'] = {
        key:{job:value for job, value in original_plan[key].items() if job in soft}
        for key in ('owners', 'starts', 'finishes')}
    p['reference']['routes'] = {
        robot:[job for job in route if job in soft]
        for robot, route in original_plan['routes'].items()}
    p['resource_leases'] = []
    for resource, lease in snapshot['resource_leases'].get('owners', {}).items():
        holders = [
            job for job, record in p['issued_bindings'].items()
            if record['record_task_id'] == lease.get('lease_id')]
        if len(holders) != 1:
            raise ValueError('Actual lease lacks a represented immutable holder: '+resource)
        p['resource_leases'].append(dict(
            resource=resource, holder_task=holders[0],
            lease_id=lease['lease_id'], owner=lease['robot'],
            source=deepcopy(lease)))
    retired = []
    retained = []
    for lock in p.get('blocked_resources', []):
        if lock.get('job') in completed and lock['resource'] not in snapshot['resource_leases'].get('owners', {}):
            retired.append(dict(lock=deepcopy(lock),
                                reason='Original pre-monitor projection superseded by actual completion and current lease state.'))
        else:
            retained.append(deepcopy(lock))
    p['blocked_resources'] = retained
    p['retired_old_projection_locks'] = retired
    p['fixed_resources'] = []
    old_event = snapshot['protocol']['event']
    verify = snapshot['protocol']['tasks']['E1:verify']
    p['event_index'] = dict(E1=dict(
        event_id='E1', phase='ACTIVE',
        tasks=dict(verify='E1_verify', monitor='E1_monitor',
                   pickup='E1_pickup', deliver='E1_deliver'),
        candidate_at=snapshot['tasks']['E1_verify']['release'],
        confirmed_at=verify['finished_at'],
        verification_source=deepcopy(seed['sources']['original_explicit_review']),
        position_valid=old_event['position_valid'],
        position_source=old_event['space']['provenance'],
        handover_required=True, clearance_task='E1_monitor_clear',
        clearance_margin=8.,
        source_note='Observed E1 state and start are preserved. Only future occupations are optimized.'))
    p['hard_owners']['E1_monitor_clear'] = binding['owner']
    p['third_role_policies'] = [
        dict(event_id='E1', normal_task='C0_r3_W2')]
    p['events'] = {}
    if candidate:
        space = registered_space(config, 'B')
        task = dict(
            task_id='E2:verify', role='verify', revision=1, attempt=1,
            capabilities=['move', 'camera'], completion_dependencies=[],
            target=dict(frame='map', xy=space['service_points']['verify'],
                        space_revision=1))
        compiled = compile_tasks(
            dict(tasks=[task]), p['time'], config, 'B', dense_tasks.phases)['E1_verify']
        compiled.update(event_id='E2', protocol_task_id='E2:verify',
                        execution_authorized=False)
        p['tasks']['E2_verify'] = compiled
        p['allowed_robots']['E2_verify'] = list(p['robots'])
        p['event_index']['E2'] = dict(
            event_id='E2', phase='CANDIDATE', tasks=dict(verify='E2_verify'),
            candidate_at=p['time'], confirmed_at=None,
            position_valid=True, position_source='video_source_registered',
            event_origin='EXPLICIT_OFFLINE_MODEL_CANDIDATE_NOT_A_NEW_IMAGE_OBSERVATION',
            response_release='BLOCKED_UNTIL_OWN_VERIFY_AND_EXPLICIT_FALL_VERDICT',
            spatial_execution_status='MODEL_ONLY_REGION_B_NOT_PHYSICALLY_QUALIFIED')
    p['physical_execution_authorized'] = False
    p['planning_assumptions'] = dict(
        travel='Frozen anchor travel priors; an issued robot retains its current goal. These are forecasts, not actual arrival ACKs.',
        continuing_monitor='Residual interval begins at snapshot time; actual start and execution identity remain in active_bindings.',
        event_closure='No plan output changes an actual event lifecycle.',
        qualification='No new navigation, concurrency or alternative-role execution qualification.',
        hidden_obstacle_truth_used=False)
    return p


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--seed', type=Path, required=True)
    parser.add_argument('--mode', choices=['active-single', 'concurrent-candidate'], required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    problem = prepare(args.seed, args.mode == 'concurrent-candidate')
    write(args.output/'problem.json', problem)
    write(args.output/'protocol.json', dict(
        frozen_before_solve=True, input_sha256=indexed.digest(problem),
        seed_sha256=sha(args.seed),
        source_manifest={str(path):sha(path) for path in (
            Path(__file__), HERE/'event_model.py', HERE/'solve_model.py',
            ROOT/'src/kaiti_task_sim/clinic_visual.py',
            indexed.WORKSPACE/'tools/dense_tasks.py')},
        mode=args.mode, execution_authorized=False))
    gate = indexed.preflight(problem)
    write(args.output/'preflight.json', gate)
    print(json.dumps(dict(status=gate['status'], errors=gate['errors'],
                          events=list(problem['event_index']),
                          remaining_tasks=len(problem['tasks'])), ensure_ascii=False))
    sys.exit(0 if gate['passed'] else 2)
