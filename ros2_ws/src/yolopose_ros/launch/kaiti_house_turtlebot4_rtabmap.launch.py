from __future__ import annotations

from pathlib import Path

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, LogInfo, TimerAction
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import EnvironmentVariable, LaunchConfiguration, PathJoinSubstitution
from launch_ros.substitutions import FindPackageShare


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
            DeclareLaunchArgument("rtabmap_viz", default_value="false"),
            DeclareLaunchArgument("rtabmap_rviz", default_value="false"),
            DeclareLaunchArgument("rtabmap_start_delay", default_value="12.0"),
            DeclareLaunchArgument("visualization_enabled", default_value="true"),
            LogInfo(
                msg=[
                    "House Phase 4a stack: custom house + TurtleBot4 + yolopose_ros ros_image + ",
                    "RTAB-Map sidecar mapping. Nav2 and PlanSys2 lifecycle remain outside this launch.",
                ]
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
