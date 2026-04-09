from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description() -> LaunchDescription:
    return LaunchDescription(
        [
            Node(
                package="yolopose_ros",
                executable="pose_stream_node",
                name="pose_stream_node",
                output="screen",
                parameters=[
                    {"project_root": "/home/yhc/kaiti_yolopose_framework"},
                    {"infer_config": "configs/infer_pose_stream.yaml"},
                    {"event_topic": "/yolopose/events"},
                ],
            )
        ]
    )
