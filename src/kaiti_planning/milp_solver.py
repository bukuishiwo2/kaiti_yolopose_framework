from __future__ import annotations

from dataclasses import asdict
from typing import Any

from .models import PlanResult, PlanningProblem, ResourceState, TaskAssignment

try:
    import pulp
except ImportError:  # pragma: no cover - exercised by runtime environment
    pulp = None


def _require_pulp() -> Any:
    if pulp is None:
        raise ImportError(
            "PuLP is required for MILP solving. Install it with `pip install PuLP`."
        )
    return pulp


def initial_resource_states(problem: PlanningProblem) -> dict[str, ResourceState]:
    states: dict[str, ResourceState] = {}
    for resource in problem.resources:
        predicate = resource.id
        if resource.kind == "corridor":
            predicate = (
                "corridor_free"
                if resource.state == "free"
                else "corridor_blocked"
            )
        elif resource.kind == "charger":
            predicate = "charger_available" if resource.state == "available" else "charger_unavailable"
        states[resource.id] = ResourceState(
            resource_id=resource.id,
            predicate=predicate,
            state=resource.state,
            available_from=0.0,
            wait_time=0.0,
        )
    return states


def _is_fixed_zero(value: Any) -> bool:
    return isinstance(value, (int, float)) and float(value) == 0.0


def _task_finish_map(assignments: list[TaskAssignment]) -> dict[str, float]:
    return {item.task: float(item.finish) for item in assignments}


def _task_start_map(assignments: list[TaskAssignment]) -> dict[str, float]:
    return {item.task: float(item.start) for item in assignments}


def explain_plan_timing(
    problem: PlanningProblem,
    assignments: list[TaskAssignment],
    *,
    current_time: float,
    resource_states: dict[str, ResourceState] | None = None,
    committed_assignments: list[TaskAssignment] | None = None,
) -> dict[str, Any]:
    resource_states = resource_states or initial_resource_states(problem)
    committed_assignments = committed_assignments or []
    assignment_map = task_assignment_map(assignments)
    task_map = problem.task_by_id()
    resource_by_id = problem.resource_by_id()
    committed_ids = {item.task for item in committed_assignments}
    committed_map = {item.task: item for item in committed_assignments}
    finish_map = _task_finish_map(assignments)
    explanations: list[dict[str, Any]] = []

    for assignment in sorted(assignments, key=lambda item: (item.start, item.robot, item.task)):
        task = task_map[assignment.task]
        assigned_robot = problem.robot_by_id()[assignment.robot]
        release_earliest = max(float(current_time), float(task.release))
        robot_initial_earliest = float(problem.travel_times[assigned_robot.start][task.location])
        robot_sequence_earliest = robot_initial_earliest
        robot_predecessor_task = None

        for other in assignments:
            if other.task == assignment.task or other.robot != assignment.robot:
                continue
            if float(other.finish) <= float(assignment.start):
                candidate = float(other.finish) + float(problem.travel_times[other.location][task.location])
                if candidate > robot_sequence_earliest:
                    robot_sequence_earliest = candidate
                    robot_predecessor_task = other.task

        predecessor_earliest = 0.0
        predecessor_tasks: list[str] = []
        for before, after in problem.precedence:
            if after != task.id or before not in finish_map:
                continue
            candidate = float(finish_map[before])
            if candidate > predecessor_earliest:
                predecessor_earliest = candidate
            predecessor_tasks.append(before)

        resource_ready_by_resource: dict[str, float] = {}
        shared_resource_by_resource: dict[str, float] = {}
        event_zone_earliest = 0.0
        event_zone_resource = None
        for resource_id in task.resources:
            resource_state = resource_states.get(resource_id)
            resource_ready = max(
                float(current_time),
                float(resource_state.available_from if resource_state is not None else 0.0),
            )
            resource_ready_by_resource[resource_id] = resource_ready

            shared_ready = 0.0
            for other in assignments:
                if other.task == assignment.task or resource_id not in other.resources:
                    continue
                if float(other.finish) <= float(assignment.start):
                    candidate = float(other.finish) + float(resource_by_id[resource_id].release_buffer)
                    if candidate > shared_ready:
                        shared_ready = candidate
            for committed in committed_assignments:
                if committed.task == assignment.task or resource_id not in committed.resources:
                    continue
                candidate = float(committed.finish) + float(resource_by_id[resource_id].release_buffer)
                if candidate > shared_ready:
                    shared_ready = candidate
            shared_resource_by_resource[resource_id] = shared_ready
            if resource_by_id[resource_id].kind == "event_zone":
                event_zone_earliest = max(event_zone_earliest, max(resource_ready, shared_ready))
                event_zone_resource = resource_id

        resource_earliest = max(resource_ready_by_resource.values() or [0.0])
        shared_resource_earliest = max(shared_resource_by_resource.values() or [0.0])
        final_start = float(assignment.start)
        governing = []
        candidates = {
            "release": release_earliest,
            "robot_sequence": robot_sequence_earliest,
            "predecessor": predecessor_earliest,
            "resource_window": resource_earliest,
            "shared_resource": shared_resource_earliest,
            "event_zone": event_zone_earliest,
        }
        for name, value in candidates.items():
            if abs(value - final_start) <= 1e-6:
                governing.append(name)
        if assignment.task in committed_ids:
            governing = ["committed_prefix"]

        explanations.append(
            {
                "task": assignment.task,
                "robot": assignment.robot,
                "is_committed": assignment.task in committed_ids,
                "release_earliest": round(release_earliest, 3),
                "resource_earliest": round(resource_earliest, 3),
                "resource_ready_by_resource": {
                    key: round(value, 3) for key, value in resource_ready_by_resource.items()
                },
                "predecessor_earliest": round(predecessor_earliest, 3),
                "predecessor_tasks": predecessor_tasks,
                "robot_sequence_earliest": round(robot_sequence_earliest, 3),
                "robot_predecessor_task": robot_predecessor_task,
                "event_zone_earliest": round(event_zone_earliest, 3),
                "event_zone_resource": event_zone_resource,
                "shared_resource_earliest": round(shared_resource_earliest, 3),
                "shared_resource_by_resource": {
                    key: round(value, 3) for key, value in shared_resource_by_resource.items()
                },
                "final_start": round(final_start, 3),
                "governing_constraints": governing,
            }
        )

    return {
        "start_time_breakdown": explanations,
        "task_rows": {
            item["task"]: {
                "resource earliest": item["resource_earliest"],
                "predecessor earliest": item["predecessor_earliest"],
                "robot sequence earliest": item["robot_sequence_earliest"],
                "event zone earliest": item["event_zone_earliest"],
                "final start": item["final_start"],
                "governing_constraints": item["governing_constraints"],
            }
            for item in explanations
        },
        "committed_tasks": sorted(committed_map),
    }


def solve_milp(
    problem: PlanningProblem,
    *,
    backend: str = "pulp",
    current_time: float = 0.0,
    resource_states: dict[str, ResourceState] | None = None,
    committed_assignments: list[TaskAssignment] | None = None,
    incumbent_assignments: list[TaskAssignment] | None = None,
    excluded_task_ids: set[str] | None = None,
    plan_kind: str = "static",
) -> PlanResult:
    lib = _require_pulp()
    if backend.lower() != "pulp":
        raise ValueError("only backend='pulp' is currently supported")

    resource_states = resource_states or initial_resource_states(problem)
    committed_assignments = committed_assignments or []
    incumbent_assignments = incumbent_assignments or []
    excluded_task_ids = excluded_task_ids or set()

    tasks = [task for task in problem.tasks if task.id not in excluded_task_ids]
    task_map = {task.id: task for task in tasks}
    task_ids = [task.id for task in tasks]
    robot_ids = [robot.id for robot in problem.robots]
    robot_map = problem.robot_by_id()
    resource_map = resource_states
    travel = problem.travel_times
    committed_ids = {assignment.task for assignment in committed_assignments}
    committed_map = {assignment.task: assignment for assignment in committed_assignments}
    incumbent_map = {assignment.task: assignment for assignment in incumbent_assignments}

    model = lib.LpProblem("graduation_design_milp", lib.LpMinimize)
    big_m = 10_000.0

    x: dict[tuple[str, str], Any] = {}
    for robot in problem.robots:
        for task in tasks:
            compatible = set(task.capabilities).issubset(set(robot.capabilities))
            if compatible:
                x[(robot.id, task.id)] = lib.LpVariable(
                    f"x_{robot.id}_{task.id}", lowBound=0, upBound=1, cat="Binary"
                )
            else:
                x[(robot.id, task.id)] = 0

    s = {}
    for task in tasks:
        if task.id in committed_ids:
            low_bound = float(committed_map[task.id].start)
        else:
            low_bound = max(current_time, float(task.release))
        s[task.id] = lib.LpVariable(f"s_{task.id}", lowBound=low_bound)
    f = {task.id: lib.LpVariable(f"f_{task.id}", lowBound=0) for task in tasks}
    tardiness = {
        task.id: lib.LpVariable(f"L_{task.id}", lowBound=0) for task in tasks
    }
    battery_end = {
        robot.id: lib.LpVariable(
            f"b_{robot.id}",
            lowBound=0,
            upBound=max(problem.energy.full_battery, robot.battery + 100.0),
        )
        for robot in problem.robots
    }

    y: dict[tuple[str, str, str], Any] = {}
    z: dict[tuple[str, str, str], Any] = {}
    for robot_id in robot_ids:
        for idx, left in enumerate(task_ids):
            for right in task_ids[idx + 1 :]:
                y[(robot_id, left, right)] = lib.LpVariable(
                    f"y_{robot_id}_{left}_{right}", lowBound=0, upBound=1, cat="Binary"
                )
    for resource_id in resource_map:
        for idx, left in enumerate(task_ids):
            for right in task_ids[idx + 1 :]:
                z[(resource_id, left, right)] = lib.LpVariable(
                    f"z_{resource_id}_{left}_{right}", lowBound=0, upBound=1, cat="Binary"
                )

    has_incumbent = bool(incumbent_assignments)
    change_flag: dict[str, Any] = {}
    shift_delta: dict[str, Any] = {}
    if has_incumbent:
        for task in tasks:
            if task.id in committed_ids:
                continue
            change_flag[task.id] = lib.LpVariable(
                f"m_{task.id}", lowBound=0, upBound=1, cat="Binary"
            )
            shift_delta[task.id] = lib.LpVariable(f"delta_{task.id}", lowBound=0)

    for task in tasks:
        assign_vars = [x[(robot_id, task.id)] for robot_id in robot_ids]
        model += lib.lpSum(assign_vars) == (1 if task.must_complete else 0)
        model += f[task.id] == s[task.id] + float(task.duration)
        model += tardiness[task.id] >= f[task.id] - float(task.deadline)

        if task.id in committed_ids:
            committed = committed_map[task.id]
            model += s[task.id] == float(committed.start)
            for robot in problem.robots:
                assign_var = x[(robot.id, task.id)]
                if _is_fixed_zero(assign_var):
                    continue
                if robot.id == committed.robot:
                    model += assign_var == 1
                else:
                    model += assign_var == 0

        for robot in problem.robots:
            assign_var = x[(robot.id, task.id)]
            if _is_fixed_zero(assign_var):
                continue
            start_cost = float(travel[robot.start][task.location])
            model += s[task.id] >= start_cost - big_m * (1 - assign_var)

            if task.id in incumbent_map and task.id not in committed_ids and has_incumbent:
                incumbent = incumbent_map[task.id]
                incumbent_assigned = 1 if incumbent.robot == robot.id else 0
                if incumbent_assigned == 1:
                    model += change_flag[task.id] >= 1 - assign_var
                else:
                    model += change_flag[task.id] >= assign_var

        if task.id in incumbent_map and task.id not in committed_ids and has_incumbent:
            incumbent_start = float(incumbent_map[task.id].start)
            model += shift_delta[task.id] >= s[task.id] - incumbent_start
            model += shift_delta[task.id] >= incumbent_start - s[task.id]

        state_requirements = []
        for resource_id in task.resources:
            resource_state = resource_map.get(resource_id)
            if resource_state is None:
                continue
            if task.id in committed_ids:
                continue
            if resource_state.state == "blocked":
                state_requirements.append(f"blocked:{resource_id}")
            else:
                available_from = max(current_time, float(resource_state.available_from))
                model += s[task.id] >= available_from
        if state_requirements:
            raise ValueError(
                f"task {task.id} requires blocked resources: {', '.join(state_requirements)}"
            )

    for before, after in problem.precedence:
        if before in task_map and after in task_map:
            model += s[after] >= f[before]

    for robot_id in robot_ids:
        for idx, left in enumerate(task_ids):
            for right in task_ids[idx + 1 :]:
                left_var = x[(robot_id, left)]
                right_var = x[(robot_id, right)]
                if _is_fixed_zero(left_var) or _is_fixed_zero(right_var):
                    continue
                order_var = y[(robot_id, left, right)]
                left_task = task_map[left]
                right_task = task_map[right]
                left_to_right = float(travel[left_task.location][right_task.location])
                right_to_left = float(travel[right_task.location][left_task.location])
                model += (
                    s[right]
                    >= f[left] + left_to_right - big_m * (3 - left_var - right_var - order_var)
                )
                model += (
                    s[left]
                    >= f[right] + right_to_left - big_m * (2 - left_var - right_var + order_var)
                )

    task_resources = {
        task.id: set(task.resources)
        for task in tasks
    }
    for resource_id, resource_state in resource_map.items():
        release_buffer = float(problem.resource_by_id()[resource_id].release_buffer)
        for idx, left in enumerate(task_ids):
            for right in task_ids[idx + 1 :]:
                if resource_id not in task_resources[left] or resource_id not in task_resources[right]:
                    continue
                order_var = z[(resource_id, left, right)]
                model += s[right] >= f[left] + release_buffer - big_m * (1 - order_var)
                model += s[left] >= f[right] + release_buffer - big_m * order_var

    for committed in committed_assignments:
        committed_task = task_map.get(committed.task)
        if committed_task is None:
            continue
        for task in tasks:
            if task.id == committed.task:
                continue
            robot_var = x[(committed.robot, task.id)]
            if not _is_fixed_zero(robot_var):
                model += s[task.id] >= float(committed.finish) - big_m * (1 - robot_var)
            shared_resources = set(committed.resources).intersection(task.resources)
            if shared_resources:
                model += s[task.id] >= float(committed.finish)

    for robot in problem.robots:
        assigned_energy = []
        for task in tasks:
            assign_var = x[(robot.id, task.id)]
            if _is_fixed_zero(assign_var):
                continue
            start_cost = float(travel[robot.start][task.location])
            task_cost = float(problem.energy.task_costs.get(task.type, 0.0))
            move_cost = float(problem.energy.move_cost_per_sec) * start_cost
            charge_gain = float(problem.energy.charge_gain.get(task.id, 0.0))
            assigned_energy.append((task_cost + move_cost - charge_gain) * assign_var)
        model += battery_end[robot.id] == float(robot.battery) - lib.lpSum(assigned_energy)
        model += battery_end[robot.id] >= float(problem.energy.safe_battery)

    travel_cost_terms = []
    delay_cost_terms = []
    interrupt_cost_terms = []
    resource_cost_terms = []
    energy_cost_terms = []
    change_cost_terms = []

    for robot in problem.robots:
        for task in tasks:
            assign_var = x[(robot.id, task.id)]
            if _is_fixed_zero(assign_var):
                continue
            start_cost = float(travel[robot.start][task.location])
            travel_cost_terms.append(start_cost * assign_var)
            task_cost = float(problem.energy.task_costs.get(task.type, 0.0))
            energy_cost_terms.append((task_cost + problem.energy.move_cost_per_sec * start_cost) * assign_var)

    for task in tasks:
        delay_cost_terms.append(float(task.priority_weight) * tardiness[task.id])
        interrupt_cost_terms.append(float(task.interrupt_penalty) * s[task.id])
        for resource_id in task.resources:
            resource_state = resource_map.get(resource_id)
            if resource_state and resource_state.state == "temporary_occupied":
                resource_cost_terms.append(float(resource_state.wait_time) * 0.1)
        if has_incumbent and task.id in change_flag:
            change_cost_terms.append(10.0 * change_flag[task.id] + shift_delta[task.id])

    model += (
        problem.weights.alpha_travel * lib.lpSum(travel_cost_terms)
        + problem.weights.beta_delay * lib.lpSum(delay_cost_terms)
        + problem.weights.gamma_interrupt * lib.lpSum(interrupt_cost_terms)
        + problem.weights.delta_resource * lib.lpSum(resource_cost_terms)
        + problem.weights.eta_energy * lib.lpSum(energy_cost_terms)
        + problem.weights.mu_change * lib.lpSum(change_cost_terms)
    )

    solver = lib.PULP_CBC_CMD(msg=False)
    model.solve(solver)

    status = lib.LpStatus[model.status]
    if status != "Optimal":
        return PlanResult(
            solver_status=status,
            objective_value=None,
            assignments=[],
            metrics={"task_count": float(len(tasks))},
            planner_mode="milp",
            plan_kind=plan_kind,
            current_time=current_time,
            notes=["solver_did_not_find_optimal_solution"],
            diagnostics={},
        )

    assignments: list[TaskAssignment] = []
    for committed in committed_assignments:
        assignments.append(committed)
    for task in tasks:
        if task.id in committed_ids:
            continue
        assigned_robot = None
        for robot in problem.robots:
            assign_var = x[(robot.id, task.id)]
            if not _is_fixed_zero(assign_var) and lib.value(assign_var) > 0.5:
                assigned_robot = robot.id
                break
        if assigned_robot is None:
            continue
        assignments.append(
            TaskAssignment(
                robot=assigned_robot,
                task=task.id,
                start=round(float(lib.value(s[task.id])), 3),
                finish=round(float(lib.value(f[task.id])), 3),
                location=task.location,
                resources=list(task.resources),
                energy_after=round(float(lib.value(battery_end[assigned_robot])), 3),
            )
        )

    objective_numeric = float(lib.value(model.objective) or 0.0)
    assignments.sort(key=lambda item: (item.start, item.robot, item.task))
    total_delay = sum(
        max(0.0, assignment.finish - float(task_map[assignment.task].deadline))
        for assignment in assignments
        if assignment.task in task_map
    )
    event_response_start = min(
        [assignment.start for assignment in assignments if task_map.get(assignment.task, None) and task_map[assignment.task].event_task]
        or [0.0]
    )
    metrics = {
        "task_count": float(len(assignments)),
        "total_delay": round(float(total_delay), 3),
        "event_response_start": round(float(event_response_start), 3),
        "makespan": round(float(max([item.finish for item in assignments] or [0.0])), 3),
        "objective": round(objective_numeric, 3),
    }

    return PlanResult(
        solver_status=status,
        objective_value=round(objective_numeric, 3),
        assignments=assignments,
        metrics=metrics,
        planner_mode="milp",
        plan_kind=plan_kind,
        current_time=current_time,
        notes=[],
        diagnostics=explain_plan_timing(
            problem,
            assignments,
            current_time=current_time,
            resource_states=resource_states,
            committed_assignments=committed_assignments,
        ),
    )


def committed_prefix(assignments: list[TaskAssignment], current_time: float) -> list[TaskAssignment]:
    return [item for item in assignments if item.start < current_time]


def task_assignment_map(assignments: list[TaskAssignment]) -> dict[str, TaskAssignment]:
    return {item.task: item for item in assignments}


def count_plan_changes(
    old_assignments: list[TaskAssignment],
    new_assignments: list[TaskAssignment],
) -> dict[str, float]:
    old_map = task_assignment_map(old_assignments)
    new_map = task_assignment_map(new_assignments)
    task_ids = sorted(set(old_map) | set(new_map))
    modified = 0
    reassigned = 0
    shifted = 0
    for task_id in task_ids:
        old_item = old_map.get(task_id)
        new_item = new_map.get(task_id)
        if old_item is None or new_item is None:
            modified += 1
            continue
        if old_item.robot != new_item.robot:
            modified += 1
            reassigned += 1
            continue
        if round(old_item.start, 3) != round(new_item.start, 3):
            modified += 1
            shifted += 1
    return {
        "modified_task_count": float(modified),
        "reassigned_task_count": float(reassigned),
        "shifted_task_count": float(shifted),
    }
