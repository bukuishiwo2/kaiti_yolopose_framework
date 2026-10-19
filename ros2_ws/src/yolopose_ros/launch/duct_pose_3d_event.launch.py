from pathlib import Path

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.conditions import IfCondition, UnlessCondition
from launch.substitutions import EnvironmentVariable, LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


REPO_ROOT = str(Path(__file__).resolve().parents[4])


def generate_launch_description() -> LaunchDescription:
    package_share = FindPackageShare("yolopose_ros")
    return LaunchDescription(
        [
            DeclareLaunchArgument(
                "project_root",
                default_value=EnvironmentVariable("KAITI_PROJECT_ROOT", default_value=REPO_ROOT),
            ),
            DeclareLaunchArgument(
                "infer_config", default_value="configs/infer_pose_stream_duct.yaml"
            ),
            DeclareLaunchArgument("rgb_compressed_topic", default_value="/inference/color/image_raw/compressed"),
            DeclareLaunchArgument(
                "depth_compressed_topic",
                default_value="/camera/depth/image_raw/compressedDepth",
            ),
            DeclareLaunchArgument("camera_info_topic", default_value="/camera/color/camera_info"),
            DeclareLaunchArgument("visualization_enabled", default_value="true"),
            DeclareLaunchArgument("rviz", default_value="false"),
            DeclareLaunchArgument("fusion_on_robot", default_value="true"),
            DeclareLaunchArgument("visualization_on_robot", default_value="true"),
            Node(
                package="yolopose_ros",
                executable="pose_stream_node",
                name="pose_stream_node",
                parameters=[
                    PathJoinSubstitution([package_share, "config", "perception_bridge.yaml"]),
                    {
                        "project_root": LaunchConfiguration("project_root"),
                        "infer_config": LaunchConfiguration("infer_config"),
                        "input_mode": "ros_compressed_image",
                        "ros_image_topic": LaunchConfiguration("rgb_compressed_topic"),
                        "visualization_enabled": LaunchConfiguration("visualization_enabled"),
                    },
                ],
                output="screen",
            ),
            Node(
                package="yolopose_ros",
                executable="pose_3d_fusion_node",
                name="pose_3d_fusion_node",
                condition=UnlessCondition(LaunchConfiguration("fusion_on_robot")),
                parameters=[
                    PathJoinSubstitution([package_share, "config", "duct_pose_3d.yaml"]),
                    {
                        "depth_compressed_topic": LaunchConfiguration("depth_compressed_topic"),
                        "use_compressed_depth": True,
                        "camera_info_topic": LaunchConfiguration("camera_info_topic"),
                    },
                ],
                output="screen",
            ),
            Node(
                package="yolopose_ros",
                executable="pose_3d_visualization_node",
                name="pose_3d_visualization_node",
                condition=UnlessCondition(LaunchConfiguration("visualization_on_robot")),
                output="screen",
            ),
            Node(
                package="rviz2",
                executable="rviz2",
                name="duct_pose_3d_rviz",
                arguments=[
                    "-d",
                    PathJoinSubstitution([package_share, "rviz", "duct_pose_3d.rviz"]),
                ],
                condition=IfCondition(LaunchConfiguration("rviz")),
                output="screen",
            ),
        ]
    )
