"""Pure forward-only jog gate. No ROS or hardware side effects.

This is one layer, NOT a replacement for a motor-driver watchdog or a mux.
An explicit new arm is required after every stop, fault or manual takeover.
"""
from dataclasses import dataclass
import math


def jog_displacement(origin, heading, position, yaw):
    """Project odometry into the initial robot-forward direction, not map X."""
    dx, dy = position[0]-origin[0], position[1]-origin[1]
    forward = dx*math.cos(heading) + dy*math.sin(heading)
    lateral = -dx*math.sin(heading) + dy*math.cos(heading)
    turn = math.atan2(math.sin(yaw-heading), math.cos(yaw-heading))
    return forward, lateral, turn


def left_foot_forward_target(payload, now_ns):
    """Fail-closed, single-person left ankle for a straight forward approach."""
    try:
        if not 0 <= (now_ns-int(payload['stamp_ns']))/1e9 <= .9:
            return None
        people = payload.get('persons', [])
        if len(people) != 1:
            return None
        joint = next(j for j in people[0]['joints'] if j['index'] == 15)
        xyz = joint.get('position_base')
        if (not joint.get('valid') or float(joint.get('confidence', 0)) < .6
                or not xyz or len(xyz) != 3 or not all(math.isfinite(v) for v in xyz)
                or not .1 < xyz[0] < 5 or abs(xyz[1]) > .15 or not -.05 < xyz[2] < .30
                or not math.isfinite(float(joint.get('position_std_m', 1)))
                or float(joint.get('position_std_m', 1)) > .10):
            return None
        return list(xyz)
    except (ValueError, KeyError, StopIteration, TypeError):
        return None


def left_foot_speed(x):
    if not math.isfinite(x) or x <= .85:
        return 0.0
    return .05 if x > 1.05 else .02


@dataclass(frozen=True)
class JogLimits:
    speed_mps: float = 0.02
    distance_m: float = 0.10
    duration_sec: float = 5.0
    command_timeout_sec: float = 0.25
    sensor_timeout_sec: float = 0.30
    clearance_m: float = 0.70


class JogGate:
    def __init__(self, limits=JogLimits()):
        values = vars(limits).values()
        if not all(math.isfinite(x) and x > 0 for x in values):
            raise ValueError('Limits must be finite and positive')
        if limits.speed_mps > 0.02 or limits.distance_m > 0.10 or limits.duration_sec > 5:
            raise ValueError('Initial jog hard limits exceeded')
        self.limits = limits
        self.armed = False
        self.reason = 'disarmed'
        self.started = self.last_request = -math.inf
        self.origin = None

    def stop(self, reason):
        self.armed, self.reason = False, reason
        return 0.0, reason

    def arm(self, now, xy):
        if not all(math.isfinite(v) for v in (now, *xy)):
            return self.stop('invalid_origin')
        self.started, self.origin = now, tuple(xy)
        # No old command may survive a new arm operation.
        self.last_request = -math.inf
        self.armed, self.reason = True, 'armed_waiting_request'

    def request(self, now):
        if self.armed and math.isfinite(now):
            self.last_request = now

    def evaluate(self, *, now, xy, odom_age, scan_age, clearance,
                 remote_age, remote_ok, brake_released, manual_neutral,
                 original_command_age, original_neutral):
        if not self.armed:
            return 0.0, self.reason
        numbers = (now, *xy, odom_age, scan_age, clearance, remote_age, original_command_age)
        if not all(math.isfinite(v) for v in numbers):
            return self.stop('invalid_sensor')
        if now < self.started:
            return self.stop('clock_reversed')
        if not remote_ok or not brake_released:
            return self.stop('remote_stop_or_failsafe')
        if not manual_neutral or not original_neutral:
            return self.stop('original_control_takeover')
        if any(not 0 <= age <= self.limits.sensor_timeout_sec
               for age in (odom_age, scan_age, remote_age, original_command_age)):
            return self.stop('sensor_or_remote_stale')
        if not 0 <= now - self.last_request <= self.limits.command_timeout_sec:
            return self.stop('request_expired')
        if clearance <= self.limits.clearance_m:
            return self.stop('obstacle')
        if now - self.started >= self.limits.duration_sec:
            return self.stop('duration_limit')
        if math.dist(xy, self.origin) >= self.limits.distance_m:
            return self.stop('distance_limit')
        self.reason = 'forward_jog_permitted'
        return self.limits.speed_mps, self.reason
