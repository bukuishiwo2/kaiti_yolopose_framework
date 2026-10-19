#!/usr/bin/env python3
"""SHADOW ONLY: subscribes to live state, publishes JSON, never motor commands."""
import json
import math
import time

import rclpy
from geometry_msgs.msg import Twist, TwistStamped
from nav_msgs.msg import Odometry
from rclpy.qos import qos_profile_sensor_data
from rclpy.executors import ExternalShutdownException
from sensor_msgs.msg import LaserScan
from std_msgs.msg import Bool, String
from std_srvs.srv import Trigger
from sbus_tcp_process.msg import Sbus
from yolopose_ros.motion_safety import JogGate


def main():
    rclpy.init()
    node = rclpy.create_node('motion_guard_shadow')
    gate = JogGate()
    seen = {}
    state = dict(xy=(math.nan, math.nan), clearance=math.nan,
                 remote_ok=False, brake_released=False, neutral=False)
    status = node.create_publisher(String, '/research/motion/shadow_status', 1)

    def odom(msg):
        seen['odom'] = time.monotonic()
        state['xy'] = (msg.pose.pose.position.x, msg.pose.pose.position.y)

    def scan(msg):
        seen['scan'] = time.monotonic()
        # All-around clearance is conservative, not a verified swept footprint.
        values = [r for r in msg.ranges if math.isfinite(r) and msg.range_min <= r <= msg.range_max]
        state['clearance'] = min(values) if values else math.nan

    def remote(msg):
        seen['remote'] = time.monotonic()
        state['remote_ok'] = not (msg.failsafe or msg.frame_lost)

    def original(msg):
        seen['original'] = time.monotonic()
        values = (msg.linear.x, msg.linear.y, msg.linear.z,
                  msg.angular.x, msg.angular.y, msg.angular.z)
        state['neutral'] = all(math.isfinite(x) and abs(x) < 1e-5 for x in values)

    def brake(msg):
        state['brake_released'] = not msg.data
        if msg.data:
            gate.stop('remote_brake')

    def request(msg):
        age = (node.get_clock().now().nanoseconds - msg.header.stamp.sec * 10**9
               - msg.header.stamp.nanosec) / 1e9
        other = (msg.twist.linear.y, msg.twist.linear.z, msg.twist.angular.x,
                 msg.twist.angular.y, msg.twist.angular.z)
        if (msg.header.frame_id == 'base_link' and 0 <= age <= .25
                and math.isfinite(msg.twist.linear.x) and 0 < msg.twist.linear.x <= .02
                and all(math.isfinite(x) and x == 0 for x in other)):
            gate.request(time.monotonic())
        else:
            gate.stop('invalid_request')

    def arm(_req, response):
        gate.arm(time.monotonic(), state['xy'])
        response.success = gate.armed
        response.message = 'SHADOW ONLY; no hardware output; ' + gate.reason
        return response

    def tick():
        now = time.monotonic()
        age = lambda key: now - seen.get(key, -math.inf)
        velocity, reason = gate.evaluate(now=now, xy=state['xy'], odom_age=age('odom'),
            scan_age=age('scan'), clearance=state['clearance'], remote_age=age('remote'),
            remote_ok=state['remote_ok'], brake_released=state['brake_released'],
            manual_neutral=state['neutral'], original_command_age=age('original'),
            original_neutral=state['neutral'])
        ages = {key: round(now - value, 3) for key, value in seen.items()}
        data = {'shadow_only': True, 'motor_output_connected': False, 'commands_sent': 0,
                'proposed_forward_mps': velocity, 'reason': reason,
                'source_receive_ages_sec': ages, 'remote_ok': state['remote_ok'],
                'brake_released': state['brake_released'], 'original_neutral': state['neutral'],
                'clearance_m': state['clearance'] if math.isfinite(state['clearance']) else None}
        status.publish(String(data=json.dumps(data, allow_nan=False)))

    node.create_subscription(Odometry, '/mecanum_odometry', odom, qos_profile_sensor_data)
    node.create_subscription(LaserScan, '/scan', scan, qos_profile_sensor_data)
    node.create_subscription(Sbus, '/sbus', remote, qos_profile_sensor_data)
    node.create_subscription(Twist, '/cmd_vel', original, 1)
    node.create_subscription(Bool, '/motor_brake_mode', brake, 1)
    node.create_subscription(TwistStamped, '/research/motion/request', request, 1)
    node.create_service(Trigger, '/research/motion/shadow_arm', arm)
    node.create_timer(.05, tick)
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
