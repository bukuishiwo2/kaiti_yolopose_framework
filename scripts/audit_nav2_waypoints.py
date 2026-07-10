#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import rclpy
import yaml
from geometry_msgs.msg import PoseStamped
from nav2_simple_commander.robot_navigator import BasicNavigator


def _pose(navigator: BasicNavigator, waypoint: dict) -> PoseStamped:
    pose = PoseStamped()
    pose.header.frame_id = str(waypoint.get("frame_id", "map"))
    pose.header.stamp = navigator.get_clock().now().to_msg()
    pose.pose.position.x = float(waypoint["x"])
    pose.pose.position.y = float(waypoint["y"])
    pose.pose.position.z = float(waypoint.get("z", 0.0))
    pose.pose.orientation.x = float(waypoint.get("qx", 0.0))
    pose.pose.orientation.y = float(waypoint.get("qy", 0.0))
    pose.pose.orientation.z = float(waypoint.get("qz", 0.0))
    pose.pose.orientation.w = float(waypoint.get("qw", 1.0))
    return pose


def _path_length(path) -> float:
    length = 0.0
    for left, right in zip(path.poses, path.poses[1:]):
        length += math.hypot(
            right.pose.position.x - left.pose.position.x,
            right.pose.position.y - left.pose.position.y,
        )
    return length


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit saved-map waypoint reachability through Nav2 getPath().")
    parser.add_argument("--waypoints", type=Path, default=Path("configs/planner_waypoints.yaml"))
    parser.add_argument("--start", default="A")
    parser.add_argument("--goals", default="B,C,D,S")
    parser.add_argument("--namespace", default="")
    parser.add_argument("--require-all", action="store_true")
    args = parser.parse_args()

    raw = yaml.safe_load(args.waypoints.read_text(encoding="utf-8"))
    waypoints = raw["waypoints"]
    goal_ids = [item.strip() for item in args.goals.split(",") if item.strip()]
    rclpy.init()
    navigator = BasicNavigator(namespace=args.namespace) if args.namespace else BasicNavigator()
    results = []
    try:
        start = _pose(navigator, waypoints[args.start])
        for goal_id in goal_ids:
            path = navigator.getPath(start, _pose(navigator, waypoints[goal_id]), use_start=True)
            results.append(
                {
                    "start": args.start,
                    "goal": goal_id,
                    "path_exists": path is not None,
                    "pose_count": len(path.poses) if path is not None else 0,
                    "path_length": round(_path_length(path), 4) if path is not None else None,
                }
            )
    finally:
        navigator.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()

    output = {"ok": all(item["path_exists"] for item in results), "results": results}
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 1 if args.require_all and not output["ok"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
