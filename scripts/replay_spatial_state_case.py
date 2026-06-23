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
from kaiti_planning.spatial_state import (
    SpatialStateEstimator,
    build_grid_from_replay_frame,
    load_region_specs,
    load_spatial_replay_config,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay occupancy-grid-derived spatial states.")
    parser.add_argument("--config", required=True)
    parser.add_argument("--regions", default="configs/planner_regions.yaml")
    parser.add_argument("--replay", default="configs/planner_spatial_replay.yaml")
    args = parser.parse_args()

    problem = load_problem_from_yaml(Path(args.config))
    region_specs = load_region_specs(Path(args.regions))
    replay_cfg = load_spatial_replay_config(Path(args.replay))
    estimator = SpatialStateEstimator(problem, region_specs=region_specs)

    timeline = []
    for frame in replay_cfg.frames:
        grid = build_grid_from_replay_frame(replay_cfg, frame)
        snapshot = estimator.update_from_occupancy_grid(
            grid_data=grid,
            width=replay_cfg.width,
            height=replay_cfg.height,
            resolution=replay_cfg.resolution,
            origin_x=replay_cfg.origin_x,
            origin_y=replay_cfg.origin_y,
            current_time=frame.time,
            source="replay_grid",
        )
        timeline.append(
            {
                "time": frame.time,
                "notes": frame.notes,
                "snapshot": snapshot.to_dict(),
            }
        )

    print(json.dumps({"timeline": timeline}, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
