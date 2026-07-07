from __future__ import annotations

from pathlib import Path

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, LogInfo
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import EnvironmentVariable, LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


REPO_ROOT = str(Path(__file__).resolve().parents[4])


def generate_launch_description() -> LaunchDescription:
    nav2_precheck_launch = PathJoinSubstitution(
        [FindPackageShare("yolopose_ros"), "launch", "kaiti_house_nav2_precheck.launch.py"]
    )
    planning_stack_launch = PathJoinSubstitution(
        [FindPackageShare("yolopose_ros"), "launch", "planning_stack.launch.py"]
    )
    planning_config = PathJoinSubstitution(
        [FindPackageShare("yolopose_ros"), "config", "planning_stack.yaml"]
    )
    dispatcher_config = PathJoinSubstitution(
        [FindPackageShare("yolopose_ros"), "config", "phase5_nav2_dispatcher.yaml"]
    )

    return LaunchDescription(
        [
            DeclareLaunchArgument(
                "project_root",
                default_value=EnvironmentVariable("KAITI_PROJECT_ROOT", default_value=REPO_ROOT),
            ),
            DeclareLaunchArgument("launch_nav2_precheck", default_value="true"),
            DeclareLaunchArgument("launch_planning_stack", default_value="true"),
            DeclareLaunchArgument("launch_dispatcher", default_value="true"),
            DeclareLaunchArgument("dispatcher_config", default_value=dispatcher_config),
            DeclareLaunchArgument("dispatch_enabled", default_value="false"),
            DeclareLaunchArgument("allowed_actions", default_value=""),
            DeclareLaunchArgument("planning_config", default_value=planning_config),
            DeclareLaunchArgument("use_sim_time", default_value="true"),
            DeclareLaunchArgument("autostart", default_value="true"),
            DeclareLaunchArgument("use_composition", default_value="False"),
            DeclareLaunchArgument("use_respawn", default_value="False"),
            DeclareLaunchArgument("namespace", default_value=""),
            DeclareLaunchArgument("log_level", default_value="info"),
            DeclareLaunchArgument("nav2_start_delay", default_value="45.0"),
            DeclareLaunchArgument("turtlebot4_model", default_value="standard"),
            DeclareLaunchArgument("turtlebot4_world", default_value="kaiti_house_world"),
            DeclareLaunchArgument("turtlebot4_rviz", default_value="false"),
            DeclareLaunchArgument("turtlebot4_x", default_value="0.8"),
            DeclareLaunchArgument("turtlebot4_y", default_value="0.8"),
            DeclareLaunchArgument("turtlebot4_z", default_value="0.0"),
            DeclareLaunchArgument("turtlebot4_yaw", default_value="0.0"),
            DeclareLaunchArgument("visualization_enabled", default_value="true"),
            LogInfo(
                msg=[
                    "House planning precheck: custom world + TurtleBot4 + RTAB-Map + Nav2 + ",
                    "/planning/* topics. Dispatcher stays disabled by default.",
                ]
            ),
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource(nav2_precheck_launch),
                condition=IfCondition(LaunchConfiguration("launch_nav2_precheck")),
                launch_arguments={
                    "project_root": LaunchConfiguration("project_root"),
                    "use_sim_time": LaunchConfiguration("use_sim_time"),
                    "autostart": LaunchConfiguration("autostart"),
                    "use_composition": LaunchConfiguration("use_composition"),
                    "use_respawn": LaunchConfiguration("use_respawn"),
                    "namespace": LaunchConfiguration("namespace"),
                    "log_level": LaunchConfiguration("log_level"),
                    "nav2_start_delay": LaunchConfiguration("nav2_start_delay"),
                    "turtlebot4_model": LaunchConfiguration("turtlebot4_model"),
                    "turtlebot4_world": LaunchConfiguration("turtlebot4_world"),
                    "turtlebot4_rviz": LaunchConfiguration("turtlebot4_rviz"),
                    "turtlebot4_x": LaunchConfiguration("turtlebot4_x"),
                    "turtlebot4_y": LaunchConfiguration("turtlebot4_y"),
                    "turtlebot4_z": LaunchConfiguration("turtlebot4_z"),
                    "turtlebot4_yaw": LaunchConfiguration("turtlebot4_yaw"),
                    "visualization_enabled": LaunchConfiguration("visualization_enabled"),
                }.items(),
            ),
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource(planning_stack_launch),
                condition=IfCondition(LaunchConfiguration("launch_planning_stack")),
                launch_arguments={
                    "project_root": LaunchConfiguration("project_root"),
                    "planning_config": LaunchConfiguration("planning_config"),
                }.items(),
            ),
            Node(
                package="yolopose_ros",
                executable="planner_nav2_dispatcher_node",
                name="planner_nav2_dispatcher_node",
                output="screen",
                condition=IfCondition(LaunchConfiguration("launch_dispatcher")),
                parameters=[
                    LaunchConfiguration("dispatcher_config"),
                    {
                        "dispatch_enabled": LaunchConfiguration("dispatch_enabled"),
                        "allowed_actions": LaunchConfiguration("allowed_actions"),
                    },
                ],
            ),
            LogInfo(
                msg=[
                    "Precheck topics: /planning/semantic_state, /planning/spatial_state, /planning/plan, ",
                    "/planning/execution_feedback, /task_planner/request, /navigate_to_pose.",
                ]
            ),
        ]
    )
