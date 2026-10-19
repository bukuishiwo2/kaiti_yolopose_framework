import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'ros2_ws/src/yolopose_ros'))
from yolopose_ros.motion_safety import JogGate, JogLimits
from yolopose_ros.motion_safety import jog_displacement
import math


def test_jog_uses_body_heading_not_world_x():
    f, l, turn = jog_displacement((1, 2), math.pi/2, (1, 2.04), math.pi/2)
    assert f == pytest.approx(.04)
    assert l == pytest.approx(0)
    assert turn == pytest.approx(0)


def test_jog_heading_wrap_does_not_fake_rotation():
    assert abs(jog_displacement((0, 0), math.pi-.01, (0, 0), -math.pi+.01)[2]) == pytest.approx(.02)


def ready():
    gate = JogGate()
    gate.arm(10, (0, 0))
    gate.request(10)
    return gate, dict(now=10.1, xy=(0.01, 0), odom_age=.02, scan_age=.02,
                     clearance=2.0, remote_age=.02, remote_ok=True,
                     brake_released=True, manual_neutral=True,
                     original_command_age=.02, original_neutral=True)


def test_forward_jog_is_bounded():
    gate, data = ready()
    assert gate.evaluate(**data) == (.02, 'forward_jog_permitted')


@pytest.mark.parametrize('key,value,reason', [
    ('now', 10.3, 'request_expired'),
    ('remote_ok', False, 'remote_stop_or_failsafe'),
    ('brake_released', False, 'remote_stop_or_failsafe'),
    ('manual_neutral', False, 'original_control_takeover'),
    ('original_neutral', False, 'original_control_takeover'),
    ('odom_age', .4, 'sensor_or_remote_stale'),
    ('scan_age', .4, 'sensor_or_remote_stale'),
    ('remote_age', .4, 'sensor_or_remote_stale'),
    ('original_command_age', .4, 'sensor_or_remote_stale'),
    ('clearance', .7, 'obstacle'),
    ('clearance', float('nan'), 'invalid_sensor'),
    ('xy', (.1, 0), 'distance_limit'),
    ('now', 9.9, 'clock_reversed'),
])
def test_fault_stops_and_latches(key, value, reason):
    gate, data = ready()
    good = data.copy()
    data[key] = value
    assert gate.evaluate(**data) == (0, reason)
    gate.request(10.1)
    assert gate.evaluate(**good) == (0, reason)


def test_duration_limit_cannot_be_extended_by_requests():
    gate, data = ready()
    data['now'] = 15
    gate.request(15)
    assert gate.evaluate(**data) == (0, 'duration_limit')


def test_rearm_does_not_reuse_command():
    gate, data = ready()
    gate.arm(10, (0, 0))
    assert gate.evaluate(**data) == (0, 'request_expired')


@pytest.mark.parametrize('limits', [JogLimits(speed_mps=.03), JogLimits(distance_m=.2),
                                    JogLimits(duration_sec=6), JogLimits(speed_mps=float('nan'))])
def test_hard_limits_cannot_be_relaxed(limits):
    with pytest.raises(ValueError):
        JogGate(limits)
