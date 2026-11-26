"""Regression coverage for rejection scope and asynchronous commit checks."""
from copy import deepcopy
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'experiments/clinic_priority'))
from feedback_repair import (
    Comparison, FeedbackComparison, check_prefix, path_checks, revised_problem, READ,
)
from kaiti_task_sim.clinic_assignment import WORKSPACE


@pytest.fixture
def captured():
    run = WORKSPACE/'verification/online_pair_2026-11-26_07/full_a7'
    if not (run/'response/problem.json').is_file():
        pytest.skip('Historical snapshot is stored in the Clinic runtime workspace')
    return (READ(run/'response/problem.json'), READ(run/'response/solve/result.json'),
            READ(run/'result.json'))


def test_rejection_changes_one_transition_and_invalidates_original_plan(captured):
    problem, result, run = captured
    arc, edge = next(path_checks(problem, result['plan'], 'C0_r1_W3'))
    assert arc == ('r2', 'src', 'C0_r1_W3')
    assert edge == ('r2', 'CPW2', 'ADL')
    witness = run['path_witness'][0]
    revised = revised_problem(problem, arc, witness)
    assert {k: v for k, v in revised.items() if k != 'rejected_transition'} == problem
    _, before, _ = Comparison.model(problem, 'full')
    _, after, _ = FeedbackComparison.model(revised, 'full')
    extra = set(after.constraints) - set(before.constraints)
    assert extra == {'rejected_transition_a_r2_src_C0_r1_W3'}
    row = after.constraints[extra.pop()]
    assert row.sense == row.constant == 0
    assert [(v.name, c) for v, c in row.items()] == [('a_r2_src_C0_r1_W3', 1)]
    audit = FeedbackComparison.validate(revised, result['plan'], 'full', result['objective'])
    assert [error['name'] for error in audit['errors']] == ['rejected_transition']
    with pytest.raises(ValueError, match='does not match'):
        revised_problem(problem, ('r2', 'src', 'C0_r2_W3'), witness)


def test_prefix_checks_live_dispatch_identity_and_history(captured):
    problem, result, run = captured
    states = deepcopy(problem['snapshot_states'])
    completed = {j: run['completed'][j] for j in problem['actual_known_finishes']}
    check_prefix(problem, result['plan'], states, completed)
    states['r2']['record']['plan_revision'] += 1
    with pytest.raises(ValueError, match='dispatch facts changed'):
        check_prefix(problem, result['plan'], states, completed)
    completed.pop('E1_verify')
    with pytest.raises(ValueError, match='Completed fact changed'):
        check_prefix(problem, result['plan'], states, completed)
