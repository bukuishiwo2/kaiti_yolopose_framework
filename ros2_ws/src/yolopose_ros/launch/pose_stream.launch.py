from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import EnvironmentVariable, LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare
from pathlib import Path


REPO_ROOT = str(Path(__file__).resolve().parents[4])


def generate_launch_description() -> LaunchDescription:
    bridge_config = PathJoinSubstitution(
        [FindPackageShare("yolopose_ros"), "config", "perception_bridge.yaml"]
    )

    return LaunchDescription(
        [
            DeclareLaunchArgument(
                "project_root",
                default_value=EnvironmentVariable("KAITI_PROJECT_ROOT", default_value=REPO_ROOT),
            ),
            DeclareLaunchArgument("bridge_config", default_value=bridge_config),
            DeclareLaunchArgument("input_mode", default_value="mock"),
            DeclareLaunchArgument("video_file_path", default_value=""),
            DeclareLaunchArgument("camera_device", default_value=""),
            DeclareLaunchArgument("camera_index", default_value="-1"),
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
        ]
    )
