from __future__ import annotations

from pathlib import Path

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, LogInfo, RegisterEventHandler
from launch.conditions import IfCondition
from launch.event_handlers import OnProcessExit
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import EnvironmentVariable, LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


REPO_ROOT = str(Path(__file__).resolve().parents[4])


def _launch_nav2_after_gate(event, _context, nav2_include):
    if event.returncode == 0:
        return [LogInfo(msg="Robot ready gate passed; launching Nav2."), nav2_include]
    return [LogInfo(msg="Robot ready gate failed; Nav2 launch skipped.")]


def generate_launch_description() -> LaunchDescription:
    phase4a_house_launch = PathJoinSubstitution(
        [FindPackageShare("yolopose_ros"), "launch", "kaiti_house_turtlebot4_rtabmap.launch.py"]
    )
    nav2_launch = PathJoinSubstitution(
        [FindPackageShare("nav2_bringup"), "launch", "navigation_launch.py"]
    )
    nav2_params = PathJoinSubstitution(
        [FindPackageShare("yolopose_ros"), "config", "phase4b_nav2_precheck.yaml"]
    )

    robot_ready_gate = Node(
        package="yolopose_ros",
        executable="robot_ready_gate_node",
        name="robot_ready_gate_node",
        output="screen",
        parameters=[
            {
                "joint_states_topic": "joint_states",
                "odom_topic": LaunchConfiguration("odom_topic"),
                "map_topic": "map",
                "base_frame": LaunchConfiguration("base_frame_id"),
                "odom_frame": "odom",
                "global_frame": "map",
                "require_global_frame": True,
                "wait_timeout_sec": LaunchConfiguration("nav2_start_delay"),
            }
        ],
    )

    nav2_include = IncludeLaunchDescription(
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
    )

    return LaunchDescription(
        [
            DeclareLaunchArgument(
                "project_root",
                default_value=EnvironmentVariable("KAITI_PROJECT_ROOT", default_value=REPO_ROOT),
            ),
            DeclareLaunchArgument("launch_phase4a_house", default_value="true"),
            DeclareLaunchArgument("launch_nav2", default_value="true"),
            DeclareLaunchArgument("params_file", default_value=nav2_params),
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
            DeclareLaunchArgument("rgb_topic", default_value="/oakd/rgb/preview/image_raw"),
            DeclareLaunchArgument("depth_topic", default_value="/oakd/rgb/preview/depth"),
            DeclareLaunchArgument("camera_info_topic", default_value="/oakd/rgb/preview/camera_info"),
            DeclareLaunchArgument("scan_topic", default_value="/scan"),
            DeclareLaunchArgument("odom_topic", default_value="/odom"),
            DeclareLaunchArgument("base_frame_id", default_value="base_link"),
            DeclareLaunchArgument("visualization_enabled", default_value="true"),
            LogInfo(
                msg=[
                    "House Phase 4b Nav2 precheck: custom house + TurtleBot4 + RTAB-Map baseline + ",
                    "Nav2 servers. Planner still must not dispatch goals automatically in this phase.",
                ]
            ),
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource(phase4a_house_launch),
                condition=IfCondition(LaunchConfiguration("launch_phase4a_house")),
                launch_arguments={
                    "project_root": LaunchConfiguration("project_root"),
                    "namespace": LaunchConfiguration("namespace"),
                    "turtlebot4_model": LaunchConfiguration("turtlebot4_model"),
                    "turtlebot4_world": LaunchConfiguration("turtlebot4_world"),
                    "turtlebot4_rviz": LaunchConfiguration("turtlebot4_rviz"),
                    "turtlebot4_x": LaunchConfiguration("turtlebot4_x"),
                    "turtlebot4_y": LaunchConfiguration("turtlebot4_y"),
                    "turtlebot4_z": LaunchConfiguration("turtlebot4_z"),
                    "turtlebot4_yaw": LaunchConfiguration("turtlebot4_yaw"),
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
            robot_ready_gate,
            RegisterEventHandler(
                OnProcessExit(
                    target_action=robot_ready_gate,
                    on_exit=lambda event, context: _launch_nav2_after_gate(
                        event, context, nav2_include
                    ),
                )
            ),
        ]
    )
