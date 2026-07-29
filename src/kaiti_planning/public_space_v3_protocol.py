"""S0-only contracts for the public-space V3.0.1 logical protocol.

This module deliberately contains no ROS nodes, perception, navigation, zone
generation, or online repair solver.  It freezes message validation, revision
rejection, and the nine top-level repair/fallback decisions so later stages
have an executable contract.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml


UINT64_MAX = (1 << 64) - 1


@dataclass(frozen=True)
class FieldRule:
    kind: str
    required: bool = True
    nullable: bool = False
    enum_key: str | None = None
    length: int | None = None
    minimum: float | None = None
    maximum: float | None = None


@dataclass(frozen=True)
class MessageRule:
    fields: Mapping[str, FieldRule]
    revision_fields: tuple[str, ...] = ()


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    field: str
    detail: str


@dataclass(frozen=True)
class ValidationResult:
    accepted: bool
    issues: tuple[ValidationIssue, ...] = ()

    @property
    def reason_codes(self) -> tuple[str, ...]:
        return tuple(issue.code for issue in self.issues)


@dataclass(frozen=True)
class RepairGateContext:
    local_solver_status: str = "FEASIBLE"
    local_time_limit_reached: bool = False
    feasible_incumbent: bool = True
    validator_passed: bool = True
    frozen_safety_conflict: bool = False
    safely_releasable: bool = True
    service_pair_valid: bool = True
    remaining_tasks: int = 0
    affected_tasks: int = 0
    all_active_robots_affected: bool = False
    global_resource_or_safety_structure_changed: bool = False
    local_failures_in_window: int = 0
    robot_unavailable_breaks_hard_role: bool = False
    multiple_changes_make_local_boundary_untrusted: bool = False


@dataclass(frozen=True)
class RepairDecision:
    selected_kind: str
    fallback_rule_id: str | None
    affected_ratio: float
    affected_ratio_gate_applied: bool


@dataclass(frozen=True)
class ZoneAckDecision:
    state: str
    missing_robot_ids: tuple[str, ...]
    reason_code: str


def _r(
    kind: str,
    *,
    required: bool = True,
    nullable: bool = False,
    enum_key: str | None = None,
    length: int | None = None,
    minimum: float | None = None,
    maximum: float | None = None,
) -> FieldRule:
    return FieldRule(
        kind=kind,
        required=required,
        nullable=nullable,
        enum_key=enum_key,
        length=length,
        minimum=minimum,
        maximum=maximum,
    )


MESSAGE_RULES: dict[str, MessageRule] = {
    "SemanticEvent3D": MessageRule(
        fields={
            "stamp_ns": _r("int", minimum=0),
            "frame_id": _r("str"),
            "event_id": _r("str"),
            "track_id": _r("str"),
            "event_type": _r("str"),
            "semantic_state": _r("str", enum_key="semantic_state"),
            "confidence": _r("number", minimum=0, maximum=1),
            "observation_quality": _r("number", minimum=0, maximum=1),
            "pose_valid": _r("bool"),
            "position": _r("list", nullable=True, length=3),
            "covariance": _r("list", nullable=True, length=36),
            "observer_robot_id": _r("str"),
            "observer_pose_map": _r("list", nullable=True, length=3),
            "observation_distance_m": _r("number", nullable=True, minimum=0),
            "region_id": _r("str"),
            "region_probability": _r("number", minimum=0, maximum=1),
            "valid_until_ns": _r("int", minimum=0),
            "perception_revision": _r("int", minimum=0, maximum=UINT64_MAX),
            "reason_code": _r("str"),
        },
        revision_fields=("perception_revision",),
    ),
    "DynamicZone": MessageRule(
        fields={
            "stamp_ns": _r("int", minimum=0),
            "frame_id": _r("str"),
            "zone_id": _r("str"),
            "event_id": _r("str"),
            "center_xy": _r("list", length=2),
            "covariance_xy": _r("list", length=4),
            "safe_radius": _r("number", minimum=0),
            "polygon_xy": _r("list"),
            "hard_keepout": _r("bool"),
            "provisional": _r("bool"),
            "zone_revision": _r("int", minimum=0, maximum=UINT64_MAX),
            "source_perception_revision": _r("int", minimum=0, maximum=UINT64_MAX),
            "valid_until_ns": _r("int", minimum=0),
            "lifecycle": _r("str", enum_key="zone_lifecycle"),
            "reason_code": _r("str"),
        },
        revision_fields=("zone_revision", "source_perception_revision"),
    ),
    "RoleServicePointArray": MessageRule(
        fields={
            "event_id": _r("str"),
            "pair_valid": _r("bool"),
            "generation_status": _r("str", enum_key="service_generation_status"),
            "generation_runtime_sec": _r("number", minimum=0),
            "zone_revision": _r("int", minimum=0, maximum=UINT64_MAX),
            "service_revision": _r("int", minimum=0, maximum=UINT64_MAX),
            "failure_reason": _r("str"),
            "points": _r("list"),
        },
        revision_fields=("zone_revision", "service_revision"),
    ),
    "SemanticEdgeState": MessageRule(
        fields={
            "edge_id": _r("str"),
            "from_region": _r("str"),
            "to_region": _r("str"),
            "state": _r("str", enum_key="edge_state"),
            "path_exists": _r("bool"),
            "path_length_m": _r("number", nullable=True, minimum=0),
            "baseline_length_m": _r("number", minimum=0),
            "cost_ratio": _r("number", nullable=True, minimum=0),
            "state_since_ns": _r("int", minimum=0),
            "valid_until_ns": _r("int", minimum=0),
            "edge_revision": _r("int", minimum=0, maximum=UINT64_MAX),
            "reason_code": _r("str"),
        },
        revision_fields=("edge_revision",),
    ),
    "ZoneApplyAck": MessageRule(
        fields={
            "robot_id": _r("str"),
            "zone_id": _r("str"),
            "zone_revision": _r("int", minimum=0, maximum=UINT64_MAX),
            "applied": _r("bool"),
            "applied_at_ns": _r("int", minimum=0),
            "reason_code": _r("str"),
        },
        revision_fields=("zone_revision",),
    ),
    "PlanningTrigger": MessageRule(
        fields={
            "stamp_ns": _r("int", minimum=0),
            "trigger_type": _r("str", enum_key="planning_trigger"),
            "changed_entity_ids": _r("list"),
            "world_revision": _r("int", minimum=0, maximum=UINT64_MAX),
            "source_revision": _r("int", minimum=0, maximum=UINT64_MAX),
            "reason_code": _r("str"),
        },
        revision_fields=("world_revision", "source_revision"),
    ),
    "TaskPlan": MessageRule(
        fields={
            "planner_instance_id": _r("str"),
            "plan_id": _r("str"),
            "plan_revision": _r("int", minimum=0, maximum=UINT64_MAX),
            "source_world_revision": _r("int", minimum=0, maximum=UINT64_MAX),
            "source_zone_revision": _r("int", minimum=0, maximum=UINT64_MAX),
            "generated_at_ns": _r("int", minimum=0),
            "valid_from_ns": _r("int", minimum=0),
            "plan_epoch_ns": _r("int", minimum=0),
            "solver_status": _r("str", enum_key="solver_status"),
            "plan_kind": _r("str", enum_key="plan_kind"),
            "assignments": _r("list"),
            "resource_reservations": _r("list"),
            "affected_tasks": _r("list"),
            "frozen_tasks": _r("list"),
            "objective_components": _r("dict"),
            "runtime_sec": _r("number", minimum=0),
            "mip_gap": _r("number", minimum=0, maximum=1),
            "validator_passed": _r("bool"),
            "reason_code": _r("str"),
        },
        revision_fields=("plan_revision", "source_world_revision", "source_zone_revision"),
    ),
    "ExecutionFeedback": MessageRule(
        fields={
            "stamp_ns": _r("int", minimum=0),
            "robot_id": _r("str"),
            "plan_id": _r("str"),
            "plan_revision": _r("int", minimum=0, maximum=UINT64_MAX),
            "source_world_revision": _r("int", minimum=0, maximum=UINT64_MAX),
            "task_id": _r("str"),
            "attempt": _r("int", minimum=0),
            "state": _r("str", enum_key="execution_state"),
            "failure_class": _r("str", enum_key="execution_failure_class"),
            "actual_pose_map": _r("list", length=3),
            "nav2_error_code": _r("int"),
            "reason_code": _r("str"),
        },
        revision_fields=("plan_revision", "source_world_revision"),
    ),
    "RepairStatus": MessageRule(
        fields={
            "stamp_ns": _r("int", minimum=0),
            "trigger_type": _r("str", enum_key="planning_trigger"),
            "solved_world_revision": _r("int", minimum=0, maximum=UINT64_MAX),
            "selected_kind": _r("str", enum_key="repair_selected_kind"),
            "affected_tasks": _r("list"),
            "frozen_tasks": _r("list"),
            "remaining_task_count": _r("int", minimum=0),
            "affected_task_count": _r("int", minimum=0),
            "affected_ratio": _r("number", minimum=0),
            "affected_ratio_gate_applied": _r("bool"),
            "all_active_robots_affected": _r("bool"),
            "global_resource_or_safety_structure_changed": _r("bool"),
            "local_solver_status": _r("str", enum_key="solver_status"),
            "full_solver_status": _r("str", enum_key="solver_status"),
            "fallback_used": _r("bool"),
            "fallback_reason": _r("str", nullable=True),
            "local_changes": _r("int", minimum=0),
            "full_changes": _r("int", minimum=0),
            "change_records": _r("list"),
            "runtime_sec": _r("number", minimum=0),
            "validator_passed": _r("bool"),
            "published": _r("bool"),
            "reason_code": _r("str"),
        },
        revision_fields=("solved_world_revision",),
    ),
    "HoldSafeCommand": MessageRule(
        fields={
            "stamp_ns": _r("int", minimum=0),
            "command_id": _r("str"),
            "world_revision": _r("int", minimum=0, maximum=UINT64_MAX),
            "plan_revision": _r("int", minimum=0, maximum=UINT64_MAX),
            "target_robot_ids": _r("list"),
            "cancel_active_nav": _r("bool"),
            "dispatch_lock": _r("bool"),
            "reason_code": _r("str"),
        },
        revision_fields=("world_revision", "plan_revision"),
    ),
    "SafetyStopStatus": MessageRule(
        fields={
            "stamp_ns": _r("int", minimum=0),
            "command_id": _r("str"),
            "robot_id": _r("str"),
            "world_revision": _r("int", minimum=0, maximum=UINT64_MAX),
            "command_received_at_ns": _r("int", minimum=0),
            "cancel_requested_at_ns": _r("int", nullable=True, minimum=0),
            "cancel_acknowledged": _r("bool"),
            "cancel_ack_at_ns": _r("int", nullable=True, minimum=0),
            "active_nav_goal": _r("bool"),
            "linear_speed_mps": _r("number"),
            "angular_speed_rps": _r("number"),
            "dispatch_locked": _r("bool"),
            "state": _r("str", enum_key="safety_stop_state"),
            "reason_code": _r("str"),
        },
        revision_fields=("world_revision",),
    ),
}


SERVICE_POINT_FIELDS = {
    "service_point_id",
    "event_id",
    "role",
    "pose_map",
    "clearance_m",
    "path_exists",
    "path_length_m",
    "estimated_time_sec",
    "zone_revision",
    "service_revision",
    "valid_until_ns",
    "reason_code",
}


OBJECTIVE_COMPONENT_FIELDS = {
    "Cmax_bar",
    "L_bar",
    "Nchange_bar",
    "Rwait_bar",
    "Erisk_bar",
    "raw_values",
    "normalization_denominators",
}


TASK_ASSIGNMENT_FIELDS = {
    "robot_id",
    "task_id",
    "event_id",
    "task_type",
    "target_pose_map",
    "start_offset_sec",
    "finish_offset_sec",
    "deadline_ns",
    "predecessors",
    "resources",
    "required_zone_revision",
}


def load_contract_config(path: str | Path) -> dict[str, Any]:
    payload = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("public-space config must be a mapping")
    return payload


def flatten_parameter_names(parameters: Mapping[str, Any]) -> list[str]:
    names: list[str] = []
    for key, value in parameters.items():
        if isinstance(value, Mapping):
            names.extend(flatten_parameter_names(value))
        else:
            names.append(str(key))
    return names


def flatten_parameters(parameters: Mapping[str, Any]) -> dict[str, Any]:
    flat: dict[str, Any] = {}
    for key, value in parameters.items():
        if isinstance(value, Mapping):
            nested = flatten_parameters(value)
            duplicate = set(flat).intersection(nested)
            if duplicate:
                raise ValueError(f"duplicate parameter names: {sorted(duplicate)}")
            flat.update(nested)
        elif key in flat:
            raise ValueError(f"duplicate parameter name: {key}")
        else:
            flat[str(key)] = value
    return flat


def _kind_matches(kind: str, value: Any) -> bool:
    if kind == "bool":
        return type(value) is bool
    if kind == "int":
        return type(value) is int
    if kind == "number":
        return (type(value) in (int, float)) and not isinstance(value, bool)
    if kind == "str":
        return isinstance(value, str)
    if kind == "list":
        return isinstance(value, list)
    if kind == "dict":
        return isinstance(value, dict)
    raise ValueError(f"unsupported field kind: {kind}")


def _contains_non_finite(value: Any) -> bool:
    if isinstance(value, float):
        return not math.isfinite(value)
    if isinstance(value, Mapping):
        return any(_contains_non_finite(item) for item in value.values())
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return any(_contains_non_finite(item) for item in value)
    return False


class ProtocolMessageValidator:
    """Strict validator for the eleven V3.0.1 logical message objects."""

    def __init__(self, config: Mapping[str, Any]):
        self.config = config
        self.enums = config["protocol"]["enums"]
        self.reason_codes = config["protocol"]["reason_codes"]
        self.parameters = flatten_parameters(config["parameters"])

    def validate(
        self,
        message_type: str,
        payload: Mapping[str, Any],
        *,
        current_revisions: Mapping[str, int] | None = None,
    ) -> ValidationResult:
        if message_type not in MESSAGE_RULES:
            return ValidationResult(
                False,
                (ValidationIssue("unknown_message_type", "", message_type),),
            )
        if not isinstance(payload, Mapping):
            return ValidationResult(
                False,
                (ValidationIssue("invalid_object", "", "payload must be a mapping"),),
            )

        rule = MESSAGE_RULES[message_type]
        issues: list[ValidationIssue] = []
        unknown = sorted(set(payload).difference(rule.fields))
        for field_name in unknown:
            issues.append(ValidationIssue("unknown_field", field_name, "field is not frozen"))

        for field_name, field_rule in rule.fields.items():
            if field_name not in payload:
                if field_rule.required:
                    issues.append(ValidationIssue("missing_field", field_name, "complete object required"))
                continue
            value = payload[field_name]
            if value is None:
                if not field_rule.nullable:
                    issues.append(ValidationIssue("null_not_allowed", field_name, "field is not nullable"))
                continue
            if not _kind_matches(field_rule.kind, value):
                issues.append(
                    ValidationIssue("invalid_type", field_name, f"expected {field_rule.kind}")
                )
                continue
            if field_rule.length is not None and len(value) != field_rule.length:
                issues.append(
                    ValidationIssue(
                        "invalid_length",
                        field_name,
                        f"expected length {field_rule.length}",
                    )
                )
            if field_rule.minimum is not None and value < field_rule.minimum:
                issues.append(ValidationIssue("below_minimum", field_name, str(field_rule.minimum)))
            if field_rule.maximum is not None and value > field_rule.maximum:
                issues.append(ValidationIssue("above_maximum", field_name, str(field_rule.maximum)))
            if field_rule.enum_key is not None and value not in self.enums[field_rule.enum_key]:
                issues.append(
                    ValidationIssue("invalid_enum", field_name, field_rule.enum_key)
                )

        if _contains_non_finite(payload):
            issues.append(ValidationIssue("non_finite_number", "", "NaN/Inf rejected"))

        reason_field = "failure_reason" if message_type == "RoleServicePointArray" else "reason_code"
        if reason_field in payload and payload[reason_field] is not None:
            allowed = self.reason_codes.get(message_type, ())
            if payload[reason_field] not in allowed:
                issues.append(
                    ValidationIssue("invalid_reason_code", reason_field, str(payload[reason_field]))
                )

        current_revisions = current_revisions or {}
        for revision_field in rule.revision_fields:
            if revision_field not in payload or type(payload[revision_field]) is not int:
                continue
            current = current_revisions.get(revision_field)
            if current is not None and payload[revision_field] < current:
                issues.append(
                    ValidationIssue(
                        "stale_revision",
                        revision_field,
                        f"{payload[revision_field]} < {current}",
                    )
                )

        self._validate_conditions(message_type, payload, issues)
        return ValidationResult(not issues, tuple(issues))

    def _validate_conditions(
        self,
        message_type: str,
        payload: Mapping[str, Any],
        issues: list[ValidationIssue],
    ) -> None:
        map_frame = self.config["contract_constants"]["map_frame"]["value"]
        if "frame_id" in payload and payload.get("frame_id") != map_frame:
            issues.append(ValidationIssue("invalid_frame", "frame_id", map_frame))

        if message_type == "SemanticEvent3D":
            if payload.get("event_type") != self.config["contract_constants"]["event_type"]["value"]:
                issues.append(ValidationIssue("invalid_event_type", "event_type", "fall required"))
            if payload.get("observer_robot_id") != "R1":
                issues.append(ValidationIssue("invalid_observer", "observer_robot_id", "R1 required"))
            if payload.get("semantic_state") == "event_confirmed" and not payload.get("event_id"):
                issues.append(ValidationIssue("missing_event_id", "event_id", "confirmed requires ID"))
            if payload.get("pose_valid"):
                if payload.get("position") is None or payload.get("covariance") is None:
                    issues.append(
                        ValidationIssue("missing_valid_pose", "position", "valid pose requires covariance")
                    )
                elif all(float(item) == 0.0 for item in payload["covariance"]):
                    issues.append(
                        ValidationIssue("zero_covariance", "covariance", "valid pose cannot be zero")
                    )
            if payload.get("semantic_state") == "event_confirmed":
                if payload.get("observer_pose_map") is None:
                    issues.append(
                        ValidationIssue("missing_observer_pose", "observer_pose_map", "confirmed required")
                    )
                if payload.get("pose_valid") and payload.get("observation_distance_m") is None:
                    issues.append(
                        ValidationIssue(
                            "missing_observation_distance",
                            "observation_distance_m",
                            "confirmed valid pose required",
                        )
                    )

        elif message_type == "DynamicZone":
            if payload.get("hard_keepout") is not True:
                issues.append(ValidationIssue("keepout_not_hard", "hard_keepout", "P0 requires true"))
            safe_radius = payload.get("safe_radius")
            if type(safe_radius) in (int, float) and not (
                self.parameters["r_safe_min_m"]
                <= safe_radius
                <= self.parameters["r_safe_max_m"]
            ):
                issues.append(
                    ValidationIssue(
                        "safe_radius_out_of_bounds",
                        "safe_radius",
                        "must remain within frozen clamp",
                    )
                )
            if payload.get("provisional") is True and safe_radius != self.parameters["r_safe_max_m"]:
                issues.append(
                    ValidationIssue(
                        "invalid_provisional_radius",
                        "safe_radius",
                        "provisional zone requires r_safe_max_m",
                    )
                )
            polygon = payload.get("polygon_xy")
            required_vertices = self.parameters["zone_polygon_vertices"]
            if isinstance(polygon, list) and len(polygon) != required_vertices:
                issues.append(
                    ValidationIssue(
                        "invalid_zone_polygon_vertices",
                        "polygon_xy",
                        str(required_vertices),
                    )
                )

        elif message_type == "RoleServicePointArray":
            points = payload.get("points")
            if isinstance(points, list):
                for index, point in enumerate(points):
                    if not isinstance(point, Mapping):
                        issues.append(
                            ValidationIssue("invalid_service_point", f"points[{index}]", "mapping required")
                        )
                        continue
                    missing = SERVICE_POINT_FIELDS.difference(point)
                    unknown = set(point).difference(SERVICE_POINT_FIELDS)
                    if missing:
                        issues.append(
                            ValidationIssue(
                                "missing_service_point_fields",
                                f"points[{index}]",
                                ",".join(sorted(missing)),
                            )
                        )
                    if unknown:
                        issues.append(
                            ValidationIssue(
                                "unknown_service_point_fields",
                                f"points[{index}]",
                                ",".join(sorted(unknown)),
                            )
                        )
                    if point.get("role") not in self.enums["service_role"]:
                        issues.append(
                            ValidationIssue("invalid_enum", f"points[{index}].role", "service_role")
                        )
                    if point.get("reason_code") not in self.reason_codes["RoleServicePointArray"]:
                        issues.append(
                            ValidationIssue(
                                "invalid_reason_code",
                                f"points[{index}].reason_code",
                                str(point.get("reason_code")),
                            )
                        )
                    for revision_field in ("zone_revision", "service_revision"):
                        if point.get(revision_field) != payload.get(revision_field):
                            issues.append(
                                ValidationIssue(
                                    "nested_revision_mismatch",
                                    f"points[{index}].{revision_field}",
                                    "must match array revision",
                                )
                            )
                if payload.get("pair_valid"):
                    roles = {point.get("role") for point in points if isinstance(point, Mapping)}
                    if len(points) != 2 or roles != {"verifier", "courier"}:
                        issues.append(
                            ValidationIssue(
                                "invalid_service_pair",
                                "points",
                                "valid pair requires verifier and courier",
                            )
                        )

        elif message_type == "TaskPlan":
            objective = payload.get("objective_components")
            if isinstance(objective, Mapping) and set(objective) != OBJECTIVE_COMPONENT_FIELDS:
                issues.append(
                    ValidationIssue(
                        "invalid_objective_components",
                        "objective_components",
                        "normalized and raw fields must be complete",
                    )
                )
            if payload.get("validator_passed") is not True:
                issues.append(
                    ValidationIssue("validator_not_passed", "validator_passed", "plan is not publishable")
                )
            assignments = payload.get("assignments")
            if isinstance(assignments, list):
                for index, assignment in enumerate(assignments):
                    if not isinstance(assignment, Mapping):
                        issues.append(
                            ValidationIssue(
                                "invalid_assignment",
                                f"assignments[{index}]",
                                "mapping required",
                            )
                        )
                        continue
                    missing = TASK_ASSIGNMENT_FIELDS.difference(assignment)
                    unknown = set(assignment).difference(TASK_ASSIGNMENT_FIELDS)
                    if missing:
                        issues.append(
                            ValidationIssue(
                                "missing_assignment_fields",
                                f"assignments[{index}]",
                                ",".join(sorted(missing)),
                            )
                        )
                    if unknown:
                        issues.append(
                            ValidationIssue(
                                "unknown_assignment_fields",
                                f"assignments[{index}]",
                                ",".join(sorted(unknown)),
                            )
                        )
                    required_zone_revision = assignment.get("required_zone_revision")
                    if (
                        type(required_zone_revision) is not int
                        or required_zone_revision < payload.get("source_zone_revision", 0)
                    ):
                        issues.append(
                            ValidationIssue(
                                "stale_assignment_zone_revision",
                                f"assignments[{index}].required_zone_revision",
                                "must be at least source_zone_revision",
                            )
                        )

        elif message_type == "ZoneApplyAck":
            if payload.get("robot_id") not in self.config["contract_constants"]["active_robot_ids"]["value"]:
                issues.append(
                    ValidationIssue("invalid_robot_id", "robot_id", "active P0 robot required")
                )

        elif message_type == "RepairStatus":
            remaining = payload.get("remaining_task_count")
            affected = payload.get("affected_task_count")
            ratio = payload.get("affected_ratio")
            if type(remaining) is int and type(affected) is int:
                expected = affected / max(1, remaining)
                if type(ratio) not in (int, float) or not math.isclose(
                    float(ratio), expected, rel_tol=0.0, abs_tol=1e-12
                ):
                    issues.append(
                        ValidationIssue(
                            "affected_ratio_mismatch",
                            "affected_ratio",
                            "must match affected/remaining",
                        )
                    )

        elif message_type == "HoldSafeCommand":
            if payload.get("cancel_active_nav") is not True:
                issues.append(
                    ValidationIssue("cancel_not_required", "cancel_active_nav", "must be true")
                )
            if payload.get("dispatch_lock") is not True:
                issues.append(
                    ValidationIssue("dispatch_not_locked", "dispatch_lock", "must be true")
                )
            targets = payload.get("target_robot_ids")
            allowed_targets = set(
                self.config["contract_constants"]["active_robot_ids"]["value"]
            )
            if not isinstance(targets, list) or not targets or not set(targets).issubset(allowed_targets):
                issues.append(
                    ValidationIssue(
                        "invalid_target_robot_ids",
                        "target_robot_ids",
                        "non-empty subset of active P0 robots required",
                    )
                )

        elif message_type == "SafetyStopStatus" and payload.get("state") == "STOPPED":
            conditions = {
                "cancel_acknowledged": payload.get("cancel_acknowledged") is True,
                "cancel_requested_at_ns": payload.get("cancel_requested_at_ns") is not None,
                "cancel_ack_at_ns": payload.get("cancel_ack_at_ns") is not None,
                "active_nav_goal": payload.get("active_nav_goal") is False,
                "linear_speed_mps": abs(float(payload.get("linear_speed_mps", math.inf)))
                <= self.parameters["hold_linear_speed_threshold_mps"],
                "angular_speed_rps": abs(float(payload.get("angular_speed_rps", math.inf)))
                <= self.parameters["hold_angular_speed_threshold_rps"],
                "dispatch_locked": payload.get("dispatch_locked") is True,
            }
            for field_name, passed in conditions.items():
                if not passed:
                    issues.append(
                        ValidationIssue(
                            "invalid_stopped_state",
                            field_name,
                            "STOPPED physical condition not met",
                        )
                    )


def select_repair_mode(
    context: RepairGateContext,
    config: Mapping[str, Any],
) -> RepairDecision:
    """Evaluate the nine frozen top-level fallback conditions.

    This is a policy contract, not a LocalRepair or MILP implementation.
    """

    params = flatten_parameters(config["parameters"])
    ratio = context.affected_tasks / max(1, context.remaining_tasks)
    ratio_applied = context.remaining_tasks >= params["affected_ratio_min_remaining_tasks"]

    rule_id: str | None = None
    if context.local_solver_status in {"INFEASIBLE", "ERROR"}:
        rule_id = "LOCAL_SOLVER_FAILURE"
    elif context.local_time_limit_reached and not context.feasible_incumbent:
        rule_id = "LOCAL_NO_FEASIBLE_INCUMBENT"
    elif not context.validator_passed:
        rule_id = "VALIDATOR_HARD_CONSTRAINT_FAILURE"
    elif context.frozen_safety_conflict and not context.safely_releasable:
        rule_id = "FROZEN_SAFETY_CONFLICT"
    elif not context.service_pair_valid:
        rule_id = "NO_VALID_SERVICE_PAIR"
    elif (
        ratio_applied and ratio > params["affected_ratio_full_replan"]
    ) or context.all_active_robots_affected or context.global_resource_or_safety_structure_changed:
        rule_id = "SCOPE_OR_GLOBAL_STRUCTURE"
    elif context.local_failures_in_window >= params["max_local_failures_in_window"]:
        rule_id = "REPEATED_LOCAL_FAILURE"
    elif context.robot_unavailable_breaks_hard_role:
        rule_id = "ROBOT_CAPABILITY_LOSS"
    elif context.multiple_changes_make_local_boundary_untrusted:
        rule_id = "LOCAL_BOUNDARY_UNTRUSTED"

    return RepairDecision(
        selected_kind="FULL_REPLAN" if rule_id else "LOCAL_REPAIR",
        fallback_rule_id=rule_id,
        affected_ratio=ratio,
        affected_ratio_gate_applied=ratio_applied,
    )


def evaluate_zone_ack_gate(
    *,
    required_zone_revision: int,
    acknowledgements: Mapping[str, int],
    elapsed_sec: float,
    config: Mapping[str, Any],
) -> ZoneAckDecision:
    """Evaluate the frozen all-active-robot keepout acknowledgement gate."""

    robot_ids = tuple(config["contract_constants"]["active_robot_ids"]["value"])
    missing = tuple(
        robot_id
        for robot_id in robot_ids
        if acknowledgements.get(robot_id, -1) < required_zone_revision
    )
    if not missing:
        return ZoneAckDecision("READY", (), "applied")

    timeout = flatten_parameters(config["parameters"])["keepout_apply_timeout_sec"]
    if elapsed_sec >= timeout:
        return ZoneAckDecision("HOLD_SAFE", missing, "zone_ack_timeout")
    return ZoneAckDecision("WAIT_FOR_ACK", missing, "apply_pending")


def evaluate_state_action_contract(
    case_input: Mapping[str, Any],
    config: Mapping[str, Any],
) -> dict[str, Any]:
    """Return the frozen table action for an S0 test vector.

    The function is intentionally declarative.  It neither mutates world state
    nor dispatches work; later online nodes must reproduce these outcomes.
    """

    if case_input.get("full_replan_failed"):
        return {
            "planner_action": "HOLD_SAFE",
            "r1_action": "KEEP_SAFE_MONITOR",
            "r2_action": "CANCEL_AND_STOP",
            "dispatch_new_goal": False,
            "reason_code": "full_replan_infeasible",
        }

    solver_revision = case_input.get("solver_world_revision")
    current_revision = case_input.get("current_world_revision")
    if (
        type(solver_revision) is int
        and type(current_revision) is int
        and solver_revision != current_revision
    ):
        return {
            "planner_action": "DISCARD_STALE",
            "publish_plan": False,
            "reason_code": "stale_solver_result",
        }

    if case_input.get("zone_ack_timeout"):
        return {
            "planner_action": "HOLD_SAFE",
            "publish_plan": False,
            "reason_code": "zone_ack_timeout",
        }

    if case_input.get("hold_safe"):
        stopped = (
            case_input.get("cancel_acknowledged") is True
            and case_input.get("active_nav_goal") is False
            and abs(float(case_input.get("linear_speed_mps", math.inf)))
            <= flatten_parameters(config["parameters"])["hold_linear_speed_threshold_mps"]
            and abs(float(case_input.get("angular_speed_rps", math.inf)))
            <= flatten_parameters(config["parameters"])["hold_angular_speed_threshold_rps"]
            and case_input.get("dispatch_locked") is True
        )
        return {
            "planner_action": "HOLD_SAFE",
            "stop_state": "STOPPED" if stopped else "FAILED",
            "dispatch_new_goal": False,
            "reason_code": "stopped" if stopped else "hold_stop_failed",
        }

    lifecycle = case_input.get("lifecycle_event")
    if lifecycle == "verify_no_fall":
        return {
            "episode_action": "CLOSE",
            "r1_action": "RESUME_PATROL",
            "r2_action": "CANCEL_UNSTARTED",
            "zone_action": "CLEAR_AFTER_HOLD",
            "planning_trigger": "EVENT_CLOSED",
        }
    if lifecycle == "deliver_completed":
        return {
            "episode_action": "SUPPLY_COMPLETED",
            "r1_action": "MONITOR_MAY_END",
            "r2_action": "EXIT_DELIVERY_POINT",
            "zone_action": "KEEP",
        }
    if lifecycle == "scene_clear":
        return {
            "episode_action": "CLOSE",
            "r1_action": "RESUME_PATROL",
            "r2_action": "RESUME_STANDBY",
            "zone_action": "CLEAR_AFTER_HOLD",
        }

    semantic_state = case_input.get("semantic_state")
    pose_valid = case_input.get("pose_valid")
    active_episode = case_input.get("active_episode", False)

    if semantic_state == "normal" and not active_episode:
        return {
            "episode_action": "NONE",
            "r1_action": "PATROL",
            "r2_action": "STANDBY",
            "zone_action": "NONE",
            "planner_action": "NO_REPLAN",
        }

    if semantic_state == "event_uncertain":
        return {
            "episode_action": "UPSERT_CANDIDATE",
            "r1_action": "REOBSERVE" if pose_valid else "LOCAL_REOBSERVE_OR_HOLD",
            "r2_action": "NO_DISPATCH" if pose_valid else "HOLD",
            "zone_action": "DEBUG_ONLY" if pose_valid else "NONE",
            "planner_action": "R1_LOCAL_OPTIONAL" if pose_valid else "NO_REPLAN",
        }

    if semantic_state == "event_confirmed" and pose_valid:
        if not case_input.get("confirmation_clearance_passed"):
            return {
                "episode_action": "KEEP_CONFIRMED_MARK_INVALID_SCENARIO",
                "r1_action": "CANCEL_AND_STOP",
                "r2_action": "CANCEL_AND_STOP",
                "zone_action": "DO_NOT_CREATE_FORMAL_ZONE",
                "planner_action": "HOLD_SAFE",
                "reason_code": "scenario_precondition_failed",
            }
        return {
            "episode_action": "CONFIRM",
            "r1_action": "VERIFY_AND_MONITOR",
            "r2_action": "PICKUP_AND_DELIVER",
            "zone_action": "CREATE_HARD_ZONE_AND_SERVICE_PAIR",
            "planner_action": "PLAN",
            "planning_trigger": "NEW_CONFIRMED_EVENT",
        }

    if semantic_state == "event_confirmed" and not pose_valid:
        if case_input.get("old_zone_available"):
            zone_action = "KEEP_OLD_ZONE"
            planner_action = "REOBSERVE_ONLY"
        elif case_input.get("fallback_center") in {"ground_projection", "region_centroid"}:
            zone_action = "CREATE_PROVISIONAL_MAX_RADIUS"
            planner_action = "REOBSERVE_ONLY"
        else:
            zone_action = "NO_GEOMETRIC_ZONE"
            planner_action = "HOLD_SAFE_REOBSERVE"
        return {
            "episode_action": "KEEP_CONFIRMED_POSITION_PENDING",
            "r1_action": "REOBSERVE_NO_LEAVE",
            "r2_action": "HOLD_NO_DELIVER",
            "zone_action": zone_action,
            "planner_action": planner_action,
            "provisional": zone_action == "CREATE_PROVISIONAL_MAX_RADIUS",
        }

    if semantic_state == "perception_degraded":
        if active_episode:
            return {
                "episode_action": "KEEP_ACTIVE",
                "r1_action": "KEEP_MONITOR_AND_REOBSERVE",
                "r2_action": "CONTINUE_ONLY_IF_SERVICE_VALID",
                "zone_action": "INFLATE_ON_STALE",
                "planner_action": "REPLAN_ON_ZONE_OR_SERVICE_THRESHOLD",
            }
        return {
            "episode_action": "KEEP_CANDIDATE_TO_TTL",
            "r1_action": "REOBSERVE_OR_HOLD",
            "r2_action": "NO_DISPATCH",
            "zone_action": "NONE",
            "planner_action": "ON_FIRST_STATE_CHANGE",
        }

    return {
        "planner_action": "REJECT_INPUT",
        "reason_code": "invalid_state_action_vector",
    }
