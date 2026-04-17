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
    phase4a_launch = PathJoinSubstitution(
        [FindPackageShare("yolopose_ros"), "launch", "phase4a_turtlebot4_rtabmap.launch.py"]
    )
    nav2_launch = PathJoinSubstitution(
        [FindPackageShare("nav2_bringup"), "launch", "navigation_launch.py"]
    )
    nav2_params = PathJoinSubstitution(
        [FindPackageShare("yolopose_ros"), "config", "phase4b_nav2_precheck.yaml"]
    )

    return LaunchDescription(
        [
            DeclareLaunchArgument(
                "project_root",
                default_value=EnvironmentVariable("KAITI_PROJECT_ROOT", default_value=REPO_ROOT),
            ),
            DeclareLaunchArgument("launch_phase4a", default_value="true"),
            DeclareLaunchArgument("launch_nav2", default_value="true"),
            DeclareLaunchArgument("params_file", default_value=nav2_params),
            DeclareLaunchArgument("use_sim_time", default_value="true"),
            DeclareLaunchArgument("autostart", default_value="true"),
            DeclareLaunchArgument("use_composition", default_value="False"),
            DeclareLaunchArgument("use_respawn", default_value="False"),
            DeclareLaunchArgument("namespace", default_value=""),
            DeclareLaunchArgument("log_level", default_value="info"),
            DeclareLaunchArgument("turtlebot4_model", default_value="standard"),
            DeclareLaunchArgument("turtlebot4_world", default_value="warehouse"),
            DeclareLaunchArgument("turtlebot4_rviz", default_value="false"),
            DeclareLaunchArgument("rgb_topic", default_value="/oakd/rgb/preview/image_raw"),
            DeclareLaunchArgument("depth_topic", default_value="/oakd/rgb/preview/depth"),
            DeclareLaunchArgument("camera_info_topic", default_value="/oakd/rgb/preview/camera_info"),
            DeclareLaunchArgument("scan_topic", default_value="/scan"),
            DeclareLaunchArgument("odom_topic", default_value="/odom"),
            DeclareLaunchArgument("base_frame_id", default_value="base_link"),
            DeclareLaunchArgument("visualization_enabled", default_value="true"),
            LogInfo(
                msg=[
                    "Phase 4b Nav2 precheck: Phase 4a RTAB-Map baseline + Nav2 navigation ",
                    "servers only. PlanSys2/LTL and automatic planner goal dispatch remain disabled.",
                ]
            ),
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource(phase4a_launch),
                condition=IfCondition(LaunchConfiguration("launch_phase4a")),
                launch_arguments={
                    "project_root": LaunchConfiguration("project_root"),
                    "turtlebot4_model": LaunchConfiguration("turtlebot4_model"),
                    "turtlebot4_world": LaunchConfiguration("turtlebot4_world"),
                    "turtlebot4_slam": "false",
                    "turtlebot4_nav2": "false",
                    "turtlebot4_rviz": LaunchConfiguration("turtlebot4_rviz"),
                    "rgb_topic": LaunchConfiguration("rgb_topic"),
                    "depth_topic": LaunchConfiguration("depth_topic"),
                    "camera_info_topic": LaunchConfiguration("camera_info_topic"),
                    "scan_topic": LaunchConfiguration("scan_topic"),
                    "odom_topic": LaunchConfiguration("odom_topic"),
                    "base_frame_id": LaunchConfiguration("base_frame_id"),
                    "use_sim_time": LaunchConfiguration("use_sim_time"),
                    "visual_odometry": "false",
                    "publish_tf_odom": "false",
                    "visualization_enabled": LaunchConfiguration("visualization_enabled"),
                }.items(),
            ),
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource(nav2_launch),
                condition=IfCondition(LaunchConfiguration("launch_nav2")),
                launch_arguments={
                    "namespace": LaunchConfiguration("namespace"),
                    "use_sim_time": LaunchConfiguration("use_sim_time"),
                    "autostart": LaunchConfiguration("autostart"),
                    "params_file": LaunchConfiguration("params_file"),
                    "use_composition": LaunchConfiguration("use_composition"),
                    "use_respawn": LaunchConfiguration("use_respawn"),
                    "log_level": LaunchConfiguration("log_level"),
                }.items(),
            ),
            LogInfo(
                msg=[
                    "Phase 4b manual smoke test only: send goals to /navigate_to_pose by hand. ",
                    "Do not route /task_planner/request into Nav2 in this phase.",
                ]
            ),
        ]
    )
