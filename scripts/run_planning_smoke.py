#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from kaiti_planning.local_repair import run_local_repair
from kaiti_planning.baselines import (
    nearest_robot_baseline,
    priority_greedy_baseline,
    request_response_baseline,
)
from kaiti_planning.milp_solver import initial_resource_states, solve_milp
from kaiti_planning.models import SolverStatus, load_problem_from_yaml
from kaiti_planning.replanner import (
    build_resource_events_from_spatial_replay,
    run_dynamic_replanning,
)
from kaiti_planning.spatial_state import load_region_specs, load_spatial_replay_config
from kaiti_planning.validator import validate_plan


def run_smoke() -> dict[str, Any]:
    minimal = load_problem_from_yaml(REPO_ROOT / "configs/planner_minimal_experiment.yaml")
    repair_problem = load_problem_from_yaml(
        REPO_ROOT / "configs/planner_local_repair_comparison.yaml"
    )
    regions = load_region_specs(REPO_ROOT / "configs/planner_regions_replay.yaml")
    replay = load_spatial_replay_config(REPO_ROOT / "configs/planner_spatial_replay.yaml")

    static_plan = solve_milp(minimal, plan_kind="smoke_static")
    static_validation = validate_plan(minimal, static_plan.assignments)
    baselines = {
        "nearest_robot": nearest_robot_baseline(minimal),
        "priority_greedy": priority_greedy_baseline(minimal),
        "request_response": request_response_baseline(minimal),
    }

    dynamic_events, dynamic_snapshots = build_resource_events_from_spatial_replay(
        minimal,
        replay_cfg=replay,
        region_specs=regions,
    )
    dynamic = run_dynamic_replanning(
        minimal,
        resource_events=dynamic_events,
        spatial_snapshots_by_time=dynamic_snapshots,
    )

    repair_events, repair_snapshots = build_resource_events_from_spatial_replay(
        repair_problem,
        replay_cfg=replay,
        region_specs=regions,
    )
    repair = run_local_repair(
        repair_problem,
        resource_events=repair_events,
        spatial_snapshots_by_time=repair_snapshots,
    )

    blocked_states = initial_resource_states(minimal)
    blocked_states["corridor_H"].state = "blocked"
    blocked_plan = solve_milp(
        minimal,
        resource_states=blocked_states,
        plan_kind="smoke_blocked",
    )

    dynamic_valid = all(
        item["plan"]["solver_status"] == SolverStatus.OPTIMAL.value
        and bool(item["validation"]["counts"]["is_valid"])
        for item in dynamic["timeline"]
    )
    repair_valid = (
        repair["full_replan"]["solver_status"] == SolverStatus.OPTIMAL.value
        and repair["local_repair"]["solver_status"] == SolverStatus.OPTIMAL.value
        and bool(repair["full_replan_validation"]["counts"]["is_valid"])
        and bool(repair["local_repair_validation"]["counts"]["is_valid"])
    )
    checks = {
        "static_plan": (
            static_plan.solver_status == SolverStatus.OPTIMAL.value
            and bool(static_validation["counts"]["is_valid"])
        ),
        "baselines": all(
            result.solver_status == SolverStatus.FEASIBLE.value
            and bool(validate_plan(minimal, result.assignments)["counts"]["is_valid"])
            for result in baselines.values()
        ),
        "dynamic_replay": dynamic_valid,
        "local_repair": repair_valid,
        "blocked_is_structured": (
            blocked_plan.solver_status == SolverStatus.INFEASIBLE_ROUTE_BLOCKED.value
            and blocked_plan.diagnostics.get("reason_code")
            == "ROUTE_BLOCKED_NO_ALTERNATIVE"
        ),
    }
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "details": {
            "static_status": static_plan.solver_status,
            "dynamic_timeline_count": len(dynamic["timeline"]),
            "local_repair_modified_tasks": repair["local_repair_modified_tasks"],
            "full_replan_modified_tasks": repair["full_replan_modified_tasks"],
            "blocked_status": blocked_plan.solver_status,
            "blocked_resources": blocked_plan.diagnostics.get("blocking_resources", []),
        },
    }


def main() -> None:
    result = run_smoke()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not result["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
