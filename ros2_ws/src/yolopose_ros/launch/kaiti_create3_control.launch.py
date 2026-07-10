"""Minimal ros2_control readiness launch for the simulated Create3/TurtleBot4 base.

主要功能:
- 只启动 controller_ready_node。
- 负责查询 controller_manager，并把 joint_state_broadcaster 与 diffdrive_controller
  推进到 active。
- 是底盘“可控/不可控”最关键的健康检查入口。

适用阶段:
- kaiti_create3_nodes 和 house sim 启动过程中自动调用。

不负责:
- 不生成机器人、不启动 Gazebo、不提供传感器桥接。
"""

from __future__ import annotations

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description() -> LaunchDescription:
    namespace = LaunchConfiguration("namespace")
    controller_manager_timeout = LaunchConfiguration("controller_manager_timeout")
    switch_timeout = LaunchConfiguration("switch_timeout")
    service_call_timeout = LaunchConfiguration("service_call_timeout")
    controller_activation_settle_sec = LaunchConfiguration("controller_activation_settle_sec")

    ensure_controllers_ready = Node(
        package="yolopose_ros",
        executable="controller_ready_node",
        namespace=namespace,
        additional_env={"RCUTILS_LOGGING_BUFFERED_STREAM": "1"},
        parameters=[
            {
                "controller_manager": "controller_manager",
                "controllers": ["joint_state_broadcaster", "diffdrive_controller"],
                "wait_timeout_sec": controller_manager_timeout,
                "command_timeout_sec": service_call_timeout,
                "switch_timeout_sec": switch_timeout,
                "activation_settle_sec": controller_activation_settle_sec,
            }
        ],
        output="screen",
    )

    return LaunchDescription(
        [
            DeclareLaunchArgument("namespace", default_value=""),
            DeclareLaunchArgument("controller_manager_timeout", default_value="60"),
            DeclareLaunchArgument("switch_timeout", default_value="30"),
            DeclareLaunchArgument("service_call_timeout", default_value="30"),
            DeclareLaunchArgument("controller_activation_settle_sec", default_value="2.0"),
            ensure_controllers_ready,
        ]
    )
