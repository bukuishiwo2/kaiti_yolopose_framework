from __future__ import annotations

from pathlib import Path
import sys

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
SCRIPTS_ROOT = PROJECT_ROOT / "scripts"
for path in (SRC_ROOT, SCRIPTS_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from kaiti_planning.milp_solver import initial_resource_states, solve_milp
from kaiti_planning.models import SolverStatus, load_problem_from_yaml
from kaiti_planning.spatial_state import (
    RegionBounds,
    RegionSpec,
    SpatialStateEstimator,
    clear_robot_footprint,
    compose_static_dynamic_grid,
)
from kaiti_planning.validator import validate_plan
from run_planning_smoke import run_smoke


def _load_yaml(path: str) -> dict:
    return yaml.safe_load((PROJECT_ROOT / path).read_text(encoding="utf-8"))


def test_house_and_replay_region_profiles_are_explicit() -> None:
    house = _load_yaml("configs/planner_regions_house.yaml")
    replay = _load_yaml("configs/planner_regions_replay.yaml")
    legacy = _load_yaml("configs/planner_regions.yaml")

    assert house["meta"]["profile"] == "house"
    assert replay["meta"]["profile"] == "replay"
    assert {item["id"] for item in house["regions"]} == {item["id"] for item in legacy["regions"]}
    assert house["regions"] != legacy["regions"]
    assert house["regions"] != replay["regions"]


def test_house_regions_cover_service_waypoints_and_the_physical_doorway() -> None:
    regions = {
        item["id"]: item for item in _load_yaml("configs/planner_regions_house.yaml")["regions"]
    }
    waypoints = _load_yaml("configs/planner_waypoints.yaml")["waypoints"]

    def contains(region_id: str, waypoint_id: str) -> bool:
        bounds = regions[region_id]["bounds"]
        point = waypoints[waypoint_id]
        return (
            bounds["x_min"] <= point["x"] <= bounds["x_max"]
            and bounds["y_min"] <= point["y"] <= bounds["y_max"]
        )

    assert contains("event_zone_B", "B")
    assert contains("supply_point_S", "S")
    assert contains("charger_D", "D")
    doorway = regions["corridor_H"]["bounds"]
    assert doorway["x_min"] <= 2.45 <= doorway["x_max"]
    assert doorway["y_min"] <= 2.10 <= doorway["y_max"]
    fall_marker = {"x": 3.45, "y": 3.15}
    event_bounds = regions["event_zone_B"]["bounds"]
    assert event_bounds["x_min"] <= fall_marker["x"] <= event_bounds["x_max"]
    assert event_bounds["y_min"] <= fall_marker["y"] <= event_bounds["y_max"]


def test_low_quantile_width_keeps_a_real_zero_width_bottleneck() -> None:
    problem = load_problem_from_yaml(PROJECT_ROOT / "configs/planner_graduation_v2.yaml")
    estimator = SpatialStateEstimator(problem)
    spec = RegionSpec(
        id="bottleneck",
        kind="corridor",
        resource_id="corridor_H",
        bounds=RegionBounds(0.0, 1.0, 0.0, 1.0),
        width_axis="x",
        width_quantile=0.10,
    )
    cells = [[0, 0, 0, 0] for _ in range(9)] + [[100, 100, 100, 100]]
    assert estimator._min_passage_width(spec, cells, 0.25) == 0.0


def test_static_dynamic_fusion_does_not_treat_static_inflation_as_new_obstacle() -> None:
    fused = compose_static_dynamic_grid(
        static_grid=[0, 100, 0, 0, -1],
        costmap_grid=[80, 100, 90, 0, 100],
        costmap_baseline=[80, 100, 0, 0, 100],
    )
    assert fused == [0, 100, 100, 0, -1]


def test_self_footprint_clear_preserves_static_obstacles() -> None:
    cleared = clear_robot_footprint(
        fused_grid=[100, 100, 100, 0],
        static_grid=[0, 100, 0, 0],
        width=2,
        height=2,
        resolution=1.0,
        origin_x=0.0,
        origin_y=0.0,
        robot_x=0.5,
        robot_y=0.5,
        radius=0.75,
    )
    assert cleared == [0, 100, 100, 0]


def test_persistent_blocked_resource_returns_structured_result() -> None:
    problem = load_problem_from_yaml(PROJECT_ROOT / "configs/planner_minimal_experiment.yaml")
    states = initial_resource_states(problem)
    states["corridor_H"].state = "blocked"

    result = solve_milp(problem, resource_states=states)
    validation = validate_plan(problem, result.assignments, resource_states=states)

    assert result.solver_status == SolverStatus.INFEASIBLE_ROUTE_BLOCKED.value
    assert result.diagnostics["reason_code"] == "ROUTE_BLOCKED_NO_ALTERNATIVE"
    assert result.diagnostics["blocking_resources"] == ["corridor_H"]
    assert validation["counts"]["is_valid"] is False
    assert validation["counts"]["unique_assignment_count"] > 0


def test_frozen_planning_smoke() -> None:
    result = run_smoke()
    assert result["passed"] is True
