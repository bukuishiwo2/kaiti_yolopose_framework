"""Three official TB4 Lite robot/control components with isolated Nav2 graphs."""
from pathlib import Path
import json, os
from support.clinic_runtime.config import profile
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, ExecuteProcess, IncludeLaunchDescription, GroupAction
from launch.conditions import UnlessCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node, PushRosNamespace, SetRemap

def generate_launch_description():
    root = Path(__file__).resolve().parents[1]
    config = root / 'config/three_tb4'
    execution = root / 'config/hospital_bed'
    scenario = json.loads((root / profile()['scenario']).read_text())
    prepared = Path(os.environ['CLINIC_RUNTIME_PREPARED'])
    actions = [DeclareLaunchArgument('headless', default_value='false'), ExecuteProcess(cmd=['ign', 'gazebo', '--force-version', '6', '-s', '-r', '-v', '3', str(root / 'worlds/clinic_l1_three.sdf')], output='screen'), ExecuteProcess(cmd=['/usr/bin/python3', '-u', str(root / 'tools/start_three_gui.py')], output='screen', condition=UnlessCondition(LaunchConfiguration('headless'))), Node(package='ros_gz_bridge', executable='parameter_bridge', name='three_clock_truth_bridge', arguments=['/clock@rosgraph_msgs/msg/Clock[ignition.msgs.Clock', '/world/clinic_l1_three/dynamic_pose/info@tf2_msgs/msg/TFMessage[ignition.msgs.Pose_V'], output='screen'), ExecuteProcess(cmd=['/usr/bin/python3', '-u', str(root / 'tools/bed_resources.py'), '--ros-args', '-p', 'use_sim_time:=true'], output='screen'), ExecuteProcess(cmd=['/usr/bin/python3', '-u', '-m', 'support.clinic_runtime.bootstrap'], output='screen')]
    actions.append(ExecuteProcess(cmd=['/usr/bin/python3', '-u', str(root / 'tools/dense_reference_tf.py')], output='screen'))
    actions.append(ExecuteProcess(cmd=['/usr/bin/python3', '-u', str(root / 'tools/aligned_health.py'), '--ros-args', '-p', 'use_sim_time:=true'], output='screen'))
    actions.append(ExecuteProcess(cmd=['/usr/bin/python3', '-u', str(root / 'tools/bed_keepout.py'), '--ros-args', '-p', 'use_sim_time:=true'], output='screen'))
    actions.append(ExecuteProcess(cmd=['/usr/bin/python3', '-u', str(root / 'tools/bed_driver.py'), '--ros-args', '-p', 'use_sim_time:=true'], output='screen'))
    for (rid, r) in scenario['robots'].items():
        group = GroupAction([PushRosNamespace(rid), SetRemap(src='/tf', dst='tf'), SetRemap(src='/tf_static', dst='tf_static'), Node(package='robot_state_publisher', executable='robot_state_publisher', name='robot_state_publisher', parameters=[{'use_sim_time': True, 'robot_description': (config / f'{rid}.urdf').read_text()}], output='screen'), Node(package='ros_gz_bridge', executable='parameter_bridge', name='laser_bridge', arguments=[f'/world/clinic_l1_three/model/{rid}/link/rplidar_link/sensor/rplidar/scan@sensor_msgs/msg/LaserScan[ignition.msgs.LaserScan'], remappings=[(f'/world/clinic_l1_three/model/{rid}/link/rplidar_link/sensor/rplidar/scan', 'scan_raw')], output='screen'), ExecuteProcess(cmd=['/usr/bin/python3', '-u', str(root / 'tools/tb4_io.py'), '--ros-args', '-r', f'__ns:=/{rid}', '-r', f'/tf:=/{rid}/tf', '-r', f'/tf_static:=/{rid}/tf_static', '-p', 'use_sim_time:=true'], output='screen'), ExecuteProcess(cmd=['/usr/bin/python3', '-u', str(root / 'tools/aligned_service_worker.py'), '--ros-args', '-r', f'__ns:=/{rid}', '-r', f'/tf:=/{rid}/tf', '-r', f'/tf_static:=/{rid}/tf_static', '-r', f'/odom:=/{rid}/odom', '-r', f'/clinic_experiment/service_request:=/{rid}/experiment/service_request', '-r', f'/clinic_experiment/service_feedback:=/{rid}/experiment/service_feedback', '-p', 'use_sim_time:=true'], output='screen')])
        actions.append(group)
        actions.extend([Node(package='nav2_map_server', executable='map_server', namespace=rid, name='semantic_map_server', parameters=[{'use_sim_time': True, 'yaml_filename': str(root / 'config/hospital_aligned/semantic_navigation.yaml'), 'topic_name': 'semantic_map', 'frame_id': 'map'}], output='screen'), Node(package='nav2_lifecycle_manager', executable='lifecycle_manager', namespace=rid, name='semantic_map_lifecycle', parameters=[{'use_sim_time': True, 'autostart': True, 'node_names': ['semantic_map_server']}], output='screen')])
        actions.append(IncludeLaunchDescription(PythonLaunchDescriptionSource('/opt/ros/humble/share/nav2_bringup/launch/bringup_launch.py'), launch_arguments={'namespace': rid, 'use_namespace': 'true', 'map': str(root / 'verification/hospital_semantics/collision_audit.yaml'), 'params_file': str(prepared / f'{rid}_nav2.yaml'), 'use_sim_time': 'true', 'autostart': 'true', 'use_composition': 'False', 'log_level': 'warn'}.items()))
    return LaunchDescription(actions)
