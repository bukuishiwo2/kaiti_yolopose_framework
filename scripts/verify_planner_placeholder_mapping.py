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

from yolopose_ros.system_semantics import build_planner_status  # noqa: E402


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def main() -> int:
    planner_mode = "plansys2_placeholder"
    request_topic = "/task_planner/request"
    cases = [
        ("monitor", "stable"),
        ("wait_for_update", "no_person_present"),
        ("need_reobserve", "low_visibility"),
        ("trigger_safe_mode", "fall_detected"),
        ("hold", "waiting_for_perception"),
        ("unsupported_action", "free_text_should_not_mask_invalid_action"),
    ]

    outputs: dict[str, dict[str, object]] = {}
    for action, reason in cases:
        request = {
            "ts": _timestamp(),
            "role": "system_supervisor",
            "planner_mode": planner_mode,
            "requested_action": action,
            "reason": reason,
        }
        outputs[action] = build_planner_status(
            ts=str(request["ts"]),
            planner_mode=planner_mode,
            request_topic=request_topic,
            requested_action=action,
            reason=reason,
            request=request,
        )

    print(json.dumps(outputs, ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
