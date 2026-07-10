from __future__ import annotations

from collections import defaultdict
from typing import Any

from .models import PlanningProblem, ResourceReservation, ResourceState, TaskAssignment
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
    resource_reservations: list[ResourceReservation] | None = None,
    selected_arcs: list[dict[str, str]] | None = None,
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
        "pickup_delivery": [],
        "energy_trace": [],
        "arc_structure": [],
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

    for task in problem.tasks:
        count = assignment_counts[task.id]
        expected = 1 if task.must_complete else 0
        if count != expected:
            violations["unique_assignment"].append(
                {"task": task.id, "count": count, "expected": expected}
            )

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
            expected_before = battery
            if assignment.energy_before is not None and abs(float(assignment.energy_before) - expected_before) > 1e-3:
                violations["energy_trace"].append(
                    {
                        "robot": robot_id,
                        "task": assignment.task,
                        "field": "energy_before",
                        "reported": float(assignment.energy_before),
                        "expected": round(expected_before, 3),
                    }
                )
            actual_before = (
                float(assignment.energy_before)
                if assignment.energy_before is not None
                else expected_before
            )
            service_cost = float(problem.energy.task_costs.get(task.type, 0.0))
            maximum_gain = float(problem.energy.charge_gain.get(task.id, 0.0))
            minimum_after = actual_before - service_cost
            maximum_after = min(
                float(problem.energy.full_battery), minimum_after + maximum_gain
            )
            if assignment.energy_before is not None and assignment.energy_after is not None:
                reported_after = float(assignment.energy_after)
                if reported_after + 1e-3 < minimum_after or reported_after > maximum_after + 1e-3:
                    violations["energy_trace"].append(
                        {
                            "robot": robot_id,
                            "task": assignment.task,
                            "field": "energy_after",
                            "reported": reported_after,
                            "expected_range": [round(minimum_after, 3), round(maximum_after, 3)],
                        }
                    )
                battery = reported_after
            else:
                battery = maximum_after
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

    if resource_reservations:
        reservations_by_resource = defaultdict(list)
        for reservation in resource_reservations:
            reservations_by_resource[reservation.resource_id].append(reservation)
            state = resource_states.get(reservation.resource_id)
            if reservation.exit_time + 1e-6 < reservation.enter_time:
                violations["resource_window"].append(
                    {"resource": reservation.resource_id, "reason": "negative_interval"}
                )
            if state and state.state == "blocked":
                violations["resource_window"].append(
                    {"resource": reservation.resource_id, "state": "blocked"}
                )
            elif state and reservation.enter_time + 1e-6 < float(state.available_from):
                violations["resource_window"].append(
                    {
                        "resource": reservation.resource_id,
                        "enter_time": reservation.enter_time,
                        "available_from": float(state.available_from),
                    }
                )
        for resource_id, items in reservations_by_resource.items():
            if resource_map[resource_id].capacity != 1:
                continue
            items.sort(key=lambda item: (item.enter_time, item.exit_time, item.robot_id))
            for left, right in zip(items, items[1:]):
                required = left.exit_time + max(left.safety_buffer, right.safety_buffer)
                if right.enter_time + 1e-6 < required:
                    violations["resource_conflict"].append(
                        {
                            "resource": resource_id,
                            "left_task": left.task_id,
                            "right_task": right.task_id,
                            "left_exit": float(left.exit_time),
                            "right_enter": float(right.enter_time),
                            "required_not_before": float(required),
                        }
                    )
    else:
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

    for pickup_id in sorted(task_id for task_id in task_map if task_id.startswith("pickup:")):
        deliver_id = f"deliver:{pickup_id.split(':', 1)[1]}"
        pickup = assignment_map.get(pickup_id)
        deliver = assignment_map.get(deliver_id)
        if pickup and deliver and pickup.robot != deliver.robot:
            violations["pickup_delivery"].append(
                {
                    "pickup": pickup_id,
                    "deliver": deliver_id,
                    "pickup_robot": pickup.robot,
                    "deliver_robot": deliver.robot,
                }
            )

    if selected_arcs is not None:
        assignments_by_robot = defaultdict(set)
        for assignment in assignments:
            assignments_by_robot[assignment.robot].add(assignment.task)
        arcs_by_robot = defaultdict(list)
        for arc in selected_arcs:
            arcs_by_robot[str(arc["robot"])].append((str(arc["from"]), str(arc["to"])))
        for robot_id in robot_map:
            robot_arcs = arcs_by_robot[robot_id]
            start_nodes = [origin for origin, _ in robot_arcs if origin.startswith("__start__")]
            end_nodes = [destination for _, destination in robot_arcs if destination.startswith("__end__")]
            if len(start_nodes) != 1 or len(end_nodes) != 1:
                violations["arc_structure"].append(
                    {"robot": robot_id, "reason": "invalid_start_or_end_degree"}
                )
                continue
            outgoing = defaultdict(list)
            incoming = defaultdict(list)
            for origin, destination in robot_arcs:
                outgoing[origin].append(destination)
                incoming[destination].append(origin)
            for task_id in assignments_by_robot[robot_id]:
                if len(incoming[task_id]) != 1 or len(outgoing[task_id]) != 1:
                    violations["arc_structure"].append(
                        {"robot": robot_id, "task": task_id, "reason": "invalid_task_degree"}
                    )
            start = next(origin for origin, _ in robot_arcs if origin.startswith("__start__"))
            visited_tasks = set()
            visited_nodes = set()
            current = start
            while not current.startswith("__end__"):
                if current in visited_nodes or len(outgoing[current]) != 1:
                    violations["arc_structure"].append(
                        {"robot": robot_id, "node": current, "reason": "cycle_or_branch"}
                    )
                    break
                visited_nodes.add(current)
                current = outgoing[current][0]
                if current in task_map:
                    visited_tasks.add(current)
            if visited_tasks != assignments_by_robot[robot_id]:
                violations["arc_structure"].append(
                    {
                        "robot": robot_id,
                        "reason": "disconnected_tasks",
                        "missing": sorted(assignments_by_robot[robot_id] - visited_tasks),
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
        "pickup_delivery_violation_count": float(len(violations["pickup_delivery"])),
        "energy_trace_violation_count": float(len(violations["energy_trace"])),
        "arc_structure_violation_count": float(len(violations["arc_structure"])),
    }
    counts["is_valid"] = float(sum(int(value) for key, value in counts.items() if key != "is_valid")) == 0.0

    return {
        "counts": counts,
        "violations": violations,
    }
