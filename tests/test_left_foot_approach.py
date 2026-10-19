import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'ros2_ws/src/yolopose_ros'))
from yolopose_ros.motion_safety import left_foot_forward_target, left_foot_speed


def observation():
    return {'stamp_ns': 10_000_000_000, 'persons': [{'joints': [
        {'index': 15, 'valid': True, 'confidence': .98,
         'position_base': [3, .02, .07], 'position_std_m': .02},
        {'index': 16, 'valid': True, 'confidence': .98,
         'position_base': [3, .5, .07], 'position_std_m': .02}]}]}


def test_selects_left_ankle_not_right_or_average():
    assert left_foot_forward_target(observation(), 10_500_000_000) == [3, .02, .07]


@pytest.mark.parametrize('change', ['old', 'future', 'two_people', 'sideways', 'uncertain', 'invalid', 'nan'])
def test_ambiguous_or_unsafe_foot_is_not_a_target(change):
    d = observation()
    j = d['persons'][0]['joints'][0]
    if change == 'old': d['stamp_ns'] -= 1_000_000_000
    if change == 'future': d['stamp_ns'] += 1_000_000_000
    if change == 'two_people': d['persons'] *= 2
    if change == 'sideways': j['position_base'][1] = .3
    if change == 'uncertain': j['position_std_m'] = .2
    if change == 'invalid': j['valid'] = False
    if change == 'nan': j['position_base'][0] = float('nan')
    assert left_foot_forward_target(d, 10_500_000_000) is None


def test_speed_stages_and_standoff():
    assert left_foot_speed(3) == .05
    assert left_foot_speed(1) == .02
    assert left_foot_speed(.85) == 0
    assert left_foot_speed(float('nan')) == 0
