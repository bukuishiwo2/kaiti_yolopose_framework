#!/usr/bin/env python3
"""Read-only source-age probe; run on robot domain 8 to include display outputs."""
import argparse
import json
import statistics
import time

import rclpy
from rclpy.qos import QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import CompressedImage
from std_msgs.msg import String
from visualization_msgs.msg import MarkerArray


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--seconds', type=float, default=10)
    args = parser.parse_args()
    rclpy.init()
    node = rclpy.create_node('research_latency_readonly_probe')
    samples = {}

    def add(key, value):
        samples.setdefault(key, []).append(value)

    def image(key, msg):
        stamp = msg.header.stamp.sec * 10**9 + msg.header.stamp.nanosec
        add(key, (node.get_clock().now().nanoseconds - stamp) / 1e6)

    def event(msg):
        data = json.loads(msg.data)
        stamp = data.get('source_ros_stamp_ns')
        if stamp:
            add('event_age', (node.get_clock().now().nanoseconds - stamp) / 1e6)
            add('inference', (data['event_ros_stamp_ns'] - data['processing_started_ros_stamp_ns']) / 1e6)

    def pose(msg):
        data = json.loads(msg.data)
        add('pose_age', (node.get_clock().now().nanoseconds - data['stamp_ns']) / 1e6)

    def markers(msg):
        if msg.markers:
            image('marker_age', msg.markers[-1])

    qos = QoSProfile(depth=1, reliability=ReliabilityPolicy.BEST_EFFORT)
    for key, topic in [('camera_age', '/camera/color/image_raw/compressed'),
                       ('debug_age', '/perception/debug_image/compressed'),
                       ('annotated_age', '/perception/pose_3d_debug_image/compressed')]:
        node.create_subscription(CompressedImage, topic, lambda msg, k=key: image(k, msg), qos)
    node.create_subscription(String, '/perception/events', event, 1)
    node.create_subscription(String, '/perception/pose_observation_3d', pose, 1)
    node.create_subscription(MarkerArray, '/perception/pose_3d_markers', markers, qos)
    deadline = time.monotonic() + args.seconds
    try:
        while time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=0.1)
        result = {key: {'count': len(values), 'min_ms': round(min(values), 1),
                        'median_ms': round(statistics.median(values), 1),
                        'max_ms': round(max(values), 1)} for key, values in samples.items()}
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if samples else 1
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    raise SystemExit(main())
