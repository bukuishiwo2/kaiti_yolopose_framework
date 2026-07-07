from __future__ import annotations

from irobot_create_common_bringup.namespace import GetNamespacedName
from irobot_create_common_bringup.offset import OffsetParser, RotationalOffsetX, RotationalOffsetY

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, GroupAction, IncludeLaunchDescription, TimerAction
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node, PushRosNamespace
from launch_ros.substitutions import FindPackageShare


def generate_launch_description() -> LaunchDescription:
    turtlebot4_ros_ign_bridge_launch = PathJoinSubstitution(
        [FindPackageShare("turtlebot4_ignition_bringup"), "launch", "ros_ign_bridge.launch.py"]
    )
    rviz_launch = PathJoinSubstitution(
        [FindPackageShare("turtlebot4_viz"), "launch", "view_robot.launch.py"]
    )
    turtlebot4_node_launch = PathJoinSubstitution(
        [FindPackageShare("turtlebot4_ignition_bringup"), "launch", "turtlebot4_nodes.launch.py"]
    )
    create3_nodes_launch = PathJoinSubstitution(
        [FindPackageShare("yolopose_ros"), "launch", "kaiti_create3_nodes.launch.py"]
    )
    create3_ignition_nodes_launch = PathJoinSubstitution(
        [FindPackageShare("irobot_create_ignition_bringup"), "launch", "create3_ignition_nodes.launch.py"]
    )
    robot_description_launch = PathJoinSubstitution(
        [FindPackageShare("turtlebot4_description"), "launch", "robot_description.launch.py"]
    )
    dock_description_launch = PathJoinSubstitution(
        [FindPackageShare("irobot_create_common_bringup"), "launch", "dock_description.launch.py"]
    )
    localization_launch = PathJoinSubstitution(
        [FindPackageShare("turtlebot4_navigation"), "launch", "localization.launch.py"]
    )
    slam_launch = PathJoinSubstitution(
        [FindPackageShare("turtlebot4_navigation"), "launch", "slam.launch.py"]
    )
    nav2_launch = PathJoinSubstitution(
        [FindPackageShare("turtlebot4_navigation"), "launch", "nav2.launch.py"]
    )

    namespace = LaunchConfiguration("namespace")
    use_sim_time = LaunchConfiguration("use_sim_time")
    x = LaunchConfiguration("x")
    y = LaunchConfiguration("y")
    z = LaunchConfiguration("z")
    yaw = LaunchConfiguration("yaw")
    robot_name = GetNamespacedName(namespace, "turtlebot4")
    dock_name = GetNamespacedName(namespace, "standard_dock")
    dock_offset_x = RotationalOffsetX(0.157, yaw)
    dock_offset_y = RotationalOffsetY(0.157, yaw)
    x_dock = OffsetParser(x, dock_offset_x)
    y_dock = OffsetParser(y, dock_offset_y)
    z_robot = OffsetParser(z, -0.0025)
    yaw_dock = OffsetParser(yaw, 3.1416)

    spawn_robot_group_action = GroupAction(
        [
            PushRosNamespace(namespace),
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource([robot_description_launch]),
                launch_arguments={
                    "model": LaunchConfiguration("model"),
                    "use_sim_time": use_sim_time,
                }.items(),
            ),
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource([dock_description_launch]),
                launch_arguments={"gazebo": "ignition"}.items(),
            ),
            Node(
                package="ros_ign_gazebo",
                executable="create",
                arguments=[
                    "-name",
                    robot_name,
                    "-x",
                    x,
                    "-y",
                    y,
                    "-z",
                    z_robot,
                    "-Y",
                    yaw,
                    "-topic",
                    "robot_description",
                ],
                output="screen",
            ),
            Node(
                package="ros_ign_gazebo",
                executable="create",
                arguments=[
                    "-name",
                    dock_name,
                    "-x",
                    x_dock,
                    "-y",
                    y_dock,
                    "-z",
                    z,
                    "-Y",
                    yaw_dock,
                    "-topic",
                    "standard_dock_description",
                ],
                output="screen",
            ),
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource([turtlebot4_ros_ign_bridge_launch]),
                launch_arguments={
                    "model": LaunchConfiguration("model"),
                    "robot_name": robot_name,
                    "dock_name": dock_name,
                    "namespace": namespace,
                    "world": LaunchConfiguration("world"),
                    "use_sim_time": use_sim_time,
                }.items(),
            ),
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource([turtlebot4_node_launch]),
                launch_arguments={
                    "model": LaunchConfiguration("model"),
                    "param_file": LaunchConfiguration("param_file"),
                }.items(),
            ),
            TimerAction(
                period=LaunchConfiguration("controller_start_delay"),
                actions=[
                    IncludeLaunchDescription(
                        PythonLaunchDescriptionSource([create3_nodes_launch]),
                        launch_arguments={
                            "namespace": namespace,
                            "gazebo": "ignition",
                            "controller_manager_timeout": LaunchConfiguration(
                                "controller_manager_timeout"
                            ),
                            "switch_timeout": LaunchConfiguration("switch_timeout"),
                            "service_call_timeout": LaunchConfiguration("service_call_timeout"),
                        }.items(),
                    ),
                    IncludeLaunchDescription(
                        PythonLaunchDescriptionSource([create3_ignition_nodes_launch]),
                        launch_arguments={
                            "robot_name": robot_name,
                            "dock_name": dock_name,
                        }.items(),
                    ),
                ],
            ),
            Node(
                name="rplidar_stf",
                package="tf2_ros",
                executable="static_transform_publisher",
                output="screen",
                arguments=["0", "0", "0", "0", "0", "0.0", "rplidar_link", [robot_name, "/rplidar_link/rplidar"]],
                remappings=[("/tf", "tf"), ("/tf_static", "tf_static")],
            ),
            Node(
                name="camera_stf",
                package="tf2_ros",
                executable="static_transform_publisher",
                output="screen",
                arguments=[
                    "0",
                    "0",
                    "0",
                    "1.5707",
                    "-1.5707",
                    "0",
                    "oakd_rgb_camera_optical_frame",
                    [robot_name, "/oakd_rgb_camera_frame/rgbd_camera"],
                ],
                remappings=[("/tf", "tf"), ("/tf_static", "tf_static")],
            ),
        ]
    )

    return LaunchDescription(
        [
            DeclareLaunchArgument("rviz", default_value="false"),
            DeclareLaunchArgument("use_sim_time", default_value="true"),
            DeclareLaunchArgument("model", default_value="standard"),
            DeclareLaunchArgument("namespace", default_value=""),
            DeclareLaunchArgument("world", default_value="kaiti_house_world"),
            DeclareLaunchArgument("localization", default_value="false"),
            DeclareLaunchArgument("slam", default_value="false"),
            DeclareLaunchArgument("nav2", default_value="false"),
            DeclareLaunchArgument("x", default_value="0.8"),
            DeclareLaunchArgument("y", default_value="0.8"),
            DeclareLaunchArgument("z", default_value="0.0"),
            DeclareLaunchArgument("yaw", default_value="0.0"),
            DeclareLaunchArgument(
                "param_file",
                default_value=PathJoinSubstitution(
                    [FindPackageShare("turtlebot4_ignition_bringup"), "config", "turtlebot4_node.yaml"]
                ),
            ),
            DeclareLaunchArgument("controller_manager_timeout", default_value="60"),
            DeclareLaunchArgument("switch_timeout", default_value="30"),
            DeclareLaunchArgument("service_call_timeout", default_value="30"),
            DeclareLaunchArgument("controller_start_delay", default_value="8.0"),
            spawn_robot_group_action,
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource([localization_launch]),
                launch_arguments={"namespace": namespace, "use_sim_time": use_sim_time}.items(),
                condition=IfCondition(LaunchConfiguration("localization")),
            ),
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource([slam_launch]),
                launch_arguments={"namespace": namespace, "use_sim_time": use_sim_time}.items(),
                condition=IfCondition(LaunchConfiguration("slam")),
            ),
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource([nav2_launch]),
                launch_arguments={"namespace": namespace, "use_sim_time": use_sim_time}.items(),
                condition=IfCondition(LaunchConfiguration("nav2")),
            ),
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource([rviz_launch]),
                launch_arguments={"namespace": namespace, "use_sim_time": use_sim_time}.items(),
                condition=IfCondition(LaunchConfiguration("rviz")),
            ),
        ]
    )
