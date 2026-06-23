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

from kaiti_planning.baselines import (
    nearest_robot_baseline,
    priority_greedy_baseline,
    request_response_baseline,
)
from kaiti_planning.milp_solver import solve_milp
from kaiti_planning.models import load_problem_from_yaml


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate planner baselines.")
    parser.add_argument("--config", required=True)
    parser.add_argument("--backend", default="pulp")
    args = parser.parse_args()

    problem = load_problem_from_yaml(Path(args.config))
    results = {
        "nearest_robot": nearest_robot_baseline(problem).to_dict(),
        "priority_greedy": priority_greedy_baseline(problem).to_dict(),
        "request_response": request_response_baseline(problem).to_dict(),
        "milp": solve_milp(problem, backend=args.backend, plan_kind="static").to_dict(),
    }
    print(json.dumps(results, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
