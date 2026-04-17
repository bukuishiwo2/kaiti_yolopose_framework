from __future__ import annotations

import json
import math
from dataclasses import dataclass
from enum import Enum
from typing import Any


ACTION_GOAL_MAP = {
    "trigger_safe_mode": "safe_mode_staging",
    "need_reobserve": "reobserve_vantage",
}
DEFAULT_TRIGGER_SAFE_MODE_REASONS = {
    "fall_detected",
    "fall_detected_rule_fallback",
}
DEFAULT_NEED_REOBSERVE_REASONS = {
    "low_visibility",
    "occluded",
    "occluded_or_no_visible_keypoints",
    "feature_not_reliable",
    "need_reobserve",
}


class DispatchDecisionKind(str, Enum):
    DISPATCH = "dispatch"
    REJECT = "reject"
    CANCEL = "cancel"


@dataclass(frozen=True)
class NamedGoal:
    name: str
    frame_id: str
    x: float
    y: float
    z: float
    qx: float
    qy: float
    qz: float
    qw: float
    behavior_tree: str = ""


@dataclass(frozen=True)
class DispatcherConfig:
    dispatch_enabled: bool
    allowed_actions: set[str]
    goal_frame_id: str
    cooldown_sec: float
    action_goal_map: dict[str, str]
    named_goals: dict[str, NamedGoal]
    trigger_safe_mode_reasons: set[str]
    need_reobserve_reasons: set[str]


@dataclass(frozen=True)
class DispatchDecision:
    kind: DispatchDecisionKind
    requested_action: str
    reason: str
    decision_reason: str
    goal_name: str | None = None
    goal: NamedGoal | None = None
    signature: tuple[str, str, str] | None = None


def parse_request_payload(payload: str) -> tuple[dict[str, Any] | None, str | None]:
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return None, "invalid_json"
    if not isinstance(data, dict):
        return None, "request_not_json_object"
    return data, None


def as_normalized_set(values: Any) -> set[str]:
    if values is None:
        return set()
    if isinstance(values, str):
        clean = values.strip()
        if clean in {"", "[]"}:
            return set()
        if clean.startswith("["):
            try:
                parsed = json.loads(clean.replace("'", '"'))
                if isinstance(parsed, list):
                    values = parsed
                else:
                    values = [clean]
            except json.JSONDecodeError:
                values = clean.split(",")
        else:
            values = clean.split(",")
    return {str(value).strip().lower() for value in values if str(value).strip()}


def as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _finite_number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def _valid_quaternion(qx: float, qy: float, qz: float, qw: float) -> bool:
    norm = math.sqrt(qx * qx + qy * qy + qz * qz + qw * qw)
    return math.isfinite(norm) and abs(norm - 1.0) <= 0.05


def parse_goal_pose(
    name: str,
    frame_id: str,
    pose_xyzw: Any,
    behavior_tree: str = "",
) -> NamedGoal | None:
    if not isinstance(pose_xyzw, (list, tuple)) or len(pose_xyzw) != 7:
        return None

    parsed = [_finite_number(value) for value in pose_xyzw]
    if any(value is None for value in parsed):
        return None

    x, y, z, qx, qy, qz, qw = [float(value) for value in parsed]
    if not _valid_quaternion(qx, qy, qz, qw):
        return None

    clean_frame = str(frame_id).strip()
    if not clean_frame:
        return None

    return NamedGoal(
        name=str(name).strip(),
        frame_id=clean_frame,
        x=x,
        y=y,
        z=z,
        qx=qx,
        qy=qy,
        qz=qz,
        qw=qw,
        behavior_tree=str(behavior_tree).strip(),
    )


def evaluate_dispatch_request(
    request: dict[str, Any],
    config: DispatcherConfig,
    now_monotonic: float,
    active_goal: bool,
    last_signature: tuple[str, str, str] | None,
    last_dispatch_monotonic: float | None,
) -> DispatchDecision:
    requested_action = str(request.get("requested_action", "")).strip().lower()
    reason = str(request.get("reason", "")).strip().lower()
    planner_mode = str(request.get("planner_mode", "")).strip()

    if not requested_action:
        return DispatchDecision(
            kind=DispatchDecisionKind.REJECT,
            requested_action=requested_action,
            reason=reason,
            decision_reason="missing_requested_action",
        )

    if not planner_mode:
        return DispatchDecision(
            kind=DispatchDecisionKind.REJECT,
            requested_action=requested_action,
            reason=reason,
            decision_reason="missing_planner_mode",
        )

    if requested_action == "hold":
        if active_goal:
            return DispatchDecision(
                kind=DispatchDecisionKind.CANCEL,
                requested_action=requested_action,
                reason=reason,
                decision_reason="hold_cancels_active_dispatch_goal",
            )
        return DispatchDecision(
            kind=DispatchDecisionKind.REJECT,
            requested_action=requested_action,
            reason=reason,
            decision_reason="hold_without_active_goal",
        )

    if requested_action not in ACTION_GOAL_MAP:
        return DispatchDecision(
            kind=DispatchDecisionKind.REJECT,
            requested_action=requested_action,
            reason=reason,
            decision_reason="action_not_navigation_dispatchable",
        )

    if not config.dispatch_enabled:
        return DispatchDecision(
            kind=DispatchDecisionKind.REJECT,
            requested_action=requested_action,
            reason=reason,
            decision_reason="dispatch_disabled",
        )

    if requested_action not in config.allowed_actions:
        return DispatchDecision(
            kind=DispatchDecisionKind.REJECT,
            requested_action=requested_action,
            reason=reason,
            decision_reason="action_not_in_allowed_actions",
        )

    if requested_action == "trigger_safe_mode" and reason not in config.trigger_safe_mode_reasons:
        return DispatchDecision(
            kind=DispatchDecisionKind.REJECT,
            requested_action=requested_action,
            reason=reason,
            decision_reason="reason_not_allowed_for_safe_mode_dispatch",
        )

    if requested_action == "need_reobserve" and reason not in config.need_reobserve_reasons:
        return DispatchDecision(
            kind=DispatchDecisionKind.REJECT,
            requested_action=requested_action,
            reason=reason,
            decision_reason="reason_not_allowed_for_reobserve_dispatch",
        )

    goal_name = config.action_goal_map.get(requested_action, "")
    goal = config.named_goals.get(goal_name)
    if goal is None:
        return DispatchDecision(
            kind=DispatchDecisionKind.REJECT,
            requested_action=requested_action,
            reason=reason,
            decision_reason="configured_goal_missing",
            goal_name=goal_name,
        )

    if goal.frame_id != config.goal_frame_id:
        return DispatchDecision(
            kind=DispatchDecisionKind.REJECT,
            requested_action=requested_action,
            reason=reason,
            decision_reason="goal_frame_not_allowed",
            goal_name=goal_name,
        )

    signature = (requested_action, reason, goal_name)
    if active_goal:
        return DispatchDecision(
            kind=DispatchDecisionKind.REJECT,
            requested_action=requested_action,
            reason=reason,
            decision_reason="active_goal_reject_new",
            goal_name=goal_name,
            goal=goal,
            signature=signature,
        )

    if (
        last_signature == signature
        and last_dispatch_monotonic is not None
        and (now_monotonic - last_dispatch_monotonic) < config.cooldown_sec
    ):
        return DispatchDecision(
            kind=DispatchDecisionKind.REJECT,
            requested_action=requested_action,
            reason=reason,
            decision_reason="duplicate_request_in_cooldown",
            goal_name=goal_name,
            goal=goal,
            signature=signature,
        )

    return DispatchDecision(
        kind=DispatchDecisionKind.DISPATCH,
        requested_action=requested_action,
        reason=reason,
        decision_reason="dispatch_allowed",
        goal_name=goal_name,
        goal=goal,
        signature=signature,
    )
