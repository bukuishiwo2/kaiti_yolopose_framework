#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from kaiti_planning.milp_solver import initial_resource_states, solve_milp
from kaiti_planning.models import load_problem_from_yaml
from kaiti_planning.validator import validate_plan
from kaiti_planning.world_state import WorldState


def main() -> None:
    world = WorldState(load_problem_from_yaml(REPO_ROOT / "configs/planner_graduation_v2.yaml"))
    event = world.ingest_perception(
        "confirmed", current_time=30.0, location_id="B", track_id="demo-person"
    )
    if event.event_id is None:
        raise RuntimeError("failed to create demo event")
    world.record_verification(event.event_id, "fall", current_time=40.0)
    problem = world.planning_problem()
    states = initial_resource_states(problem)
    result = solve_milp(problem, current_time=40.0, resource_states=states)
    payload = result.to_dict()
    payload["event_id"] = event.event_id
    payload["world_revision"] = world.world_revision
    payload["validation"] = validate_plan(
        problem,
        result.assignments,
        current_time=40.0,
        resource_states=states,
        resource_reservations=result.resource_reservations,
        selected_arcs=result.diagnostics.get("selected_arcs"),
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
