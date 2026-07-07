from __future__ import annotations

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, LogInfo
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.substitutions import FindPackageShare


def generate_launch_description() -> LaunchDescription:
    default_world = PathJoinSubstitution(
        [FindPackageShare("yolopose_ros"), "worlds", "kaiti_house_world.sdf"]
    )
    gz_sim_launch = PathJoinSubstitution(
        [FindPackageShare("ros_gz_sim"), "launch", "gz_sim.launch.py"]
    )

    return LaunchDescription(
        [
            DeclareLaunchArgument("world", default_value=default_world),
            DeclareLaunchArgument("headless", default_value="false"),
            LogInfo(
                msg=[
                    "Launching Kaiti house custom world in Gazebo Sim. ",
                    "This launch starts the world only; TurtleBot4 spawning, RTAB-Map, Nav2, ",
                    "and PlanSys2 lifecycle integration are layered on top in later stages.",
                ]
            ),
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource(gz_sim_launch),
                launch_arguments={
                    "gz_args": [
                        "-r ",
                        LaunchConfiguration("world"),
                    ],
                }.items(),
            ),
            LogInfo(
                msg=[
                    "Recommended robot: TurtleBot4 standard. ",
                    "Recommended experiment count: 3 robots, but bringup should proceed 1 -> 2 -> 3.",
                ]
            ),
        ]
    )
