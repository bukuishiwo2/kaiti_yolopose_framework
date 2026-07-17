#!/usr/bin/env python3
"""Drive a conservative coverage route while RTAB-Map is building the house map.

This helper is deliberately not an exploration algorithm.  It follows an audited
route through the fixed graduation-test world, stops when the laser reports an
unexpected obstacle, and performs an in-place scan at selected coverage points.
"""

from __future__ import annotations

import argparse
import json
import math
import time
from pathlib import Path

import rclpy
import yaml
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import LaserScan


def _wrap(angle: float) -> float:
    return math.atan2(math.sin(angle), math.cos(angle))


def _yaw(msg: Odometry) -> float:
    q = msg.pose.pose.orientation
    return math.atan2(2.0 * (q.w * q.z + q.x * q.y), 1.0 - 2.0 * (q.y**2 + q.z**2))


class MappingRouteDriver(Node):
    def __init__(
        self,
        *,
        cmd_topic: str,
        pose_topic: str,
        scan_topic: str,
        heading_offset: float,
    ) -> None:
        super().__init__("house_mapping_route_driver")
        self.cmd_pub = self.create_publisher(Twist, cmd_topic, 10)
        self.create_subscription(Odometry, pose_topic, self._on_odom, qos_profile_sensor_data)
        self.create_subscription(LaserScan, scan_topic, self._on_scan, qos_profile_sensor_data)
        self.odom: Odometry | None = None
        self.front_clearance = math.inf
        self.heading_offset = heading_offset

    def _on_odom(self, msg: Odometry) -> None:
        self.odom = msg

    def _on_scan(self, msg: LaserScan) -> None:
        values = []
        for index, distance in enumerate(msg.ranges):
            angle = msg.angle_min + index * msg.angle_increment
            # This is a forward stop gate, not a footprint/costmap substitute.
            # A wider cone incorrectly treats the audited B aisle's side wall
            # as a head-on obstacle while the Create3 reflex layer still guards
            # bumper and side hazards.
            if abs(_wrap(angle)) <= math.radians(8.0) and math.isfinite(distance):
                if msg.range_min <= distance <= msg.range_max:
                    values.append(float(distance))
        # A simulated scan can occasionally contain one near-range speckle.
        # Use the lower quartile of the whole front sector so a contiguous
        # obstacle still stops the robot, while edge returns and small groups
        # of simulated near-range speckles cannot abort the route.
        values.sort()
        percentile_index = max(0, int(0.25 * (len(values) - 1)))
        self.front_clearance = values[percentile_index] if values else math.inf

    def stop(self) -> None:
        self.cmd_pub.publish(Twist())

    def wait_until_ready(self, timeout: float = 20.0) -> None:
        deadline = time.monotonic() + timeout
        while rclpy.ok() and time.monotonic() < deadline:
            rclpy.spin_once(self, timeout_sec=0.1)
            if self.odom is not None and math.isfinite(self.front_clearance):
                return
        raise RuntimeError("Timed out waiting for the pose topic and /scan")

    def drive_to(
        self,
        x: float,
        y: float,
        *,
        timeout: float,
        obstacle_stop: float,
        position_tolerance: float,
    ) -> dict:
        started = time.monotonic()
        while rclpy.ok() and time.monotonic() - started < timeout:
            rclpy.spin_once(self, timeout_sec=0.05)
            assert self.odom is not None
            pose = self.odom.pose.pose.position
            dx, dy = x - pose.x, y - pose.y
            distance = math.hypot(dx, dy)
            if distance <= position_tolerance:
                self.stop()
                return {
                    "x": float(pose.x),
                    "y": float(pose.y),
                    "position_error": distance,
                    "front_clearance": self.front_clearance,
                }

            base_heading = _wrap(_yaw(self.odom) + self.heading_offset)
            heading_error = _wrap(math.atan2(dy, dx) - base_heading)
            command = Twist()
            if abs(heading_error) > 0.22:
                command.angular.z = max(-0.55, min(0.55, 1.35 * heading_error))
            else:
                if self.front_clearance < obstacle_stop:
                    self.stop()
                    raise RuntimeError(
                        f"Unexpected obstacle {self.front_clearance:.3f} m ahead while driving "
                        f"to ({x:.2f}, {y:.2f})"
                    )
                command.linear.x = min(0.28, max(0.08, 0.55 * distance))
                command.angular.z = max(-0.35, min(0.35, 1.1 * heading_error))
            self.cmd_pub.publish(command)
        self.stop()
        raise RuntimeError(f"Timed out driving to ({x:.2f}, {y:.2f})")

    def scan_in_place(self, *, angular_speed: float = 0.42, timeout: float = 24.0) -> None:
        assert self.odom is not None
        previous_yaw = _yaw(self.odom)
        accumulated = 0.0
        started = time.monotonic()
        while rclpy.ok() and accumulated < 2.0 * math.pi and time.monotonic() - started < timeout:
            rclpy.spin_once(self, timeout_sec=0.05)
            assert self.odom is not None
            current_yaw = _yaw(self.odom)
            accumulated += abs(_wrap(current_yaw - previous_yaw))
            previous_yaw = current_yaw
            command = Twist()
            command.angular.z = angular_speed
            self.cmd_pub.publish(command)
        self.stop()
        if accumulated < 2.0 * math.pi:
            raise RuntimeError("Timed out during in-place mapping scan")
        # Allow RTAB-Map's 1 Hz detector to consume the final view.
        deadline = time.monotonic() + 1.2
        while rclpy.ok() and time.monotonic() < deadline:
            rclpy.spin_once(self, timeout_sec=0.1)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--route", type=Path, default=Path("configs/house_mapping_route.yaml"))
    parser.add_argument("--cmd-topic", default="/cmd_vel")
    parser.add_argument(
        "--pose-topic",
        default="/sim_ground_truth_pose",
        help="Odometry-shaped pose source; house simulation defaults to Gazebo ground truth.",
    )
    parser.add_argument(
        "--relative-pose",
        action="store_true",
        help="Treat the pose origin as the configured spawn instead of world coordinates.",
    )
    parser.add_argument(
        "--heading-offset",
        type=float,
        default=0.0,
        help="Yaw offset from the pose model frame to the base forward axis.",
    )
    parser.add_argument("--scan-topic", default="/scan")
    parser.add_argument("--trace", type=Path)
    parser.add_argument(
        "--start-at",
        help="Resume at this waypoint ID without revisiting the completed prefix.",
    )
    parser.add_argument("--segment-timeout", type=float, default=45.0)
    # TurtleBot4 footprint radius is well below 0.20 m.  A 0.40 m front
    # clearance keeps a conservative margin while permitting the audited B
    # passage, whose side returns enter the 24-degree front sector at ~0.47 m.
    parser.add_argument("--obstacle-stop", type=float, default=0.40)
    parser.add_argument("--position-tolerance", type=float, default=0.12)
    args = parser.parse_args()

    document = yaml.safe_load(args.route.read_text(encoding="utf-8"))
    spawn_x, spawn_y = (float(value) for value in document["meta"]["spawn_xy"])
    route = document["route"]
    if args.start_at:
        matching_indices = [index for index, item in enumerate(route) if item["id"] == args.start_at]
        if not matching_indices:
            raise ValueError(f"Unknown --start-at waypoint: {args.start_at}")
        route = route[matching_indices[0] :]
    trace = {"route": str(args.route), "started_at": time.time(), "visits": [], "status": "running"}

    rclpy.init()
    node = MappingRouteDriver(
        cmd_topic=args.cmd_topic,
        pose_topic=args.pose_topic,
        scan_topic=args.scan_topic,
        heading_offset=args.heading_offset,
    )
    try:
        node.wait_until_ready()
        for waypoint in route:
            target_x = float(waypoint["x"]) - (spawn_x if args.relative_pose else 0.0)
            target_y = float(waypoint["y"]) - (spawn_y if args.relative_pose else 0.0)
            node.get_logger().info(
                f"Mapping route -> {waypoint['id']} world=({waypoint['x']}, {waypoint['y']}) "
                f"odom=({target_x:.2f}, {target_y:.2f})"
            )
            result = node.drive_to(
                target_x,
                target_y,
                timeout=args.segment_timeout,
                obstacle_stop=args.obstacle_stop,
                position_tolerance=args.position_tolerance,
            )
            if bool(waypoint.get("scan", False)):
                node.scan_in_place()
            result.update({"id": waypoint["id"], "scan": bool(waypoint.get("scan", False))})
            trace["visits"].append(result)
        trace["status"] = "completed"
        return_code = 0
    except Exception as exc:  # noqa: BLE001 - CLI must always stop and preserve evidence
        trace["status"] = "failed"
        trace["error"] = str(exc)
        node.get_logger().error(str(exc))
        return_code = 1
    finally:
        node.stop()
        trace["finished_at"] = time.time()
        if args.trace:
            args.trace.parent.mkdir(parents=True, exist_ok=True)
            args.trace.write_text(json.dumps(trace, indent=2), encoding="utf-8")
        node.destroy_node()
        rclpy.shutdown()
    return return_code


if __name__ == "__main__":
    raise SystemExit(main())
