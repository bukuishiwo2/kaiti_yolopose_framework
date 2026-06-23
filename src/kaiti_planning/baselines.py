from __future__ import annotations

from collections import defaultdict
from typing import Callable

from .models import PlanResult, PlanningProblem, ResourceState, Task, TaskAssignment
from .milp_solver import initial_resource_states
from .task_graph import topological_task_order


def _resource_ready_time(resource_states: dict[str, ResourceState], resources: list[str]) -> float:
    if not resources:
        return 0.0
    return max(float(resource_states[resource_id].available_from) for resource_id in resources)


def _greedy_schedule(
    problem: PlanningProblem,
    *,
    task_order: list[str],
    score_fn: Callable[[str, Task, float, float, float], float],
    plan_kind: str,
) -> PlanResult:
    task_map = problem.task_by_id()
    resource_states = initial_resource_states(problem)
    robot_state = {
        robot.id: {
            "time": 0.0,
            "location": robot.start,
            "battery": float(robot.battery),
        }
        for robot in problem.robots
    }
    predecessors = {task.id: [] for task in problem.tasks}
    for before, after in problem.precedence:
        predecessors.setdefault(after, []).append(before)

    assignments: list[TaskAssignment] = []
    task_finish: dict[str, float] = {}
    resource_next_free = defaultdict(float)

    for task_id in task_order:
        task = task_map[task_id]
        compatible = [
            robot for robot in problem.robots
            if set(task.capabilities).issubset(set(robot.capabilities))
        ]
        if not compatible:
            return PlanResult(
                solver_status="Infeasible",
                objective_value=None,
                assignments=[],
                metrics={"task_count": 0.0},
                planner_mode=plan_kind,
                plan_kind=plan_kind,
                notes=[f"no_compatible_robot_for_{task.id}"],
            )

        earliest_from_preds = max([task_finish.get(pred, 0.0) for pred in predecessors.get(task.id, [])] or [0.0])
        chosen = None
        chosen_payload = None
        for robot in compatible:
            start_travel = float(problem.travel_times[robot_state[robot.id]["location"]][task.location])
            ready_time = max(
                float(task.release),
                robot_state[robot.id]["time"] + start_travel,
                earliest_from_preds,
                _resource_ready_time(resource_states, task.resources),
                max([resource_next_free[resource_id] for resource_id in task.resources] or [0.0]),
            )
            finish_time = ready_time + float(task.duration)
            battery_after = (
                float(robot_state[robot.id]["battery"])
                - float(problem.energy.move_cost_per_sec) * start_travel
                - float(problem.energy.task_costs.get(task.type, 0.0))
                + float(problem.energy.charge_gain.get(task.id, 0.0))
            )
            if battery_after < float(problem.energy.safe_battery):
                continue
            score = score_fn(robot.id, task, ready_time, finish_time, battery_after)
            if chosen is None or score < chosen:
                chosen = score
                chosen_payload = (robot.id, ready_time, finish_time, battery_after)

        if chosen_payload is None:
            return PlanResult(
                solver_status="Infeasible",
                objective_value=None,
                assignments=assignments,
                metrics={"task_count": float(len(assignments))},
                planner_mode=plan_kind,
                plan_kind=plan_kind,
                notes=[f"resource_or_battery_infeasible_for_{task.id}"],
            )

        robot_id, ready_time, finish_time, battery_after = chosen_payload
        assignments.append(
            TaskAssignment(
                robot=robot_id,
                task=task.id,
                start=round(ready_time, 3),
                finish=round(finish_time, 3),
                location=task.location,
                resources=list(task.resources),
                energy_after=round(battery_after, 3),
            )
        )
        robot_state[robot_id]["time"] = finish_time
        robot_state[robot_id]["location"] = task.location
        robot_state[robot_id]["battery"] = battery_after
        task_finish[task.id] = finish_time
        for resource_id in task.resources:
            state = resource_states[resource_id]
            release_time = finish_time + float(problem.resource_by_id()[resource_id].release_buffer)
            resource_next_free[resource_id] = release_time
            state.available_from = release_time

    total_delay = sum(
        max(0.0, assignment.finish - float(task_map[assignment.task].deadline))
        for assignment in assignments
    )
    event_starts = [assignment.start for assignment in assignments if task_map[assignment.task].event_task]
    metrics = {
        "task_count": float(len(assignments)),
        "total_delay": round(total_delay, 3),
        "event_response_start": round(min(event_starts or [0.0]), 3),
        "makespan": round(max([item.finish for item in assignments] or [0.0]), 3),
    }
    return PlanResult(
        solver_status="Heuristic",
        objective_value=None,
        assignments=assignments,
        metrics=metrics,
        planner_mode=plan_kind,
        plan_kind=plan_kind,
        notes=[],
    )


def nearest_robot_baseline(problem: PlanningProblem) -> PlanResult:
    task_map = problem.task_by_id()
    order = sorted(
        task_map,
        key=lambda task_id: (task_map[task_id].release, task_map[task_id].deadline, task_id),
    )

    def score(robot_id: str, task: Task, ready_time: float, finish_time: float, battery_after: float) -> float:
        return finish_time

    return _greedy_schedule(problem, task_order=order, score_fn=score, plan_kind="nearest_robot")


def priority_greedy_baseline(problem: PlanningProblem) -> PlanResult:
    task_map = problem.task_by_id()
    topo = topological_task_order(problem)
    order = sorted(
        topo,
        key=lambda task_id: (-task_map[task_id].priority_weight, task_map[task_id].release, task_id),
    )

    def score(robot_id: str, task: Task, ready_time: float, finish_time: float, battery_after: float) -> float:
        return ready_time + 0.25 * finish_time

    return _greedy_schedule(problem, task_order=order, score_fn=score, plan_kind="priority_greedy")


def request_response_baseline(problem: PlanningProblem) -> PlanResult:
    task_map = problem.task_by_id()
    topo = topological_task_order(problem)
    order = sorted(
        topo,
        key=lambda task_id: (task_map[task_id].release, -task_map[task_id].priority_weight, task_id),
    )

    def score(robot_id: str, task: Task, ready_time: float, finish_time: float, battery_after: float) -> float:
        response_bias = 0.0 if task.event_task else 10.0
        battery_penalty = max(0.0, 30.0 - battery_after)
        return finish_time + response_bias + battery_penalty

    return _greedy_schedule(problem, task_order=order, score_fn=score, plan_kind="request_response")
