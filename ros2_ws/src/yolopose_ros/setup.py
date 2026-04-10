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
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="yhc",
    maintainer_email="you@example.com",
    description="ROS2 wrapper for YOLO pose inference.",
    license="Apache-2.0",
    entry_points={
        "console_scripts": [
            "pose_stream_node = yolopose_ros.pose_stream_node:main",
            "system_supervisor_node = yolopose_ros.system_supervisor_node:main",
        ],
    },
)
