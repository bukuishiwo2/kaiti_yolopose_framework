from __future__ import annotations

from pathlib import Path

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, LogInfo
from launch.substitutions import EnvironmentVariable, LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


REPO_ROOT = str(Path(__file__).resolve().parents[4])


def generate_launch_description() -> LaunchDescription:
    perception_config = PathJoinSubstitution(
        [FindPackageShare("yolopose_ros"), "config", "perception_bridge.yaml"]
    )
    system_config = PathJoinSubstitution(
        [FindPackageShare("yolopose_ros"), "config", "system_stack.yaml"]
    )

    return LaunchDescription(
        [
            DeclareLaunchArgument(
                "project_root",
                default_value=EnvironmentVariable("KAITI_PROJECT_ROOT", default_value=REPO_ROOT),
            ),
            DeclareLaunchArgument("bridge_config", default_value=perception_config),
            DeclareLaunchArgument("system_config", default_value=system_config),
            DeclareLaunchArgument("input_mode", default_value="mock"),
            DeclareLaunchArgument("video_file_path", default_value=""),
            DeclareLaunchArgument("camera_device", default_value=""),
            DeclareLaunchArgument("camera_index", default_value="-1"),
            LogInfo(
                msg=[
                    "ROS2 system stack skeleton is starting. ",
                    "RTAB-Map, Nav2, and PlanSys2 are documented as next-stage integrations.",
                ]
            ),
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
                    },
                ],
            ),
            Node(
                package="yolopose_ros",
                executable="system_supervisor_node",
                name="system_supervisor_node",
                output="screen",
                parameters=[LaunchConfiguration("system_config")],
            ),
            LogInfo(
                msg=[
                    "Planned mapping layer: RTAB-Map -> /map, /rtabmap/localization_pose, /tf.",
                    "Planned navigation layer: Nav2 -> /navigate_to_pose.",
                    "Planned planner layer: PlanSys2/LTL -> /kaiti/task_planner/request.",
                ]
            ),
        ]
    )
