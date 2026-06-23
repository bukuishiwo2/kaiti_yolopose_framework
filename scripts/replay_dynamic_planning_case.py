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

from kaiti_planning.models import load_problem_from_yaml
from kaiti_planning.replanner import (
    build_resource_events_from_spatial_replay,
    run_dynamic_replanning,
)
from kaiti_planning.spatial_state import load_region_specs, load_spatial_replay_config


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay the frozen dynamic planning case.")
    parser.add_argument("--config", required=True)
    parser.add_argument("--backend", default="pulp")
    parser.add_argument("--regions", default="")
    parser.add_argument("--spatial-replay", default="")
    args = parser.parse_args()

    problem = load_problem_from_yaml(Path(args.config))
    resource_events = None
    spatial_snapshots = None
    if args.regions and args.spatial_replay:
        region_specs = load_region_specs(Path(args.regions))
        replay_cfg = load_spatial_replay_config(Path(args.spatial_replay))
        resource_events, spatial_snapshots = build_resource_events_from_spatial_replay(
            problem,
            replay_cfg=replay_cfg,
            region_specs=region_specs,
        )
    result = run_dynamic_replanning(
        problem,
        backend=args.backend,
        resource_events=resource_events,
        spatial_snapshots_by_time=spatial_snapshots,
    )
    print(json.dumps(result, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
