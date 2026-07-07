from __future__ import annotations

import sys
import time

import rclpy
from nav_msgs.msg import OccupancyGrid
from nav_msgs.msg import Odometry
from rcl_interfaces.msg import ParameterDescriptor
from rclpy.duration import Duration
from rclpy.node import Node
from rclpy.time import Time
from sensor_msgs.msg import JointState
from tf2_ros import Buffer, TransformListener


class RobotReadyGateNode(Node):
    """Wait until the simulated robot publishes state and TF consistently."""

    def __init__(self) -> None:
        super().__init__("robot_ready_gate_node")

        dynamic_number = ParameterDescriptor(dynamic_typing=True)

        self.declare_parameter("joint_states_topic", "joint_states")
        self.declare_parameter("odom_topic", "odom")
        self.declare_parameter("map_topic", "map")
        self.declare_parameter("base_frame", "base_link")
        self.declare_parameter("odom_frame", "odom")
        self.declare_parameter("global_frame", "map")
        self.declare_parameter("require_global_frame", False)
        self.declare_parameter("wait_timeout_sec", 90.0, dynamic_number)
        self.declare_parameter("poll_period_sec", 0.2, dynamic_number)
        self.declare_parameter("tf_timeout_sec", 0.5, dynamic_number)
        self.declare_parameter("settle_after_ready_sec", 1.5, dynamic_number)

        self._joint_states_topic = str(self.get_parameter("joint_states_topic").value).strip()
        self._odom_topic = str(self.get_parameter("odom_topic").value).strip()
        self._map_topic = str(self.get_parameter("map_topic").value).strip()
        self._base_frame = str(self.get_parameter("base_frame").value).strip() or "base_link"
        self._odom_frame = str(self.get_parameter("odom_frame").value).strip() or "odom"
        self._global_frame = str(self.get_parameter("global_frame").value).strip() or "map"
        self._require_global_frame = bool(self.get_parameter("require_global_frame").value)
        self._wait_timeout_sec = max(1.0, float(self.get_parameter("wait_timeout_sec").value))
        self._poll_period_sec = max(0.05, float(self.get_parameter("poll_period_sec").value))
        self._tf_timeout_sec = max(0.05, float(self.get_parameter("tf_timeout_sec").value))
        self._settle_after_ready_sec = max(
            0.0, float(self.get_parameter("settle_after_ready_sec").value)
        )

        self._joint_state_seen = False
        self._odom_seen = False
        self._map_seen = False
        self._joint_state_stamp = 0.0
        self._odom_stamp = 0.0
        self._map_stamp = 0.0

        self.create_subscription(JointState, self._joint_states_topic, self._on_joint_state, 10)
        self.create_subscription(Odometry, self._odom_topic, self._on_odom, 10)
        self.create_subscription(OccupancyGrid, self._map_topic, self._on_map, 10)
        self._tf_buffer = Buffer()
        self._tf_listener = TransformListener(self._tf_buffer, self, spin_thread=False)

    def _on_joint_state(self, _msg: JointState) -> None:
        self._joint_state_seen = True
        self._joint_state_stamp = time.monotonic()

    def _on_odom(self, _msg: Odometry) -> None:
        self._odom_seen = True
        self._odom_stamp = time.monotonic()

    def _on_map(self, _msg: OccupancyGrid) -> None:
        self._map_seen = True
        self._map_stamp = time.monotonic()

    def _tf_ready(self, target_frame: str, source_frame: str) -> bool:
        try:
            return self._tf_buffer.can_transform(
                target_frame,
                source_frame,
                Time(),
                timeout=Duration(seconds=self._tf_timeout_sec),
            )
        except Exception:  # pragma: no cover - runtime defensive logging
            return False

    def run(self) -> int:
        deadline = time.monotonic() + self._wait_timeout_sec
        self.get_logger().info(
            "Waiting for %s, %s and TF %s -> %s"
            % (
                self._joint_states_topic,
                self._odom_topic,
                self._odom_frame,
                self._base_frame,
            )
        )
        if self._require_global_frame:
            self.get_logger().info(
                "Global readiness also required: %s and TF %s -> %s"
                % (self._map_topic, self._global_frame, self._base_frame)
            )

        while time.monotonic() < deadline:
            rclpy.spin_once(self, timeout_sec=self._poll_period_sec)
            base_ready = (
                self._joint_state_seen
                and self._odom_seen
                and self._tf_ready(self._odom_frame, self._base_frame)
            )
            global_ready = True
            if self._require_global_frame:
                global_ready = self._map_seen and self._tf_ready(
                    self._global_frame, self._base_frame
                )
            if base_ready and global_ready:
                self.get_logger().info(
                    "Robot state ready: joint_states seen, odom seen, TF %s -> %s available%s"
                    % (
                        self._odom_frame,
                        self._base_frame,
                        (
                            ", map seen, TF %s -> %s available"
                            % (self._global_frame, self._base_frame)
                        )
                        if self._require_global_frame
                        else "",
                    )
                )
                if self._settle_after_ready_sec > 0.0:
                    time.sleep(self._settle_after_ready_sec)
                return 0

        self.get_logger().error(
            "Timed out waiting for robot state readiness: joint_states=%s odom=%s base_tf=%s map=%s global_tf=%s"
            % (
                self._joint_state_seen,
                self._odom_seen,
                self._tf_ready(self._odom_frame, self._base_frame),
                self._map_seen,
                self._tf_ready(self._global_frame, self._base_frame),
            )
        )
        return 1


def main() -> None:
    rclpy.init(args=sys.argv)
    node = RobotReadyGateNode()
    try:
        exit_code = node.run()
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
    raise SystemExit(exit_code)
