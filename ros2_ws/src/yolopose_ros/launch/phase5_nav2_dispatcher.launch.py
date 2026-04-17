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
    phase4b_launch = PathJoinSubstitution(
        [FindPackageShare("yolopose_ros"), "launch", "phase4b_nav2_precheck.launch.py"]
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
            DeclareLaunchArgument("launch_phase4b", default_value="true"),
            DeclareLaunchArgument("dispatcher_config", default_value=dispatcher_config),
            DeclareLaunchArgument("dispatch_enabled", default_value="false"),
            DeclareLaunchArgument("allowed_actions", default_value=""),
            DeclareLaunchArgument("use_sim_time", default_value="true"),
            LogInfo(
                msg=[
                    "Phase 5 controlled Nav2 dispatcher is starting. ",
                    "Default dispatch_enabled=false, so /task_planner/request is observed ",
                    "but not routed to /navigate_to_pose unless explicitly enabled.",
                ]
            ),
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource(phase4b_launch),
                condition=IfCondition(LaunchConfiguration("launch_phase4b")),
                launch_arguments={
                    "project_root": LaunchConfiguration("project_root"),
                    "use_sim_time": LaunchConfiguration("use_sim_time"),
                }.items(),
            ),
            Node(
                package="yolopose_ros",
                executable="planner_nav2_dispatcher_node",
                name="planner_nav2_dispatcher_node",
                output="screen",
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
                    "Phase 5 boundary: task_planner_bridge_node remains a placeholder. ",
                    "Only planner_nav2_dispatcher_node may call /navigate_to_pose, ",
                    "and only after explicit dispatch gate and action whitelist checks.",
                ]
            ),
        ]
    )
