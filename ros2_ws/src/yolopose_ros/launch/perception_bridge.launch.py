from __future__ import annotations

from pathlib import Path

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import EnvironmentVariable, LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


REPO_ROOT = str(Path(__file__).resolve().parents[4])


def generate_launch_description() -> LaunchDescription:
    perception_config = PathJoinSubstitution(
        [FindPackageShare("yolopose_ros"), "config", "perception_bridge.yaml"]
    )

    return LaunchDescription(
        [
            DeclareLaunchArgument(
                "project_root",
                default_value=EnvironmentVariable("KAITI_PROJECT_ROOT", default_value=REPO_ROOT),
            ),
            DeclareLaunchArgument("bridge_config", default_value=perception_config),
            DeclareLaunchArgument("input_mode", default_value="mock"),
            DeclareLaunchArgument("video_file_path", default_value=""),
            DeclareLaunchArgument("camera_device", default_value=""),
            DeclareLaunchArgument("camera_index", default_value="-1"),
            DeclareLaunchArgument("ros_image_topic", default_value="/camera/image_raw"),
            DeclareLaunchArgument("visualization_enabled", default_value="false"),
            DeclareLaunchArgument("visualization_topic", default_value="/perception/debug_image"),
            DeclareLaunchArgument("supervisor_status_topic", default_value="/system/supervisor/status"),
            Node(
                package="yolopose_ros",
                executable="pose_stream_node",
                name="pose_stream_node",
                output="screen",
                parameters=[
                    LaunchConfiguration("bridge_config"),
                    {
                        "project_root": LaunchConfiguration("project_root"),
                        "input_mode": LaunchConfiguration("input_mode"),
                        "video_file_path": LaunchConfiguration("video_file_path"),
                        "camera_device": LaunchConfiguration("camera_device"),
                        "camera_index": LaunchConfiguration("camera_index"),
                        "ros_image_topic": LaunchConfiguration("ros_image_topic"),
                        "visualization_enabled": LaunchConfiguration("visualization_enabled"),
                        "visualization_topic": LaunchConfiguration("visualization_topic"),
                        "supervisor_status_topic": LaunchConfiguration("supervisor_status_topic"),
                    },
                ],
            ),
        ]
    )
