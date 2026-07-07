from glob import glob

from setuptools import setup

package_name = "yolopose_ros"

setup(
    name=package_name,
    version="0.0.1",
    packages=[package_name],
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
        ("share/" + package_name + "/launch", glob("launch/*.launch.py")),
        ("share/" + package_name + "/config", glob("config/*.yaml")),
        ("share/" + package_name + "/gui", glob("gui/*.config")),
        ("share/" + package_name + "/worlds", glob("worlds/*.sdf")),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="yhc",
    maintainer_email="you@example.com",
    description="ROS2 wrapper for YOLO pose inference.",
    license="Apache-2.0",
    entry_points={
        "console_scripts": [
            "camera_stream_node = yolopose_ros.camera_stream_node:main",
            "pose_stream_node = yolopose_ros.pose_stream_node:main",
            "system_supervisor_node = yolopose_ros.system_supervisor_node:main",
            "task_planner_bridge_node = yolopose_ros.task_planner_bridge_node:main",
            "planner_nav2_dispatcher_node = yolopose_ros.planner_nav2_dispatcher_node:main",
            "controller_ready_node = yolopose_ros.controller_ready_node:main",
            "robot_ready_gate_node = yolopose_ros.robot_ready_gate_node:main",
            "semantic_state_node = yolopose_ros.semantic_state_node:main",
            "spatial_state_node = yolopose_ros.spatial_state_node:main",
            "milp_planner_node = yolopose_ros.milp_planner_node:main",
            "execution_feedback_bridge_node = yolopose_ros.execution_feedback_bridge_node:main",
        ],
    },
)
