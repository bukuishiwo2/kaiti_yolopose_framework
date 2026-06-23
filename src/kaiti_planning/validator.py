from __future__ import annotations

from collections import defaultdict
from typing import Any

from .models import PlanningProblem, ResourceState, TaskAssignment
from .milp_solver import initial_resource_states, task_assignment_map


def _float_eq(left: float, right: float, tol: float = 1e-6) -> bool:
    return abs(float(left) - float(right)) <= tol


def validate_plan(
    problem: PlanningProblem,
    assignments: list[TaskAssignment],
    *,
    current_time: float = 0.0,
    resource_states: dict[str, ResourceState] | None = None,
    frozen_assignments: list[TaskAssignment] | None = None,
) -> dict[str, Any]:
    resource_states = resource_states or initial_resource_states(problem)
    frozen_assignments = frozen_assignments or []
    task_map = problem.task_by_id()
    robot_map = problem.robot_by_id()
    resource_map = problem.resource_by_id()
    assignment_map = task_assignment_map(assignments)

    violations: dict[str, list[dict[str, Any]]] = {
        "unique_assignment": [],
        "capability": [],
        "precedence": [],
        "robot_overlap": [],
        "resource_conflict": [],
        "resource_window": [],
        "battery": [],
        "event_response": [],
        "deadline": [],
        "frozen": [],
    }

    assignment_counts = defaultdict(int)
    for assignment in assignments:
        assignment_counts[assignment.task] += 1
        task = task_map.get(assignment.task)
        if task is None:
            continue
        robot = robot_map[assignment.robot]
        started_before_replan = float(assignment.start) < float(current_time)
        if not set(task.capabilities).issubset(set(robot.capabilities)):
            violations["capability"].append(
                {"task": assignment.task, "robot": assignment.robot}
            )
        if not started_before_replan and assignment.start + 1e-6 < max(current_time, float(task.release)):
            violations["event_response"].append(
                {
                    "task": assignment.task,
                    "start": float(assignment.start),
                    "required_not_before": max(current_time, float(task.release)),
                }
            )
        if assignment.finish > float(task.deadline) + 1e-6:
            violations["deadline"].append(
                {
                    "task": assignment.task,
                    "finish": float(assignment.finish),
                    "deadline": float(task.deadline),
                }
            )
        for resource_id in task.resources:
            state = resource_states.get(resource_id)
            if state is None:
                continue
            if started_before_replan:
                continue
            if state.state == "blocked":
                violations["resource_window"].append(
                    {"task": assignment.task, "resource": resource_id, "state": state.state}
                )
            elif assignment.start + 1e-6 < float(state.available_from):
                violations["resource_window"].append(
                    {
                        "task": assignment.task,
                        "resource": resource_id,
                        "start": float(assignment.start),
                        "available_from": float(state.available_from),
                    }
                )

    for task_id, count in assignment_counts.items():
        if count != 1:
            violations["unique_assignment"].append({"task": task_id, "count": count})

    for before, after in problem.precedence:
        before_assignment = assignment_map.get(before)
        after_assignment = assignment_map.get(after)
        if before_assignment is None or after_assignment is None:
            continue
        if after_assignment.start + 1e-6 < before_assignment.finish:
            violations["precedence"].append(
                {
                    "before": before,
                    "after": after,
                    "before_finish": float(before_assignment.finish),
                    "after_start": float(after_assignment.start),
                }
            )

    by_robot = defaultdict(list)
    by_resource = defaultdict(list)
    for assignment in assignments:
        by_robot[assignment.robot].append(assignment)
        for resource_id in assignment.resources:
            by_resource[resource_id].append(assignment)

    for robot_id, items in by_robot.items():
        items.sort(key=lambda item: (item.start, item.finish, item.task))
        prev_location = robot_map[robot_id].start
        prev_finish = 0.0
        battery = float(robot_map[robot_id].battery)
        for idx, assignment in enumerate(items):
            task = task_map[assignment.task]
            travel_time = float(problem.travel_times[prev_location][task.location])
            earliest = prev_finish + travel_time
            if assignment.start + 1e-6 < earliest:
                violations["robot_overlap"].append(
                    {
                        "robot": robot_id,
                        "task": assignment.task,
                        "start": float(assignment.start),
                        "required_not_before": earliest,
                    }
                )
            battery -= float(problem.energy.move_cost_per_sec) * travel_time
            battery -= float(problem.energy.task_costs.get(task.type, 0.0))
            battery += float(problem.energy.charge_gain.get(task.id, 0.0))
            if battery + 1e-6 < float(problem.energy.safe_battery):
                violations["battery"].append(
                    {
                        "robot": robot_id,
                        "task": assignment.task,
                        "battery_after": round(battery, 3),
                        "safe_battery": float(problem.energy.safe_battery),
                    }
                )
            prev_location = task.location
            prev_finish = float(assignment.finish)
            if idx > 0 and assignment.start + 1e-6 < items[idx - 1].finish:
                violations["robot_overlap"].append(
                    {
                        "robot": robot_id,
                        "left_task": items[idx - 1].task,
                        "right_task": assignment.task,
                    }
                )

    for resource_id, items in by_resource.items():
        items.sort(key=lambda item: (item.start, item.finish, item.task))
        release_buffer = float(resource_map[resource_id].release_buffer)
        for idx in range(1, len(items)):
            left = items[idx - 1]
            right = items[idx]
            if right.start + 1e-6 < left.finish + release_buffer:
                violations["resource_conflict"].append(
                    {
                        "resource": resource_id,
                        "left_task": left.task,
                        "right_task": right.task,
                        "left_finish": float(left.finish),
                        "right_start": float(right.start),
                        "required_not_before": float(left.finish + release_buffer),
                    }
                )

    frozen_map = task_assignment_map(frozen_assignments)
    for task_id, frozen in frozen_map.items():
        current = assignment_map.get(task_id)
        if current is None:
            violations["frozen"].append({"task": task_id, "reason": "missing_in_plan"})
            continue
        if current.robot != frozen.robot or not _float_eq(current.start, frozen.start):
            violations["frozen"].append(
                {
                    "task": task_id,
                    "expected_robot": frozen.robot,
                    "actual_robot": current.robot,
                    "expected_start": float(frozen.start),
                    "actual_start": float(current.start),
                }
            )

    counts = {
        "unique_assignment_count": float(len(violations["unique_assignment"])),
        "capability_violation_count": float(len(violations["capability"])),
        "precedence_violation_count": float(len(violations["precedence"])),
        "robot_overlap_count": float(len(violations["robot_overlap"])),
        "resource_conflict_count": float(len(violations["resource_conflict"])),
        "resource_window_violation_count": float(len(violations["resource_window"])),
        "battery_violation_count": float(len(violations["battery"])),
        "event_response_violation_count": float(len(violations["event_response"])),
        "deadline_violation_count": float(len(violations["deadline"])),
        "frozen_violation_count": float(len(violations["frozen"])),
    }
    counts["is_valid"] = float(sum(int(value) for key, value in counts.items() if key != "is_valid")) == 0.0

    return {
        "counts": counts,
        "violations": violations,
    }
