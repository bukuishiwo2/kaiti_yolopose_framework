"""House sim root launch for TurtleBot4 manual-control bringup.

主要功能:
- 启动自定义家居 world 的 Ignition Gazebo 仿真。
- 启动 TurtleBot4 / Create3 相关桥接、底盘控制器、基础传感器节点。
- 额外提供 clean-start 检查，阻止上一轮残留进程和本轮重复启动叠加。
- 默认增加 /cmd_vel 到 diff-drive controller 的兜底直连，保证手动键盘控制优先可用。

适用阶段:
- Phase 4a/4b/5 的底层仿真基座。
- 手动验证 Gazebo、底盘控制、/odom、/joint_states、/scan、/rgbd 是否正常。

不负责:
- 不直接启动 RTAB-Map、Nav2、PlanSys2、planning stack。
"""

from __future__ import annotations

import os
import subprocess

from pathlib import Path

from ament_index_python.packages import get_package_share_directory

from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    IncludeLaunchDescription,
    LogInfo,
    OpaqueFunction,
    SetEnvironmentVariable,
)
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch.conditions import IfCondition


STALE_PROCESS_PATTERNS = [
    "ign gazebo",
    "rtabmap",
    "controller_ready_node",
    "robot_ready_gate_node",
    "ros_gz_bridge parameter_bridge",
    "irobot_create_nodes",
    "turtlebot4_node",
]


def _check_clean_start(context, *_args, **_kwargs):
    require_clean_start = (
        str(LaunchConfiguration("require_clean_start").perform(context)).strip().lower() == "true"
    )
    if not require_clean_start:
        return []

    matches = []
    for pattern in STALE_PROCESS_PATTERNS:
        completed = subprocess.run(
            ["pgrep", "-fa", pattern],
            check=False,
            capture_output=True,
            text=True,
        )
        for line in completed.stdout.splitlines():
            normalized = line.strip()
            if not normalized:
                continue
            if "pgrep -fa" in normalized:
                continue
            # A parent launch command may itself contain words such as
            # ``rtabmap`` in the launch filename or arguments.  It is part of
            # the launch currently being evaluated, not a stale ROS process.
            # Skip this process and all ancestors while retaining genuine
            # processes left behind by an earlier run.
            fields = normalized.split(maxsplit=1)
            try:
                matched_pid = int(fields[0])
            except (IndexError, ValueError):
                matched_pid = -1
            ancestor_pids = {os.getpid()}
            parent_pid = os.getppid()
            while parent_pid > 1 and parent_pid not in ancestor_pids:
                ancestor_pids.add(parent_pid)
                try:
                    with open(f"/proc/{parent_pid}/stat", encoding="utf-8") as stat_file:
                        parent_pid = int(stat_file.read().split()[3])
                except (FileNotFoundError, IndexError, OSError, ValueError):
                    break
            if matched_pid in ancestor_pids:
                continue
            matches.append(normalized)

    if matches:
        raise RuntimeError(
            "Detected stale simulation-related processes before launch:\n"
            + "\n".join(matches)
            + "\nRun `bash scripts/cleanup_house_sim_processes.sh` and relaunch, or pass "
            + "`require_clean_start:=false` only if you intentionally reuse an existing sim."
        )
    return []


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
            "controller_activation_settle_sec": LaunchConfiguration(
                "controller_activation_settle_sec"
            ),
            "controller_start_delay": LaunchConfiguration("controller_start_delay"),
            "rviz": LaunchConfiguration("turtlebot4_rviz"),
            "x": LaunchConfiguration("turtlebot4_x"),
            "y": LaunchConfiguration("turtlebot4_y"),
            "z": LaunchConfiguration("turtlebot4_z"),
            "yaw": LaunchConfiguration("turtlebot4_yaw"),
            "spawn_dock": LaunchConfiguration("spawn_dock"),
        }.items(),
    )

    cmd_vel_direct_bridge = Node(
        package="yolopose_ros",
        executable="cmd_vel_direct_bridge_node",
        name="cmd_vel_direct_bridge_node",
        output="screen",
        condition=IfCondition(LaunchConfiguration("direct_cmd_vel_bridge_enabled")),
        parameters=[
            {
                "input_topic": "/cmd_vel",
                "output_topic": "/diffdrive_controller/cmd_vel_unstamped",
            }
        ],
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
            DeclareLaunchArgument("controller_activation_settle_sec", default_value="2.0"),
            DeclareLaunchArgument("controller_start_delay", default_value="8.0"),
            DeclareLaunchArgument("require_clean_start", default_value="true"),
            DeclareLaunchArgument("direct_cmd_vel_bridge_enabled", default_value="true"),
            DeclareLaunchArgument("turtlebot4_x", default_value="0.8"),
            DeclareLaunchArgument("turtlebot4_y", default_value="0.8"),
            DeclareLaunchArgument("turtlebot4_z", default_value="0.0"),
            DeclareLaunchArgument("turtlebot4_yaw", default_value="0.0"),
            DeclareLaunchArgument("spawn_dock", default_value="true"),
            OpaqueFunction(function=_check_clean_start),
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
            cmd_vel_direct_bridge,
        ]
    )
