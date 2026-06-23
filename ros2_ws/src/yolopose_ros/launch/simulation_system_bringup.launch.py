from __future__ import annotations

from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription, LogInfo
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import PathJoinSubstitution
from launch_ros.substitutions import FindPackageShare


def generate_launch_description() -> LaunchDescription:
    system_stack = PathJoinSubstitution(
        [FindPackageShare("yolopose_ros"), "launch", "system_stack.launch.py"]
    )
    return LaunchDescription(
        [
            LogInfo(
                msg=[
                    "simulation_system_bringup.launch.py is kept as a compatibility shim. ",
                    "It forwards to system_stack.launch.py.",
                ]
            ),
            IncludeLaunchDescription(PythonLaunchDescriptionSource(system_stack)),
        ]
    )
