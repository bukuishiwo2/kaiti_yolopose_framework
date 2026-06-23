#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from kaiti_planning.milp_solver import solve_milp
from kaiti_planning.models import load_problem_from_yaml
from kaiti_planning.validator import validate_plan


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the frozen MILP planner.")
    parser.add_argument("--config", required=True)
    parser.add_argument("--backend", default="pulp")
    args = parser.parse_args()

    problem = load_problem_from_yaml(Path(args.config))
    result = solve_milp(problem, backend=args.backend, plan_kind="static")
    payload = result.to_dict()
    payload["validation"] = validate_plan(problem, result.assignments, current_time=0.0)
    print(json.dumps(payload, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
