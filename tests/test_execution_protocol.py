from __future__ import annotations

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from kaiti_planning.execution_protocol import (
    RevisionGate,
    can_apply_deferred_revision,
    expand_assignments,
)
from kaiti_planning.models import load_problem_from_yaml


def _plan(revision: int, world_revision: int, **extra):
    return {
        "planner_instance_id": "planner-A",
        "plan_id": "house-demo",
        "revision": revision,
        "world_revision": world_revision,
        "solver_status": "OPTIMAL",
        **extra,
    }


def test_revision_gate_rejects_duplicate_stale_and_implicit_restart() -> None:
    gate = RevisionGate()
    assert gate.evaluate(_plan(1, 1)).accepted is True
    assert gate.evaluate(_plan(1, 1)).reason == "duplicate_revision"
    assert gate.evaluate(_plan(0, 0)).reason == "stale_revision"
    assert gate.evaluate(_plan(2, 0)).reason == "stale_world_revision"
    restarted = _plan(1, 1)
    restarted["planner_instance_id"] = "planner-B"
    assert gate.evaluate(restarted).reason == "different_planning_session_requires_reset"
    restarted["reset_execution"] = True
    assert gate.evaluate(restarted).reason == "explicit_session_reset"


def test_dynamic_v2_tasks_expand_once_and_completed_steps_never_repeat() -> None:
    problem = load_problem_from_yaml(PROJECT_ROOT / "configs/planner_graduation_v2.yaml")
    assignments = [
        {"robot": "R2", "task": "pickup:event_1", "location": "S", "start": 10},
        {"robot": "R2", "task": "deliver:event_1", "location": "B", "start": 20},
    ]
    first = expand_assignments(
        assignments,
        robot_id="R2",
        task_registry=problem.task_by_id(),
    )
    assert [(step.task_id, step.location_id) for step in first] == [
        ("pickup:event_1", "S"),
        ("deliver:event_1", "B"),
    ]
    completed = {first[0].key}
    refreshed = expand_assignments(
        assignments,
        robot_id="R2",
        task_registry=problem.task_by_id(),
        completed_step_keys=completed,
    )
    assert [(step.task_id, step.location_id) for step in refreshed] == [
        ("deliver:event_1", "B")
    ]


def test_legacy_delivery_expands_pickup_without_duplicate_task_goal() -> None:
    legacy = load_problem_from_yaml(PROJECT_ROOT / "configs/planner_minimal_experiment.yaml")
    steps = expand_assignments(
        [{"robot": "R2", "task": "T4", "location": "B", "start": 53}],
        robot_id="R2",
        task_registry=legacy.task_by_id(),
    )
    assert [(step.step_name, step.location_id) for step in steps] == [
        ("pickup_location", "S"),
        ("task_location", "B"),
    ]


def test_deferred_revision_never_replaces_a_partially_executed_queue() -> None:
    assert can_apply_deferred_revision(
        has_pending_plan=True,
        queue_length=2,
        goal_pending=False,
        goal_active=False,
    ) is False
    assert can_apply_deferred_revision(
        has_pending_plan=True,
        queue_length=0,
        goal_pending=False,
        goal_active=True,
    ) is False
    assert can_apply_deferred_revision(
        has_pending_plan=True,
        queue_length=0,
        goal_pending=False,
        goal_active=False,
    ) is True
