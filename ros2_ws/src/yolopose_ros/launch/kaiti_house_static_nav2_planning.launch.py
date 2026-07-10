"""Known-map house launch for Nav2 + MILP planning execution.

主要功能:
- 启动家居 Gazebo / TurtleBot4 仿真，但不启动 RTAB-Map 在线建图。
- 使用已保存的静态地图 `maps/kaiti_house.yaml` 启动 Nav2 map_server、AMCL 和导航服务器。
- 启动 `/planning/*` 栈，用于验证 `MILP -> Nav2 -> execution feedback` 闭环。

适用阶段:
- 毕设已知环境下的任务规划与执行验证。
- 避免 RTAB-Map 在线 `/map` 边界变化导致 waypoint 越界。

不负责:
- 不做未知环境探索建图。
- 不让 PlanSys2 代替 MILP 做全局任务分配。
"""

from __future__ import annotations

from pathlib import Path

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, LogInfo, TimerAction
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import EnvironmentVariable, LaunchConfiguration, PathJoinSubstitution
from launch_ros.substitutions import FindPackageShare


REPO_ROOT = str(Path(__file__).resolve().parents[4])


def generate_launch_description() -> LaunchDescription:
    sim_launch = PathJoinSubstitution(
        [FindPackageShare("yolopose_ros"), "launch", "kaiti_house_turtlebot4_sim.launch.py"]
    )
    nav2_bringup_launch = PathJoinSubstitution(
        [FindPackageShare("nav2_bringup"), "launch", "bringup_launch.py"]
    )
    planning_stack_launch = PathJoinSubstitution(
        [FindPackageShare("yolopose_ros"), "launch", "planning_stack.launch.py"]
    )
    nav2_params = PathJoinSubstitution(
        [FindPackageShare("yolopose_ros"), "config", "phase4b_nav2_precheck.yaml"]
    )
    planning_config = PathJoinSubstitution(
        [FindPackageShare("yolopose_ros"), "config", "planning_stack.yaml"]
    )

    return LaunchDescription(
        [
            DeclareLaunchArgument(
                "project_root",
                default_value=EnvironmentVariable("KAITI_PROJECT_ROOT", default_value=REPO_ROOT),
            ),
            DeclareLaunchArgument("map", default_value=[LaunchConfiguration("project_root"), "/maps/kaiti_house.yaml"]),
            DeclareLaunchArgument("params_file", default_value=nav2_params),
            DeclareLaunchArgument("planning_config", default_value=planning_config),
            DeclareLaunchArgument("use_sim_time", default_value="true"),
            DeclareLaunchArgument("autostart", default_value="true"),
            DeclareLaunchArgument("namespace", default_value=""),
            DeclareLaunchArgument("use_namespace", default_value="false"),
            DeclareLaunchArgument("use_composition", default_value="False"),
            DeclareLaunchArgument("use_respawn", default_value="False"),
            DeclareLaunchArgument("log_level", default_value="info"),
            DeclareLaunchArgument("turtlebot4_model", default_value="standard"),
            DeclareLaunchArgument("turtlebot4_world", default_value="kaiti_house_world"),
            DeclareLaunchArgument("turtlebot4_rviz", default_value="false"),
            DeclareLaunchArgument("turtlebot4_x", default_value="0.8"),
            DeclareLaunchArgument("turtlebot4_y", default_value="0.8"),
            DeclareLaunchArgument("turtlebot4_z", default_value="0.0"),
            DeclareLaunchArgument("turtlebot4_yaw", default_value="0.0"),
            DeclareLaunchArgument("planning_start_delay", default_value="15.0"),
            LogInfo(
                msg=[
                    "Known-map planning launch: TurtleBot4 house sim + Nav2 static map + AMCL + ",
                    "MILP planning stack. Use RViz 2D Pose Estimate once before enabling execution.",
                ]
            ),
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource(sim_launch),
                launch_arguments={
                    "namespace": LaunchConfiguration("namespace"),
                    "use_sim_time": LaunchConfiguration("use_sim_time"),
                    "turtlebot4_model": LaunchConfiguration("turtlebot4_model"),
                    "turtlebot4_world": LaunchConfiguration("turtlebot4_world"),
                    "turtlebot4_rviz": LaunchConfiguration("turtlebot4_rviz"),
                    "turtlebot4_x": LaunchConfiguration("turtlebot4_x"),
                    "turtlebot4_y": LaunchConfiguration("turtlebot4_y"),
                    "turtlebot4_z": LaunchConfiguration("turtlebot4_z"),
                    "turtlebot4_yaw": LaunchConfiguration("turtlebot4_yaw"),
                }.items(),
            ),
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource(nav2_bringup_launch),
                launch_arguments={
                    "namespace": LaunchConfiguration("namespace"),
                    "use_namespace": LaunchConfiguration("use_namespace"),
                    "slam": "False",
                    "map": LaunchConfiguration("map"),
                    "use_sim_time": LaunchConfiguration("use_sim_time"),
                    "params_file": LaunchConfiguration("params_file"),
                    "autostart": LaunchConfiguration("autostart"),
                    "use_composition": LaunchConfiguration("use_composition"),
                    "use_respawn": LaunchConfiguration("use_respawn"),
                    "log_level": LaunchConfiguration("log_level"),
                }.items(),
            ),
            TimerAction(
                period=LaunchConfiguration("planning_start_delay"),
                actions=[
                    IncludeLaunchDescription(
                        PythonLaunchDescriptionSource(planning_stack_launch),
                        launch_arguments={
                            "project_root": LaunchConfiguration("project_root"),
                            "planning_config": LaunchConfiguration("planning_config"),
                        }.items(),
                    )
                ],
            ),
        ]
    )
