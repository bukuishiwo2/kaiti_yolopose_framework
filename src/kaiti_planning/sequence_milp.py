from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import tempfile
from time import perf_counter
from typing import Any

from .models import (
    PlanResult,
    PlanningProblem,
    ResourceReservation,
    ResourceState,
    SolverStatus,
    TaskAssignment,
)


@dataclass
class _ReservationCandidate:
    resource_id: str
    robot_id: str
    task_id: str
    route_arc: str
    selected: Any
    enter: Any
    exit: Any
    safety_buffer: float


def _fixed_zero(value: Any) -> bool:
    return isinstance(value, (int, float)) and float(value) == 0.0


def _charger_locations(problem: PlanningProblem) -> list[str]:
    return sorted({task.location for task in problem.tasks if task.type == "charge"})


def _return_time(problem: PlanningProblem, location: str, fallback: str) -> float:
    chargers = _charger_locations(problem)
    targets = chargers or [fallback]
    return min(float(problem.travel_times[location][target]) for target in targets)


def _pickup_delivery_pairs(task_ids: set[str]) -> list[tuple[str, str]]:
    pairs = []
    for pickup in sorted(task_id for task_id in task_ids if task_id.startswith("pickup:")):
        deliver = f"deliver:{pickup.split(':', 1)[1]}"
        if deliver in task_ids:
            pairs.append((pickup, deliver))
    return pairs


def _parse_cbc_log(path: Path) -> tuple[float | None, float | None]:
    if not path.exists():
        return None, None
    text = path.read_text(encoding="utf-8", errors="replace")
    bound_match = re.findall(r"Lower bound:\s*([-+0-9.eE]+)", text)
    gap_match = re.findall(r"Gap:\s*([-+0-9.eE]+)", text)
    bound = float(bound_match[-1]) if bound_match else None
    gap = abs(float(gap_match[-1])) if gap_match else None
    return bound, gap


def solve_sequence_milp(
    problem: PlanningProblem,
    *,
    lib: Any,
    current_time: float,
    resource_states: dict[str, ResourceState],
    committed_assignments: list[TaskAssignment],
    incumbent_assignments: list[TaskAssignment],
    excluded_task_ids: set[str],
    plan_kind: str,
) -> PlanResult:
    tasks = [task for task in problem.tasks if task.id not in excluded_task_ids]
    task_map = {task.id: task for task in tasks}
    task_ids = list(task_map)
    robot_ids = [robot.id for robot in problem.robots]
    robot_map = problem.robot_by_id()
    committed_map = {item.task: item for item in committed_assignments if item.task in task_map}
    incumbent_map = {item.task: item for item in incumbent_assignments if item.task in task_map}
    horizon_end = float(current_time) + float(problem.solver.planning_horizon)

    blocking_tasks = []
    waiting_tasks = []
    for task in tasks:
        blocked = {
            resource_id
            for resource_id in task.resources
            if resource_states.get(resource_id)
            and resource_states[resource_id].state == "blocked"
        }
        compatible_robots = [
            robot
            for robot in problem.robots
            if set(task.capabilities).issubset(robot.capabilities)
        ]
        direct_route_blocks = []
        for robot in compatible_robots:
            route_blocked = {
                use.resource_id
                for use in problem.route_resource_uses(robot.start, task.location)
                if resource_states.get(use.resource_id)
                and resource_states[use.resource_id].state == "blocked"
            }
            direct_route_blocks.append(route_blocked)
        if direct_route_blocks and all(direct_route_blocks):
            blocked.update(set.intersection(*direct_route_blocks))
        if blocked and task.must_complete and task.id not in committed_map:
            blocking_tasks.append({"task_id": task.id, "resource_ids": sorted(blocked)})
        waiting = [
            resource_id
            for resource_id in task.resources
            if resource_states.get(resource_id)
            and resource_states[resource_id].state == "temporary_occupied"
            and float(resource_states[resource_id].available_from) > horizon_end
        ]
        if waiting and task.must_complete and task.id not in committed_map:
            waiting_tasks.append({"task_id": task.id, "resource_ids": sorted(waiting)})
    if blocking_tasks:
        return PlanResult(
            solver_status=SolverStatus.INFEASIBLE_ROUTE_BLOCKED.value,
            objective_value=None,
            assignments=[],
            metrics={"task_count": float(len(tasks)), "assigned_task_count": 0.0},
            plan_kind=plan_kind,
            current_time=current_time,
            notes=["required_service_resource_is_blocked"],
            diagnostics={
                "reason_code": "ROUTE_BLOCKED_NO_ALTERNATIVE",
                "blocking_tasks": blocking_tasks,
                "blocking_resources": sorted(
                    {item for row in blocking_tasks for item in row["resource_ids"]}
                ),
                "earliest_retry_time": None,
                "alternative_route_available": False,
            },
            time_limit=float(problem.solver.time_limit),
        )
    if waiting_tasks:
        waiting_resources = sorted(
            {item for row in waiting_tasks for item in row["resource_ids"]}
        )
        return PlanResult(
            solver_status=SolverStatus.WAITING_FOR_RESOURCE.value,
            objective_value=None,
            assignments=[],
            metrics={"task_count": float(len(tasks)), "assigned_task_count": 0.0},
            plan_kind=plan_kind,
            current_time=current_time,
            notes=["temporary_resource_available_after_planning_horizon"],
            diagnostics={
                "reason_code": "TEMPORARY_RESOURCE_OUTSIDE_HORIZON",
                "blocking_tasks": waiting_tasks,
                "blocking_resources": waiting_resources,
                "earliest_retry_time": min(
                    float(resource_states[item].available_from) for item in waiting_resources
                ),
                "alternative_route_available": False,
            },
            time_limit=float(problem.solver.time_limit),
        )

    max_travel = max(
        [float(value) for row in problem.travel_times.values() for value in row.values()]
        or [0.0]
    )
    big_m = max(
        10.0,
        float(problem.solver.planning_horizon)
        + sum(float(task.duration) for task in tasks)
        + max_travel * (len(tasks) + 2),
    )
    model = lib.LpProblem("graduation_sequence_arc_milp", lib.LpMinimize)

    x: dict[tuple[str, str], Any] = {}
    for robot in problem.robots:
        for task in tasks:
            if set(task.capabilities).issubset(robot.capabilities):
                x[(robot.id, task.id)] = lib.LpVariable(
                    f"x_{robot.id}_{task.id}", 0, 1, cat="Binary"
                )
            else:
                x[(robot.id, task.id)] = 0

    s = {
        task.id: lib.LpVariable(
            f"s_{task.id}",
            lowBound=max(float(current_time), float(task.release)),
            upBound=horizon_end,
        )
        for task in tasks
    }
    f = {
        task.id: lib.LpVariable(f"f_{task.id}", lowBound=0, upBound=horizon_end + task.duration)
        for task in tasks
    }
    tardiness = {task.id: lib.LpVariable(f"late_{task.id}", lowBound=0) for task in tasks}

    arcs: dict[tuple[str, str, str], Any] = {}
    arc_times: dict[tuple[str, str, str], float] = {}
    start_nodes = {robot_id: f"__start__:{robot_id}" for robot_id in robot_ids}
    end_nodes = {robot_id: f"__end__:{robot_id}" for robot_id in robot_ids}
    for robot in problem.robots:
        start = start_nodes[robot.id]
        end = end_nodes[robot.id]
        arcs[(robot.id, start, end)] = lib.LpVariable(f"a_{robot.id}_start_end", 0, 1, cat="Binary")
        arc_times[(robot.id, start, end)] = 0.0
        for task in tasks:
            arcs[(robot.id, start, task.id)] = lib.LpVariable(
                f"a_{robot.id}_start_{task.id}", 0, 1, cat="Binary"
            )
            arc_times[(robot.id, start, task.id)] = float(
                problem.travel_times[robot.start][task.location]
            )
            arcs[(robot.id, task.id, end)] = lib.LpVariable(
                f"a_{robot.id}_{task.id}_end", 0, 1, cat="Binary"
            )
            arc_times[(robot.id, task.id, end)] = _return_time(
                problem, task.location, robot.start
            )
        for left in tasks:
            for right in tasks:
                if left.id == right.id:
                    continue
                arcs[(robot.id, left.id, right.id)] = lib.LpVariable(
                    f"a_{robot.id}_{left.id}_{right.id}", 0, 1, cat="Binary"
                )
                arc_times[(robot.id, left.id, right.id)] = float(
                    problem.travel_times[left.location][right.location]
                )

    order = {
        (robot_id, task_id): lib.LpVariable(
            f"order_{robot_id}_{task_id}", lowBound=0, upBound=max(1, len(tasks))
        )
        for robot_id in robot_ids
        for task_id in task_ids
    }

    for task in tasks:
        model += f[task.id] == s[task.id] + float(task.duration)
        model += tardiness[task.id] >= f[task.id] - float(task.deadline)
        model += lib.lpSum(x[(robot_id, task.id)] for robot_id in robot_ids) == (
            1 if task.must_complete else 0
        )
        for resource_id in task.resources:
            state = resource_states.get(resource_id)
            if state is not None:
                model += s[task.id] >= max(float(current_time), float(state.available_from))

    for robot_id in robot_ids:
        start = start_nodes[robot_id]
        end = end_nodes[robot_id]
        model += lib.lpSum(
            variable for (rid, origin, _), variable in arcs.items() if rid == robot_id and origin == start
        ) == 1
        model += lib.lpSum(
            variable for (rid, _, destination), variable in arcs.items() if rid == robot_id and destination == end
        ) == 1
        for task_id in task_ids:
            incoming = lib.lpSum(
                variable
                for (rid, _, destination), variable in arcs.items()
                if rid == robot_id and destination == task_id
            )
            outgoing = lib.lpSum(
                variable
                for (rid, origin, _), variable in arcs.items()
                if rid == robot_id and origin == task_id
            )
            model += incoming == x[(robot_id, task_id)]
            model += outgoing == x[(robot_id, task_id)]
            model += order[(robot_id, task_id)] >= x[(robot_id, task_id)]
            model += order[(robot_id, task_id)] <= max(1, len(tasks)) * x[(robot_id, task_id)]

    route_waits: dict[tuple[str, str, str, int], Any] = {}
    resource_exposure_terms: list[Any] = []
    reservation_candidates: list[_ReservationCandidate] = []
    for key, arc in arcs.items():
        robot_id, origin, destination = key
        robot = robot_map[robot_id]
        travel_time = arc_times[key]
        if origin.startswith("__start__"):
            departure: Any = float(current_time)
            origin_location = robot.start
        else:
            departure = f[origin]
            origin_location = task_map[origin].location
        if destination.startswith("__end__"):
            charger_locations = _charger_locations(problem)
            destination_location = min(
                charger_locations or [robot.start],
                key=lambda loc: float(problem.travel_times[origin_location][loc]),
            )
        else:
            destination_location = task_map[destination].location

        uses = problem.route_resource_uses(origin_location, destination_location)
        cumulative_wait: Any = 0.0
        for index, use in enumerate(uses):
            wait = lib.LpVariable(
                f"wait_{robot_id}_{origin}_{destination}_{index}", lowBound=0, upBound=big_m
            )
            route_waits[(robot_id, origin, destination, index)] = wait
            model += wait <= big_m * arc
            enter = departure + float(use.enter_fraction) * travel_time + cumulative_wait + wait
            exit_time = enter + max(
                0.0, float(use.exit_fraction - use.enter_fraction) * travel_time
            )
            state = resource_states.get(use.resource_id)
            if state is not None:
                model += enter >= float(state.available_from) - big_m * (1 - arc)
                if state.state == "blocked":
                    model += arc == 0
                if state.state == "temporary_occupied":
                    resource_exposure_terms.append(float(state.wait_time) * arc)
            reservation_candidates.append(
                _ReservationCandidate(
                    resource_id=use.resource_id,
                    robot_id=robot_id,
                    task_id=(destination if destination in task_map else "__return__"),
                    route_arc=f"{origin}->{destination}",
                    selected=arc,
                    enter=enter,
                    exit=exit_time,
                    safety_buffer=float(use.safety_buffer),
                )
            )
            cumulative_wait += wait

        if destination in task_map:
            model += s[destination] >= departure + travel_time + cumulative_wait - big_m * (1 - arc)
        if origin in task_map and destination in task_map:
            model += order[(robot_id, destination)] >= order[(robot_id, origin)] + 1 - len(tasks) * (1 - arc)

    for task in tasks:
        for robot_id in robot_ids:
            selected = x[(robot_id, task.id)]
            if _fixed_zero(selected):
                continue
            for resource_id in task.resources:
                state = resource_states.get(resource_id)
                if state is not None and state.state == "temporary_occupied":
                    resource_exposure_terms.append(float(state.wait_time) * selected)
                reservation_candidates.append(
                    _ReservationCandidate(
                        resource_id=resource_id,
                        robot_id=robot_id,
                        task_id=task.id,
                        route_arc="service",
                        selected=selected,
                        enter=s[task.id],
                        exit=f[task.id],
                        safety_buffer=float(problem.resource_by_id()[resource_id].release_buffer),
                    )
                )

    for resource_id in problem.resource_by_id():
        candidates = [item for item in reservation_candidates if item.resource_id == resource_id]
        if problem.resource_by_id()[resource_id].capacity != 1:
            continue
        for left_index, left in enumerate(candidates):
            for right_index in range(left_index + 1, len(candidates)):
                right = candidates[right_index]
                if left.selected is right.selected:
                    continue
                sequence = lib.LpVariable(
                    f"res_order_{resource_id}_{left_index}_{right_index}", 0, 1, cat="Binary"
                )
                inactive = 2 - left.selected - right.selected
                buffer = max(left.safety_buffer, right.safety_buffer)
                model += right.enter >= left.exit + buffer - big_m * (1 - sequence) - big_m * inactive
                model += left.enter >= right.exit + buffer - big_m * sequence - big_m * inactive

    for before, after in problem.precedence:
        if before in task_map and after in task_map:
            model += s[after] >= f[before]
    for pickup, deliver in _pickup_delivery_pairs(set(task_ids)):
        for robot_id in robot_ids:
            model += x[(robot_id, pickup)] == x[(robot_id, deliver)]

    for task_id, committed in committed_map.items():
        model += s[task_id] == float(committed.start)
        for robot_id in robot_ids:
            selected = x[(robot_id, task_id)]
            if not _fixed_zero(selected):
                model += selected == (1 if robot_id == committed.robot else 0)

    energy_before: dict[tuple[str, str], Any] = {}
    energy_after: dict[tuple[str, str], Any] = {}
    charge_amount: dict[tuple[str, str], Any] = {}
    energy_risk = []
    for robot in problem.robots:
        for task in tasks:
            selected = x[(robot.id, task.id)]
            if _fixed_zero(selected):
                continue
            key = (robot.id, task.id)
            energy_before[key] = lib.LpVariable(f"eb_{robot.id}_{task.id}", 0, problem.energy.full_battery)
            energy_after[key] = lib.LpVariable(f"ea_{robot.id}_{task.id}", 0, problem.energy.full_battery)
            model += energy_before[key] >= problem.energy.safe_battery * selected
            model += energy_after[key] >= problem.energy.safe_battery * selected
            model += energy_before[key] <= problem.energy.full_battery * selected
            model += energy_after[key] <= problem.energy.full_battery * selected
            max_gain = float(problem.energy.charge_gain.get(task.id, 0.0))
            charge_amount[key] = lib.LpVariable(f"charge_{robot.id}_{task.id}", 0, max_gain)
            model += charge_amount[key] <= max_gain * selected
            service_cost = float(problem.energy.task_costs.get(task.type, 0.0))
            delta = energy_after[key] - energy_before[key] + service_cost - charge_amount[key]
            model += delta <= big_m * (1 - selected)
            model += delta >= -big_m * (1 - selected)
            risk = lib.LpVariable(f"energy_risk_{robot.id}_{task.id}", lowBound=0)
            model += risk >= problem.energy.full_battery * selected - energy_after[key]
            energy_risk.append(risk)

    for key, arc in arcs.items():
        robot_id, origin, destination = key
        move_energy = problem.energy.move_cost_per_sec * arc_times[key]
        if destination in task_map:
            before = energy_before.get((robot_id, destination))
            if before is None:
                model += arc == 0
                continue
            source_energy: Any = (
                float(robot_map[robot_id].battery)
                if origin.startswith("__start__")
                else energy_after.get((robot_id, origin))
            )
            if source_energy is None:
                model += arc == 0
                continue
            delta = before - source_energy + move_energy
            model += delta <= big_m * (1 - arc)
            model += delta >= -big_m * (1 - arc)
        elif origin in task_map:
            after = energy_after.get((robot_id, origin))
            if after is not None:
                model += after - move_energy >= problem.energy.safe_battery - big_m * (1 - arc)

    reassigned_flags = []
    shifted_deltas = []
    order_change_terms = []
    for task_id, incumbent in incumbent_map.items():
        if task_id in committed_map:
            continue
        flag = lib.LpVariable(f"reassigned_{task_id}", 0, 1, cat="Binary")
        incumbent_selected = x.get((incumbent.robot, task_id), 0)
        if _fixed_zero(incumbent_selected):
            model += flag == 1
        else:
            model += flag >= 1 - incumbent_selected
        reassigned_flags.append(flag)
        shift = lib.LpVariable(f"shift_{task_id}", lowBound=0)
        model += shift >= s[task_id] - float(incumbent.start)
        model += shift >= float(incumbent.start) - s[task_id]
        shifted_deltas.append(shift)
    by_robot: dict[str, list[TaskAssignment]] = {robot_id: [] for robot_id in robot_ids}
    for assignment in incumbent_assignments:
        if assignment.task in task_map:
            by_robot.setdefault(assignment.robot, []).append(assignment)
    for robot_id, items in by_robot.items():
        items.sort(key=lambda item: (item.start, item.finish, item.task))
        for left, right in zip(items, items[1:]):
            arc = arcs.get((robot_id, left.task, right.task))
            if arc is not None:
                order_change_terms.append(1 - arc)

    travel_term = lib.lpSum(arc_times[key] * arc for key, arc in arcs.items())
    delay_term = lib.lpSum(task_map[task_id].priority_weight * tardiness[task_id] for task_id in task_ids)
    resource_wait_term = lib.lpSum(route_waits.values()) + lib.lpSum(resource_exposure_terms)
    energy_term = lib.lpSum(energy_risk)
    change_term = lib.lpSum(reassigned_flags) * 10 + lib.lpSum(shifted_deltas) + lib.lpSum(order_change_terms) * 5
    objective = (
        problem.weights.alpha_travel * travel_term
        + problem.weights.beta_delay * delay_term
        + problem.weights.delta_resource * resource_wait_term
        + problem.weights.eta_energy * energy_term
        + problem.weights.mu_change * change_term
    )
    model += objective

    with tempfile.NamedTemporaryFile(prefix="kaiti_cbc_", suffix=".log", delete=False) as handle:
        log_path = Path(handle.name)
    solver = lib.PULP_CBC_CMD(
        msg=False,
        timeLimit=float(problem.solver.time_limit),
        gapRel=float(problem.solver.mip_gap),
        logPath=str(log_path),
    )
    started = perf_counter()
    model.solve(solver)
    runtime = perf_counter() - started
    raw_status = lib.LpStatus[model.status]
    best_bound, parsed_gap = _parse_cbc_log(log_path)
    log_path.unlink(missing_ok=True)

    has_assignment = all(
        abs(sum(float(lib.value(x[(robot_id, task.id)]) or 0.0) for robot_id in robot_ids) - (1 if task.must_complete else 0)) <= 1e-4
        for task in tasks
    )
    if raw_status == "Optimal":
        status = SolverStatus.OPTIMAL.value
        parsed_gap = 0.0 if parsed_gap is None else parsed_gap
    elif has_assignment and raw_status in {"Not Solved", "Undefined"}:
        status = SolverStatus.TIME_LIMIT_FEASIBLE.value
    else:
        status = SolverStatus.INFEASIBLE.value if raw_status in {"Infeasible", "Unbounded"} else SolverStatus.ERROR.value
    if status not in {SolverStatus.OPTIMAL.value, SolverStatus.TIME_LIMIT_FEASIBLE.value}:
        return PlanResult(
            solver_status=status,
            objective_value=None,
            assignments=[],
            metrics={"task_count": float(len(tasks))},
            plan_kind=plan_kind,
            current_time=current_time,
            notes=["sequence_solver_did_not_find_feasible_solution"],
            diagnostics={"raw_solver_status": raw_status, "big_m": big_m},
            solver_runtime=round(runtime, 6),
            mip_gap=parsed_gap,
            best_bound=best_bound,
            time_limit=float(problem.solver.time_limit),
        )

    assignments = list(committed_assignments)
    for task in tasks:
        if task.id in committed_map:
            continue
        robot_id = next(
            robot_id
            for robot_id in robot_ids
            if not _fixed_zero(x[(robot_id, task.id)]) and float(lib.value(x[(robot_id, task.id)]) or 0.0) > 0.5
        )
        assignments.append(
            TaskAssignment(
                robot=robot_id,
                task=task.id,
                start=round(float(lib.value(s[task.id])), 3),
                finish=round(float(lib.value(f[task.id])), 3),
                location=task.location,
                resources=list(task.resources),
                energy_before=round(float(lib.value(energy_before[(robot_id, task.id)])), 3),
                energy_after=round(float(lib.value(energy_after[(robot_id, task.id)])), 3),
            )
        )
    assignments.sort(key=lambda item: (item.start, item.robot, item.task))

    reservations = []
    for candidate in reservation_candidates:
        if float(lib.value(candidate.selected) or 0.0) <= 0.5:
            continue
        reservations.append(
            ResourceReservation(
                resource_id=candidate.resource_id,
                robot_id=candidate.robot_id,
                task_id=candidate.task_id,
                route_arc=candidate.route_arc,
                enter_time=round(float(lib.value(candidate.enter)), 3),
                exit_time=round(float(lib.value(candidate.exit)), 3),
                safety_buffer=candidate.safety_buffer,
            )
        )
    reservations.sort(key=lambda item: (item.enter_time, item.resource_id, item.robot_id))

    components = {
        "travel": round(float(lib.value(travel_term) or 0.0), 3),
        "delay": round(float(lib.value(delay_term) or 0.0), 3),
        "resource_wait": round(float(lib.value(resource_wait_term) or 0.0), 3),
        "energy_risk": round(float(lib.value(energy_term) or 0.0), 3),
        "plan_change": round(float(lib.value(change_term) or 0.0), 3),
    }
    objective_value = round(float(lib.value(model.objective) or 0.0), 3)
    return PlanResult(
        solver_status=status,
        objective_value=objective_value,
        assignments=assignments,
        metrics={
            "task_count": float(len(assignments)),
            "makespan": round(max((item.finish for item in assignments), default=0.0), 3),
            "objective": objective_value,
        },
        plan_kind=plan_kind,
        current_time=current_time,
        diagnostics={
            "raw_solver_status": raw_status,
            "big_m": round(big_m, 3),
            "selected_arcs": [
                {"robot": rid, "from": origin, "to": destination}
                for (rid, origin, destination), arc in arcs.items()
                if float(lib.value(arc) or 0.0) > 0.5
            ],
        },
        resource_reservations=reservations,
        objective_components=components,
        solver_runtime=round(runtime, 6),
        mip_gap=parsed_gap,
        best_bound=(objective_value if best_bound is None and status == SolverStatus.OPTIMAL.value else best_bound),
        time_limit=float(problem.solver.time_limit),
    )
