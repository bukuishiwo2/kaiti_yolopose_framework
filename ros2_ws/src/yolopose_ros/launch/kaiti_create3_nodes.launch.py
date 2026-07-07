from __future__ import annotations

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description() -> LaunchDescription:
    control_launch = PathJoinSubstitution(
        [FindPackageShare("yolopose_ros"), "launch", "kaiti_create3_control.launch.py"]
    )
    hazards_params_yaml_file = PathJoinSubstitution(
        [FindPackageShare("irobot_create_common_bringup"), "config", "hazard_vector_params.yaml"]
    )
    ir_intensity_params_yaml_file = PathJoinSubstitution(
        [FindPackageShare("irobot_create_common_bringup"), "config", "ir_intensity_vector_params.yaml"]
    )
    wheel_status_params_yaml_file = PathJoinSubstitution(
        [FindPackageShare("irobot_create_common_bringup"), "config", "wheel_status_params.yaml"]
    )
    mock_params_yaml_file = PathJoinSubstitution(
        [FindPackageShare("irobot_create_common_bringup"), "config", "mock_params.yaml"]
    )
    robot_state_yaml_file = PathJoinSubstitution(
        [FindPackageShare("irobot_create_common_bringup"), "config", "robot_state_params.yaml"]
    )
    kidnap_estimator_yaml_file = PathJoinSubstitution(
        [FindPackageShare("irobot_create_common_bringup"), "config", "kidnap_estimator_params.yaml"]
    )
    ui_mgr_params_yaml_file = PathJoinSubstitution(
        [FindPackageShare("irobot_create_common_bringup"), "config", "ui_mgr_params.yaml"]
    )

    diffdrive_controller = IncludeLaunchDescription(
        PythonLaunchDescriptionSource([control_launch]),
        launch_arguments={
            "namespace": LaunchConfiguration("namespace"),
            "controller_manager_timeout": LaunchConfiguration("controller_manager_timeout"),
            "switch_timeout": LaunchConfiguration("switch_timeout"),
            "service_call_timeout": LaunchConfiguration("service_call_timeout"),
        }.items(),
    )

    hazards_vector_node = Node(
        package="irobot_create_nodes",
        name="hazards_vector_publisher",
        executable="hazards_vector_publisher",
        parameters=[hazards_params_yaml_file, {"use_sim_time": True}],
        output="screen",
    )
    ir_intensity_vector_node = Node(
        package="irobot_create_nodes",
        name="ir_intensity_vector_publisher",
        executable="ir_intensity_vector_publisher",
        parameters=[ir_intensity_params_yaml_file, {"use_sim_time": True}],
        output="screen",
    )
    motion_control_node = Node(
        package="irobot_create_nodes",
        name="motion_control",
        executable="motion_control",
        parameters=[{"use_sim_time": True}],
        output="screen",
        remappings=[("/tf", "tf"), ("/tf_static", "tf_static")],
    )
    wheel_status_node = Node(
        package="irobot_create_nodes",
        name="wheel_status_publisher",
        executable="wheel_status_publisher",
        parameters=[wheel_status_params_yaml_file, {"use_sim_time": True}],
        output="screen",
    )
    mock_topics_node = Node(
        package="irobot_create_nodes",
        name="mock_publisher",
        executable="mock_publisher",
        parameters=[mock_params_yaml_file, {"use_sim_time": True}],
        output="screen",
    )
    robot_state_node = Node(
        package="irobot_create_nodes",
        name="robot_state",
        executable="robot_state",
        parameters=[robot_state_yaml_file, {"use_sim_time": True}],
        output="screen",
    )
    kidnap_estimator_node = Node(
        package="irobot_create_nodes",
        name="kidnap_estimator_publisher",
        executable="kidnap_estimator_publisher",
        parameters=[kidnap_estimator_yaml_file, {"use_sim_time": True}],
        output="screen",
    )
    ui_mgr_node = Node(
        package="irobot_create_nodes",
        name="ui_mgr",
        executable="ui_mgr",
        parameters=[
            ui_mgr_params_yaml_file,
            {"use_sim_time": True},
            {"gazebo": LaunchConfiguration("gazebo")},
        ],
        output="screen",
    )

    return LaunchDescription(
        [
            DeclareLaunchArgument("gazebo", default_value="ignition"),
            DeclareLaunchArgument("namespace", default_value=""),
            DeclareLaunchArgument("controller_manager_timeout", default_value="60"),
            DeclareLaunchArgument("switch_timeout", default_value="30"),
            DeclareLaunchArgument("service_call_timeout", default_value="30"),
            diffdrive_controller,
            hazards_vector_node,
            ir_intensity_vector_node,
            motion_control_node,
            wheel_status_node,
            mock_topics_node,
            robot_state_node,
            kidnap_estimator_node,
            ui_mgr_node,
        ]
    )
