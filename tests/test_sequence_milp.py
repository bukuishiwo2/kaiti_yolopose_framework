from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from kaiti_planning.milp_solver import initial_resource_states, solve_milp
from kaiti_planning.models import ResourceReservation, SolverStatus, load_problem_from_yaml
from kaiti_planning.validator import validate_plan
from kaiti_planning.world_state import WorldState


def _supply_case():
    world = WorldState(
        load_problem_from_yaml(PROJECT_ROOT / "configs/planner_graduation_v2.yaml")
    )
    update = world.ingest_perception(
        "confirmed", current_time=30.0, location_id="B", track_id=1
    )
    assert update.event_id is not None
    world.record_verification(update.event_id, "fall", current_time=40.0)
    problem = world.planning_problem()
    states = initial_resource_states(problem)
    result = solve_milp(problem, current_time=40.0, resource_states=states)
    return update.event_id, problem, states, result


def test_sequence_solver_uses_connected_arcs_energy_and_reservation_intervals() -> None:
    event_id, problem, states, result = _supply_case()
    validation = validate_plan(
        problem,
        result.assignments,
        current_time=40.0,
        resource_states=states,
        resource_reservations=result.resource_reservations,
        selected_arcs=result.diagnostics["selected_arcs"],
    )
    assignment_map = {item.task: item for item in result.assignments}

    assert result.solver_status == SolverStatus.OPTIMAL.value
    assert result.diagnostics["big_m"] < 10_000
    assert result.solver_runtime is not None
    assert result.mip_gap == 0.0
    assert result.best_bound is not None
    assert result.time_limit == 5.0
    assert assignment_map[f"pickup:{event_id}"].robot == assignment_map[f"deliver:{event_id}"].robot
    assert all(item.energy_before is not None and item.energy_after is not None for item in result.assignments)
    assert any(item.route_arc != "service" for item in result.resource_reservations)
    assert validation["counts"]["is_valid"] is True

    selected = result.diagnostics["selected_arcs"]
    for robot_id in {item["robot"] for item in selected}:
        robot_arcs = [item for item in selected if item["robot"] == robot_id]
        assert sum(item["from"].startswith("__start__") for item in robot_arcs) == 1
        assert sum(item["to"].startswith("__end__") for item in robot_arcs) == 1


def test_sequence_validator_rejects_cross_robot_delivery_energy_and_overlap() -> None:
    event_id, problem, states, result = _supply_case()
    assignments = deepcopy(result.assignments)
    deliver = next(item for item in assignments if item.task == f"deliver:{event_id}")
    deliver.robot = "R1" if deliver.robot != "R1" else "R2"
    energy_item = next(item for item in assignments if item.energy_after is not None)
    energy_item.energy_after = float(energy_item.energy_after) + 5.0

    reservations = deepcopy(result.resource_reservations)
    corridor = [item for item in reservations if item.resource_id == "corridor_H"]
    assert len(corridor) >= 2
    corridor[1].enter_time = corridor[0].enter_time
    corridor[1].exit_time = corridor[0].exit_time

    validation = validate_plan(
        problem,
        assignments,
        current_time=40.0,
        resource_states=states,
        resource_reservations=reservations,
    )
    assert validation["counts"]["pickup_delivery_violation_count"] > 0
    assert validation["counts"]["energy_trace_violation_count"] > 0
    assert validation["counts"]["resource_conflict_count"] > 0
    assert validation["counts"]["is_valid"] is False

    bad_arcs = deepcopy(result.diagnostics["selected_arcs"])
    robot_id = next(item.robot for item in result.assignments if item.task == f"pickup:{event_id}")
    robot_tasks = [item.task for item in result.assignments if item.robot == robot_id]
    bad_arcs = [item for item in bad_arcs if item["robot"] != robot_id]
    bad_arcs.extend(
        [
            {"robot": robot_id, "from": f"__start__:{robot_id}", "to": robot_tasks[0]},
            {"robot": robot_id, "from": robot_tasks[0], "to": f"__end__:{robot_id}"},
            {"robot": robot_id, "from": robot_tasks[1], "to": robot_tasks[1]},
        ]
    )
    arc_validation = validate_plan(
        problem,
        result.assignments,
        current_time=40.0,
        resource_states=states,
        resource_reservations=result.resource_reservations,
        selected_arcs=bad_arcs,
    )
    assert arc_validation["counts"]["arc_structure_violation_count"] > 0


def test_temporary_and_blocked_route_states_are_structured() -> None:
    world = WorldState(
        load_problem_from_yaml(PROJECT_ROOT / "configs/planner_graduation_v2.yaml")
    )
    world.ingest_perception("confirmed", current_time=30.0, location_id="B", track_id=1)
    problem = world.planning_problem()

    temporary = initial_resource_states(problem)
    temporary["corridor_H"].state = "temporary_occupied"
    temporary["corridor_H"].available_from = 80.0
    temporary["corridor_H"].wait_time = 50.0
    delayed = solve_milp(problem, current_time=30.0, resource_states=temporary)
    assert delayed.solver_status == SolverStatus.OPTIMAL.value
    assert delayed.objective_components["resource_wait"] > 0
    assert all(
        reservation.enter_time >= 80.0
        for reservation in delayed.resource_reservations
        if reservation.resource_id == "corridor_H"
    )

    outside_horizon = initial_resource_states(problem)
    outside_horizon["event_zone_B"].state = "temporary_occupied"
    outside_horizon["event_zone_B"].available_from = 400.0
    outside_horizon["event_zone_B"].wait_time = 370.0
    waiting = solve_milp(problem, current_time=30.0, resource_states=outside_horizon)
    assert waiting.solver_status == SolverStatus.WAITING_FOR_RESOURCE.value
    assert waiting.diagnostics["earliest_retry_time"] == 400.0

    blocked = initial_resource_states(problem)
    blocked["corridor_H"].state = "blocked"
    infeasible = solve_milp(problem, current_time=30.0, resource_states=blocked)
    assert infeasible.solver_status == SolverStatus.INFEASIBLE_ROUTE_BLOCKED.value
    assert infeasible.diagnostics["blocking_resources"] == ["corridor_H"]
