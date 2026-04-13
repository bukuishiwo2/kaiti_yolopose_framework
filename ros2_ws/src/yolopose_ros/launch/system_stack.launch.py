from __future__ import annotations

from pathlib import Path

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, LogInfo
from launch.conditions import IfCondition
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
            DeclareLaunchArgument("camera_stream_enabled", default_value="false"),
            DeclareLaunchArgument("camera_image_topic", default_value="/camera/image_raw"),
            DeclareLaunchArgument("camera_width", default_value="640"),
            DeclareLaunchArgument("camera_height", default_value="480"),
            DeclareLaunchArgument("camera_fps", default_value="10.0"),
            DeclareLaunchArgument("camera_frame_id", default_value="kaiti_camera_optical_frame"),
            DeclareLaunchArgument("visualization_enabled", default_value="false"),
            DeclareLaunchArgument("visualization_topic", default_value="/perception/debug_image"),
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
                        "ros_image_topic": LaunchConfiguration("camera_image_topic"),
                        "visualization_enabled": LaunchConfiguration("visualization_enabled"),
                        "visualization_topic": LaunchConfiguration("visualization_topic"),
                        "supervisor_status_topic": "/system/supervisor/status",
                    },
                ],
            ),
            Node(
                package="yolopose_ros",
                executable="camera_stream_node",
                name="camera_stream_node",
                output="screen",
                condition=IfCondition(LaunchConfiguration("camera_stream_enabled")),
                parameters=[
                    LaunchConfiguration("system_config"),
                    {
                        "image_topic": LaunchConfiguration("camera_image_topic"),
                        "camera_device": LaunchConfiguration("camera_device"),
                        "camera_index": LaunchConfiguration("camera_index"),
                        "camera_width": LaunchConfiguration("camera_width"),
                        "camera_height": LaunchConfiguration("camera_height"),
                        "camera_fps": LaunchConfiguration("camera_fps"),
                        "camera_frame_id": LaunchConfiguration("camera_frame_id"),
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
            Node(
                package="yolopose_ros",
                executable="task_planner_bridge_node",
                name="task_planner_bridge_node",
                output="screen",
                parameters=[LaunchConfiguration("system_config")],
            ),
            LogInfo(
                msg=[
                    "Planned mapping layer: RTAB-Map -> /map, /rtabmap/localization_pose, /tf.",
                    " Planned navigation layer: Nav2 -> /navigate_to_pose.",
                    " Camera stream option: /camera/image_raw -> pose_stream_node(input_mode=ros_image).",
                    " Visualization option: /perception/debug_image for rqt_image_view.",
                    " Current planner placeholder: /task_planner/request -> /task_planner/status.",
                    " Planned planner layer: PlanSys2/LTL will replace the placeholder consumer.",
                ]
            ),
        ]
    )
