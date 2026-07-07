from __future__ import annotations

import os

from pathlib import Path

from ament_index_python.packages import get_package_share_directory

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, LogInfo, SetEnvironmentVariable
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node


def generate_launch_description() -> LaunchDescription:
    pkg_yolopose_ros = get_package_share_directory("yolopose_ros")
    pkg_turtlebot4_ignition_bringup = get_package_share_directory("turtlebot4_ignition_bringup")
    pkg_turtlebot4_ignition_gui_plugins = get_package_share_directory(
        "turtlebot4_ignition_gui_plugins"
    )
    pkg_turtlebot4_description = get_package_share_directory("turtlebot4_description")
    pkg_irobot_create_description = get_package_share_directory("irobot_create_description")
    pkg_irobot_create_ignition_bringup = get_package_share_directory(
        "irobot_create_ignition_bringup"
    )
    pkg_irobot_create_ignition_plugins = get_package_share_directory(
        "irobot_create_ignition_plugins"
    )
    pkg_ros_ign_gazebo = get_package_share_directory("ros_ign_gazebo")

    ign_gazebo_launch = PathJoinSubstitution([pkg_ros_ign_gazebo, "launch", "ign_gazebo.launch.py"])
    turtlebot4_spawn_launch = PathJoinSubstitution(
        [pkg_yolopose_ros, "launch", "kaiti_house_turtlebot4_spawn.launch.py"]
    )
    gui_config = PathJoinSubstitution([pkg_yolopose_ros, "gui", "kaiti_house_gui.config"])

    custom_worlds_path = os.path.join(pkg_yolopose_ros, "worlds")
    ign_resource_path = SetEnvironmentVariable(
        name="IGN_GAZEBO_RESOURCE_PATH",
        value=[
            custom_worlds_path,
            ":",
            os.path.join(pkg_turtlebot4_ignition_bringup, "worlds"),
            ":",
            os.path.join(pkg_irobot_create_ignition_bringup, "worlds"),
            ":",
            str(Path(pkg_turtlebot4_description).parent.resolve()),
            ":",
            str(Path(pkg_irobot_create_description).parent.resolve()),
        ],
    )
    ign_gui_plugin_path = SetEnvironmentVariable(
        name="IGN_GUI_PLUGIN_PATH",
        value=[
            os.path.join(pkg_turtlebot4_ignition_gui_plugins, "lib"),
            ":",
            os.path.join(pkg_irobot_create_ignition_plugins, "lib"),
        ],
    )

    ignition_gazebo = IncludeLaunchDescription(
        PythonLaunchDescriptionSource([ign_gazebo_launch]),
        launch_arguments={
            "ign_args": [
                LaunchConfiguration("turtlebot4_world"),
                ".sdf -r -v 4 --gui-config ",
                gui_config,
            ]
        }.items(),
    )

    clock_bridge = Node(
        package="ros_gz_bridge",
        executable="parameter_bridge",
        name="clock_bridge",
        output="screen",
        arguments=["/clock@rosgraph_msgs/msg/Clock[ignition.msgs.Clock"],
    )

    turtlebot4_spawn = IncludeLaunchDescription(
        PythonLaunchDescriptionSource([turtlebot4_spawn_launch]),
        launch_arguments={
            "namespace": LaunchConfiguration("namespace"),
            "use_sim_time": LaunchConfiguration("use_sim_time"),
            "model": LaunchConfiguration("turtlebot4_model"),
            "world": LaunchConfiguration("turtlebot4_world"),
            "controller_manager_timeout": LaunchConfiguration("controller_manager_timeout"),
            "switch_timeout": LaunchConfiguration("switch_timeout"),
            "service_call_timeout": LaunchConfiguration("service_call_timeout"),
            "controller_start_delay": LaunchConfiguration("controller_start_delay"),
            "rviz": LaunchConfiguration("turtlebot4_rviz"),
            "x": LaunchConfiguration("turtlebot4_x"),
            "y": LaunchConfiguration("turtlebot4_y"),
            "z": LaunchConfiguration("turtlebot4_z"),
            "yaw": LaunchConfiguration("turtlebot4_yaw"),
        }.items(),
    )

    return LaunchDescription(
        [
            DeclareLaunchArgument("namespace", default_value=""),
            DeclareLaunchArgument("use_sim_time", default_value="true"),
            DeclareLaunchArgument("turtlebot4_model", default_value="standard"),
            DeclareLaunchArgument("turtlebot4_world", default_value="kaiti_house_world"),
            DeclareLaunchArgument("turtlebot4_rviz", default_value="false"),
            DeclareLaunchArgument("controller_manager_timeout", default_value="60"),
            DeclareLaunchArgument("switch_timeout", default_value="30"),
            DeclareLaunchArgument("service_call_timeout", default_value="30"),
            DeclareLaunchArgument("controller_start_delay", default_value="8.0"),
            DeclareLaunchArgument("turtlebot4_x", default_value="0.8"),
            DeclareLaunchArgument("turtlebot4_y", default_value="0.8"),
            DeclareLaunchArgument("turtlebot4_z", default_value="0.0"),
            DeclareLaunchArgument("turtlebot4_yaw", default_value="0.0"),
            LogInfo(
                msg=[
                    "Launching TurtleBot4 in custom house world ",
                    LaunchConfiguration("turtlebot4_world"),
                    " at pose (",
                    LaunchConfiguration("turtlebot4_x"),
                    ", ",
                    LaunchConfiguration("turtlebot4_y"),
                    ", yaw=",
                    LaunchConfiguration("turtlebot4_yaw"),
                    ").",
                ]
            ),
            ign_resource_path,
            ign_gui_plugin_path,
            ignition_gazebo,
            clock_bridge,
            turtlebot4_spawn,
        ]
    )
