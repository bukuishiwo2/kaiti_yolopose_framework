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
    assert house["regions"] == legacy["regions"]
    assert house["regions"] != replay["regions"]


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
