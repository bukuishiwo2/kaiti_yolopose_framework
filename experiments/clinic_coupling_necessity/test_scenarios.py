"""Safety and fairness checks of new fixtures, not deployment/S1 tests."""
from copy import deepcopy
import importlib.util
from pathlib import Path
import sys
import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
spec = importlib.util.spec_from_file_location('coupling_run_test', HERE/'run.py')
run = importlib.util.module_from_spec(spec)
spec.loader.exec_module(run)
ca = run.ca
pytestmark=pytest.mark.skipif(not (ca.base.WORKSPACE/'runs/dense_loop_a13/result.json').is_file(),
                             reason='historical Clinic snapshots are not part of a clean repository checkout')


def test_s1_nearest_occupancy_does_not_change_source_or_accepted_reference():
    p = run.build(run.RUNS[0], 'S1', 0)
    q = run.build(run.RUNS[0], 'S1', 2)
    nearest = q['scenario']['parameters']['nearest_by_projected_source']
    assert q['robots'][nearest]['ready'] == p['robots'][nearest]['ready']+180.
    assert p['reference'] == q['reference'] == q['accepted_reference']
    assert p['prefixes'] == q['prefixes']
    assert p['immutable_projection'] == q['immutable_projection']


def test_new_supply_pair_is_not_fabricated_as_accepted_and_has_its_own_identity():
    p = run.build(run.RUNS[0], 'S3', 1)
    for j in ('ND_pickup', 'ND_deliver'):
        assert j in p['nominal_owners'] and j not in p['accepted_reference']['owners']
        assert all(j not in q for q in p['accepted_reference']['routes'].values())
        assert 'protocol_task_id' not in p['tasks'][j]
        assert p['tasks'][j]['cargo_group'] == 'ND'
    assert ['ND_pickup', 'ND_deliver'] in p['cargo_pairs']
    assert p['tasks']['ND_pickup']['resources'] == ['G1']


def test_all_four_models_share_objective_and_constraints_except_owner_locks():
    p = run.build(run.RUNS[0], 'S3', 0)
    assert len({ca.common_signature(p, m) for m in ca.METHODS}) == 1


def test_evaluation_due_does_not_relax_or_change_existing_hard_deadlines():
    p = run.build(run.RUNS[0], 'S5', 0, 'EVALUATION_ONLY')
    q = run.build(run.RUNS[0], 'S5', 0, 'HARD')
    source = run.read(Path(p['parent_problem']))
    assert p['assignment_weights'] == q['assignment_weights'] == source['assignment_weights']
    for j in p['routine_due_at']:
        assert p['tasks'][j]['deadline'] == source['tasks'][j]['deadline']
        assert q['tasks'][j]['deadline'] == min(source['tasks'][j]['deadline'], q['routine_due_at'][j])


def test_context_changes_only_new_emergency_and_business_relationship():
    p = run.build(run.RUNS[1], 'S5', 2, 'HARD')
    q = run.context(p)
    assert q['robots'] == p['robots'] and q['prefixes'] == p['prefixes']
    assert q['accepted_reference'] == p['accepted_reference']
    assert q['routine_due_at'] == p['routine_due_at']
    assert not q['events'] and not q.get('necessary_normal')
    assert all(q['tasks'][j] == p['tasks'][j] for j in q['tasks'])


def test_active_monitor_and_unknown_cargo_release_block_without_fabricated_plan():
    specs = run.blocked_specs()
    results = [run.probe_blocked(s) for s in specs]
    assert 'before monitor/pickup start only' in results[0]['native_active_event_probe']
    assert results[1]['cargo_evidence_disagreement']['r2']['projected_commitment'] == 'E1'
    for q in results:
        assert q['attempted_performance_solves'] == 0 and 'plan' not in q
        assert q['execution_authorized'] is False


def test_full_validator_rejects_reassigned_new_cargo_and_hard_owner():
    p = run.build(run.RUNS[0], 'S3', 0)
    q = ca.greedy(p)
    assert q.get('plan') and ca.validate(p, q['plan'], 'B1', q['objective'])['passed']
    original = q['plan']
    bad = deepcopy(original)
    old = bad['owners']['ND_deliver']
    other = next(r for r in p['robots'] if r != old)
    bad['routes'][old].remove('ND_deliver')
    bad['routes'][other].append('ND_deliver')
    bad['owners']['ND_deliver'] = other
    assert not ca.validate(p, bad, 'B3')['passed']
    changed = deepcopy(p)
    changed['hard_owners']['ND_pickup'] = other
    assert not ca.validate(changed, original, 'B3')['passed']
