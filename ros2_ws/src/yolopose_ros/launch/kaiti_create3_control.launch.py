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
                "activation_settle_sec": switch_timeout,
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
            ensure_controllers_ready,
        ]
    )
