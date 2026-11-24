"""Model acceptance, identity mutations and unavailable-state boundaries."""
from copy import deepcopy
import os
from pathlib import Path
import sys
import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import event_model as model
import capability_cases
import solve_model

CLINIC_WORKSPACE = Path(os.environ.get('CLINIC_WORKSPACE', '/home/yhc/clinic_planning_ws')).expanduser()
EVIDENCE = CLINIC_WORKSPACE/'verification/multievent_2026-11-23_k1'
SEED = EVIDENCE/'active_monitor_fixture_seed_01.json'
pytestmark = pytest.mark.skipif(not SEED.is_file(), reason='real active-monitor snapshot is not part of a clean repository checkout')


def fixture():
    source = EVIDENCE/'capability_dev_01/A3_two_positive_monitor_intervals_overlap'
    problem = solve_model.read(source/'problem.json')
    result = solve_model.read(source/'solve/result.json')
    assert result['status'] == 'PASS'
    return problem, result['plan']


def test_frozen_success_preserves_active_execution_and_both_events():
    p, plan = fixture()
    assert model.validate(p, plan)['passed']
    binding = p['active_bindings']['E1_monitor']
    assert plan['owners']['E1_monitor'] == binding['owner'] == 'r1'
    assert binding['actual_started_at'] < p['time']
    assert plan['starts']['E1_monitor'] == p['time']
    assert all(j in plan['owners'] for j in ('E1_monitor', 'E2_monitor', 'E1_pickup', 'E2_pickup'))


def test_service_identity_swap_and_missing_monitor_are_blocked():
    p, _ = fixture()
    swapped = deepcopy(p)
    swapped['tasks']['E2_monitor']['event_id'] = 'E1'
    assert model.preflight(swapped)['status'] == 'BLOCKED'
    missing = deepcopy(p)
    missing['tasks'].pop('E1_monitor')
    assert model.preflight(missing)['status'] == 'BLOCKED'


def test_wrong_close_or_other_event_receipts_cannot_drop_obligations():
    p, _ = fixture()
    p['event_index']['E1']['phase'] = 'COMPLETED'
    p['event_index']['E1']['terminal_evidence'] = dict(
        event_id='E2', source='CONTROLLED_NEGATIVE_TEST', evidence_id='wrong-close')
    assert model.preflight(p)['status'] == 'BLOCKED'


@pytest.mark.parametrize('mutation', [
    'active_owner', 'issued_owner', 'early_release', 'shared_G1_overlap',
    'cross_event_cargo_owner', 'old_version', 'lost_execution_identity'])
def test_independent_checker_rejects_illegal_plan_mutations(mutation):
    p, plan = fixture()
    q = deepcopy(plan)
    if mutation == 'active_owner':
        q['owners']['E1_monitor'] = 'r3'
    elif mutation == 'issued_owner':
        q['owners']['E1_pickup'] = 'r3'
    elif mutation == 'early_release':
        q['finishes']['E1_monitor'] = p['time']+.1
    elif mutation == 'shared_G1_overlap':
        q['starts']['E2_pickup'] = q['starts']['E1_pickup']
        q['finishes']['E2_pickup'] = q['starts']['E1_pickup']+p['tasks']['E2_pickup']['duration']
    elif mutation == 'cross_event_cargo_owner':
        q['owners']['E2_deliver'] = 'r1'
    elif mutation == 'old_version':
        q['state_version'] -= 1
    else:
        q['retained_active_bindings']['E1_monitor']['attempt'] += 1
    assert not model.validate(p, q)['passed']


def test_residual_minimum_is_equivalent_to_actual_started_minimum():
    p, _ = fixture()
    binding = p['active_bindings']['E1_monitor']
    minimum = binding['original_minimum_duration']
    residual = p['tasks']['E1_monitor']['minimum_duration']
    assert residual == max(0., minimum-(p['time']-binding['actual_started_at']))
    for finish in (p['time']-.1, p['time'], p['time']+.1,
                   binding['actual_started_at']+minimum, p['time']+100.):
        old = finish >= p['time'] and finish >= binding['actual_started_at']+minimum
        new = finish >= p['time']+residual
        assert old == new


@pytest.mark.skipif(not (CLINIC_WORKSPACE/'verification/visual_positive_2026-11-18_c1/positive_02/trace.jsonl').is_file(),
                    reason='historical positive execution trace is not part of a clean repository checkout')
def test_sequential_fixture_closes_only_actual_E1_and_keeps_new_E2_separate():
    p = capability_cases.sequential_after_actual_closure(SEED)
    assert model.preflight(p)['passed']
    assert p['event_index']['E1']['phase'] == 'COMPLETED'
    assert p['event_index']['E2']['phase'] == 'CONFIRMED'
    assert all(j.startswith('E2_') for j in p['tasks'])
    assert p['sequential_source']['trace'].endswith('positive_02/trace.jsonl')
    assert p['event_index']['E2']['verification_source']['actual_execution'] is False


def test_same_G1_constraints_retained_and_no_response_threshold_or_weight_change():
    p = capability_cases.positive_second(SEED)
    assert p['tasks']['E1_pickup']['resources'] == p['tasks']['E2_pickup']['resources'] == ['G1']
    assert p['assignment_weights'] == model.FROZEN_WEIGHTS
    event = p['event_index']['E2']
    assert p['tasks']['E2_monitor']['start_deadline'] == event['confirmed_at']+360.
    assert p['third_role_policies'][0]['event_id'] == 'E1'


def test_unknown_blockage_stays_blocked_not_fake_fixed_ready_success():
    p = capability_cases.positive_second(SEED)
    p['issued_bindings']['E1_pickup']['state'] = 'BED_WAIT'
    assert model.preflight(p)['status'] == 'BLOCKED'
