import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'ros2_ws/src/yolopose_ros'))
from yolopose_ros.human_approach_geometry import approach_candidate


def person(x, y):
    return {'joints': [{'index': 15, 'valid': True, 'position_map': [x, y, 0.15]},
                       {'index': 16, 'valid': True, 'position_map': [x, y, 0.15]}]}


def test_standoff_and_facing_person():
    goal, reason = approach_candidate(person(4, 3), [0, 0, 0.04])
    assert reason == 'candidate_only'
    assert math.isclose(math.dist(goal['target_xy_map'], [4, 3]), 1)
    assert math.isclose(goal['target_yaw'], math.atan2(3, 4))
    assert goal['ankle_count'] == 2


def test_nearby_person_does_not_make_robot_retreat():
    assert approach_candidate(person(0.5, 0), [0, 0, 0])[1] == 'already_within_standoff'


def test_missing_or_nonfinite_ankles_rejected():
    assert approach_candidate({'joints': []}, [0, 0, 0])[0] is None
    assert approach_candidate(person(float('nan'), 0), [0, 0, 0])[0] is None
