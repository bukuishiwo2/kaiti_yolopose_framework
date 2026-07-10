from __future__ import annotations

from collections import defaultdict, deque
from copy import deepcopy
from typing import Any, Callable

from .milp_solver import count_plan_changes, solve_milp
from .models import PlanResult, PlanningProblem, ResourceState, SolverStatus, TaskAssignment
from .validator import validate_plan
from .world_state import WorldState

FEASIBLE_STATUSES = {SolverStatus.OPTIMAL.value, SolverStatus.FEASIBLE.value, SolverStatus.TIME_LIMIT_FEASIBLE.value}


def affected_tasks(
    problem: PlanningProblem,
    incumbent: PlanResult,
    disturbance: dict[str, Any],
    *,
    completed_task_ids: set[str],
) -> set[str]:
    seeds: set[str] = set()
    kind = str(disturbance.get("kind", ""))
    if kind == "resource":
        resource_id = str(disturbance["resource_id"])
        seeds.update(
            reservation.task_id
            for reservation in incumbent.resource_reservations
            if reservation.resource_id == resource_id and reservation.task_id != "__return__"
        )
        seeds.update(task.id for task in problem.tasks if resource_id in task.resources)
    elif kind == "robot":
        robot_id = str(disturbance["robot_id"])
        seeds.update(item.task for item in incumbent.assignments if item.robot == robot_id)
    elif kind in {"navigation_failure", "action_failure"}:
        seeds.add(str(disturbance["task_id"]))
    elif kind == "semantic":
        incumbent_ids = {item.task for item in incumbent.assignments}
        seeds.update(task.id for task in problem.tasks if task.event_task and task.id not in incumbent_ids)
    else:
        seeds.update(task.id for task in problem.tasks if task.event_task)
    seeds.difference_update(completed_task_ids)

    graph: dict[str, set[str]] = defaultdict(set)
    for before, after in problem.precedence:
        graph[before].add(after)
    by_robot: dict[str, list[TaskAssignment]] = defaultdict(list)
    for item in incumbent.assignments:
        if item.task not in completed_task_ids:
            by_robot[item.robot].append(item)
    for items in by_robot.values():
        items.sort(key=lambda item: (item.start, item.finish, item.task))
        for left, right in zip(items, items[1:]):
            graph[left.task].add(right.task)

    affected = set(seeds)
    pending = deque(sorted(seeds))
    while pending:
        task_id = pending.popleft()
        for successor in graph.get(task_id, set()):
            if successor not in affected and successor not in completed_task_ids:
                affected.add(successor)
                pending.append(successor)
    return affected


def repair_after_disturbance(
    problem: PlanningProblem,
    incumbent: PlanResult,
    *,
    current_time: float,
    resource_states: dict[str, ResourceState],
    disturbance: dict[str, Any],
) -> dict[str, Any]:
    completed = [item for item in incumbent.assignments if item.finish <= current_time]
    active = [item for item in incumbent.assignments if item.start < current_time < item.finish]
    completed_ids = {item.task for item in completed}
    active_ids = {item.task for item in active}
    prefix_ids = completed_ids | active_ids
    affected = affected_tasks(
        problem,
        incumbent,
        disturbance,
        completed_task_ids=completed_ids,
    )
    frozen_future = [
        item
        for item in incumbent.assignments
        if item.task not in completed_ids | active_ids | affected
    ]
    working_problem = deepcopy(problem)
    working_problem.tasks = [task for task in working_problem.tasks if task.id not in prefix_ids]
    working_ids = {task.id for task in working_problem.tasks}
    working_problem.precedence = [
        (before, after)
        for before, after in working_problem.precedence
        if before in working_ids and after in working_ids
    ]
    for robot in working_problem.robots:
        prefix = sorted(
            [item for item in completed + active if item.robot == robot.id],
            key=lambda item: (item.finish, item.task),
        )
        if prefix:
            last = prefix[-1]
            robot.start = last.location
            if last.energy_after is not None:
                robot.battery = float(last.energy_after)
    solve_time = max([current_time] + [item.finish for item in active])
    incumbent_future = [item for item in incumbent.assignments if item.task in working_ids]

    full = solve_milp(
        working_problem,
        current_time=solve_time,
        resource_states=resource_states,
        plan_kind="full_replan",
    )
    local = solve_milp(
        working_problem,
        current_time=solve_time,
        resource_states=resource_states,
        committed_assignments=frozen_future,
        incumbent_assignments=incumbent_future,
        plan_kind="local_repair",
    )
    fallback_used = local.solver_status not in FEASIBLE_STATUSES
    selected = full if fallback_used else local
    selected_kind = "full_replan_fallback" if fallback_used else "local_repair"
    validation = validate_plan(
        working_problem,
        selected.assignments,
        current_time=solve_time,
        resource_states=resource_states,
        frozen_assignments=([] if fallback_used else frozen_future),
        resource_reservations=selected.resource_reservations,
        selected_arcs=selected.diagnostics.get("selected_arcs"),
    ) if selected.solver_status in FEASIBLE_STATUSES else None
    return {
        "disturbance": disturbance,
        "affected_tasks": sorted(affected),
        "completed_tasks": sorted(completed_ids),
        "active_tasks": sorted(active_ids),
        "frozen_tasks": sorted(item.task for item in frozen_future),
        "local_repair": local.to_dict(),
        "full_replan": full.to_dict(),
        "selected_plan": selected.to_dict(),
        "selected_kind": selected_kind,
        "fallback_used": fallback_used,
        "validation": validation,
        "local_changes": count_plan_changes(incumbent_future, local.assignments),
        "full_changes": count_plan_changes(incumbent_future, full.assignments),
    }


class RevisionPlanningCoordinator:
    def __init__(self, world: WorldState) -> None:
        self.world = world
        self.solve_in_progress = False
        self.pending_trigger = False
        self.last_solved_revision = -1
        self.last_published_plan: PlanResult | None = None

    def solve_latest(
        self,
        *,
        resource_states: dict[str, ResourceState],
        before_publish: Callable[[], None] | None = None,
    ) -> dict[str, Any]:
        if self.solve_in_progress:
            self.pending_trigger = True
            return {"published": False, "reason": "solve_in_progress"}
        self.solve_in_progress = True
        solved_revision = self.world.world_revision
        problem = self.world.planning_problem()
        result = solve_milp(problem, resource_states=resource_states, plan_kind="world_revision")
        if before_publish is not None:
            before_publish()
        stale = self.world.world_revision != solved_revision
        self.solve_in_progress = False
        if stale:
            self.pending_trigger = True
            return {
                "published": False,
                "reason": "stale_world_revision",
                "solved_revision": solved_revision,
                "current_revision": self.world.world_revision,
            }
        self.pending_trigger = False
        self.last_solved_revision = solved_revision
        self.last_published_plan = result
        plan_revision = self.world.next_plan_revision()
        return {
            "published": True,
            "world_revision": solved_revision,
            "plan_revision": plan_revision,
            "plan": result.to_dict(),
        }
