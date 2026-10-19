#!/usr/bin/env python3
"""One forward-only local jog; experimental motor endpoint ONLY.

Any SBUS channel change or original nonzero command latches an abort.
No navigation goal, original cmd_vel publisher, or brake release publisher.
"""
import argparse
import json
import math
import time
from pathlib import Path

import rclpy
from geometry_msgs.msg import Twist, TwistStamped
from nav_msgs.msg import Odometry
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import LaserScan
from sbus_tcp_process.msg import Sbus
from std_msgs.msg import Bool
from std_msgs.msg import String
from obstacle_dect_msgs.msg import AvoidanceDecision
from tf2_ros import Buffer, TransformListener
from yolopose_ros.motion_safety import jog_displacement, left_foot_forward_target, left_foot_speed


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--zero-only', action='store_true')
    parser.add_argument('--approach-left-foot', action='store_true')
    parser.add_argument('--neutral-file', required=True)
    parser.add_argument('--report', required=True)
    args = parser.parse_args()
    neutral = json.loads(Path(args.neutral_file).read_text())['raw_channels']
    rclpy.init()
    n = rclpy.create_node('bounded_guarded_jog')
    tf = Buffer()
    listener = TransformListener(tf, n)
    seen, state = {}, {'xy': None, 'yaw': None, 'vx': None, 'safe_scan': False, 'remote': False,
                       'original_zero': False, 'abort': None, 'clearance': None,
                       'left_foot': None, 'foot_source_ns': 0,
                       'vendor_avoidance_stop': False, 'vendor_avoidance_seen': False}
    pub = n.create_publisher(TwistStamped, '/research/motion/motor_request', 1)
    active = False

    def stamp_age(m):
        return (n.get_clock().now().nanoseconds - m.header.stamp.sec * 10**9 - m.header.stamp.nanosec) / 1e9

    def odom(m):
        if not 0 <= stamp_age(m) <= .30:
            return
        seen['odom'] = time.monotonic()
        state['xy'] = (m.pose.pose.position.x, m.pose.pose.position.y)
        q = m.pose.pose.orientation
        state['yaw'] = math.atan2(2*(q.w*q.z+q.x*q.y), 1-2*(q.y*q.y+q.z*q.z))
        state['vx'] = m.twist.twist.linear.x

    def remote(m):
        seen['remote'] = time.monotonic()
        state['remote'] = not (m.failsafe or m.frame_lost)
        changed = any(abs(int(a)-int(b)) > 20 for a, b in zip(m.raw_channels, neutral))
        if changed or not state['remote']:
            state['abort'] = 'operator_channel_change_or_failsafe'

    def original(m):
        seen['original'] = time.monotonic()
        values = (m.linear.x, m.linear.y, m.angular.z)
        state['original_zero'] = all(math.isfinite(v) and abs(v) < 1e-5 for v in values)
        if not state['original_zero']:
            state['abort'] = 'original_control_nonzero'

    def brake(m):
        if active and m.data:
            state['abort'] = 'original_brake'

    def foot(m):
        try:
            d = json.loads(m.data)
            if len(d.get('persons', [])) != 1:
                state['left_foot'] = None
                return
            # Never keep an old target when a valid new ankle is outside the
            # verified straight corridor. Brief low-confidence misses may use
            # the previous point only within BOTH source and receive deadlines.
            for j in d['persons'][0].get('joints', []):
                xyz_new = j.get('position_base')
                if j.get('index') == 15 and j.get('valid') and xyz_new and abs(xyz_new[1]) > .15:
                    state['left_foot'] = None
                    return
            xyz = left_foot_forward_target(d, n.get_clock().now().nanoseconds)
            if xyz is None:
                return
            state['left_foot'] = xyz
            state['foot_source_ns'] = int(d['stamp_ns'])
            seen['foot'] = time.monotonic()
        except (ValueError, KeyError, StopIteration, TypeError):
            return

    def avoidance(m):
        state['vendor_avoidance_seen'] = True
        seen['avoidance'] = time.monotonic()
        state['vendor_avoidance_stop'] = bool(m.stop_required or m.uturn_required)
        if active and state['vendor_avoidance_stop']:
            state['abort'] = 'vendor_avoidance_stop'

    def scan(m):
        state['safe_scan'] = False
        if not 0 <= stamp_age(m) <= .30:
            return
        try:
            t = tf.lookup_transform('base_link', m.header.frame_id, rclpy.time.Time()).transform
        except Exception:
            return
        # Verified installation is a level scan. Refuse a changed installation.
        if abs(t.rotation.x) > .001 or abs(t.rotation.y) > .001:
            return
        yaw = 2 * math.atan2(t.rotation.z, t.rotation.w)
        front, corridor = [], []
        for i, distance in enumerate(m.ranges):
            if not math.isfinite(distance) or not m.range_min <= distance <= m.range_max:
                continue
            angle = m.angle_min + i * m.angle_increment + yaw
            x = t.translation.x + distance * math.cos(angle)
            y = t.translation.y + distance * math.sin(angle)
            if math.cos(angle) > math.cos(math.radians(25)):
                front.append(x)
            if x >= t.translation.x and abs(y) <= .30:
                corridor.append(x)
        # No masking of any point in the forward swept strip. The old rear
        # near-point is excluded by direction, not by deleting a range band.
        state['clearance'] = min(corridor) if corridor else None
        state['safe_scan'] = len(front) >= 20 and bool(corridor) and min(corridor) > .80
        seen['scan'] = time.monotonic()

    n.create_subscription(Odometry, '/mecanum_odometry', odom, qos_profile_sensor_data)
    n.create_subscription(Sbus, '/sbus', remote, qos_profile_sensor_data)
    n.create_subscription(Twist, '/cmd_vel', original, 1)
    n.create_subscription(Bool, '/motor_brake_mode', brake, 1)
    n.create_subscription(LaserScan, '/scan', scan, qos_profile_sensor_data)
    n.create_subscription(String, '/perception/pose_observation_3d', foot, 1)
    n.create_subscription(AvoidanceDecision, '/avoidance/decision', avoidance, qos_profile_sensor_data)

    def ready():
        return (not state['abort'] and state['remote'] and state['original_zero']
                and state['safe_scan'] and state['xy'] is not None
                and all(math.isfinite(x) for x in state['xy'])
                and all(0 <= time.monotonic()-seen.get(k, -math.inf) <= .30
                        for k in ['odom', 'scan', 'remote', 'original'])
                and (not args.approach_left_foot or
                     (state['left_foot'] is not None and not state['vendor_avoidance_stop']
                      and time.monotonic()-seen.get('foot', -math.inf) <= .5
                      and 0 <= (n.get_clock().now().nanoseconds-state['foot_source_ns'])/1e9 <= .9
                      and (not state['vendor_avoidance_seen'] or time.monotonic()-seen.get('avoidance', -math.inf) <= .5))))

    def send(v):
        m = TwistStamped()
        m.header.frame_id = 'base_link'
        m.header.stamp = n.get_clock().now().to_msg()
        m.twist.linear.x = v
        pub.publish(m)

    result = {'nonzero_commands': 0, 'requested_limit_m': .05, 'speed_mps': .02,
              'operator_abort': 'any raw SBUS channel deviation >20', 'executed': False}
    result['odometry_trace'] = []
    if args.approach_left_foot:
        result.update(standoff_m=.85, max_distance_m=2.5, max_duration_sec=70,
                      requested_limit_m=2.5, speed_mps=.05, target_joint='left_ankle:15')
    try:
        start = time.monotonic()
        while time.monotonic()-start < 5:
            rclpy.spin_once(n, timeout_sec=.02)
            if args.execute or args.zero_only:
                send(0.)
        if not ready() or state['vx'] is None or abs(state['vx']) > .01:
            result['reason'] = 'preflight_not_ready'
        elif not args.execute:
            result['reason'] = 'zero_only_ready' if args.zero_only else 'preflight_ready_no_execution'
        else:
            subscribers = n.get_subscriptions_info_by_topic('/research/motion/motor_request')
            if len(subscribers) != 1 or subscribers[0].node_name != 'M0601C_Motor':
                raise RuntimeError('Experimental motor subscriber not uniquely verified')
            active = True
            result['executed'] = True
            origin = state['xy']
            heading = state['yaw']
            result['origin'] = origin
            result['initial_left_foot'] = state['left_foot']
            start = time.monotonic()
            next_decision = start
            while True:
                # Drain ROS continuously. Sleeping after a single callback
                # starves scan/odom/SBUS subscriptions and ages queued data.
                rclpy.spin_once(n, timeout_sec=.005)
                if time.monotonic() < next_decision:
                    continue
                next_decision = time.monotonic() + .05
                distance = math.dist(origin, state['xy'])
                result['odometry_trace'].append({'elapsed_sec': time.monotonic()-start,
                    'xy': state['xy'], 'vx_mps': state['vx'], 'distance_m': distance,
                    'left_foot': state['left_foot']})
                if not ready():
                    result['reason'] = state['abort'] or 'sensor_or_corridor_not_ready'
                    result['stop_source_receive_ages'] = {
                        k: time.monotonic()-v for k,v in seen.items()}
                    break
                forward, lateral, turn = jog_displacement(origin, heading, state['xy'], state['yaw'])
                if abs(lateral) > (.05 if args.approach_left_foot else .02) or abs(turn) > math.radians(5) or forward < -.01:
                    result['reason'] = 'direction_or_rotation_abort'
                    break
                if args.approach_left_foot and state['left_foot'][0] <= .85:
                    result['reason'] = 'left_foot_safe_standoff_reached'
                    break
                if time.monotonic()-start >= (70 if args.approach_left_foot else 2.0) or distance >= (2.5 if args.approach_left_foot else .04):
                    result['reason'] = 'short_jog_limit'
                    break
                send(left_foot_speed(state['left_foot'][0]) if args.approach_left_foot else .02)
                result['nonzero_commands'] += 1
            result['end_xy'] = state['xy']
            result['measured_distance_m'] = math.dist(origin, state['xy'])
    except (KeyboardInterrupt, Exception) as e:
        result['reason'] = 'interrupted:' + type(e).__name__ + ':' + str(e)
    finally:
        if (args.execute or args.zero_only) and rclpy.ok():
            stop_started = time.monotonic()
            next_zero = stop_started
            while time.monotonic()-stop_started < 1:
                rclpy.spin_once(n, timeout_sec=.005)
                if time.monotonic() >= next_zero:
                    send(0.)
                    next_zero = time.monotonic() + .05
            result['final_vx_mps'] = state['vx']
            result['settled_end_xy'] = state['xy']
            result['settled_left_foot'] = state['left_foot']
            if 'origin' in result:
                result['settled_distance_m'] = math.dist(result['origin'], state['xy'])
        result['last_state'] = state
        Path(args.report).write_text(json.dumps(result, indent=2, allow_nan=False))
        print(json.dumps(result, indent=2, allow_nan=False))
        n.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
