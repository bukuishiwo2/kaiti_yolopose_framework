#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
ROS2_SRC = REPO_ROOT / "ros2_ws" / "src" / "yolopose_ros"
if str(ROS2_SRC) not in sys.path:
    sys.path.insert(0, str(ROS2_SRC))

from yolopose_ros.planner_nav2_dispatcher_logic import (  # noqa: E402
    ACTION_GOAL_MAP,
    DEFAULT_NEED_REOBSERVE_REASONS,
    DEFAULT_TRIGGER_SAFE_MODE_REASONS,
    DispatcherConfig,
    DispatchDecisionKind,
    NamedGoal,
    evaluate_dispatch_request,
)


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _request(action: str, reason: str) -> dict[str, object]:
    return {
        "ts": _timestamp(),
        "role": "system_supervisor",
        "planner_mode": "plansys2_placeholder",
        "requested_action": action,
        "reason": reason,
    }


def _goal(name: str = "safe_mode_staging") -> NamedGoal:
    return NamedGoal(
        name=name,
        frame_id="map",
        x=1.0,
        y=0.0,
        z=0.0,
        qx=0.0,
        qy=0.0,
        qz=0.0,
        qw=1.0,
    )


def _config(
    *,
    enabled: bool,
    allowed: set[str] | None = None,
    named_goals: dict[str, NamedGoal] | None = None,
) -> DispatcherConfig:
    return DispatcherConfig(
        dispatch_enabled=enabled,
        allowed_actions=allowed or set(),
        goal_frame_id="map",
        cooldown_sec=5.0,
        action_goal_map=dict(ACTION_GOAL_MAP),
        named_goals=named_goals
        if named_goals is not None
        else {
            "safe_mode_staging": _goal("safe_mode_staging"),
            "reobserve_vantage": _goal("reobserve_vantage"),
        },
        trigger_safe_mode_reasons=set(DEFAULT_TRIGGER_SAFE_MODE_REASONS),
        need_reobserve_reasons=set(DEFAULT_NEED_REOBSERVE_REASONS),
    )


def _decision_json(decision) -> dict[str, object]:
    return {
        "kind": decision.kind.value,
        "requested_action": decision.requested_action,
        "reason": decision.reason,
        "decision_reason": decision.decision_reason,
        "goal_name": decision.goal_name,
        "signature": list(decision.signature) if decision.signature else None,
    }


def main() -> int:
    cases = {
        "dispatch_disabled_blocks_safe_mode": (
            _request("trigger_safe_mode", "fall_detected"),
            _config(enabled=False, allowed={"trigger_safe_mode"}),
            False,
            None,
            None,
            DispatchDecisionKind.REJECT,
            "dispatch_disabled",
        ),
        "missing_planner_mode_blocks_request": (
            {**_request("trigger_safe_mode", "fall_detected"), "planner_mode": ""},
            _config(enabled=True, allowed={"trigger_safe_mode"}),
            False,
            None,
            None,
            DispatchDecisionKind.REJECT,
            "missing_planner_mode",
        ),
        "monitor_is_not_navigation_dispatchable": (
            _request("monitor", "stable"),
            _config(enabled=True, allowed={"trigger_safe_mode", "need_reobserve"}),
            False,
            None,
            None,
            DispatchDecisionKind.REJECT,
            "action_not_navigation_dispatchable",
        ),
        "wait_for_update_is_not_navigation_dispatchable": (
            _request("wait_for_update", "no_person_present"),
            _config(enabled=True, allowed={"trigger_safe_mode", "need_reobserve"}),
            False,
            None,
            None,
            DispatchDecisionKind.REJECT,
            "action_not_navigation_dispatchable",
        ),
        "need_reobserve_temporal_window_not_ready_blocked": (
            _request("need_reobserve", "temporal_window_not_ready"),
            _config(enabled=True, allowed={"need_reobserve"}),
            False,
            None,
            None,
            DispatchDecisionKind.REJECT,
            "reason_not_allowed_for_reobserve_dispatch",
        ),
        "need_reobserve_low_visibility_dispatches": (
            _request("need_reobserve", "low_visibility"),
            _config(enabled=True, allowed={"need_reobserve"}),
            False,
            None,
            None,
            DispatchDecisionKind.DISPATCH,
            "dispatch_allowed",
        ),
        "safe_mode_fall_dispatches": (
            _request("trigger_safe_mode", "fall_detected"),
            _config(enabled=True, allowed={"trigger_safe_mode"}),
            False,
            None,
            None,
            DispatchDecisionKind.DISPATCH,
            "dispatch_allowed",
        ),
        "missing_named_goal_blocks_dispatch": (
            _request("trigger_safe_mode", "fall_detected"),
            _config(enabled=True, allowed={"trigger_safe_mode"}, named_goals={}),
            False,
            None,
            None,
            DispatchDecisionKind.REJECT,
            "configured_goal_missing",
        ),
        "duplicate_in_cooldown_blocks_dispatch": (
            _request("trigger_safe_mode", "fall_detected"),
            _config(enabled=True, allowed={"trigger_safe_mode"}),
            False,
            ("trigger_safe_mode", "fall_detected", "safe_mode_staging"),
            8.0,
            DispatchDecisionKind.REJECT,
            "duplicate_request_in_cooldown",
        ),
        "hold_cancels_active_goal": (
            _request("hold", "planner_hold"),
            _config(enabled=True, allowed={"trigger_safe_mode"}),
            True,
            None,
            None,
            DispatchDecisionKind.CANCEL,
            "hold_cancels_active_dispatch_goal",
        ),
        "unsupported_action_rejected": (
            _request("dispatch_delivery", "demo"),
            _config(enabled=True, allowed={"dispatch_delivery"}),
            False,
            None,
            None,
            DispatchDecisionKind.REJECT,
            "action_not_navigation_dispatchable",
        ),
    }

    outputs: dict[str, object] = {}
    failures: list[str] = []
    for name, (
        request,
        config,
        active_goal,
        last_signature,
        last_dispatch_time,
        expected_kind,
        expected_reason,
    ) in cases.items():
        decision = evaluate_dispatch_request(
            request=request,
            config=config,
            now_monotonic=10.0,
            active_goal=active_goal,
            last_signature=last_signature,
            last_dispatch_monotonic=last_dispatch_time,
        )
        outputs[name] = _decision_json(decision)
        if decision.kind != expected_kind or decision.decision_reason != expected_reason:
            failures.append(name)

    print(json.dumps(outputs, ensure_ascii=True, indent=2))
    if failures:
        print("FAILED_CASES=" + ",".join(failures), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
