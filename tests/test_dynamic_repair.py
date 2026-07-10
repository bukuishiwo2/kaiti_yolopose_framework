from __future__ import annotations

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from kaiti_planning.dynamic_repair import RevisionPlanningCoordinator, repair_after_disturbance
from kaiti_planning.milp_solver import initial_resource_states, solve_milp
from kaiti_planning.models import SolverStatus, load_problem_from_yaml
from kaiti_planning.world_state import WorldState


def _base_case():
    world = WorldState(load_problem_from_yaml(PROJECT_ROOT / "configs/planner_graduation_v2.yaml"))
    event = world.ingest_perception("confirmed", current_time=0.0, location_id="B", track_id=1)
    assert event.event_id is not None
    world.record_verification(event.event_id, "fall", current_time=0.0)
    problem = world.planning_problem()
    states = initial_resource_states(problem)
    plan = solve_milp(problem, resource_states=states)
    assert plan.solver_status == SolverStatus.OPTIMAL.value
    return world, problem, states, plan


def test_revision_coordinator_discards_stale_solve_result() -> None:
    world = WorldState(load_problem_from_yaml(PROJECT_ROOT / "configs/planner_graduation_v2.yaml"))
    states = initial_resource_states(world.planning_problem())
    coordinator = RevisionPlanningCoordinator(world)
    stale = coordinator.solve_latest(
        resource_states=states,
        before_publish=lambda: world.update_robot_battery("R1", 79.0),
    )
    assert stale["published"] is False
    assert stale["reason"] == "stale_world_revision"
    assert coordinator.pending_trigger is True

    fresh = coordinator.solve_latest(resource_states=states)
    assert fresh["published"] is True
    assert fresh["world_revision"] == world.world_revision
    assert fresh["plan_revision"] == 1


def test_five_disturbance_types_have_affected_sets_and_structured_fallback() -> None:
    world, problem, states, incumbent = _base_case()
    current_time = 40.0
    cases = []

    temporary = initial_resource_states(problem)
    temporary["corridor_H"].state = "temporary_occupied"
    temporary["corridor_H"].available_from = 80.0
    temporary["corridor_H"].wait_time = 40.0
    cases.append((problem, temporary, {"kind": "resource", "resource_id": "corridor_H"}))

    blocked = initial_resource_states(problem)
    blocked["corridor_H"].state = "blocked"
    cases.append((problem, blocked, {"kind": "resource", "resource_id": "corridor_H"}))

    low_battery_problem = world.planning_problem()
    low_battery_problem.robot_by_id()["R1"].battery = 25.0
    cases.append((low_battery_problem, initial_resource_states(low_battery_problem), {"kind": "robot", "robot_id": "R1"}))

    cases.append((problem, states, {"kind": "navigation_failure", "task_id": f"deliver:{next(iter(world.events))}"}))

    world.ingest_perception("confirmed", current_time=40.0, location_id="B", track_id=2)
    new_event_problem = world.planning_problem()
    cases.append((new_event_problem, initial_resource_states(new_event_problem), {"kind": "semantic"}))

    results = [
        repair_after_disturbance(
            case_problem,
            incumbent,
            current_time=current_time,
            resource_states=case_states,
            disturbance=disturbance,
        )
        for case_problem, case_states, disturbance in cases
    ]
    assert all(result["affected_tasks"] for result in results)
    assert results[1]["fallback_used"] is True
    assert results[1]["selected_plan"]["solver_status"] == SolverStatus.INFEASIBLE_ROUTE_BLOCKED.value
    assert any(result["selected_kind"] == "local_repair" for result in results)
