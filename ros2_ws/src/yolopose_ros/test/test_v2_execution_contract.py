from __future__ import annotations

from pathlib import Path
import sys

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[4]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from kaiti_planning.execution_protocol import (  # noqa: E402
    RevisionGate,
    can_apply_deferred_revision,
    expand_assignments,
)


def _plan(revision: int) -> dict:
    return {
        "planner_instance_id": "planner-test",
        "plan_id": "house-v2",
        "revision": revision,
        "world_revision": revision,
        "solver_status": "OPTIMAL",
    }


def test_ros_executor_contract_rejects_duplicate_revision() -> None:
    gate = RevisionGate()
    assert gate.evaluate(_plan(1)).accepted
    assert gate.evaluate(_plan(1)).reason == "duplicate_revision"
    assert gate.evaluate(_plan(0)).reason == "stale_revision"


def test_ros_executor_contract_defers_revision_until_queue_boundary() -> None:
    assert not can_apply_deferred_revision(
        has_pending_plan=True,
        queue_length=1,
        goal_pending=False,
        goal_active=False,
    )
    assert can_apply_deferred_revision(
        has_pending_plan=True,
        queue_length=0,
        goal_pending=False,
        goal_active=False,
    )


def test_ros_executor_accepts_dynamic_event_task_ids_without_static_registry() -> None:
    rows = [
        {"robot": "R2", "task": "pickup:event_7", "task_type": "pickup_supply", "location": "S"},
        {"robot": "R2", "task": "deliver:event_7", "task_type": "deliver_supply", "location": "B"},
    ]
    steps = expand_assignments(rows, robot_id="R2", task_registry={})
    assert [step.location_id for step in steps] == ["S", "B"]
    assert len({step.key for step in steps}) == 2


def test_ros_planning_config_uses_v2_and_disables_execution_by_default() -> None:
    config_path = PROJECT_ROOT / "ros2_ws/src/yolopose_ros/config/planning_stack.yaml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    planner = config["milp_planner_node"]["ros__parameters"]
    executor = config["milp_plan_executor_node"]["ros__parameters"]
    assert planner["planner_config_path"] == "configs/planner_graduation_v2.yaml"
    assert planner["verification_result_on_success"] == ""
    assert executor["execution_enabled"] is False
    assert executor["plan_stale_sec"] >= planner["plan_valid_sec"]
