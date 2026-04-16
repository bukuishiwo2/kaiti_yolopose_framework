from __future__ import annotations

from pathlib import Path

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, LogInfo
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import EnvironmentVariable, LaunchConfiguration, PathJoinSubstitution
from launch_ros.substitutions import FindPackageShare


REPO_ROOT = str(Path(__file__).resolve().parents[4])


def generate_launch_description() -> LaunchDescription:
    system_stack_launch = PathJoinSubstitution(
        [FindPackageShare("yolopose_ros"), "launch", "system_stack.launch.py"]
    )
    turtlebot4_launch = PathJoinSubstitution(
        [
            FindPackageShare(LaunchConfiguration("simulator_launch_package")),
            "launch",
            LaunchConfiguration("simulator_launch_file"),
        ]
    )
    rtabmap_launch = PathJoinSubstitution(
        [FindPackageShare("rtabmap_launch"), "launch", "rtabmap.launch.py"]
    )

    return LaunchDescription(
        [
            DeclareLaunchArgument(
                "project_root",
                default_value=EnvironmentVariable("KAITI_PROJECT_ROOT", default_value=REPO_ROOT),
            ),
            DeclareLaunchArgument("launch_turtlebot4", default_value="true"),
            DeclareLaunchArgument("launch_system_stack", default_value="true"),
            DeclareLaunchArgument("launch_rtabmap", default_value="true"),
            DeclareLaunchArgument("simulator_launch_package", default_value="turtlebot4_ignition_bringup"),
            DeclareLaunchArgument("simulator_launch_file", default_value="turtlebot4_ignition.launch.py"),
            DeclareLaunchArgument("turtlebot4_model", default_value="standard"),
            DeclareLaunchArgument("turtlebot4_world", default_value="warehouse"),
            DeclareLaunchArgument("turtlebot4_slam", default_value="false"),
            DeclareLaunchArgument("turtlebot4_nav2", default_value="false"),
            DeclareLaunchArgument("turtlebot4_rviz", default_value="false"),
            DeclareLaunchArgument("rgb_topic", default_value="/oakd/rgb/preview/image_raw"),
            DeclareLaunchArgument("depth_topic", default_value="/oakd/rgb/preview/depth"),
            DeclareLaunchArgument("camera_info_topic", default_value="/oakd/rgb/preview/camera_info"),
            DeclareLaunchArgument("scan_topic", default_value="/scan"),
            DeclareLaunchArgument("odom_topic", default_value="/odom"),
            DeclareLaunchArgument("base_frame_id", default_value="base_link"),
            DeclareLaunchArgument("use_sim_time", default_value="true"),
            DeclareLaunchArgument("approx_sync", default_value="true"),
            DeclareLaunchArgument("subscribe_scan", default_value="true"),
            DeclareLaunchArgument("visual_odometry", default_value="false"),
            DeclareLaunchArgument("publish_tf_odom", default_value="false"),
            DeclareLaunchArgument("rtabmap_args", default_value="--delete_db_on_start"),
            DeclareLaunchArgument("rtabmap_rviz", default_value="false"),
            DeclareLaunchArgument("visualization_enabled", default_value="true"),
            LogInfo(
                msg=[
                    "Phase 4a stack: TurtleBot4 simulator + yolopose_ros ros_image input + ",
                    "RTAB-Map sidecar mapping. Nav2 and PlanSys2/LTL remain disabled.",
                ]
            ),
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource(turtlebot4_launch),
                condition=IfCondition(LaunchConfiguration("launch_turtlebot4")),
                launch_arguments={
                    "model": LaunchConfiguration("turtlebot4_model"),
                    "world": LaunchConfiguration("turtlebot4_world"),
                    "slam": LaunchConfiguration("turtlebot4_slam"),
                    "nav2": LaunchConfiguration("turtlebot4_nav2"),
                    "rviz": LaunchConfiguration("turtlebot4_rviz"),
                }.items(),
            ),
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource(system_stack_launch),
                condition=IfCondition(LaunchConfiguration("launch_system_stack")),
                launch_arguments={
                    "project_root": LaunchConfiguration("project_root"),
                    "input_mode": "ros_image",
                    "camera_stream_enabled": "false",
                    "camera_image_topic": LaunchConfiguration("rgb_topic"),
                    "visualization_enabled": LaunchConfiguration("visualization_enabled"),
                }.items(),
            ),
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource(rtabmap_launch),
                condition=IfCondition(LaunchConfiguration("launch_rtabmap")),
                launch_arguments={
                    "use_sim_time": LaunchConfiguration("use_sim_time"),
                    "rtabmap_args": LaunchConfiguration("rtabmap_args"),
                    "rgb_topic": LaunchConfiguration("rgb_topic"),
                    "depth_topic": LaunchConfiguration("depth_topic"),
                    "camera_info_topic": LaunchConfiguration("camera_info_topic"),
                    "frame_id": LaunchConfiguration("base_frame_id"),
                    "odom_topic": LaunchConfiguration("odom_topic"),
                    "approx_sync": LaunchConfiguration("approx_sync"),
                    "subscribe_scan": LaunchConfiguration("subscribe_scan"),
                    "scan_topic": LaunchConfiguration("scan_topic"),
                    "visual_odometry": LaunchConfiguration("visual_odometry"),
                    "publish_tf_odom": LaunchConfiguration("publish_tf_odom"),
                    "rviz": LaunchConfiguration("rtabmap_rviz"),
                }.items(),
            ),
            LogInfo(
                msg=[
                    "Phase 4a expected inputs: rgb=",
                    LaunchConfiguration("rgb_topic"),
                    " depth=",
                    LaunchConfiguration("depth_topic"),
                    " camera_info=",
                    LaunchConfiguration("camera_info_topic"),
                    " odom=",
                    LaunchConfiguration("odom_topic"),
                    " scan=",
                    LaunchConfiguration("scan_topic"),
                    ". Expected outputs: /map, /localization_pose, /tf.",
                ]
            ),
        ]
    )
