"""Independent evidence criteria for spatial station screening and service."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'experiments/clinic_priority'))
from qualify_spatial_stand import execution_checks, screen_passed


def test_path_screen_rejects_empty_and_off_target_path():
    assert screen_passed(4, 81, .12, 2.03)
    assert not screen_passed(6, 0, None, 0.)
    assert not screen_passed(4, 1, 0., 0.)
    assert not screen_passed(4, 81, .13, 2.03)


def test_tracking_arrival_and_ack_are_independent():
    target = [14.5,-14.3,1.27]
    record = dict(task_id='task',robot='r1',target=dict(zip(('x','y','yaw'),target)),
        navigation_attempts=[dict(status=5,handoff={'requested_at':5.},arrival_guard_passed=True)],
        stable_at=10.,stable_since=9.2,
        arrival=dict(position_error=.12,yaw_error=.08,tf_age=.03,scan_age=.08,odom_age=.03),
        status='SUCCEEDED',service_started=11.,service_finished=14.)
    feedback = [dict(task_id='task',robot='r1',attempt=1,phase=phase,at=stamp)
                for phase,stamp in [('started',21.),('succeeded',24.)]]
    assert all(execution_checks(record,feedback,target).values())
    missing = execution_checks(record,feedback[:1],target)
    assert missing['tracking'] and missing['stable_arrival'] and not missing['worker_ack']
    record['navigation_attempts'][0]['status'] = 6
    record['navigation_attempts'][0].pop('arrival_guard_passed')
    blocked = execution_checks(record,[],target)
    assert not any(blocked[k] for k in ('tracking','stable_arrival','worker_ack'))
