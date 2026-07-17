"""Phase 4a house stack with TurtleBot4 sim, perception bridge, and RTAB-Map sidecar.

主要功能:
- 以上一层 kaiti_house_turtlebot4_sim 为底座启动家居仿真。
- 启动 yolopose_ros 的 system stack，复用 ROS 图像输入链路。
- 延迟拉起 RTAB-Map，验证 RGBD / LiDAR / odom 到 map 的建图链。

适用阶段:
- 研究内容一的空间状态上游数据采集。
- Nav2 接入前的建图与地图话题健康检查。

不负责:
- 不直接启动 Nav2 生命周期。
- 不负责 /planning/* 规划接口联调。
"""

from __future__ import annotations

from pathlib import Path

from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    ExecuteProcess,
    IncludeLaunchDescription,
    LogInfo,
    TimerAction,
)
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import EnvironmentVariable, LaunchConfiguration, PathJoinSubstitution
from launch_ros.substitutions import FindPackageShare
from launch_ros.actions import Node


REPO_ROOT = str(Path(__file__).resolve().parents[4])


def generate_launch_description() -> LaunchDescription:
    custom_sim_launch = PathJoinSubstitution(
        [FindPackageShare("yolopose_ros"), "launch", "kaiti_house_turtlebot4_sim.launch.py"]
    )
    system_stack_launch = PathJoinSubstitution(
        [FindPackageShare("yolopose_ros"), "launch", "system_stack.launch.py"]
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
            DeclareLaunchArgument("namespace", default_value=""),
            DeclareLaunchArgument("turtlebot4_model", default_value="standard"),
            DeclareLaunchArgument("turtlebot4_world", default_value="kaiti_house_world"),
            DeclareLaunchArgument("turtlebot4_rviz", default_value="false"),
            DeclareLaunchArgument("turtlebot4_x", default_value="0.8"),
            DeclareLaunchArgument("turtlebot4_y", default_value="0.8"),
            DeclareLaunchArgument("turtlebot4_z", default_value="0.0"),
            DeclareLaunchArgument("turtlebot4_yaw", default_value="0.0"),
            DeclareLaunchArgument("spawn_dock", default_value="true"),
            DeclareLaunchArgument("rgb_topic", default_value="/oakd/rgb/preview/image_raw"),
            DeclareLaunchArgument("depth_topic", default_value="/oakd/rgb/preview/depth"),
            DeclareLaunchArgument("camera_info_topic", default_value="/oakd/rgb/preview/camera_info"),
            DeclareLaunchArgument("scan_topic", default_value="/scan"),
            DeclareLaunchArgument("odom_topic", default_value="/mapping/ground_truth_odom"),
            DeclareLaunchArgument("ground_truth_odom_topic", default_value="/sim_ground_truth_pose"),
            DeclareLaunchArgument("use_sim_ground_truth_odom", default_value="true"),
            # Subscribe to the configured Odometry topic by default.  This lets
            # simulation mapping use /sim_ground_truth_pose and avoids treating
            # drifting wheel odometry as an immutable TF trajectory.
            DeclareLaunchArgument("odom_frame_id", default_value=""),
            DeclareLaunchArgument("base_frame_id", default_value="base_link"),
            DeclareLaunchArgument("use_sim_time", default_value="true"),
            DeclareLaunchArgument("approx_sync", default_value="true"),
            DeclareLaunchArgument("subscribe_scan", default_value="true"),
            DeclareLaunchArgument("visual_odometry", default_value="false"),
            DeclareLaunchArgument("publish_tf_odom", default_value="false"),
            DeclareLaunchArgument("rtabmap_args", default_value="--delete_db_on_start"),
            DeclareLaunchArgument("rtabmap_viz", default_value="false"),
            DeclareLaunchArgument("rtabmap_rviz", default_value="false"),
            DeclareLaunchArgument("rtabmap_start_delay", default_value="20.0"),
            DeclareLaunchArgument("visualization_enabled", default_value="true"),
            LogInfo(
                msg=[
                    "House Phase 4a stack: custom house + TurtleBot4 + yolopose_ros ros_image + ",
                    "RTAB-Map sidecar mapping. Nav2 and PlanSys2 lifecycle remain outside this launch.",
                ]
            ),
            Node(
                package="yolopose_ros",
                executable="ground_truth_odom_relay_node",
                name="ground_truth_odom_relay",
                output="screen",
                condition=IfCondition(LaunchConfiguration("use_sim_ground_truth_odom")),
                parameters=[
                    {
                        "input_topic": LaunchConfiguration("ground_truth_odom_topic"),
                        "output_topic": LaunchConfiguration("odom_topic"),
                        # Reuse the connected ROS odom frame for sensor TF
                        # lookup; the pose values themselves come from Gazebo.
                        "odom_frame_id": "odom",
                        "base_frame_id": LaunchConfiguration("base_frame_id"),
                        "publish_tf": True,
                    }
                ],
            ),
            TimerAction(
                period=16.0,
                actions=[
                    ExecuteProcess(
                        cmd=[
                            "ros2",
                            "param",
                            "set",
                            "/diffdrive_controller",
                            "enable_odom_tf",
                            "false",
                        ],
                        output="screen",
                    )
                ],
            ),
            LogInfo(
                msg=(
                    "This launch already starts the house simulation. If a house sim is already "
                    "running, relaunch with launch_turtlebot4:=false."
                )
            ),
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource(custom_sim_launch),
                condition=IfCondition(LaunchConfiguration("launch_turtlebot4")),
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
                    "spawn_dock": LaunchConfiguration("spawn_dock"),
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
            TimerAction(
                period=LaunchConfiguration("rtabmap_start_delay"),
                actions=[
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
                            "odom_frame_id": LaunchConfiguration("odom_frame_id"),
                            "publish_tf_map": "true",
                            "approx_sync": LaunchConfiguration("approx_sync"),
                            "subscribe_scan": LaunchConfiguration("subscribe_scan"),
                            "scan_topic": LaunchConfiguration("scan_topic"),
                            "visual_odometry": LaunchConfiguration("visual_odometry"),
                            "publish_tf_odom": LaunchConfiguration("publish_tf_odom"),
                            "rtabmap_viz": LaunchConfiguration("rtabmap_viz"),
                            "rviz": LaunchConfiguration("rtabmap_rviz"),
                        }.items(),
                    )
                ],
            ),
        ]
    )
