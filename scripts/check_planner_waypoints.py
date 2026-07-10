#!/usr/bin/env python3
"""Check planner waypoints against an occupancy-grid map extent.

This is a lightweight offline guard for the ROS2 MILP-to-Nav2 demo. It verifies
that semantic waypoints such as A/B/C/D/S are inside the map bounds before Nav2
receives them as NavigateToPose goals.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import yaml


def _load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{path} does not contain a YAML mapping")
    return data


def _bounds(args: argparse.Namespace) -> tuple[float, float, float, float]:
    x_min = float(args.origin_x)
    y_min = float(args.origin_y)
    x_max = x_min + float(args.width) * float(args.resolution)
    y_max = y_min + float(args.height) * float(args.resolution)
    return x_min, x_max, y_min, y_max


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--waypoints", default="configs/planner_waypoints.yaml")
    parser.add_argument("--origin-x", type=float, required=True)
    parser.add_argument("--origin-y", type=float, required=True)
    parser.add_argument("--width", type=int, required=True)
    parser.add_argument("--height", type=int, required=True)
    parser.add_argument("--resolution", type=float, required=True)
    parser.add_argument(
        "--margin",
        type=float,
        default=0.10,
        help="Minimum distance in meters from the map border.",
    )
    args = parser.parse_args()

    root = Path.cwd()
    waypoint_path = Path(args.waypoints)
    if not waypoint_path.is_absolute():
        waypoint_path = root / waypoint_path

    data = _load_yaml(waypoint_path)
    waypoints = data.get("waypoints") or {}
    if not isinstance(waypoints, dict):
        raise ValueError("waypoints must be a mapping")

    x_min, x_max, y_min, y_max = _bounds(args)
    safe_x_min = x_min + args.margin
    safe_x_max = x_max - args.margin
    safe_y_min = y_min + args.margin
    safe_y_max = y_max - args.margin

    print(
        "map_bounds: "
        f"x=[{x_min:.3f}, {x_max:.3f}] y=[{y_min:.3f}, {y_max:.3f}] "
        f"safe_margin={args.margin:.2f}"
    )
    print("waypoint\tinside\tinside_margin\tx\ty")

    failures = 0
    for waypoint_id, payload in sorted(waypoints.items()):
        if not isinstance(payload, dict):
            failures += 1
            print(f"{waypoint_id}\tFalse\tFalse\t<invalid>\t<invalid>")
            continue
        x = float(payload["x"])
        y = float(payload["y"])
        inside = x_min <= x <= x_max and y_min <= y <= y_max
        inside_margin = safe_x_min <= x <= safe_x_max and safe_y_min <= y <= safe_y_max
        if not inside or not inside_margin:
            failures += 1
        print(f"{waypoint_id}\t{inside}\t{inside_margin}\t{x:.3f}\t{y:.3f}")

    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
