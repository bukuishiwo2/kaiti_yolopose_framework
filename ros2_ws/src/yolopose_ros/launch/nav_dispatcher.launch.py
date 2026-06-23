from __future__ import annotations

from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription, LogInfo
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import PathJoinSubstitution
from launch_ros.substitutions import FindPackageShare


def generate_launch_description() -> LaunchDescription:
    phase5_launch = PathJoinSubstitution(
        [FindPackageShare("yolopose_ros"), "launch", "phase5_nav2_dispatcher.launch.py"]
    )
    return LaunchDescription(
        [
            LogInfo(
                msg=[
                    "nav_dispatcher.launch.py is kept as a compatibility shim. ",
                    "It forwards to phase5_nav2_dispatcher.launch.py.",
                ]
            ),
            IncludeLaunchDescription(PythonLaunchDescriptionSource(phase5_launch)),
        ]
    )
