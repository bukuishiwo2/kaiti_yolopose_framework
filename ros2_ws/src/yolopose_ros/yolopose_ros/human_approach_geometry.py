"""Geometry for a display-only approach candidate on a locally flat floor."""
import math


def approach_candidate(person, robot_position, standoff_m=1.0):
    if not math.isfinite(standoff_m) or standoff_m < 0.7:
        raise ValueError('standoff_m must be finite and at least 0.7')
    ankles = [j['position_map'] for j in person.get('joints', [])
              if j.get('index') in (15, 16) and j.get('valid')
              and j.get('position_map') is not None]
    if not ankles:
        return None, 'ankles_unavailable'
    if len(robot_position) != 3 or any(len(p) != 3 for p in ankles):
        return None, 'invalid_coordinates'
    if not all(math.isfinite(float(v)) for p in [robot_position, *ankles] for v in p):
        return None, 'invalid_coordinates'
    foot = [sum(float(p[i]) for p in ankles) / len(ankles) for i in range(3)]
    dx, dy = float(robot_position[0]) - foot[0], float(robot_position[1]) - foot[1]
    distance = math.hypot(dx, dy)
    if distance <= standoff_m:
        return None, 'already_within_standoff'
    x, y = foot[0] + standoff_m * dx / distance, foot[1] + standoff_m * dy / distance
    return {'foot_anchor_map': foot, 'target_xy_map': [x, y],
            'target_yaw': math.atan2(foot[1] - y, foot[0] - x),
            'standoff_m': standoff_m, 'ankle_count': len(ankles)}, 'candidate_only'
