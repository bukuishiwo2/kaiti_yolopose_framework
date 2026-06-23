from __future__ import annotations

from collections import defaultdict, deque
from typing import Any

from .milp_solver import committed_prefix, count_plan_changes, solve_milp
from .models import DynamicEvent, PlanResult, PlanningProblem
from .validator import validate_plan
from .spatial_state import SpatialStateEstimator


def _seed_affected_tasks(problem: PlanningProblem, event: DynamicEvent) -> set[str]:
    affected: set[str] = set()
    if event.kind == "semantic":
        predicate = str(event.payload.get("predicate", ""))
        if predicate == "fall_confirmed":
            affected.update([task.id for task in problem.tasks if task.event_task])
    elif event.kind == "resource":
        resource_id = str(event.payload.get("resource_id", ""))
        affected.update([task.id for task in problem.tasks if resource_id in task.resources])
    elif event.kind == "robot":
        robot_id = str(event.payload.get("robot_id", ""))
        affected.update(
            [
                task.id
                for task in problem.tasks
                if robot_id and any(cap in {"charge", "move"} for cap in task.capabilities)
            ]
        )
    else:
        affected.update([task.id for task in problem.tasks if task.event_task])
    return affected


def identify_affected_tasks(
    problem: PlanningProblem,
    event: DynamicEvent,
    *,
    incumbent_assignments: list[Any],
    excluded_task_ids: set[str] | None = None,
) -> set[str]:
    excluded_task_ids = excluded_task_ids or set()
    seeds = {task_id for task_id in _seed_affected_tasks(problem, event) if task_id not in excluded_task_ids}
    if not seeds:
        return set()

    graph: dict[str, set[str]] = defaultdict(set)
    for before, after in problem.precedence:
        if before not in excluded_task_ids and after not in excluded_task_ids:
            graph[before].add(after)

    by_robot: dict[str, list[Any]] = defaultdict(list)
    by_resource: dict[str, list[Any]] = defaultdict(list)
    for assignment in incumbent_assignments:
        if assignment.task in excluded_task_ids:
            continue
        by_robot[assignment.robot].append(assignment)
        for resource_id in assignment.resources:
            by_resource[resource_id].append(assignment)

    for assignments in by_robot.values():
        assignments.sort(key=lambda item: (item.start, item.finish, item.task))
        for left, right in zip(assignments, assignments[1:]):
            graph[left.task].add(right.task)

    for assignments in by_resource.values():
        assignments.sort(key=lambda item: (item.start, item.finish, item.task))
        for left, right in zip(assignments, assignments[1:]):
            graph[left.task].add(right.task)

    affected = set(seeds)
    queue = deque(sorted(seeds))
    while queue:
        current = queue.popleft()
        for neighbor in graph.get(current, set()):
            if neighbor in affected:
                continue
            affected.add(neighbor)
            queue.append(neighbor)
    return affected


def run_local_repair(
    problem: PlanningProblem,
    *,
    backend: str = "pulp",
    resource_events: list[DynamicEvent] | None = None,
    spatial_snapshots_by_time: dict[float, Any] | None = None,
) -> dict[str, Any]:
    full_baseline = solve_milp(problem, backend=backend, plan_kind="static")
    estimator = SpatialStateEstimator(problem)
    latest_resource_states = estimator.resource_states
    target_event = None
    event_time = 0.0
    trigger_source = "dynamic_script"
    target_resource_states = latest_resource_states

    events = resource_events
    if events is None:
        events = [event for event in sorted(problem.dynamic_events, key=lambda item: item.time) if event.kind == "resource"]

    for event in events:
        if spatial_snapshots_by_time and float(event.time) in spatial_snapshots_by_time:
            latest_resource_states = spatial_snapshots_by_time[float(event.time)].resource_states
        else:
            latest_resource_states = estimator.apply_dynamic_event(
                {"kind": event.kind, **event.payload},
                current_time=event.time,
            ).resource_states
        if str(event.payload.get("state", "")) not in {"free", "available"} and target_event is None:
            target_event = event
            event_time = event.time
            trigger_source = str(event.payload.get("source", trigger_source))
            target_resource_states = latest_resource_states

    if target_event is None:
        return {
            "full_replan": full_baseline.to_dict(),
            "local_repair": full_baseline.to_dict(),
            "affected_tasks": [],
            "comparison": count_plan_changes(full_baseline.assignments, full_baseline.assignments),
        }

    committed = committed_prefix(full_baseline.assignments, event_time)
    excluded = {assignment.task for assignment in committed if assignment.finish <= event_time}
    finished_prefix = [assignment for assignment in committed if assignment.finish <= event_time]
    active_commitments = [assignment for assignment in committed if assignment.finish > event_time]
    affected_tasks = identify_affected_tasks(
        problem,
        target_event,
        incumbent_assignments=full_baseline.assignments,
        excluded_task_ids=excluded,
    )
    frozen_future = [
        assignment
        for assignment in full_baseline.assignments
        if assignment.task not in excluded
        and assignment.task not in affected_tasks
        and assignment.task not in {item.task for item in active_commitments}
    ]
    frozen_assignments = sorted(
        active_commitments + frozen_future,
        key=lambda item: (item.start, item.robot, item.task),
    )
    local_fixed_assignments = sorted(
        finished_prefix + active_commitments + frozen_future,
        key=lambda item: (item.start, item.robot, item.task),
    )

    full_replan = solve_milp(
        problem,
        backend=backend,
        current_time=event_time,
        resource_states=target_resource_states,
        committed_assignments=committed,
        incumbent_assignments=[],
        excluded_task_ids=excluded,
        plan_kind="full_replan",
    )

    local_repair = solve_milp(
        problem,
        backend=backend,
        current_time=event_time,
        resource_states=target_resource_states,
        committed_assignments=local_fixed_assignments,
        incumbent_assignments=full_baseline.assignments,
        excluded_task_ids=excluded,
        plan_kind="local_repair",
    )

    full_validation = validate_plan(
        problem,
        full_replan.assignments,
        current_time=event_time,
        resource_states=target_resource_states,
        frozen_assignments=committed,
    )
    local_validation = validate_plan(
        problem,
        local_repair.assignments,
        current_time=event_time,
        resource_states=target_resource_states,
        frozen_assignments=local_fixed_assignments,
    )

    return {
        "trigger_source": trigger_source,
        "trigger_time": event_time,
        "trigger_resource": str(target_event.payload.get("resource_id", "")),
        "trigger_state": str(target_event.payload.get("state", "")),
        "event_payload": dict(target_event.payload),
        "affected_tasks": sorted(affected_tasks),
        "frozen_tasks": [assignment.task for assignment in local_fixed_assignments],
        "full_replan": full_replan.to_dict(),
        "local_repair": local_repair.to_dict(),
        "full_replan_validation": full_validation,
        "local_repair_validation": local_validation,
        "full_replan_modified_tasks": count_plan_changes(full_baseline.assignments, full_replan.assignments),
        "local_repair_modified_tasks": count_plan_changes(full_baseline.assignments, local_repair.assignments),
        "comparison_vs_full_replan": count_plan_changes(full_baseline.assignments, full_replan.assignments),
        "comparison_vs_local_repair": count_plan_changes(full_baseline.assignments, local_repair.assignments),
        "local_vs_full": count_plan_changes(full_replan.assignments, local_repair.assignments),
        "resource_conflict_count": local_validation["counts"]["resource_conflict_count"],
        "deadline_violation_count": local_validation["counts"]["deadline_violation_count"],
    }
