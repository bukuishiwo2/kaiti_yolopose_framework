#!/usr/bin/env python3
"""Read-only navigation gate. Never publishes velocity or sends an action goal."""
import argparse
import json
import time

import rclpy
from rclpy.action import get_action_names_and_types
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from std_msgs.msg import String
from tf2_msgs.msg import TFMessage


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--seconds', type=float, default=5)
    args = parser.parse_args()
    rclpy.init()
    node = rclpy.create_node('human_navigation_readonly_preflight')
    static_edges, dynamic_edges = set(), set()
    latest_candidate = {}

    def tf(msg, edges):
        for item in msg.transforms:
            edges.add((item.header.frame_id.lstrip('/'), item.child_frame_id.lstrip('/')))

    def candidate(msg):
        latest_candidate.clear()
        latest_candidate.update(json.loads(msg.data))

    static_qos = QoSProfile(depth=10, durability=DurabilityPolicy.TRANSIENT_LOCAL,
                            reliability=ReliabilityPolicy.RELIABLE)
    node.create_subscription(TFMessage, '/tf_static', lambda msg: tf(msg, static_edges), static_qos)
    node.create_subscription(TFMessage, '/tf', lambda msg: tf(msg, dynamic_edges), 100)
    node.create_subscription(String, '/perception/human_approach_candidate_status', candidate, 1)
    try:
        deadline = time.monotonic() + args.seconds
        while time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=0.1)
        actions = dict(get_action_names_and_types(node))
        topics = dict(node.get_topic_names_and_types())
        velocity_writers = [{'node': info.node_name, 'namespace': info.node_namespace}
                            for info in node.get_publishers_info_by_topic('/cmd_vel')]
        reasons = []
        if not any('nav2_msgs/action/NavigateToPose' in types for types in actions.values()):
            reasons.append('NAVIGATE_TO_POSE_UNAVAILABLE')
        if not any('nav2_msgs/action/ComputePathToPose' in types for types in actions.values()):
            reasons.append('PATH_PLANNER_UNAVAILABLE')
        if not any('costmap' in topic for topic in topics):
            reasons.append('COSTMAP_UNAVAILABLE')
        moving_edges = {('map', 'odom'), ('odom', 'base_footprint'), ('odom', 'base_link')}
        if static_edges & moving_edges:
            reasons.append('MOVING_CHAIN_HAS_STATIC_TF_REQUIRES_AUDIT')
        if static_edges & dynamic_edges:
            reasons.append('STATIC_DYNAMIC_TF_EDGE_CONFLICT')
        if velocity_writers:
            reasons.append('EXISTING_VELOCITY_WRITERS_ARBITRATION_UNVERIFIED')
        stamp = latest_candidate.get('stamp_ns', 0)
        age = (node.get_clock().now().nanoseconds - stamp) / 1e9
        if not latest_candidate.get('candidate') or not -0.15 <= age <= 1.0:
            reasons.append('FRESH_HUMAN_TARGET_UNAVAILABLE')
        if not latest_candidate.get('collision_checked'):
            reasons.append('TARGET_COLLISION_UNCHECKED')
        # This tool cannot validate hardware emergency-stop or deadman wiring.
        reasons.append('HARDWARE_STOP_AND_COMMAND_WATCHDOG_NOT_VERIFIED')
        print(json.dumps({'motion_allowed': False, 'reasons': reasons,
                          'actions': actions, 'static_edges': sorted(static_edges),
                          'dynamic_edges': sorted(dynamic_edges),
                          'velocity_writers': velocity_writers,
                          'candidate_age_sec': age if stamp else None,
                          'candidate': latest_candidate.get('candidate'),
                          'commands_sent': 0}, ensure_ascii=False, indent=2))
        return 2 if reasons else 0
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    raise SystemExit(main())
