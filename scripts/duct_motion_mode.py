#!/usr/bin/env python3
"""Scoped runtime-only motor experiment switch, with automatic restoration.

Run via the ROS wrapper as root for activate/restore. Vendor files never edited.
"""
import argparse
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import time

from duct_motion_baseline import verify

ROOT = Path('/home/duct/pose3d_motion_experiment')
OVERRIDE = Path('/run/systemd/system/robot-start.service.d/90-pose3d-motion.conf')
CONTENT = '[Service]\nExecStart=\nExecStart=/bin/bash /home/duct/start_duct_motion_experiment.sh base\nRestart=no\n'


def run(*args, check=True):
    return subprocess.run(args, check=check, capture_output=True, text=True)


def quiet(capture=False):
    import rclpy
    from geometry_msgs.msg import Twist
    from nav_msgs.msg import Odometry
    from sbus_tcp_process.msg import Sbus
    from rclpy.qos import qos_profile_sensor_data
    rclpy.init()
    n = rclpy.create_node('experiment_stationary_gate')
    data = {}
    samples = []
    def remote(m):
        channels = [int(x) for x in m.raw_channels]
        data['remote'] = (time.monotonic(), not (m.failsafe or m.frame_lost), channels)
        samples.append(channels)
    def command(m):
        values = (m.linear.x, m.linear.y, m.angular.z)
        data['command'] = (time.monotonic(), all(math.isfinite(x) and abs(x)<1e-5 for x in values))
    def odom(m):
        values = (m.twist.twist.linear.x, m.twist.twist.linear.y, m.twist.twist.angular.z)
        data['odom'] = (time.monotonic(), all(math.isfinite(x) and abs(x)<.01 for x in values))
    n.create_subscription(Sbus, '/sbus', remote, qos_profile_sensor_data)
    n.create_subscription(Twist, '/cmd_vel', command, 1)
    n.create_subscription(Odometry, '/mecanum_odometry', odom, qos_profile_sensor_data)
    start = time.monotonic()
    bad = False
    while time.monotonic()-start < 3:
        rclpy.spin_once(n, timeout_sec=.05)
        if any(not value[1] for value in data.values()):
            bad = True
    now = time.monotonic()
    ok = (not bad and all(k in data and now-data[k][0] < .3 for k in ('remote','command','odom'))
          and len(samples) >= 10)
    if capture and ok:
        neutral = samples[-1]
        ok = all(all(abs(a-b) <= 20 for a,b in zip(row,neutral)) for row in samples)
        if ok:
            (ROOT / 'neutral.json').write_text(json.dumps({'raw_channels': neutral, 'captured_time': time.time()}))
    elif ok:
        neutral = json.loads((ROOT / 'neutral.json').read_text())['raw_channels']
        ok = all(abs(a-b) <= 20 for a,b in zip(data['remote'][2],neutral))
    n.destroy_node()
    rclpy.try_shutdown()
    return ok


def prepare():
    verify()
    source = Path('/data/ductcleanrob/install/motor_driver/share/motor_driver/launch/base_robot.launch.py').read_text()
    old = "'M0601C_Motor_enabled': 'True'"
    anchor = '    ld.add_action(motor_driver)'
    if source.count(old) != 1 or source.count(anchor) != 1:
        raise RuntimeError('Unknown original base launch; refusing to transform')
    source = source.replace(old, "'M0601C_Motor_enabled': 'False'", 1)
    node = '''    ld.add_action(Node(
        executable='/home/duct/pose3d_motion_experiment/guarded_motor_source/build/duct_guarded_motor',
        name='M0601C_Motor', output='screen',
        parameters=[motor_driver_params, {'guarded_mode': True}], respawn=False))
'''
    source = source.replace(anchor, node + anchor, 1)
    (ROOT / 'guarded_base.launch.py').write_text(source)
    if not quiet(capture=True):
        raise RuntimeError('Neutral/stationary capture failed; no switch made')
    return {'prepared': True, 'hardware_mode_changed': False}


def activate():
    if os.geteuid() != 0:
        raise RuntimeError('Root required for scoped systemd switch')
    verify()
    if OVERRIDE.exists() or not (ROOT / 'guarded_base.launch.py').is_file():
        raise RuntimeError('Unexpected mode state')
    if time.time()-json.loads((ROOT/'neutral.json').read_text())['captured_time'] > 180 or not quiet():
        raise RuntimeError('Operator neutral/stationary gate failed')
    # Install recovery BEFORE changing the startup path. Timer retries if the
    # operator has not returned the sticks to neutral for safe restoration.
    run('systemd-run', '--collect', '--unit=pose3d-motion-auto-restore', '--on-active=120s',
        '--property=Restart=on-failure', '--property=RestartSec=5',
        '/bin/bash', '/home/duct/start_duct_motion_experiment.sh', 'mode', 'restore')
    OVERRIDE.parent.mkdir(parents=True, exist_ok=True)
    OVERRIDE.write_text(CONTENT)
    run('systemctl', 'daemon-reload')
    try:
        run('systemctl', 'restart', 'robot-start.service')
    except Exception:
        restore()
        raise
    return {'experimental_driver_started_zero_by_default': True, 'auto_restore_sec': 120}


def restore():
    if not OVERRIDE.exists():
        return {'already_original': True, **verify()}
    if OVERRIDE.read_text() != CONTENT:
        raise RuntimeError('Runtime override was changed; refusing destructive recovery')
    run('systemctl', 'stop', 'pose3d-motion-jog.service', check=False)
    time.sleep(.5)  # Independent driver lease expires before any switch.
    if not quiet():
        raise RuntimeError('Not neutral/stationary: remain zero-command in experiment; retry restoration')
    run('systemctl', 'stop', 'robot-start.service')
    shutil.copy2(OVERRIDE, ROOT / 'last_runtime_override.conf')
    OVERRIDE.unlink()  # Only this tool's exact, archived runtime file.
    run('systemctl', 'daemon-reload')
    run('systemctl', 'start', 'robot-start.service')
    run('systemctl', 'stop', 'pose3d-motion-auto-restore.timer', check=False)
    return {'restored_original_startup': True, **verify()}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['prepare', 'activate', 'restore'])
    args = parser.parse_args()
    print(json.dumps(globals()[args.action](), indent=2))


if __name__ == '__main__':
    main()
