#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

import rclpy
from geometry_msgs.msg import PoseWithCovarianceStamped
from nav_msgs.msg import Path as NavPath
from rclpy.node import Node
from std_msgs.msg import String


class EvidenceRecorder(Node):
    def __init__(self, output_path: Path) -> None:
        super().__init__("v2_execution_evidence_recorder")
        self.output_path = output_path
        self.rows: list[dict[str, Any]] = []
        for topic in (
            "/planning/plan",
            "/planning/executor_status",
            "/planning/semantic_state",
            "/planning/spatial_state",
        ):
            self.create_subscription(String, topic, self._string_callback(topic), 10)
        self.create_subscription(NavPath, "/plan", self._path_callback, 10)
        self.create_subscription(PoseWithCovarianceStamped, "/amcl_pose", self._pose_callback, 10)

    def _base_row(self, topic: str) -> dict[str, Any]:
        return {
            "received_at_ros": self.get_clock().now().nanoseconds / 1_000_000_000.0,
            "topic": topic,
        }

    def _string_callback(self, topic: str):
        def callback(message: String) -> None:
            try:
                payload: Any = json.loads(message.data)
            except json.JSONDecodeError:
                payload = {"raw": message.data}
            self.rows.append({**self._base_row(topic), "payload": payload})

        return callback

    def _path_callback(self, message: NavPath) -> None:
        poses = message.poses
        self.rows.append(
            {
                **self._base_row("/plan"),
                "payload": {
                    "frame_id": message.header.frame_id,
                    "pose_count": len(poses),
                    "start": (
                        {"x": poses[0].pose.position.x, "y": poses[0].pose.position.y}
                        if poses
                        else None
                    ),
                    "goal": (
                        {"x": poses[-1].pose.position.x, "y": poses[-1].pose.position.y}
                        if poses
                        else None
                    ),
                },
            }
        )

    def _pose_callback(self, message: PoseWithCovarianceStamped) -> None:
        pose = message.pose.pose
        self.rows.append(
            {
                **self._base_row("/amcl_pose"),
                "payload": {
                    "frame_id": message.header.frame_id,
                    "x": pose.position.x,
                    "y": pose.position.y,
                    "qz": pose.orientation.z,
                    "qw": pose.orientation.w,
                },
            }
        )

    def flush(self) -> None:
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        with self.output_path.open("w", encoding="utf-8") as handle:
            for row in self.rows:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Record the v2 MILP/Nav2 visual acceptance trace.")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--duration-sec", type=float, default=240.0)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    rclpy.init()
    node = EvidenceRecorder(args.output)
    deadline = time.monotonic() + max(1.0, args.duration_sec)
    try:
        while rclpy.ok() and time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=0.2)
    except KeyboardInterrupt:
        pass
    finally:
        node.flush()
        print(json.dumps({"output": str(args.output), "rows": len(node.rows)}, ensure_ascii=False))
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
