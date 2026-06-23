from __future__ import annotations

from dataclasses import asdict
from typing import Any

from .milp_solver import committed_prefix, count_plan_changes, initial_resource_states, solve_milp
from .models import DynamicEvent, PlanResult, PlanningProblem, SemanticStateOutput
from .semantic_state import SemanticStateMachine
from .spatial_state import (
    SpatialReplayConfig,
    SpatialStateEstimator,
    build_grid_from_replay_frame,
)
from .validator import validate_plan


def _synthetic_semantic_event(event: DynamicEvent) -> dict[str, Any]:
    state = str(event.payload.get("state", "normal"))
    fall_score = 0.95 if state == "event_confirmed" else 0.55
    visible_count = 8 if state != "perception_degraded" else 2
    return {
        "seq_fall_score": fall_score,
        "seq_visible_keypoint_count": visible_count,
        "seq_window_ready": True,
        "seq_feature_valid": state != "perception_degraded",
        "seq_track_id": 1,
        "event_location": event.payload.get("location", "B"),
    }


def _forced_semantic_output(event: DynamicEvent) -> SemanticStateOutput:
    state = str(event.payload.get("state", "normal"))
    predicate = str(event.payload.get("predicate", "")) or None
    if state == "event_confirmed":
        predicate = predicate or "fall_confirmed"
    elif state == "event_uncertain":
        predicate = predicate or "fall_uncertain"
    elif state == "perception_degraded":
        predicate = predicate or "perception_degraded"
    return SemanticStateOutput(
        semantic_state=state,
        predicate=predicate,
        event_id=event.payload.get("event_id"),
        event_location=event.payload.get("location"),
        fall_score=0.95 if state == "event_confirmed" else 0.55,
        quality_score=0.92 if state != "perception_degraded" else 0.25,
        source_event=_synthetic_semantic_event(event),
    )


def build_resource_events_from_spatial_replay(
    problem: PlanningProblem,
    *,
    replay_cfg: SpatialReplayConfig,
    region_specs: dict[str, Any],
) -> tuple[list[DynamicEvent], dict[float, Any]]:
    estimator = SpatialStateEstimator(problem, region_specs=region_specs)
    resource_events: list[DynamicEvent] = []
    snapshots: dict[float, Any] = {}
    previous_states: dict[str, str] = {}

    for frame in replay_cfg.frames:
        grid = build_grid_from_replay_frame(replay_cfg, frame)
        snapshot = estimator.update_from_occupancy_grid(
            grid_data=grid,
            width=replay_cfg.width,
            height=replay_cfg.height,
            resolution=replay_cfg.resolution,
            origin_x=replay_cfg.origin_x,
            origin_y=replay_cfg.origin_y,
            current_time=frame.time,
            source="spatial_replay",
        )
        snapshots[frame.time] = snapshot
        for resource_id, state in snapshot.resource_states.items():
            previous = previous_states.get(resource_id)
            current = str(state.state)
            if previous is None:
                previous_states[resource_id] = current
                continue
            if previous != current:
                resource_events.append(
                    DynamicEvent(
                        time=float(frame.time),
                        kind="resource",
                        payload={
                            "resource_id": resource_id,
                            "state": current,
                            "available_from": float(state.available_from),
                            "wait_time": float(state.wait_time),
                            "predicate": str(state.predicate),
                            "source": "spatial_replay",
                            "notes": frame.notes,
                        },
                    )
                )
            previous_states[resource_id] = current

    return resource_events, snapshots


def run_dynamic_replanning(
    problem: PlanningProblem,
    *,
    backend: str = "pulp",
    resource_events: list[DynamicEvent] | None = None,
    spatial_snapshots_by_time: dict[float, Any] | None = None,
) -> dict[str, Any]:
    semantic_machine = SemanticStateMachine(problem.semantic)
    spatial_estimator = SpatialStateEstimator(problem)
    initial_states = initial_resource_states(problem)

    base_plan = solve_milp(
        problem,
        backend=backend,
        current_time=0.0,
        resource_states=initial_states,
        plan_kind="static",
    )
    timeline = [
        {
            "time": 0.0,
            "trigger": "initial_plan",
            "semantic_state": None,
            "spatial_state": spatial_estimator.snapshot(source="initial").to_dict(),
            "plan": base_plan.to_dict(),
            "validation": validate_plan(
                problem,
                base_plan.assignments,
                current_time=0.0,
                resource_states=initial_states,
            ),
        }
    ]
    semantic_examples = [
        SemanticStateOutput(
            semantic_state="event_uncertain",
            predicate="fall_uncertain",
            event_id=None,
            event_location="B",
            fall_score=0.6,
            quality_score=0.8,
            source_event={"example": "uncertain"},
        ).to_dict(),
        SemanticStateOutput(
            semantic_state="perception_degraded",
            predicate="perception_degraded",
            event_id=None,
            event_location="B",
            fall_score=0.1,
            quality_score=0.2,
            source_event={"example": "degraded"},
        ).to_dict(),
    ]
    current_plan = base_plan
    current_resource_states = initial_states
    events = [event for event in problem.dynamic_events if event.kind == "semantic"]
    if resource_events is None:
        events.extend([event for event in problem.dynamic_events if event.kind == "resource"])
    else:
        events.extend(resource_events)
    events.sort(key=lambda item: (item.time, 0 if item.kind == "semantic" else 1))

    for event in events:
        semantic_output: SemanticStateOutput | None = None
        if event.kind == "semantic":
            if event.payload.get("state"):
                semantic_output = _forced_semantic_output(event)
            else:
                semantic_output = semantic_machine.update(_synthetic_semantic_event(event))
        if event.kind == "resource":
            if spatial_snapshots_by_time and float(event.time) in spatial_snapshots_by_time:
                spatial_output = spatial_snapshots_by_time[float(event.time)]
            else:
                spatial_output = spatial_estimator.apply_dynamic_event(
                    {"kind": event.kind, **event.payload},
                    current_time=event.time,
                )
            current_resource_states = spatial_output.resource_states
        else:
            spatial_output = spatial_estimator.snapshot(source="semantic_only")

        committed = committed_prefix(current_plan.assignments, event.time)
        excluded = {assignment.task for assignment in committed if assignment.finish <= event.time}
        replan = solve_milp(
            problem,
            backend=backend,
            current_time=event.time,
            resource_states=current_resource_states,
            committed_assignments=committed,
            incumbent_assignments=current_plan.assignments,
            excluded_task_ids=excluded,
            plan_kind="full_replan",
        )
        diff = count_plan_changes(current_plan.assignments, replan.assignments)
        timeline.append(
            {
                "time": event.time,
                "trigger": event.kind,
                "event_payload": dict(event.payload),
                "semantic_state": None if semantic_output is None else semantic_output.to_dict(),
                "spatial_state": spatial_output.to_dict(),
                "plan": replan.to_dict(),
                "plan_changes": diff,
                "validation": validate_plan(
                    problem,
                    replan.assignments,
                    current_time=event.time,
                    resource_states=current_resource_states,
                    frozen_assignments=committed,
                ),
            }
        )
        current_plan = replan

    return {
        "initial_plan": base_plan.to_dict(),
        "semantic_examples": semantic_examples,
        "timeline": timeline,
    }
