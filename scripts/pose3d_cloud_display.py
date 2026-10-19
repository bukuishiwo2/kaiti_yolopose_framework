#!/usr/bin/env python3
"""Bounded point-count DISPLAY cloud. Does not change SLAM or planning data."""
from array import array
import math

import numpy as np
import rclpy
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import PointCloud2


def main():
    rclpy.init()
    node = rclpy.create_node('research_cloud_display')
    node.declare_parameter('max_points', 80000)
    # RTAB-Map publishes retained maps only on changes. Late-joining RViz must
    # receive the latest map even while the robot is stationary.
    qos = QoSProfile(depth=1, reliability=ReliabilityPolicy.RELIABLE,
                     durability=DurabilityPolicy.TRANSIENT_LOCAL)
    pub = node.create_publisher(PointCloud2, '/perception/cloud_map_display', qos)

    def receive(msg):
        if not msg.width or not msg.height:
            return
        if msg.point_step <= 0 or msg.row_step < msg.width * msg.point_step:
            return
        if len(msg.data) < msg.height * msg.row_step:
            return
        # Respect organized cloud row padding; keep each point's complete bytes.
        rows = np.frombuffer(msg.data, np.uint8, count=msg.height * msg.row_step)
        points = rows.reshape(msg.height, msg.row_step)[:, :msg.width * msg.point_step]
        points = points.reshape(-1, msg.point_step)
        limit = max(1, int(node.get_parameter('max_points').value))
        stride = max(1, math.ceil(len(points) / limit))
        selected = points[::stride]
        output = PointCloud2()
        output.header, output.fields = msg.header, msg.fields
        output.height, output.width = 1, len(selected)
        output.is_bigendian, output.is_dense = msg.is_bigendian, msg.is_dense
        output.point_step, output.row_step = msg.point_step, len(selected) * msg.point_step
        output.data = array('B', selected.tobytes())
        pub.publish(output)

    node.create_subscription(PointCloud2, '/cloud_map', receive, qos)
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
