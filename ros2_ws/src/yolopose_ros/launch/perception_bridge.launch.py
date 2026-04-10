from __future__ import annotations

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import EnvironmentVariable, LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description() -> LaunchDescription:
    perception_config = PathJoinSubstitution(
        [FindPackageShare("yolopose_ros"), "config", "perception_bridge.yaml"]
    )

    return LaunchDescription(
        [
            DeclareLaunchArgument(
                "project_root",
                default_value=EnvironmentVariable(
                    "KAITI_PROJECT_ROOT", default_value="/home/yhc/kaiti_yolopose_framework"
                ),
            ),
            DeclareLaunchArgument("bridge_config", default_value=perception_config),
            Node(
                package="yolopose_ros",
                executable="pose_stream_node",
                name="pose_stream_node",
                output="screen",
                parameters=[
                    LaunchConfiguration("bridge_config"),
                    {"project_root": LaunchConfiguration("project_root")},
                ],
            ),
        ]
    )
