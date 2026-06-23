from __future__ import annotations

from pathlib import Path

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, LogInfo
from launch.substitutions import EnvironmentVariable, LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


REPO_ROOT = str(Path(__file__).resolve().parents[4])


def generate_launch_description() -> LaunchDescription:
    planning_config = PathJoinSubstitution(
        [FindPackageShare("yolopose_ros"), "config", "planning_stack.yaml"]
    )

    return LaunchDescription(
        [
            DeclareLaunchArgument(
                "project_root",
                default_value=EnvironmentVariable("KAITI_PROJECT_ROOT", default_value=REPO_ROOT),
            ),
            DeclareLaunchArgument("planning_config", default_value=planning_config),
            LogInfo(
                msg=[
                    "Planning stack is starting. ",
                    "This launch adds /planning/* topics without replacing the existing placeholder chain.",
                ]
            ),
            Node(
                package="yolopose_ros",
                executable="semantic_state_node",
                name="semantic_state_node",
                output="screen",
                parameters=[
                    LaunchConfiguration("planning_config"),
                    {"project_root": LaunchConfiguration("project_root")},
                ],
            ),
            Node(
                package="yolopose_ros",
                executable="spatial_state_node",
                name="spatial_state_node",
                output="screen",
                parameters=[
                    LaunchConfiguration("planning_config"),
                    {"project_root": LaunchConfiguration("project_root")},
                ],
            ),
            Node(
                package="yolopose_ros",
                executable="milp_planner_node",
                name="milp_planner_node",
                output="screen",
                parameters=[
                    LaunchConfiguration("planning_config"),
                    {"project_root": LaunchConfiguration("project_root")},
                ],
            ),
            Node(
                package="yolopose_ros",
                executable="execution_feedback_bridge_node",
                name="execution_feedback_bridge_node",
                output="screen",
                parameters=[LaunchConfiguration("planning_config")],
            ),
            LogInfo(
                msg=[
                    "Planning topics: /planning/semantic_state, /planning/spatial_state, ",
                    "/planning/plan, /planning/execution_feedback.",
                ]
            ),
        ]
    )
