#!/usr/bin/env python3
"""Publish a map marker only. No cmd_vel, Nav2 goal, or navigation action."""
import json
import math
import sys
from pathlib import Path

import rclpy
from rclpy.duration import Duration
from std_msgs.msg import String
from visualization_msgs.msg import Marker

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'ros2_ws/src/yolopose_ros'))
from yolopose_ros.human_approach_geometry import approach_candidate


def main():
    rclpy.init()
    node = rclpy.create_node('human_approach_preview')
    node.declare_parameter('standoff_m', 1.0)
    pub = node.create_publisher(Marker, '/perception/human_approach_preview', 1)
    status = node.create_publisher(String, '/perception/human_approach_candidate_status', 1)

    def receive(msg):
        payload = json.loads(msg.data)
        age = (node.get_clock().now().nanoseconds - int(payload.get('stamp_ns', 0))) / 1e9
        marker = Marker()
        marker.header.frame_id = 'map'
        marker.header.stamp = node.get_clock().now().to_msg()
        marker.ns, marker.id = 'approach_candidate', 0
        marker.action = Marker.DELETE
        candidate, reason = None, 'map_or_time_unavailable'
        if payload.get('map_transform_valid') and -0.1 <= age <= 1.5:
            robot = payload.get('observer_position_map')
            persons = payload.get('persons', [])
            if robot is not None and persons:
                person = max(persons, key=lambda p: p.get('bbox_confidence', 0.0))
                candidate, reason = approach_candidate(
                    person, robot, float(node.get_parameter('standoff_m').value))
        if candidate:
            marker.action, marker.type = Marker.ADD, Marker.ARROW
            marker.pose.position.x, marker.pose.position.y = candidate['target_xy_map']
            # Display height only; no unverified ground height enters navigation.
            marker.pose.position.z = 0.10
            yaw = candidate['target_yaw']
            marker.pose.orientation.z = math.sin(yaw / 2)
            marker.pose.orientation.w = math.cos(yaw / 2)
            marker.scale.x, marker.scale.y, marker.scale.z = 0.6, 0.10, 0.15
            marker.color.r, marker.color.g, marker.color.b, marker.color.a = 1.0, 0.5, 0.0, 1.0
            marker.lifetime = Duration(seconds=1.5).to_msg()
        pub.publish(marker)
        data = {'reason': reason, 'candidate': candidate, 'observation_age_sec': age,
                'source_stamp': payload.get('source_stamp'),
                'stamp_ns': payload.get('stamp_ns'),
                'published_stamp_ns': node.get_clock().now().nanoseconds,
                'navigation_ready': False, 'collision_checked': False,
                'note': 'display only; requires costmap/path and motion authorization'}
        status.publish(String(data=json.dumps(data)))

    node.create_subscription(String, '/perception/pose_observation_3d', receive, 1)
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
