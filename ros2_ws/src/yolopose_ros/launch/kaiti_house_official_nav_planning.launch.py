"""Experimental known-map planning launch aligned with TurtleBot4 navigation demos.

主要功能:
- 使用本项目 custom house world 启动 TurtleBot4 仿真底座。
- 按 TurtleBot4 官方方式启动 `turtlebot4_navigation/localization.launch.py`
  和 `turtlebot4_navigation/nav2.launch.py`。
- 仅额外挂载 `/planning/*` 与 MILP executor，不重做 Nav2 / AMCL / controller 底座。

适用阶段:
- 已知地图下验证 `MILP -> NavigateToPose -> feedback`。
- 仅作为静态地图/AMCL 对照实验入口，不作为当前默认联调入口。
- 当前默认可运动联调仍使用 `kaiti_house_planning_precheck.launch.py`
  的 RTAB-Map 在线建图链路。

不负责:
- 不启动 RTAB-Map 在线建图。
- 不替代 TurtleBot4/Nav2 官方 localization、controller、planner 配置。

注意:
- 默认通过 `config/kaiti_house_localization.yaml` 给 AMCL 一个仿真初始位姿。
- 若保存地图坐标系与 Gazebo 初始位姿不一致，仍需在 RViz 使用 `2D Pose Estimate`
  手动校准一次。
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
    localization_launch = PathJoinSubstitution(
        [FindPackageShare("turtlebot4_navigation"), "launch", "localization.launch.py"]
    )
    nav2_launch = PathJoinSubstitution(
        [FindPackageShare("turtlebot4_navigation"), "launch", "nav2.launch.py"]
    )
    planning_stack_launch = PathJoinSubstitution(
        [FindPackageShare("yolopose_ros"), "launch", "planning_stack.launch.py"]
    )
    localization_params = PathJoinSubstitution(
        [FindPackageShare("yolopose_ros"), "config", "kaiti_house_localization.yaml"]
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
            DeclareLaunchArgument("localization_params", default_value=localization_params),
            DeclareLaunchArgument("planning_config", default_value=planning_config),
            DeclareLaunchArgument("namespace", default_value=""),
            DeclareLaunchArgument("use_sim_time", default_value="true"),
            DeclareLaunchArgument("turtlebot4_model", default_value="standard"),
            DeclareLaunchArgument("turtlebot4_world", default_value="kaiti_house_world"),
            DeclareLaunchArgument("turtlebot4_rviz", default_value="false"),
            DeclareLaunchArgument("turtlebot4_x", default_value="0.8"),
            DeclareLaunchArgument("turtlebot4_y", default_value="0.8"),
            DeclareLaunchArgument("turtlebot4_z", default_value="0.0"),
            DeclareLaunchArgument("turtlebot4_yaw", default_value="0.0"),
            DeclareLaunchArgument("localization_start_delay", default_value="12.0"),
            DeclareLaunchArgument("nav2_start_delay", default_value="18.0"),
            DeclareLaunchArgument("planning_start_delay", default_value="24.0"),
            LogInfo(
                msg=[
                    "Experimental official-style known-map launch: sim first, TurtleBot4 localization/Nav2 second, ",
                    "MILP planning stack last. AMCL receives the configured initial pose; ",
                    "use RViz 2D Pose Estimate if the saved map is not aligned.",
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
            TimerAction(
                period=LaunchConfiguration("localization_start_delay"),
                actions=[
                    IncludeLaunchDescription(
                        PythonLaunchDescriptionSource(localization_launch),
                        launch_arguments={
                            "namespace": LaunchConfiguration("namespace"),
                            "use_sim_time": LaunchConfiguration("use_sim_time"),
                            "map": LaunchConfiguration("map"),
                            "params": LaunchConfiguration("localization_params"),
                        }.items(),
                    )
                ],
            ),
            TimerAction(
                period=LaunchConfiguration("nav2_start_delay"),
                actions=[
                    IncludeLaunchDescription(
                        PythonLaunchDescriptionSource(nav2_launch),
                        launch_arguments={
                            "namespace": LaunchConfiguration("namespace"),
                            "use_sim_time": LaunchConfiguration("use_sim_time"),
                        }.items(),
                    )
                ],
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
