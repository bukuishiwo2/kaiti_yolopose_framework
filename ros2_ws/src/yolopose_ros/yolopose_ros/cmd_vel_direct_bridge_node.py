"""Direct /cmd_vel relay for manual driving in the house simulation.

主要功能:
- 监听标准 ROS `/cmd_vel`。
- 直接转发到 `/diffdrive_controller/cmd_vel_unstamped`。
- 当 Create3 motion_control 链存在安全拦截或 topic 路由不稳定时，提供手动控制兜底。

适用阶段:
- Gazebo 键盘控制验证。
- Nav2 接入前的手动底盘联调。

不负责:
- 不做速度规划。
- 不替代 Nav2 或 planner dispatcher。
"""

from __future__ import annotations

import sys

import rclpy
from geometry_msgs.msg import Twist
from rcl_interfaces.msg import ParameterDescriptor
from rclpy.node import Node


class CmdVelDirectBridgeNode(Node):
    """Relay /cmd_vel to ros2_control diff-drive for sim manual driving."""

    def __init__(self) -> None:
        super().__init__("cmd_vel_direct_bridge_node")

        dynamic_string = ParameterDescriptor(dynamic_typing=True)
        self.declare_parameter("input_topic", "/cmd_vel", dynamic_string)
        self.declare_parameter(
            "output_topic",
            "/diffdrive_controller/cmd_vel_unstamped",
            dynamic_string,
        )

        input_topic = str(self.get_parameter("input_topic").value).strip() or "/cmd_vel"
        output_topic = (
            str(self.get_parameter("output_topic").value).strip()
            or "/diffdrive_controller/cmd_vel_unstamped"
        )

        self._publisher = self.create_publisher(Twist, output_topic, 10)
        self._subscription = self.create_subscription(
            Twist,
            input_topic,
            self._handle_cmd_vel,
            10,
        )

        self.get_logger().info(
            "Relaying manual velocity commands from %s to %s"
            % (input_topic, output_topic)
        )

    def _handle_cmd_vel(self, message: Twist) -> None:
        self._publisher.publish(message)


def main() -> None:
    rclpy.init(args=sys.argv)
    node = CmdVelDirectBridgeNode()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
