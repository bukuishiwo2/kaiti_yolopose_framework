from __future__ import annotations

from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_ROOT = PROJECT_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from verify_v2_execution_trace import verify_trace


def _row(topic: str, payload: dict) -> dict:
    return {"topic": topic, "payload": payload}


def test_trace_accepts_distinct_tasks_that_legitimately_share_location_b() -> None:
    history = [
        {"task_id": "verify:event_1", "step_name": "task_location", "attempt": 1, "location_id": "B"},
        {"task_id": "pickup:event_1", "step_name": "task_location", "attempt": 1, "location_id": "S"},
        {"task_id": "deliver:event_1", "step_name": "task_location", "attempt": 1, "location_id": "B"},
    ]
    rows = [
        _row("/planning/plan", {"revision": 1}),
        _row("/planning/executor_status", {"dispatched_goal_history": history}),
    ]
    result = verify_trace(rows)
    assert result["ok"] is True
    assert [item["location_id"] for item in result["dispatch_sequence"]] == ["B", "S", "B"]


def test_trace_rejects_same_task_step_dispatched_twice() -> None:
    duplicate = {"task_id": "deliver:event_1", "step_name": "task_location", "attempt": 1, "location_id": "B"}
    result = verify_trace(
        [
            _row("/planning/plan", {"revision": 1}),
            _row("/planning/executor_status", {"dispatched_goal_history": [duplicate, duplicate]}),
        ]
    )
    assert result["ok"] is False
    assert "duplicate_task_step_dispatch" in result["errors"]


def test_formal_visual_gate_rejects_a_partial_trace() -> None:
    result = verify_trace(
        [
            _row("/planning/plan", {"revision": 1}),
            _row(
                "/planning/executor_status",
                {
                    "planner_state": "executing",
                    "dispatched_goal_history": [
                        {"task_id": "verify:event_1", "step_name": "task_location", "attempt": 1}
                    ],
                },
            ),
        ],
        required_task_prefixes=("verify", "pickup", "deliver"),
        require_terminal_completed=True,
    )
    assert result["ok"] is False
    assert result["missing_task_prefixes"] == ["pickup", "deliver"]
    assert "execution_not_terminal_completed" in result["errors"]
