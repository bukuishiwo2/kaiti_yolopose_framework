"""Controlled protocol fixtures; none are new camera or execution evidence."""
from copy import deepcopy
import os
from pathlib import Path
import sys
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from event_registry import MultiEventRegistry, EventTaskProtocol, ProtocolError

ROBOTS = dict(r1=['move', 'camera'], r2=['move', 'carry'],
              r3=['move', 'camera', 'carry'])
CLINIC_WORKSPACE = Path(os.environ.get('CLINIC_WORKSPACE', '/home/yhc/clinic_planning_ws')).expanduser()
ACTIVE_FIXTURE = CLINIC_WORKSPACE/'verification/multievent_2026-11-23_k1/active_monitor_fixture_seed_01.json'


def observation(event_id, at):
    return dict(
        schema='event-task/v1', kind='observation',
        message_id=event_id+':observation:'+str(at),
        event_id=event_id, at=at, source_at=at, status='confirmed',
        space=dict(valid=True, frame='map', event_xy=[1., 2.],
                   service_points=dict(verify=[1., 2.], monitor=[2., 2.],
                                       deliver=[2., 3.])))


def feedback(registry, event_id, role, phase, at, robot):
    task = registry.instances[event_id].tasks[event_id+':'+role]
    return dict(
        schema='event-task/v1', kind='feedback',
        message_id=event_id+':'+role+':'+phase+':'+str(at),
        event_id=event_id, task_id=event_id+':'+role,
        task_revision=task.get('execution_revision') or task['revision'],
        attempt=task['attempt'], robot_id=robot, phase=phase, at=at)


def verified(registry, event_id, at):
    registry.apply(observation(event_id, at))
    registry.apply(feedback(registry, event_id, 'verify', 'started', at+.1, 'r3'))
    registry.apply(
        feedback(registry, event_id, 'verify', 'succeeded', at+.2, 'r3'),
        dict(event_id=event_id, result='fall', source='CONTROLLED_TEST_FIXTURE',
             evidence_id=event_id+':explicit-review'))


def test_second_event_does_not_replace_active_first_monitor():
    registry = MultiEventRegistry(ROBOTS)
    verified(registry, 'E1', 1.)
    registry.apply(feedback(registry, 'E1', 'monitor', 'started', 1.3, 'r1'))
    before = deepcopy(registry.instances['E1'].tasks['E1:monitor'])
    registry.apply(observation('E2', 1.4))
    assert registry.instances['E1'].tasks['E1:monitor'] == before
    assert registry.instances['E2'].event['verified'] is False
    assert set(registry.instances['E2'].tasks) == {'E2:verify'}
    assert registry.snapshot()['execution_authorized'] is False


def test_cross_event_robot_commitment_and_identity_rejections_are_atomic():
    registry = MultiEventRegistry(ROBOTS)
    verified(registry, 'E1', 1.)
    registry.apply(feedback(registry, 'E1', 'monitor', 'started', 1.3, 'r1'))
    registry.apply(observation('E2', 1.4))
    before = registry.snapshot()
    with pytest.raises(ProtocolError):
        registry.apply(feedback(registry, 'E2', 'verify', 'started', 1.5, 'r1'))
    assert registry.snapshot() == before
    wrong = feedback(registry, 'E2', 'verify', 'started', 1.5, 'r3')
    wrong['task_id'] = 'E1:verify'
    with pytest.raises(ProtocolError):
        registry.apply(wrong)
    assert registry.snapshot() == before


def test_cargo_and_handover_stay_event_scoped():
    registry = MultiEventRegistry(ROBOTS)
    verified(registry, 'E1', 1.)
    registry.apply(feedback(registry, 'E1', 'monitor', 'started', 1.3, 'r1'))
    verified(registry, 'E2', 1.4)
    registry.apply(feedback(registry, 'E2', 'monitor', 'started', 1.7, 'r3'))
    registry.apply(feedback(registry, 'E1', 'pickup', 'started', 1.8, 'r2'))
    registry.apply(feedback(registry, 'E1', 'pickup', 'succeeded', 1.9, 'r2'))
    before = registry.snapshot()
    with pytest.raises(ProtocolError):
        registry.apply(feedback(registry, 'E2', 'pickup', 'started', 2., 'r2'))
    assert registry.snapshot() == before
    registry.apply(feedback(registry, 'E1', 'deliver', 'started', 2., 'r2'))
    registry.apply(feedback(registry, 'E1', 'deliver', 'succeeded', 2.1, 'r2'))
    with pytest.raises(ProtocolError):
        registry.apply(feedback(registry, 'E1', 'monitor', 'succeeded', 2.2, 'r1'))
    delivery = registry.instances['E1'].tasks['E1:deliver']
    receipt = dict(event_id='E1', at=2.2, source='CONTROLLED_TEST_RECEIVER',
                   evidence_id='receiver-E1', task_id='E1:deliver', robot_id='r2',
                   attempt=delivery['attempt'],
                   task_revision=delivery['execution_revision'])
    wrong = dict(receipt, event_id='E2')
    with pytest.raises(ProtocolError):
        registry.accept_handover(wrong)
    registry.accept_handover(receipt)
    registry.apply(feedback(registry, 'E1', 'monitor', 'succeeded', 2.3, 'r1'))
    assert registry.instances['E1'].event['lifecycle'] == 'COMPLETED'
    assert registry.instances['E2'].event['lifecycle'] == 'OPEN'
    assert registry.instances['E2'].tasks['E2:monitor']['state'] == 'RUNNING'


def test_verify_service_success_requires_bound_explicit_verdict():
    registry = MultiEventRegistry(ROBOTS)
    registry.apply(observation('E1', 1.))
    registry.apply(feedback(registry, 'E1', 'verify', 'started', 1.1, 'r3'))
    done = feedback(registry, 'E1', 'verify', 'succeeded', 1.2, 'r3')
    before = registry.snapshot()
    for verdict in (None, dict(event_id='E2', result='fall',
                               source='CONTROLLED_TEST_FIXTURE', evidence_id='wrong-event')):
        with pytest.raises(ProtocolError):
            registry.apply(done, verdict)
        assert registry.snapshot() == before
    registry.apply(done, dict(event_id='E1', result='no_fall',
                             source='CONTROLLED_TEST_FIXTURE', evidence_id='negative-review'))
    assert registry.instances['E1'].event['lifecycle'] == 'CLOSED'
    assert not registry.instances['E1'].planning_view()['tasks']


def test_single_event_core_states_match_unchanged_protocol_before_handover():
    registry = MultiEventRegistry(ROBOTS)
    legacy = EventTaskProtocol()
    first = observation('E1', 1.)
    registry.apply(first)
    legacy.apply(first)
    assert registry.instances['E1'].snapshot() == legacy.snapshot()
    for role, phase, at, robot in [
            ('verify', 'started', 1.1, 'r3'),
            ('verify', 'succeeded', 1.2, 'r3'),
            ('monitor', 'started', 1.3, 'r1')]:
        message = feedback(registry, 'E1', role, phase, at, robot)
        explicit = (dict(event_id='E1', result='fall',
                         source='CONTROLLED_TEST_FIXTURE', evidence_id='review')
                    if role == 'verify' and phase == 'succeeded' else None)
        registry.apply(message, explicit)
        original_message = deepcopy(message)
        if explicit:
            original_message['result'] = explicit['result']
        legacy.apply(original_message)
        assert registry.instances['E1'].snapshot() == legacy.snapshot()


def test_redelivered_explicit_verdict_is_deduplicated_without_rewriting_event():
    registry = MultiEventRegistry(ROBOTS)
    registry.apply(observation('E1', 1.))
    registry.apply(feedback(registry, 'E1', 'verify', 'started', 1.1, 'r3'))
    message = feedback(registry, 'E1', 'verify', 'succeeded', 1.2, 'r3')
    verdict = dict(event_id='E1', result='fall', source='CONTROLLED_TEST_FIXTURE',
                   evidence_id='reviewed-E1')
    registry.apply(message, verdict)
    tasks = deepcopy(registry.instances['E1'].tasks)
    again = dict(message, at=1.3)
    assert registry.apply(again, verdict)['decision'] == 'DUPLICATE_MESSAGE'
    assert registry.instances['E1'].tasks == tasks


@pytest.mark.skipif(not ACTIVE_FIXTURE.is_file(), reason='historical active-monitor snapshot is not part of a clean repository checkout')
def test_historical_registered_event_import_preserves_monitor_when_E2_arrives():
    import json
    evidence = CLINIC_WORKSPACE/'verification/multievent_2026-11-23_k1'
    seed_path = evidence/'active_monitor_fixture_seed_01.json'
    seed = json.loads(seed_path.read_text())
    registry = MultiEventRegistry(ROBOTS)
    observed = seed['snapshot']['protocol']
    registry.import_event(
        observed, seed['sources']['actual_snapshot'],
        registration=seed['snapshot']['evidence_validity']['registration'])
    before = deepcopy(registry.instances['E1'].tasks['E1:monitor'])
    at = seed['snapshot']['at']+.01
    registry.apply(observation('E2', at))
    assert registry.instances['E1'].tasks['E1:monitor'] == before
    assert set(registry.planning_view()['events']) == {'E1', 'E2'}
    with pytest.raises(ProtocolError):
        registry.import_event(observed, seed['sources']['actual_snapshot'],
                              registration=seed['snapshot']['evidence_validity']['registration'])


@pytest.mark.skipif(not ACTIVE_FIXTURE.is_file(), reason='historical active-monitor snapshot is not part of a clean repository checkout')
def test_historical_import_rejects_changed_state_or_forged_registration():
    import json
    seed = json.loads(ACTIVE_FIXTURE.read_text())
    source = seed['sources']['actual_snapshot']
    observed = seed['snapshot']['protocol']
    registration = seed['snapshot']['evidence_validity']['registration']
    wrong = deepcopy(observed)
    wrong['tasks']['E1:monitor']['owner'] = 'r3'
    for snapshot, evidence in (
            (wrong, registration),
            (observed, dict(registration, valid_until=99999.))):
        registry = MultiEventRegistry(ROBOTS)
        with pytest.raises(ProtocolError):
            registry.import_event(snapshot, source, registration=evidence)
        assert not registry.instances
