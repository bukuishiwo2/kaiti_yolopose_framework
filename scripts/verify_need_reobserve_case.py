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

from yolopose_ros.system_semantics import (  # noqa: E402
    ReobserveHysteresis,
    ReobserveHysteresisConfig,
    build_planner_request,
    build_planner_status,
    build_supervisor_status,
    enrich_observation,
)


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _base_event() -> dict[str, object]:
    return {
        "ts": _timestamp(),
        "role": "pose_stream_node",
        "event_type": "perception_event",
        "input_mode": "ros_image",
        "pipeline_state": "running",
        "perception_available": True,
        "reason": "running",
        "frame_id": 42,
        "source": "ros:///camera/image_raw",
        "person_count": 1,
        "person_present": True,
        "stable_person_present": True,
        "stable_fall_detected": False,
        "seq_stable_fall_detected": False,
        "seq_fall_detector_enabled": True,
        "seq_fall_model_loaded": True,
        "seq_feature_valid": True,
        "seq_window_ready": True,
        "seq_visible_keypoint_count": 10,
        "seq_invalid_reason": "",
        "seq_skip_reason": "",
        "seq_fall_score": 0.12,
    }


def main() -> int:
    planner_mode = "plansys2_placeholder"
    planner_request_topic = "/task_planner/request"

    cases = {
        "monitor_case": _base_event(),
        "need_reobserve_occluded_case": {
            **_base_event(),
            "seq_feature_valid": False,
            "seq_window_ready": False,
            "seq_visible_keypoint_count": 0,
            "seq_invalid_reason": "no_visible_keypoints",
            "seq_skip_reason": "no_visible_keypoints",
        },
        "no_person_case": {
            **_base_event(),
            "person_count": 0,
            "person_present": False,
            "stable_person_present": False,
        },
        "fall_case": {
            **_base_event(),
            "seq_stable_fall_detected": True,
            "seq_fall_score": 0.93,
        },
    }

    outputs: dict[str, dict[str, object]] = {}
    for name, raw_event in cases.items():
        hysteresis = ReobserveHysteresis(ReobserveHysteresisConfig(enter_frames=2, exit_frames=5))
        event = enrich_observation(raw_event, visible_keypoint_threshold=6)
        if name == "need_reobserve_occluded_case":
            hysteresis.update(event)
        snap = hysteresis.update(event)
        supervisor_status = build_supervisor_status(
            ts=event["ts"],
            event=event,
            planner_mode=planner_mode,
            planner_request_topic=planner_request_topic,
            need_reobserve_active=snap.active,
            need_reobserve_reason=snap.reason,
            need_reobserve_raw=snap.raw,
            reobserve_enter_count=snap.enter_count,
            reobserve_exit_count=snap.exit_count,
        )
        planner_request = build_planner_request(supervisor_status)
        planner_status = build_planner_status(
            ts=event["ts"],
            planner_mode=planner_mode,
            request_topic=planner_request_topic,
            requested_action=str(planner_request["requested_action"]),
            reason=str(planner_request["reason"]),
            request=planner_request,
        )
        outputs[name] = {
            "hysteresis_enter_frames": 2,
            "hysteresis_exit_frames": 5,
            "event": event,
            "supervisor_status": supervisor_status,
            "planner_request": planner_request,
            "planner_status": planner_status,
        }

    hysteresis = ReobserveHysteresis(ReobserveHysteresisConfig(enter_frames=2, exit_frames=5))
    jitter_sequence = [
        ("low_1", {"seq_visible_keypoint_count": 3}),
        ("stable_1", {}),
        ("low_2", {"seq_visible_keypoint_count": 3}),
        ("low_3_enter", {"seq_visible_keypoint_count": 3}),
        ("stable_hold_1", {}),
        ("stable_hold_2", {}),
        ("stable_hold_3", {}),
        ("stable_hold_4", {}),
        ("stable_exit_5", {}),
    ]
    jitter_outputs = []
    for label, patch in jitter_sequence:
        event = enrich_observation({**_base_event(), **patch}, visible_keypoint_threshold=6)
        snap = hysteresis.update(event)
        status = build_supervisor_status(
            ts=event["ts"],
            event=event,
            planner_mode=planner_mode,
            planner_request_topic=planner_request_topic,
            need_reobserve_active=snap.active,
            need_reobserve_reason=snap.reason,
            need_reobserve_raw=snap.raw,
            reobserve_enter_count=snap.enter_count,
            reobserve_exit_count=snap.exit_count,
        )
        jitter_outputs.append(
            {
                "label": label,
                "observation_state": event["observation_state"],
                "observation_reason": event["observation_reason"],
                "need_reobserve_raw": snap.raw,
                "reobserve_enter_count": snap.enter_count,
                "reobserve_exit_count": snap.exit_count,
                "planner_action": status["planner_action"],
                "reason": status["reason"],
            }
        )
    outputs["reobserve_hysteresis_jitter_case"] = {"sequence": jitter_outputs}

    print(json.dumps(outputs, ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
