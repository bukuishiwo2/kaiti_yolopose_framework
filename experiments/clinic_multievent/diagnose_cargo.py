"""Read-only causal diagnosis of the historical S4 cargo representations.

The selected snapshot is not a new execution result. This module never changes
the runtime, releases a commitment, predicts an actual unblock, or sends an ACK.
Missing execution-token fields remain missing in the diagnostic output.
"""
import argparse
import hashlib
import json
from pathlib import Path


DEFAULT_EVIDENCE = Path(
    '/home/yhc/clinic_planning_ws/verification/multievent_2026-11-23_k1')
HISTORICAL_RUN = Path(
    '/home/yhc/clinic_planning_ws/verification/visual_bed_2026-11-18_d1/'
    'bed_before_pickup_01')
WORKSPACE = Path('/home/yhc/clinic_planning_ws')


def read(path):
    return json.loads(path.read_text())


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1048576), b''):
            digest.update(block)
    return digest.hexdigest()


def source_lines(path, fragments):
    """Locate corroborating source statements without importing the runtime."""
    lines = path.read_text().splitlines()
    return dict(path=str(path), sha256=sha(path), statements=[
        dict(line=number, text=line.strip())
        for number, line in enumerate(lines, 1)
        if any(fragment in line for fragment in fragments)])


def diagnose(evidence_root):
    snapshot_path = HISTORICAL_RUN/'repair_03/problem.json'
    snapshot = read(snapshot_path)
    receipts_path = evidence_root/'bed_before_pickup_01_actual_receipts.json'
    receipts = read(receipts_path)
    trace_path = Path(receipts['source'])
    if sha(trace_path) != receipts['source_sha256']:
        raise ValueError('Original trace differs from the extracted evidence.')

    robot, event_id = 'r2', 'E1'
    actual = snapshot['actual_snapshot'][robot]
    projected = snapshot['snapshot_states'][robot]
    commitment = snapshot['active_commitments'][robot]
    execution_id = 'bed_before_pickup_01:E1_pickup:r2'
    worker_acks = [
        row for row in receipts['selected_actual_receipts']
        if row['phase'] == 'service_feedback'
        and (row.get('feedback') or {}).get('task_id') == execution_id
        and row['feedback'].get('phase') == 'succeeded']
    protocol_acks = [
        row for row in receipts['selected_actual_receipts']
        if row['phase'] == 'visual_execution_protocol_feedback'
        and (row.get('message') or {}).get('event_id') == event_id
        and row['message'].get('task_id') == 'E1:pickup'
        and row['message'].get('phase') == 'succeeded']
    if len(worker_acks) != 1 or len(protocol_acks) != 1:
        raise ValueError('Expected one actual worker/protocol pickup ACK pair.')

    worker, protocol = worker_acks[0], protocol_acks[0]
    feedback, message = worker['feedback'], protocol['message']
    event = protocol.get('event_snapshot') or {}
    source = source_lines(WORKSPACE/'tools/bed_contract.py', [
        'proxy[rid].update(job=None,cargo=None,anchor=anchor)',
        "p['actual_snapshot']=deepcopy(states)",
        "cargo_at_snapshot=s.get('cargo')"])
    normalizer = source_lines(WORKSPACE/'tools/dense_tasks.py', [
        'snapshot_states=states'])
    checks = dict(
        actual_cargo_matches_commitment=(
            actual.get('cargo') == commitment.get('cargo_at_snapshot') == event_id),
        actual_delivery_identity_matches_commitment=(
            actual.get('job') == 'E1_deliver'
            and actual.get('record', {}).get('task_id')
            == commitment.get('record_task_id')),
        actual_goal_matches_commitment=(
            actual.get('record', {}).get('target') == commitment.get('goal')),
        projected_state_is_a_cleared_suffix_source=(
            projected.get('cargo') is None and projected.get('job') is None),
        explicit_proxy_construction_found=any(
            'proxy[rid].update(job=None,cargo=None,anchor=anchor)' in row['text']
            for row in source['statements']),
        worker_and_protocol_owner_match=(
            feedback.get('robot') == message.get('robot_id') == robot),
        worker_and_protocol_attempt_match=(
            feedback.get('attempt') == message.get('attempt') == 1),
        worker_and_protocol_revision_match=(
            feedback.get('task_revision') == message.get('task_revision') == 1),
        worker_protocol_episode_time_match=not (
            abs(worker['episode_time']-protocol['episode_time']) > 1e-6),
        pickup_ack_precedes_snapshot=(
            snapshot['time'] >= protocol['episode_time']),
        protocol_custody_matches_actual=(
            event.get('event_id') == event_id
            and event.get('cargo_owner') == robot
            and event.get('cargo_disposition') == 'IN_CUSTODY'))
    classification = (
        'LEGAL_DIFFERENT_REPRESENTATION'
        if all(checks.values()) else 'INSUFFICIENT_OR_CONFLICTING_EVIDENCE')
    current_record = actual.get('record') or {}
    manifest_path = HISTORICAL_RUN/'visual_source_manifest.json'
    manifest = read(manifest_path)
    source_identity = dict(
        manifest_path=str(manifest_path), manifest_sha256=sha(manifest_path),
        current_projector_sha256=source['sha256'],
        directly_listed_projector_hash=(
            manifest.get(str(WORKSPACE/'tools/bed_contract.py'))
            if isinstance(manifest, dict) else None),
        limitation='Source statements are corroboration; no executed-version identity is inferred from a missing manifest entry.')
    return dict(
        schema='clinic-cargo-readonly-diagnosis/v1',
        status='PASS_READ_ONLY_DIAGNOSIS' if all(checks.values()) else 'UNKNOWN',
        classification=classification, checks=checks,
        snapshot=dict(path=str(snapshot_path), sha256=sha(snapshot_path),
                      episode_time=snapshot['time']),
        original_trace=dict(path=str(trace_path), sha256=receipts['source_sha256']),
        pickup_worker_ack=worker, pickup_protocol_ack=protocol,
        actual_cargo=actual.get('cargo'),
        commitment_cargo=commitment.get('cargo_at_snapshot'),
        normalized_proxy_cargo=projected.get('cargo'),
        pickup_known_finish=snapshot.get('actual_known_finishes', {}).get('E1_pickup'),
        clock_note='Compare episode_time with episode_time. Worker feedback.at is ROS time; it is retained without subtracting it from the episode clock.',
        active_delivery_token_fields={
            key:current_record.get(key)
            for key in ('task_id', 'job_id', 'attempt', 'sent_revision',
                        'protocol_task_id', 'plan_revision')},
        token_scope='The pickup ACK pair binds attempt/revision 1. Missing delivery token fields are not filled from pickup tokens; this is not a complete delivery-token audit.',
        projector_source=source, normalizer_source=normalizer,
        source_identity=source_identity,
        unknown_obstruction_recovery=dict(
            status='BLOCKED_EXECUTION_RECOVERY',
            conditional_plan='Any future schedule depends on an explicitly labelled obstacle-clear assumption and a finite validity horizon.',
            rolling_horizon='Forecast expiry requests a fresh observation and plan; expiry is not a completion or cancellation ACK.',
            dispatch_gate=[
                'Fresh observed path clearance and unchanged navigation guards',
                'Current task revision, attempt, owner and execution token',
                'Actual resource lease and dependency acknowledgements'],
            preserved_obligations=[
                'r2 retains E1 cargo until actual delivery or a separately qualified handover',
                'E1 monitoring continues until actual delivery and handover evidence',
                'Existing issued goals are not cancelled without the original ACK protocol'],
            unsupported=[
                'Cargo handover between robots',
                'Active monitor handover',
                'Guaranteed recovery time for an obstruction with unknown end']),
        physical_cargo_loss_claim=False, runtime_modified=False,
        navigation_dispatched=False, recovery_backend_implemented=False)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--evidence-root', type=Path, default=DEFAULT_EVIDENCE)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError('Existing diagnostic evidence must not be overwritten.')
    result = diagnose(args.evidence_root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2)+chr(10))
    print(json.dumps(dict(status=result['status'],
                          classification=result['classification'],
                          checks=result['checks']), ensure_ascii=False))


if __name__ == '__main__':
    main()
