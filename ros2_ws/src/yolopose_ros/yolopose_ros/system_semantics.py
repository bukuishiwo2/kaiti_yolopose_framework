from __future__ import annotations

from dataclasses import dataclass
from typing import Any


TERMINAL_PERCEPTION_STATES = {"completed", "error", "unavailable"}
REOBSERVE_OBSERVATION_STATES = {"low_visibility", "occluded", "window_not_ready"}
PLANNER_ACTION_STATUS_MAP = {
    "monitor": {
        "planner_state": "idle",
        "state_reason": "monitoring_request",
    },
    "wait_for_update": {
        "planner_state": "waiting",
        "state_reason": "waiting_for_perception_update",
    },
    "need_reobserve": {
        "planner_state": "reobserve_pending",
        "state_reason": "reobserve_requested",
    },
    "trigger_safe_mode": {
        "planner_state": "dispatching_safe_mode",
        "state_reason": "safe_mode_requested",
    },
    "hold": {
        "planner_state": "holding",
        "state_reason": "planner_hold",
    },
}
INVALID_PLANNER_REQUEST = {
    "planner_state": "invalid_request",
    "state_reason": "unsupported_requested_action",
}


@dataclass
class ReobserveHysteresisConfig:
    enter_frames: int = 2
    exit_frames: int = 5


@dataclass
class ReobserveHysteresisSnapshot:
    active: bool
    raw: bool
    enter_count: int
    exit_count: int
    reason: str


class ReobserveHysteresis:
    """Frame-count hysteresis for need_reobserve without adding new states."""

    def __init__(self, cfg: ReobserveHysteresisConfig | None = None) -> None:
        self.cfg = cfg or ReobserveHysteresisConfig()
        self.active = False
        self.enter_count = 0
        self.exit_count = 0
        self.last_reobserve_reason = "need_reobserve"

    def reset(self) -> ReobserveHysteresisSnapshot:
        self.active = False
        self.enter_count = 0
        self.exit_count = 0
        return ReobserveHysteresisSnapshot(
            active=False,
            raw=False,
            enter_count=0,
            exit_count=0,
            reason=self.last_reobserve_reason,
        )

    def update(self, event: dict[str, Any]) -> ReobserveHysteresisSnapshot:
        raw = should_need_reobserve(event)
        fall_flag, _ = resolve_fall_trigger(event)
        person_present = resolve_person_present(event)
        perception_available = _as_bool(event.get("perception_available"))
        pipeline_state = str(event.get("pipeline_state", "")).strip().lower()

        if (
            perception_available is False
            or pipeline_state in TERMINAL_PERCEPTION_STATES
            or fall_flag
            or person_present is False
        ):
            return self.reset()

        if raw:
            self.enter_count += 1
            self.exit_count = 0
            reason = str(event.get("observation_reason", "")).strip() or "need_reobserve"
            self.last_reobserve_reason = reason
            if self.enter_count >= max(1, int(self.cfg.enter_frames)):
                self.active = True
        else:
            self.enter_count = 0
            if self.active:
                self.exit_count += 1
                if self.exit_count >= max(1, int(self.cfg.exit_frames)):
                    self.active = False
                    self.exit_count = 0
            else:
                self.exit_count = 0

        return ReobserveHysteresisSnapshot(
            active=self.active,
            raw=raw,
            enter_count=self.enter_count,
            exit_count=self.exit_count,
            reason=self.last_reobserve_reason,
        )


def _as_bool(value: Any) -> bool | None:
    if value is None:
        return None
    return bool(value)


def resolve_person_present(event: dict[str, Any]) -> bool | None:
    person_present = _as_bool(event.get("person_present"))
    if person_present is not None:
        return person_present
    return _as_bool(event.get("stable_person_present"))


def resolve_observation(
    event: dict[str, Any],
    visible_keypoint_threshold: int = 6,
) -> tuple[str, str]:
    perception_available = _as_bool(event.get("perception_available"))
    pipeline_state = str(event.get("pipeline_state", "")).strip().lower()
    if perception_available is False or pipeline_state in TERMINAL_PERCEPTION_STATES:
        reason = str(event.get("reason", "")).strip() or f"perception_{pipeline_state or 'unavailable'}"
        return "unavailable", reason

    person_present = resolve_person_present(event)
    if person_present is False:
        return "no_person", "no_person_present"

    if event.get("seq_fall_detector_enabled") is False or event.get("seq_fall_model_loaded") is False:
        return "observable", "sequence_branch_unavailable"

    invalid_reason = str(event.get("seq_invalid_reason", "")).strip().lower()
    skip_reason = str(event.get("seq_skip_reason", "")).strip().lower()
    try:
        visible_count = int(event.get("seq_visible_keypoint_count", 0) or 0)
    except (TypeError, ValueError):
        visible_count = 0
    seq_feature_valid = bool(event.get("seq_feature_valid"))
    seq_window_ready = bool(event.get("seq_window_ready"))

    if invalid_reason in {"no_visible_keypoints", "no_person_candidate", "no_track_candidate"}:
        return "occluded", "occluded_or_no_visible_keypoints"
    if visible_count > 0 and visible_count < int(visible_keypoint_threshold):
        return "low_visibility", "low_visibility"
    if not seq_feature_valid:
        return "low_visibility", "feature_not_reliable"
    if not seq_window_ready or skip_reason == "waiting_for_window":
        return "window_not_ready", "temporal_window_not_ready"

    return "observable", "stable_observation"


def enrich_observation(
    event: dict[str, Any],
    visible_keypoint_threshold: int = 6,
) -> dict[str, Any]:
    payload = dict(event)
    observation_state, observation_reason = resolve_observation(
        payload,
        visible_keypoint_threshold=visible_keypoint_threshold,
    )
    payload["observation_state"] = observation_state
    payload["observation_reason"] = observation_reason
    return payload


def sequence_branch_unavailable(event: dict[str, Any]) -> bool:
    return (
        event.get("seq_fall_detector_enabled") is False
        or event.get("seq_fall_model_loaded") is False
    )


def resolve_fall_trigger(event: dict[str, Any]) -> tuple[bool, str]:
    if bool(event.get("seq_stable_fall_detected")):
        return True, "sequence_mainline"
    if sequence_branch_unavailable(event) and bool(event.get("stable_fall_detected")):
        return True, "rule_fallback"
    return False, "none"


def should_need_reobserve(event: dict[str, Any]) -> bool:
    observation_state = str(event.get("observation_state", "")).strip().lower()
    return observation_state in REOBSERVE_OBSERVATION_STATES


def build_supervisor_status(
    ts: str,
    event: dict[str, Any],
    planner_mode: str,
    planner_request_topic: str,
    need_reobserve_active: bool | None = None,
    need_reobserve_reason: str | None = None,
    need_reobserve_raw: bool | None = None,
    reobserve_enter_count: int | None = None,
    reobserve_exit_count: int | None = None,
) -> dict[str, Any]:
    fall_flag, fall_trigger_source = resolve_fall_trigger(event)
    person_present = resolve_person_present(event)

    perception_available = event.get("perception_available")
    pipeline_state = str(event.get("pipeline_state", "")).strip().lower()
    reason = str(event.get("reason", "")).strip()
    observation_state = str(event.get("observation_state", "")).strip().lower()
    observation_reason = str(event.get("observation_reason", "")).strip()

    effective_need_reobserve = (
        should_need_reobserve(event) if need_reobserve_active is None else bool(need_reobserve_active)
    )

    if perception_available is False or pipeline_state in TERMINAL_PERCEPTION_STATES:
        planner_action = "hold"
        supervisor_state = "degraded"
        if not reason:
            reason = f"perception_{pipeline_state or 'unavailable'}"
    elif fall_flag:
        planner_action = "trigger_safe_mode"
        supervisor_state = "alert"
        reason = "fall_detected_rule_fallback" if fall_trigger_source == "rule_fallback" else "fall_detected"
    elif person_present is False:
        planner_action = "wait_for_update"
        supervisor_state = "monitoring"
        reason = "no_person_present"
    elif effective_need_reobserve:
        planner_action = "need_reobserve"
        supervisor_state = "monitoring"
        reason = need_reobserve_reason or observation_reason or "need_reobserve"
    else:
        planner_action = "monitor"
        supervisor_state = "monitoring"
        if not reason:
            reason = "stable"

    return {
        "ts": ts,
        "role": "system_supervisor",
        "supervisor_state": supervisor_state,
        "planner_mode": planner_mode,
        "planner_request_topic": planner_request_topic,
        "planner_action": planner_action,
        "reason": reason,
        "fall_trigger_source": fall_trigger_source,
        "observation_state": observation_state or "unknown",
        "observation_reason": observation_reason,
        "need_reobserve_raw": should_need_reobserve(event) if need_reobserve_raw is None else bool(need_reobserve_raw),
        "reobserve_enter_count": 0 if reobserve_enter_count is None else int(reobserve_enter_count),
        "reobserve_exit_count": 0 if reobserve_exit_count is None else int(reobserve_exit_count),
        "source_event": event,
    }


def build_planner_request(status: dict[str, Any]) -> dict[str, Any]:
    return {
        "ts": status["ts"],
        "role": "system_supervisor",
        "planner_mode": status["planner_mode"],
        "requested_action": status["planner_action"],
        "reason": status["reason"],
    }


def build_planner_status(
    ts: str,
    planner_mode: str,
    request_topic: str,
    requested_action: str,
    reason: str,
    request: dict[str, Any] | None,
) -> dict[str, Any]:
    normalized_action = str(requested_action).strip().lower()
    mapping = PLANNER_ACTION_STATUS_MAP.get(normalized_action)
    request_supported = mapping is not None
    if mapping is None:
        mapping = INVALID_PLANNER_REQUEST
    planner_state = str(mapping["planner_state"])
    state_reason = str(mapping["state_reason"])
    request_reason = str(reason).strip()
    status_reason = request_reason if request_supported and request_reason else state_reason
    return {
        "ts": ts,
        "role": "task_planner_bridge",
        "planner_mode": planner_mode,
        "planner_state": planner_state,
        "active_action": normalized_action,
        "reason": status_reason,
        "state_reason": state_reason,
        "request_reason": request_reason,
        "request_supported": bool(request_supported),
        "request_topic": request_topic,
        "source_request": request,
    }
