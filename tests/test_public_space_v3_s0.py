from __future__ import annotations

from copy import deepcopy
from dataclasses import fields, replace
import hashlib
import json
import math
from pathlib import Path
import re
import sys
from typing import Any

import pytest
import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from kaiti_planning.public_space_v3_protocol import (
    MESSAGE_RULES,
    ProtocolMessageValidator,
    RepairGateContext,
    evaluate_state_action_contract,
    evaluate_zone_ack_gate,
    flatten_parameters,
    load_contract_config,
    select_repair_mode,
)
from kaiti_planning.public_space_v3_safety import (
    NS_PER_SECOND,
    PublicSpaceV3SafetyChecker,
    SafetySnapshot,
)


CONFIG_PATH = PROJECT_ROOT / "configs/public_space_v3.yaml"
REGIONS_PATH = PROJECT_ROOT / "configs/public_space_regions_v3.yaml"
VECTORS_PATH = PROJECT_ROOT / "data/eval/public_space_v3_s0_test_vectors.yaml"
BENCHMARK_TEMPLATE_PATH = (
    PROJECT_ROOT / "data/eval/public_space_v3_benchmark_manifest.template.yaml"
)
HASH_PATH = PROJECT_ROOT / "configs/generated/public_space_v3_s0_hashes.json"
PLAN_PATH = PROJECT_ROOT / "docs/research_plan_v3_0_1.md"


@pytest.fixture(scope="module")
def config() -> dict[str, Any]:
    return load_contract_config(CONFIG_PATH)


@pytest.fixture(scope="module")
def vectors() -> dict[str, Any]:
    return yaml.safe_load(VECTORS_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def validator(config: dict[str, Any]) -> ProtocolMessageValidator:
    return ProtocolMessageValidator(config)


def _markdown_parameter_values() -> dict[str, Any]:
    text = PLAN_PATH.read_text(encoding="utf-8")
    section = text.split("## 3. 冻结参数总表", 1)[1].split("## 4.", 1)[0]
    values: dict[str, Any] = {}
    for line in section.splitlines():
        match = re.match(r"\| `([^`]+)` \| ([^|]+) \|", line)
        if not match or ":E" in match.group(1):
            continue
        name, raw = match.groups()
        value_text = raw.strip().strip("`")
        if re.fullmatch(r"[-+]?\d+", value_text):
            value: Any = int(value_text)
        elif re.fullmatch(r"[-+]?(?:\d+\.\d*|\d*\.\d+)", value_text):
            value = float(value_text)
        elif value_text.startswith("[") and value_text.endswith("]"):
            value = yaml.safe_load(value_text)
        else:
            value = value_text
        assert name not in values, f"duplicate parameter in research plan: {name}"
        values[name] = value
    return values


def _sample_messages(config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    polygon = [
        [
            math.cos(2.0 * math.pi * index / 24),
            math.sin(2.0 * math.pi * index / 24),
        ]
        for index in range(24)
    ]
    covariance = [0.0] * 36
    covariance[0] = 0.04
    covariance[7] = 0.04
    point_base = {
        "event_id": "E1",
        "clearance_m": 0.5,
        "path_exists": True,
        "path_length_m": 4.0,
        "estimated_time_sec": 18.0,
        "zone_revision": 2,
        "service_revision": 3,
        "valid_until_ns": 9_000_000_000,
        "reason_code": "success",
    }
    return {
        "SemanticEvent3D": {
            "stamp_ns": 1_000_000_000,
            "frame_id": "map",
            "event_id": "E1",
            "track_id": "T1",
            "event_type": "fall",
            "semantic_state": "event_confirmed",
            "confidence": 0.9,
            "observation_quality": 0.8,
            "pose_valid": True,
            "position": [5.0, 3.0, 0.0],
            "covariance": covariance,
            "observer_robot_id": "R1",
            "observer_pose_map": [2.5, 3.0, 0.0],
            "observation_distance_m": 2.5,
            "region_id": "waiting_area",
            "region_probability": 1.0,
            "valid_until_ns": 6_000_000_000,
            "perception_revision": 1,
            "reason_code": "ok",
        },
        "DynamicZone": {
            "stamp_ns": 1_000_000_000,
            "frame_id": "map",
            "zone_id": "zone:E1",
            "event_id": "E1",
            "center_xy": [5.0, 3.0],
            "covariance_xy": [0.04, 0.0, 0.0, 0.04],
            "safe_radius": 1.2,
            "polygon_xy": polygon,
            "hard_keepout": True,
            "provisional": False,
            "zone_revision": 2,
            "source_perception_revision": 1,
            "valid_until_ns": 6_000_000_000,
            "lifecycle": "active",
            "reason_code": "created",
        },
        "RoleServicePointArray": {
            "event_id": "E1",
            "pair_valid": True,
            "generation_status": "SUCCESS",
            "generation_runtime_sec": 0.4,
            "zone_revision": 2,
            "service_revision": 3,
            "failure_reason": "success",
            "points": [
                {
                    **point_base,
                    "service_point_id": "verifier:E1",
                    "role": "verifier",
                    "pose_map": [3.5, 3.0, 0.0],
                },
                {
                    **point_base,
                    "service_point_id": "courier:E1",
                    "role": "courier",
                    "pose_map": [6.5, 3.0, math.pi],
                },
            ],
        },
        "SemanticEdgeState": {
            "edge_id": "lobby_to_connector",
            "from_region": "outpatient_lobby",
            "to_region": "connector_corridor",
            "state": "FREE",
            "path_exists": True,
            "path_length_m": 5.0,
            "baseline_length_m": 5.0,
            "cost_ratio": 1.0,
            "state_since_ns": 1_000_000_000,
            "valid_until_ns": 6_000_000_000,
            "edge_revision": 1,
            "reason_code": "free_confirmed",
        },
        "ZoneApplyAck": {
            "robot_id": "R1",
            "zone_id": "zone:E1",
            "zone_revision": 2,
            "applied": True,
            "applied_at_ns": 1_100_000_000,
            "reason_code": "applied",
        },
        "PlanningTrigger": {
            "stamp_ns": 1_200_000_000,
            "trigger_type": "NEW_CONFIRMED_EVENT",
            "changed_entity_ids": ["event:E1"],
            "world_revision": 2,
            "source_revision": 1,
            "reason_code": "revision_changed",
        },
        "TaskPlan": {
            "planner_instance_id": "planner-public-v3",
            "plan_id": "P1",
            "plan_revision": 1,
            "source_world_revision": 2,
            "source_zone_revision": 2,
            "generated_at_ns": 1_300_000_000,
            "valid_from_ns": 1_400_000_000,
            "plan_epoch_ns": 1_000_000_000,
            "solver_status": "OPTIMAL",
            "plan_kind": "INITIAL",
            "assignments": [],
            "resource_reservations": [],
            "affected_tasks": [],
            "frozen_tasks": [],
            "objective_components": {
                "Cmax_bar": 0.4,
                "L_bar": 0.0,
                "Nchange_bar": 0.0,
                "Rwait_bar": 0.1,
                "Erisk_bar": 0.0,
                "raw_values": {},
                "normalization_denominators": {},
            },
            "runtime_sec": 0.2,
            "mip_gap": 0.0,
            "validator_passed": True,
            "reason_code": "initial_plan",
        },
        "ExecutionFeedback": {
            "stamp_ns": 1_500_000_000,
            "robot_id": "R1",
            "plan_id": "P1",
            "plan_revision": 1,
            "source_world_revision": 2,
            "task_id": "verify_and_monitor:E1",
            "attempt": 1,
            "state": "EXECUTING",
            "failure_class": "NONE",
            "actual_pose_map": [3.5, 3.0, 0.0],
            "nav2_error_code": 0,
            "reason_code": "executing",
        },
        "RepairStatus": {
            "stamp_ns": 1_600_000_000,
            "trigger_type": "EDGE_BLOCKED",
            "solved_world_revision": 3,
            "selected_kind": "LOCAL_REPAIR",
            "affected_tasks": ["deliver:E1"],
            "frozen_tasks": ["verify_and_monitor:E1"],
            "remaining_task_count": 3,
            "affected_task_count": 1,
            "affected_ratio": 1 / 3,
            "affected_ratio_gate_applied": False,
            "all_active_robots_affected": False,
            "global_resource_or_safety_structure_changed": False,
            "local_solver_status": "FEASIBLE",
            "full_solver_status": "NOT_RUN",
            "fallback_used": False,
            "fallback_reason": None,
            "local_changes": 1,
            "full_changes": 0,
            "change_records": [
                {"task_id": "deliver:E1", "change_flags": ["SERVICE_POINT_CHANGED"]}
            ],
            "runtime_sec": 0.3,
            "validator_passed": True,
            "published": True,
            "reason_code": "local_repair_selected",
        },
        "HoldSafeCommand": {
            "stamp_ns": 1_700_000_000,
            "command_id": "H1",
            "world_revision": 3,
            "plan_revision": 1,
            "target_robot_ids": ["R1", "R2"],
            "cancel_active_nav": True,
            "dispatch_lock": True,
            "reason_code": "full_replan_infeasible",
        },
        "SafetyStopStatus": {
            "stamp_ns": 2_100_000_000,
            "command_id": "H1",
            "robot_id": "R2",
            "world_revision": 3,
            "command_received_at_ns": 1_700_000_000,
            "cancel_requested_at_ns": 1_750_000_000,
            "cancel_acknowledged": True,
            "cancel_ack_at_ns": 1_900_000_000,
            "active_nav_goal": False,
            "linear_speed_mps": 0.01,
            "angular_speed_rps": 0.02,
            "dispatch_locked": True,
            "state": "STOPPED",
            "reason_code": "stopped",
        },
    }


def _context(payload: dict[str, Any]) -> RepairGateContext:
    allowed = {item.name for item in fields(RepairGateContext)}
    return RepairGateContext(**{key: value for key, value in payload.items() if key in allowed})


def test_frozen_parameter_table_maps_exactly_to_config(config: dict[str, Any]) -> None:
    markdown = _markdown_parameter_values()
    machine = flatten_parameters(config["parameters"])
    assert len(markdown) == 96
    assert len(machine) == 96
    assert len(machine) == len(set(machine))
    assert machine == markdown
    assert hashlib.sha256(PLAN_PATH.read_bytes()).hexdigest() == config[
        "source_document_sha256"
    ]
    assert {name: len(flatten_parameters(group)) for name, group in config["parameters"].items()} == {
        "perception_state": 18,
        "rgbd_tf": 15,
        "nav2_robot_safety": 20,
        "dynamic_core_zone": 10,
        "service_points": 11,
        "edge_and_path_cache": 11,
        "task_and_solver": 11,
    }


def test_four_task_templates_and_non_parameter_constants_are_explicit(
    config: dict[str, Any],
) -> None:
    assert list(config["task_templates"]) == [
        "reobserve:E",
        "verify_and_monitor:E",
        "pickup:E",
        "deliver:E",
    ]
    assert config["task_templates"]["verify_and_monitor:E"]["hold_until"] == (
        "deliver_or_event_close"
    )
    assert config["task_templates"]["pickup:E"]["fixed_robot_id"] == "R2"
    assert config["task_templates"]["deliver:E"]["deadline_offset_sec"] == 120.0
    assert config["contract_constants"]["objective_weights"]["value"] == {
        "Cmax_bar": 1.0,
        "L_bar": 4.0,
        "Nchange_bar": 2.5,
        "Rwait_bar": 1.5,
        "Erisk_bar": 3.0,
    }
    for entry in config["contract_constants"].values():
        assert entry["source"]


def test_trigger_and_fallback_registries_are_complete_and_unique(
    config: dict[str, Any],
) -> None:
    triggers = config["planning_triggers"]
    fallback_ids = [item["id"] for item in config["full_replan_fallback_rules"]]
    assert len(triggers) == len(set(triggers)) == 13
    assert len(fallback_ids) == len(set(fallback_ids)) == 9
    assert triggers == config["protocol"]["enums"]["planning_trigger"]


def test_state_action_vectors_have_required_positive_negative_coverage(
    config: dict[str, Any],
    vectors: dict[str, Any],
) -> None:
    cases = vectors["state_action_cases"]
    assert sum(case["polarity"] == "positive" for case in cases) >= 12
    assert sum(case["polarity"] == "negative" for case in cases) >= 12
    assert len({case["case_id"] for case in cases}) == len(cases)
    for case in cases:
        assert evaluate_state_action_contract(case["input"], config) == case["expected"]

    required_cases = {
        "SA_P05_CONFIRMED_INVALID_KEEP_OLD_ZONE",
        "SA_P06_CONFIRMED_INVALID_PROVISIONAL_2D",
        "SA_N03_ZONE_ACK_TIMEOUT",
        "SA_N04_HOLD_SAFE_CANCEL_NOT_ACKED",
        "SA_N09_STALE_SOLVER_RESULT",
        "SA_N10_FULL_REPLAN_FAILED",
    }
    assert required_cases.issubset({case["case_id"] for case in cases})


def test_all_thirteen_triggers_accept_and_mutations_reject(
    config: dict[str, Any],
    vectors: dict[str, Any],
    validator: ProtocolMessageValidator,
) -> None:
    sample = _sample_messages(config)["PlanningTrigger"]
    cases = vectors["planning_trigger_cases"]
    assert len(cases) == 13
    for case in cases:
        valid = {**sample, **case}
        assert validator.validate("PlanningTrigger", valid).accepted
        invalid = {**valid, "trigger_type": case["trigger_type"].lower()}
        assert "invalid_enum" in validator.validate(
            "PlanningTrigger", invalid
        ).reason_codes


def test_all_nine_fallback_rules_have_positive_and_negative_cases(
    config: dict[str, Any],
    vectors: dict[str, Any],
) -> None:
    cases = vectors["fallback_rule_cases"]
    assert len(cases) == 9
    for case in cases:
        positive = select_repair_mode(_context(case["positive_context"]), config)
        negative = select_repair_mode(_context(case["negative_context"]), config)
        assert positive.selected_kind == "FULL_REPLAN"
        assert positive.fallback_rule_id == case["rule_id"]
        assert negative.selected_kind == "LOCAL_REPAIR"
        assert negative.fallback_rule_id is None


def test_small_task_repair_and_global_scope_rules(
    config: dict[str, Any],
    vectors: dict[str, Any],
) -> None:
    for case in vectors["repair_gate_cases"]:
        decision = select_repair_mode(_context(case["context"]), config)
        assert decision.selected_kind == case["expected_kind"]
        assert decision.fallback_rule_id == case["expected_rule_id"]
    small = select_repair_mode(
        RepairGateContext(remaining_tasks=3, affected_tasks=2),
        config,
    )
    assert small.affected_ratio == pytest.approx(2 / 3)
    assert small.affected_ratio_gate_applied is False
    assert small.selected_kind == "LOCAL_REPAIR"


def test_every_logical_message_has_valid_and_invalid_schema_samples(
    config: dict[str, Any],
    validator: ProtocolMessageValidator,
) -> None:
    samples = _sample_messages(config)
    assert set(samples) == set(MESSAGE_RULES)
    for message_type, sample in samples.items():
        result = validator.validate(message_type, sample)
        assert result.accepted, (message_type, result.issues)

        missing = deepcopy(sample)
        missing.pop(next(iter(MESSAGE_RULES[message_type].fields)))
        assert "missing_field" in validator.validate(
            message_type, missing
        ).reason_codes

        unknown = {**sample, "unfrozen_field": True}
        assert "unknown_field" in validator.validate(
            message_type, unknown
        ).reason_codes


def test_non_finite_negative_revision_and_conditional_messages_reject(
    config: dict[str, Any],
    validator: ProtocolMessageValidator,
) -> None:
    samples = _sample_messages(config)
    non_finite = deepcopy(samples["SemanticEvent3D"])
    non_finite["confidence"] = float("nan")
    assert "non_finite_number" in validator.validate(
        "SemanticEvent3D", non_finite
    ).reason_codes

    negative = deepcopy(samples["PlanningTrigger"])
    negative["world_revision"] = -1
    assert "below_minimum" in validator.validate(
        "PlanningTrigger", negative
    ).reason_codes

    zero_covariance = deepcopy(samples["SemanticEvent3D"])
    zero_covariance["covariance"] = [0.0] * 36
    assert "zero_covariance" in validator.validate(
        "SemanticEvent3D", zero_covariance
    ).reason_codes

    unvalidated_plan = deepcopy(samples["TaskPlan"])
    unvalidated_plan["validator_passed"] = False
    assert "validator_not_passed" in validator.validate(
        "TaskPlan", unvalidated_plan
    ).reason_codes

    stopped_without_ack_time = deepcopy(samples["SafetyStopStatus"])
    stopped_without_ack_time["cancel_ack_at_ns"] = None
    assert "invalid_stopped_state" in validator.validate(
        "SafetyStopStatus", stopped_without_ack_time
    ).reason_codes

    empty_hold_targets = deepcopy(samples["HoldSafeCommand"])
    empty_hold_targets["target_robot_ids"] = []
    assert "invalid_target_robot_ids" in validator.validate(
        "HoldSafeCommand", empty_hold_targets
    ).reason_codes


def test_confirmed_invalid_3d_and_provisional_zone_are_legal_contracts(
    config: dict[str, Any],
    validator: ProtocolMessageValidator,
) -> None:
    samples = _sample_messages(config)
    invalid_3d = deepcopy(samples["SemanticEvent3D"])
    invalid_3d.update(
        {
            "pose_valid": False,
            "position": None,
            "covariance": None,
            "observation_distance_m": None,
            "reason_code": "depth_invalid",
        }
    )
    assert validator.validate("SemanticEvent3D", invalid_3d).accepted

    provisional = deepcopy(samples["DynamicZone"])
    provisional.update(
        {
            "provisional": True,
            "safe_radius": 2.0,
            "reason_code": "provisional_2d",
        }
    )
    assert validator.validate("DynamicZone", provisional).accepted


def test_all_enums_and_reason_codes_have_accept_reject_coverage(
    config: dict[str, Any],
    validator: ProtocolMessageValidator,
) -> None:
    samples = _sample_messages(config)
    enum_targets = {
        "semantic_state": ("SemanticEvent3D", "semantic_state"),
        "zone_lifecycle": ("DynamicZone", "lifecycle"),
        "service_generation_status": ("RoleServicePointArray", "generation_status"),
        "edge_state": ("SemanticEdgeState", "state"),
        "plan_kind": ("TaskPlan", "plan_kind"),
        "solver_status": ("TaskPlan", "solver_status"),
        "execution_state": ("ExecutionFeedback", "state"),
        "execution_failure_class": ("ExecutionFeedback", "failure_class"),
        "repair_selected_kind": ("RepairStatus", "selected_kind"),
        "safety_stop_state": ("SafetyStopStatus", "state"),
        "planning_trigger": ("PlanningTrigger", "trigger_type"),
    }
    for enum_key, (message_type, field_name) in enum_targets.items():
        for enum_value in config["protocol"]["enums"][enum_key]:
            sample = deepcopy(samples[message_type])
            sample[field_name] = enum_value
            if message_type == "SafetyStopStatus" and enum_value != "STOPPED":
                sample["reason_code"] = (
                    "hold_stop_failed" if enum_value == "FAILED" else enum_value.lower()
                )
            result = validator.validate(message_type, sample)
            assert result.accepted, (enum_key, enum_value, result.issues)
        invalid = deepcopy(samples[message_type])
        invalid[field_name] = "NOT_A_FROZEN_ENUM"
        assert "invalid_enum" in validator.validate(
            message_type, invalid
        ).reason_codes

    assert set(config["protocol"]["enums"]["service_role"]) == {"verifier", "courier"}
    for role in config["protocol"]["enums"]["service_role"]:
        sample = deepcopy(samples["RoleServicePointArray"])
        sample["pair_valid"] = False
        sample["points"] = [sample["points"][0]]
        sample["points"][0]["role"] = role
        assert validator.validate("RoleServicePointArray", sample).accepted
    invalid_role = deepcopy(samples["RoleServicePointArray"])
    invalid_role["pair_valid"] = False
    invalid_role["points"] = [invalid_role["points"][0]]
    invalid_role["points"][0]["role"] = "observer"
    assert "invalid_enum" in validator.validate(
        "RoleServicePointArray", invalid_role
    ).reason_codes

    for message_type, allowed_codes in config["protocol"]["reason_codes"].items():
        reason_field = (
            "failure_reason" if message_type == "RoleServicePointArray" else "reason_code"
        )
        for reason_code in allowed_codes:
            sample = deepcopy(samples[message_type])
            sample[reason_field] = reason_code
            result = validator.validate(message_type, sample)
            assert result.accepted, (message_type, reason_code, result.issues)
        invalid = deepcopy(samples[message_type])
        invalid[reason_field] = "not_registered"
        assert "invalid_reason_code" in validator.validate(
            message_type, invalid
        ).reason_codes


def test_old_message_rejection_for_every_revision_family(
    config: dict[str, Any],
    vectors: dict[str, Any],
    validator: ProtocolMessageValidator,
) -> None:
    samples = _sample_messages(config)
    for case in vectors["revision_rejection_cases"]:
        sample = deepcopy(samples[case["message_type"]])
        sample[case["revision_field"]] = case["message_revision"]
        result = validator.validate(
            case["message_type"],
            sample,
            current_revisions={case["revision_field"]: case["current_revision"]},
        )
        assert "stale_revision" in result.reason_codes
    for message_type, rule in MESSAGE_RULES.items():
        for revision_field in rule.revision_fields:
            sample = deepcopy(samples[message_type])
            sample[revision_field] = 4
            result = validator.validate(
                message_type,
                sample,
                current_revisions={revision_field: 5},
            )
            assert "stale_revision" in result.reason_codes, (
                message_type,
                revision_field,
                result.issues,
            )


def test_zone_ack_gate_waits_then_enters_hold_safe_at_frozen_timeout(
    config: dict[str, Any],
    vectors: dict[str, Any],
) -> None:
    for case in vectors["zone_ack_gate_cases"]:
        decision = evaluate_zone_ack_gate(
            required_zone_revision=case["required_zone_revision"],
            acknowledgements=case["acknowledgements"],
            elapsed_sec=case["elapsed_sec"],
            config=config,
        )
        assert decision.state == case["expected_state"]
    assert flatten_parameters(config["parameters"])["keepout_apply_timeout_sec"] == 2.0


def test_nested_service_and_task_revisions_cannot_bypass_top_level_gate(
    config: dict[str, Any],
    validator: ProtocolMessageValidator,
) -> None:
    samples = _sample_messages(config)
    service = deepcopy(samples["RoleServicePointArray"])
    service["points"][0]["service_revision"] = 2
    assert "nested_revision_mismatch" in validator.validate(
        "RoleServicePointArray", service
    ).reason_codes

    plan = deepcopy(samples["TaskPlan"])
    plan["assignments"] = [
        {
            "robot_id": "R2",
            "task_id": "deliver:E1",
            "event_id": "E1",
            "task_type": "deliver",
            "target_pose_map": [6.5, 3.0, math.pi],
            "start_offset_sec": 20.0,
            "finish_offset_sec": 35.0,
            "deadline_ns": 120_000_000_000,
            "predecessors": ["pickup:E1"],
            "resources": [],
            "required_zone_revision": 1,
        }
    ]
    assert "stale_assignment_zone_revision" in validator.validate(
        "TaskPlan", plan
    ).reason_codes


def _safe_snapshot() -> SafetySnapshot:
    return SafetySnapshot(
        stamp_ns=2 * NS_PER_SECOND,
        robot_event_distances_m={"R1": 3.0, "R2": 3.0},
        robot_robot_distance_m=1.0,
        required_zone_revision=2,
        acked_zone_revision_by_robot={"R1": 2, "R2": 2},
        plan_dispatched=True,
        deliver_completed=True,
        safe_radius_m=1.0,
    )


def test_safety_checker_covers_all_thirteen_rules(config: dict[str, Any]) -> None:
    checker = PublicSpaceV3SafetyChecker(config)
    assert checker.evaluate(_safe_snapshot()).passed
    cases = {
        "SAFE_01": replace(
            _safe_snapshot(), robot_event_distances_m={"R1": 0.9, "R2": 3.0}
        ),
        "SAFE_02": replace(_safe_snapshot(), robot_robot_distance_m=0.34),
        "SAFE_03": replace(_safe_snapshot(), corridor_occupancy_overlap=True),
        "SAFE_04": replace(
            _safe_snapshot(), acked_zone_revision_by_robot={"R1": 2, "R2": 1}
        ),
        "SAFE_05": replace(_safe_snapshot(), stale_plan_executed=True),
        "SAFE_06": replace(
            _safe_snapshot(),
            full_replan_infeasible=True,
            old_navigation_continues=True,
        ),
        "SAFE_07": replace(
            _safe_snapshot(),
            tf_available=False,
            zero_covariance_event_published=True,
        ),
        "SAFE_08": replace(
            _safe_snapshot(), deliver_completed=False, r1_verifier_distance_m=0.26
        ),
        "SAFE_09": replace(
            _safe_snapshot(), robot_event_distances_m={"R1": 3.0, "R2": 0.9}
        ),
        "SAFE_10": replace(
            _safe_snapshot(),
            confirmed_event=True,
            event_observation_distance_m=1.34,
            formal_zone_created=True,
        ),
        "SAFE_11": replace(
            _safe_snapshot(),
            stamp_ns=2 * NS_PER_SECOND,
            hold_safe_triggered=True,
            hold_command_received_at_ns=1 * NS_PER_SECOND,
            active_nav_goal_at_hold=True,
            cancel_requested_at_ns=None,
        ),
        "SAFE_12": replace(
            _safe_snapshot(),
            stamp_ns=3 * NS_PER_SECOND,
            hold_safe_triggered=True,
            hold_command_received_at_ns=1 * NS_PER_SECOND,
            active_nav_goal_at_hold=True,
            cancel_requested_at_ns=1_100_000_000,
            cancel_ack_at_ns=1_200_000_000,
            linear_speed_mps=0.03,
        ),
        "SAFE_13": replace(
            _safe_snapshot(),
            hold_safe_triggered=True,
            dispatch_lock_released=True,
            stopped_status_matches_current_command_revision=False,
        ),
    }
    for rule_id, snapshot in cases.items():
        result = checker.evaluate(snapshot)
        assert rule_id in {violation.rule_id for violation in result.violations}


def test_regions_are_explicit_s0_fixture_with_resolved_references() -> None:
    regions = yaml.safe_load(REGIONS_PATH.read_text(encoding="utf-8"))
    assert regions["geometry_status"] == "S0_CONTRACT_FIXTURE_NOT_S7_WORLD"
    assert regions["map_asset"] is None
    region_ids = {region["region_id"] for region in regions["regions"]}
    assert len(region_ids) == len(regions["regions"])
    for region in regions["regions"]:
        assert len(region["polygon_xy"]) >= 3
    for edge in regions["semantic_edges"]:
        assert edge["from_region"] in region_ids
        assert edge["to_region"] in region_ids
        assert edge["capacity_parameter"] == "corridor_capacity"
        assert edge["minimum_width_parameter"] == "min_single_passage_width_m"


def _canonical_parameter_hash(config: dict[str, Any], keys: list[str]) -> str:
    flat = flatten_parameters(config["parameters"])
    payload = {key: flat[key] for key in keys}
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def test_hash_manifest_recomputes_parameter_and_artifact_hashes(
    config: dict[str, Any],
) -> None:
    manifest = json.loads(HASH_PATH.read_text(encoding="utf-8"))
    for group_name, group in manifest["parameter_groups"].items():
        assert _canonical_parameter_hash(config, group["keys"]) == group["sha256"]
    for item in manifest["artifacts"]:
        path = PROJECT_ROOT / item["path"]
        assert path.exists()
        assert hashlib.sha256(path.read_bytes()).hexdigest() == item["sha256"]
    for item in manifest["protected_v2_house_baseline"]:
        path = PROJECT_ROOT / item["path"]
        assert path.exists()
        assert hashlib.sha256(path.read_bytes()).hexdigest() == item["sha256"]


def test_benchmark_manifest_is_unexecuted_fixed_twenty_seed_template() -> None:
    manifest = yaml.safe_load(BENCHMARK_TEMPLATE_PATH.read_text(encoding="utf-8"))
    seeds = manifest["engineering_gate"]["seeds"]
    assert manifest["status"] == "TEMPLATE_NOT_EXECUTED"
    assert len(seeds) == len({item["seed"] for item in seeds}) == 20
    assert len({item["disturbance"] for item in seeds}) == 8
    assert manifest["run_records"] == []
    assert manifest["engineering_gate"]["success_minimum"] == 18


def test_local_markdown_links_in_s0_protocol_document_resolve() -> None:
    document = PROJECT_ROOT / "docs/public_space_v3_s0_protocol.md"
    text = document.read_text(encoding="utf-8")
    links = re.findall(r"\[[^\]]+\]\(([^)]+)\)", text)
    assert links
    for target in links:
        if "://" in target or target.startswith("#"):
            continue
        assert (document.parent / target.split("#", 1)[0]).resolve().exists(), target
