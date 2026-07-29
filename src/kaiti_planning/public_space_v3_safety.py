"""Simulation safety-rule checker interface frozen during S0.

The checker consumes already-observed facts.  It does not connect to Gazebo,
Nav2, ROS topics, or robot hardware and therefore does not implement S4/S7.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol

from .public_space_v3_protocol import flatten_parameters


NS_PER_SECOND = 1_000_000_000


@dataclass(frozen=True)
class SafetySnapshot:
    stamp_ns: int
    robot_event_distances_m: Mapping[str, float]
    robot_robot_distance_m: float
    corridor_occupancy_overlap: bool = False
    required_zone_revision: int = 0
    acked_zone_revision_by_robot: Mapping[str, int] | None = None
    plan_dispatched: bool = False
    stale_plan_executed: bool = False
    full_replan_infeasible: bool = False
    old_navigation_continues: bool = False
    tf_available: bool = True
    zero_covariance_event_published: bool = False
    deliver_completed: bool = False
    r1_verifier_distance_m: float = 0.0
    confirmed_event: bool = False
    event_observation_distance_m: float = 0.0
    safe_radius_m: float = 0.0
    formal_zone_created: bool = False
    sample_counted_valid: bool = False
    hold_safe_triggered: bool = False
    hold_command_received_at_ns: int | None = None
    active_nav_goal_at_hold: bool = False
    cancel_requested_at_ns: int | None = None
    cancel_ack_at_ns: int | None = None
    linear_speed_mps: float = 0.0
    angular_speed_rps: float = 0.0
    new_goal_dispatched_after_hold: bool = False
    dispatch_lock_released: bool = False
    stopped_status_matches_current_command_revision: bool = False


@dataclass(frozen=True)
class SafetyViolation:
    rule_id: str
    reason_code: str
    detail: str


@dataclass(frozen=True)
class SafetyCheckResult:
    passed: bool
    violations: tuple[SafetyViolation, ...]


class SafetyRuleChecker(Protocol):
    def evaluate(self, snapshot: SafetySnapshot) -> SafetyCheckResult:
        """Evaluate all thirteen frozen P0 simulation safety rules."""


class PublicSpaceV3SafetyChecker:
    """Pure reference checker for V3.0.1 section 7.2."""

    def __init__(self, config: Mapping[str, Any]):
        self.config = config
        self.params = flatten_parameters(config["parameters"])
        self.active_robot_ids = tuple(
            config["contract_constants"]["active_robot_ids"]["value"]
        )

    def evaluate(self, snapshot: SafetySnapshot) -> SafetyCheckResult:
        p = self.params
        violations: list[SafetyViolation] = []

        if any(
            distance < snapshot.safe_radius_m
            for distance in snapshot.robot_event_distances_m.values()
        ):
            violations.append(
                SafetyViolation("SAFE_01", "core_zone_penetration", "robot center entered r_safe")
            )

        if snapshot.robot_robot_distance_m < p["collision_distance_m"]:
            violations.append(
                SafetyViolation("SAFE_02", "robot_collision", "center distance below collision limit")
            )

        if snapshot.corridor_occupancy_overlap:
            violations.append(
                SafetyViolation("SAFE_03", "corridor_capacity_violation", "unplanned overlap")
            )

        acks = snapshot.acked_zone_revision_by_robot or {}
        if snapshot.plan_dispatched and snapshot.required_zone_revision > 0 and any(
            acks.get(robot_id, -1) < snapshot.required_zone_revision
            for robot_id in self.active_robot_ids
        ):
            violations.append(
                SafetyViolation("SAFE_04", "zone_revision_not_acked", "plan dispatch is unsafe")
            )

        if snapshot.stale_plan_executed:
            violations.append(
                SafetyViolation("SAFE_05", "stale_plan_executed", "old revision executed")
            )

        if snapshot.full_replan_infeasible and snapshot.old_navigation_continues:
            violations.append(
                SafetyViolation(
                    "SAFE_06",
                    "navigation_continued_after_full_replan_failure",
                    "old navigation continued",
                )
            )

        if not snapshot.tf_available and snapshot.zero_covariance_event_published:
            violations.append(
                SafetyViolation(
                    "SAFE_07",
                    "zero_covariance_without_tf",
                    "invalid 3D event was published",
                )
            )

        if (
            not snapshot.deliver_completed
            and snapshot.r1_verifier_distance_m > p["xy_goal_tolerance_m"]
        ):
            violations.append(
                SafetyViolation("SAFE_08", "r1_left_monitor_early", "monitor tolerance exceeded")
            )

        r2_distance = snapshot.robot_event_distances_m.get("R2")
        if r2_distance is not None and r2_distance < snapshot.safe_radius_m:
            violations.append(
                SafetyViolation("SAFE_09", "r2_core_zone_penetration", "R2 entered keepout")
            )

        confirmation_minimum = (
            snapshot.safe_radius_m
            + p["xy_goal_tolerance_m"]
            + p["event_confirm_clearance_margin_m"]
        )
        precondition_failed = (
            snapshot.confirmed_event
            and snapshot.event_observation_distance_m < confirmation_minimum
        )
        if precondition_failed and (
            snapshot.formal_zone_created or snapshot.sample_counted_valid
        ):
            violations.append(
                SafetyViolation(
                    "SAFE_10",
                    "scenario_precondition_failed",
                    "invalid confirmation geometry was accepted",
                )
            )

        if snapshot.hold_safe_triggered:
            issue_deadline_ns = _deadline_ns(
                snapshot.hold_command_received_at_ns,
                p["hold_cancel_issue_timeout_sec"],
            )
            issue_late = (
                snapshot.active_nav_goal_at_hold
                and (
                    (
                        snapshot.cancel_requested_at_ns is None
                        and issue_deadline_ns is not None
                        and snapshot.stamp_ns >= issue_deadline_ns
                    )
                    or (
                        issue_deadline_ns is not None
                        and snapshot.cancel_requested_at_ns is not None
                        and snapshot.cancel_requested_at_ns > issue_deadline_ns
                    )
                )
            )
            if snapshot.new_goal_dispatched_after_hold or issue_late:
                violations.append(
                    SafetyViolation(
                        "SAFE_11",
                        "hold_cancel_or_dispatch_failure",
                        "new goal dispatched or cancel not issued in time",
                    )
                )

            ack_deadline_ns = _deadline_ns(
                snapshot.cancel_requested_at_ns,
                p["hold_cancel_ack_timeout_sec"],
            )
            ack_late = (
                snapshot.active_nav_goal_at_hold
                and snapshot.cancel_requested_at_ns is not None
                and (
                    (
                        snapshot.cancel_ack_at_ns is None
                        and ack_deadline_ns is not None
                        and snapshot.stamp_ns >= ack_deadline_ns
                    )
                    or (
                        ack_deadline_ns is not None
                        and snapshot.cancel_ack_at_ns is not None
                        and snapshot.cancel_ack_at_ns > ack_deadline_ns
                    )
                )
            )
            stop_deadline_ns = _deadline_ns(
                snapshot.cancel_ack_at_ns,
                p["safe_stop_timeout_sec"],
            )
            stop_window_elapsed = (
                stop_deadline_ns is not None and snapshot.stamp_ns >= stop_deadline_ns
            )
            speed_above_stop = (
                abs(snapshot.linear_speed_mps) > p["hold_linear_speed_threshold_mps"]
                or abs(snapshot.angular_speed_rps) > p["hold_angular_speed_threshold_rps"]
            )
            if ack_late or (stop_window_elapsed and speed_above_stop):
                violations.append(
                    SafetyViolation(
                        "SAFE_12",
                        "hold_stop_failed",
                        "cancel ack or physical stop deadline failed",
                    )
                )

            if (
                snapshot.dispatch_lock_released
                and not snapshot.stopped_status_matches_current_command_revision
            ):
                violations.append(
                    SafetyViolation(
                        "SAFE_13",
                        "dispatch_lock_released_without_current_stop",
                        "current command/revision STOPPED missing",
                    )
                )

        return SafetyCheckResult(not violations, tuple(violations))


def _deadline_ns(start_ns: int | None, timeout_sec: float) -> int | None:
    if start_ns is None:
        return None
    return start_ns + round(timeout_sec * NS_PER_SECOND)
