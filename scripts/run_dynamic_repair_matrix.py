#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from kaiti_planning.dynamic_repair import repair_after_disturbance
from kaiti_planning.milp_solver import initial_resource_states, solve_milp
from kaiti_planning.models import load_problem_from_yaml
from kaiti_planning.world_state import WorldState


def main() -> None:
    world = WorldState(load_problem_from_yaml(REPO_ROOT / "configs/planner_graduation_v2.yaml"))
    event = world.ingest_perception("confirmed", current_time=0.0, location_id="B", track_id=1)
    if event.event_id is None:
        raise RuntimeError("failed to create base event")
    world.record_verification(event.event_id, "fall", current_time=0.0)
    base_problem = world.planning_problem()
    base_states = initial_resource_states(base_problem)
    incumbent = solve_milp(base_problem, resource_states=base_states)
    current_time = 40.0

    temporary = initial_resource_states(base_problem)
    temporary["corridor_H"].state = "temporary_occupied"
    temporary["corridor_H"].available_from = 80.0
    temporary["corridor_H"].wait_time = 40.0
    blocked = initial_resource_states(base_problem)
    blocked["corridor_H"].state = "blocked"
    low_battery = world.planning_problem()
    low_battery.robot_by_id()["R1"].battery = 25.0

    cases = [
        ("temporary_corridor", base_problem, temporary, {"kind": "resource", "resource_id": "corridor_H"}),
        ("persistent_blocked", base_problem, blocked, {"kind": "resource", "resource_id": "corridor_H"}),
        ("low_battery", low_battery, initial_resource_states(low_battery), {"kind": "robot", "robot_id": "R1"}),
        ("navigation_failure", base_problem, base_states, {"kind": "navigation_failure", "task_id": f"deliver:{event.event_id}"}),
    ]
    world.ingest_perception("confirmed", current_time=current_time, location_id="B", track_id=2)
    new_event_problem = world.planning_problem()
    cases.append(
        ("new_semantic_event", new_event_problem, initial_resource_states(new_event_problem), {"kind": "semantic"})
    )

    results = []
    for name, problem, states, disturbance in cases:
        outcome = repair_after_disturbance(
            problem,
            incumbent,
            current_time=current_time,
            resource_states=states,
            disturbance=disturbance,
        )
        results.append(
            {
                "scenario": name,
                "affected_tasks": outcome["affected_tasks"],
                "selected_kind": outcome["selected_kind"],
                "fallback_used": outcome["fallback_used"],
                "solver_status": outcome["selected_plan"]["solver_status"],
                "local_changes": outcome["local_changes"],
                "full_changes": outcome["full_changes"],
                "validation": outcome["validation"],
            }
        )
    print(json.dumps({"current_time": current_time, "results": results}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
