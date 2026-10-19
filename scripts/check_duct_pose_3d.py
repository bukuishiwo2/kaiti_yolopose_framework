#!/usr/bin/env python3
"""Read-only live acceptance summary; source ROS and configure DDS first."""
import argparse
import json
import time

import rclpy
from std_msgs.msg import String


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--seconds', type=float, default=20)
    args = parser.parse_args()
    rclpy.init()
    node = rclpy.create_node('pose3d_acceptance_probe')
    samples = []

    def receive(msg):
        data = json.loads(msg.data)
        samples.append(data)
        people = [{
            'valid_joints': sum(bool(j.get('valid')) for j in p.get('joints', [])),
            'center_base': p.get('center_base'),
            'center_map': p.get('center_map'),
            'distance_planar_m': p.get('distance_planar_to_robot_m'),
        } for p in data.get('persons', [])]
        print(json.dumps({
            'age_ms': round((time.time_ns() - data['stamp_ns']) / 1e6, 1),
            'sync_ms': data.get('rgb_depth_delta_ms'),
            'map_valid': data.get('map_transform_valid'),
            'map_source': data.get('map_transform_source'),
            'persons': people,
        }, ensure_ascii=False), flush=True)

    node.create_subscription(String, '/perception/pose_observation_3d', receive, 10)
    start = time.monotonic()
    try:
        while time.monotonic() - start < args.seconds:
            rclpy.spin_once(node, timeout_sec=0.2)
        print(json.dumps({'messages': len(samples),
                          'samples_with_person': sum(bool(s.get('persons')) for s in samples),
                          'map_valid_samples': sum(bool(s.get('map_transform_valid')) for s in samples)}))
    finally:
        node.destroy_node()
        rclpy.shutdown()
    return 0 if samples else 1


if __name__ == '__main__':
    raise SystemExit(main())
