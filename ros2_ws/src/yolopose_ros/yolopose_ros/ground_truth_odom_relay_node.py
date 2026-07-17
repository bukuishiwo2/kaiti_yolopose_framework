"""Normalize Gazebo ground-truth odometry frames for simulation map creation."""

from __future__ import annotations

import rclpy
from geometry_msgs.msg import TransformStamped
from nav_msgs.msg import Odometry
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from tf2_ros import TransformBroadcaster


class GroundTruthOdomRelay(Node):
    def __init__(self) -> None:
        super().__init__("ground_truth_odom_relay")
        self.declare_parameter("input_topic", "/sim_ground_truth_pose")
        self.declare_parameter("output_topic", "/mapping/ground_truth_odom")
        self.declare_parameter("odom_frame_id", "odom_ground_truth")
        self.declare_parameter("base_frame_id", "base_link")
        self.declare_parameter("publish_tf", True)

        input_topic = str(self.get_parameter("input_topic").value)
        output_topic = str(self.get_parameter("output_topic").value)
        self.odom_frame_id = str(self.get_parameter("odom_frame_id").value)
        self.base_frame_id = str(self.get_parameter("base_frame_id").value)
        self.publish_tf = bool(self.get_parameter("publish_tf").value)
        self.publisher = self.create_publisher(Odometry, output_topic, 20)
        self.tf_broadcaster = TransformBroadcaster(self) if self.publish_tf else None
        self.create_subscription(Odometry, input_topic, self._relay, qos_profile_sensor_data)
        self.get_logger().info(
            f"Normalizing simulation odometry {input_topic} -> {output_topic} "
            f"({self.odom_frame_id} -> {self.base_frame_id})"
        )

    def _relay(self, source: Odometry) -> None:
        message = Odometry()
        message.header = source.header
        message.header.frame_id = self.odom_frame_id
        message.child_frame_id = self.base_frame_id
        message.pose = source.pose
        message.twist = source.twist
        self.publisher.publish(message)
        if self.tf_broadcaster is not None:
            transform = TransformStamped()
            transform.header = message.header
            transform.child_frame_id = self.base_frame_id
            transform.transform.translation.x = source.pose.pose.position.x
            transform.transform.translation.y = source.pose.pose.position.y
            transform.transform.translation.z = source.pose.pose.position.z
            transform.transform.rotation = source.pose.pose.orientation
            self.tf_broadcaster.sendTransform(transform)


def main(args=None) -> None:
    rclpy.init(args=args)
    node = GroundTruthOdomRelay()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()
