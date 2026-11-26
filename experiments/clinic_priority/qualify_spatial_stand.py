"""Screen A-area targets with Nav2, then physically rehearse one new stand."""
import argparse
import json
import math
import os
from pathlib import Path
import sys
import time

from factorial import WORKSPACE, benchmark, READ, WRITE
from qualify_epw2 import SOURCE


ROBOT = 'r1'
JOB = 'QA_verify_stand'
ORIGIN = 'V3'
ENDPOINT_TOLERANCE = 0.12


def points(anchors):
    yaw = anchors['V1'][2]
    return [
        dict(id='V1', label='预登记核验点', pose=anchors['V1'], kind='baseline'),
        dict(id='A_VERIFY_S', label='核验点南侧备选', pose=[14.50, -14.30, yaw], kind='alternative'),
        dict(id='A_VERIFY_E', label='核验点东侧备选', pose=[15.40, -13.70, yaw], kind='alternative'),
        dict(id='A_WALL_CONTROL', label='占用栅格负对照', pose=[18.00, -13.80, yaw], kind='negative'),
    ]


def screen_passed(status, samples, endpoint_error, length):
    return (status == 4 and samples >= 2 and endpoint_error is not None
            and math.isfinite(endpoint_error) and endpoint_error <= ENDPOINT_TOLERANCE
            and math.isfinite(length) and length > 0)


def execution_checks(record, feedback, target):
    attempts = record.get('navigation_attempts', [])
    final = attempts[-1] if attempts else {}
    arrival = record.get('arrival', {})
    stable_at = record.get('stable_at', -1.)
    tokens = [row for row in feedback if row.get('task_id') == record.get('task_id')
              and row.get('robot') == ROBOT and row.get('attempt') == 1]
    states = [row['phase'] for row in tokens]
    expected = dict(zip(('x', 'y', 'yaw'), target))
    return dict(
        tracking=(final.get('status') == 4 or
                  (final.get('status') == 5 and bool(final.get('handoff')))),
        stable_arrival=(bool(final.get('arrival_guard_passed'))
            and stable_at - record.get('stable_since', math.inf) >= .7 - 1e-6
            and arrival.get('position_error', math.inf) <= .20
            and arrival.get('yaw_error', math.inf) <= .30
            and all(0 <= arrival.get(field, math.inf) <= .5 for field in ('tf_age','odom_age','scan_age'))),
        target_identity=record.get('target') == expected and record.get('robot') == ROBOT,
        worker_ack=(states == ['started', 'succeeded'] and record.get('status') == 'SUCCEEDED'
            and stable_at <= record.get('service_started', -2.) < record.get('service_finished', -2.)
            and tokens[0]['at'] < tokens[1]['at']),
    )


def publish(out, result):
    record = result['record']
    path_rows = result['screen']
    actual = dict(status=result['execution_status'], selected=result['selected'],
        failure=result.get('failure'), checks=result['execution_checks'],
        follow=[dict(status=a.get('status'), begin=a.get('begin'), end=a.get('end'))
                for a in record.get('navigation_attempts', [])],
        stable=record.get('stable_at'), stableDuration=(record['stable_at']-record['stable_since']
                if 'stable_at' in record else None), serviceStart=record.get('service_started'),
        serviceFinish=record.get('service_finished'), arrival=record.get('arrival'),
        workerFeedback=[f['phase'] for f in result['feedback']], track=result['track'],
        task=record.get('task_id'))
    WRITE(out/'viewer.json', dict(schema='clinic-spatial-stand/v1', run=out.name,
        robot=ROBOT, origin=result['start'], candidates=path_rows, actual=actual,
        evidence={name:benchmark.sha(out/name) for name in
                  ('fixture.json','summary.json','trace.jsonl','cleanup.json')}))


def run(out, domain):
    sys.path[:0] = [str(WORKSPACE), str(WORKSPACE/'tools')]
    import dense_tasks as dt
    from nav2_msgs.action import ComputePathToPose
    import rclpy
    from rclpy.executors import SingleThreadedExecutor
    from std_msgs.msg import String
    from support.clinic_runtime import episode as bed
    from support.clinic_runtime.__main__ import require_static, runtime_gate
    from support.clinic_runtime.config import prepare
    from clinic_visual_world import visual_world
    import yaml

    bed.configure_research_backend()
    cfg = dt.config()
    candidates = points(cfg['anchors'])
    captured = READ(SOURCE/'result.json')
    station_snapshot = dict(captured['protocol'])
    history = captured['completed']
    poses = {r: [history[j]['ground_truth'][k] for k in ('x','y','yaw')]
             for r,j in (('r1','C0_r1_W2'),('r2','C0_r2_W2'),('r3','C0_r3_W1'))}
    out.mkdir(parents=True, exist_ok=False)
    WRITE(out/'poses.json', poses)
    WRITE(out/'fixture.json',dict(source_run=SOURCE.name, source_sha256=benchmark.sha(SOURCE/'result.json'),
        poses=poses,event=station_snapshot['event']['space'], candidates=candidates,
        selection='first alternative passing current Nav2 query, in the stated order',
        gate='finite nonempty GridBased path with endpoint error at most 0.12 m',
        rehearsal='native three-second spatial_rehearsal, stationary peers, no shared service lease'))
    require_static(out)
    for robot, path in prepare(out/'prepared').items():
        path = Path(path)
        config = yaml.safe_load(path.read_text())
        x,y,yaw = poses[robot]
        config['amcl']['ros__parameters']['initial_pose'] = dict(x=x,y=y,z=0.,yaw=yaw)
        path.write_text(yaml.safe_dump(config,sort_keys=False))
    os.environ['CLINIC_PROBE_POSES'] = str(out/'poses.json')
    result = dict(screen=[], start=poses[ROBOT], selected=None, execution_status='NOT_RUN',
        execution_checks={}, record={}, feedback=[], track=[], failure=None)
    with visual_world(out,domain,out/'prepared'):
        try:
            runtime_gate(out,120.)
        except RuntimeError:
            checks = READ(out/'runtime_preflight.json')['robots']
            failed = [k for check in checks.values() for k,v in check.items() if not v]
            if not failed or any(not k.startswith('live:') for k in failed):
                raise
            retry = out/'runtime_recheck'
            retry.mkdir()
            runtime_gate(retry,120.)
        rclpy.init()
        args = argparse.Namespace(reference=None,arrival='pose_handoff',parking='dense_cycle',
                   localization='reference',mode='normal',policy='fixed',changes='none')
        c = bed.Episode(out,args)
        ex = SingleThreadedExecutor()
        ex.add_node(c)
        for rid,anchor in {'r1':ORIGIN,'r2':'CPW2','r3':'CTLR3'}.items():
            peer = bed.Bot(rid,c)
            peer.anchor = anchor
            c.peers[rid] = peer
            ex.add_node(peer)
        b = c.peers[ROBOT]
        last = last_pose = -1.

        def wait(test, timeout, move=False):
            nonlocal last,last_pose
            deadline = time.monotonic() + timeout
            while not test():
                if c.failed:
                    raise RuntimeError(c.failed)
                if time.monotonic() > deadline:
                    raise TimeoutError('Spatial qualification wait')
                ex.spin_once(timeout_sec=.02)
                if c.epoch is None or c.elapsed()-last < .05:
                    continue
                last = c.elapsed()
                c.update_motion()
                c.update_neck()
                if move:
                    b.step()
                    if last-last_pose>=.4:
                        last_pose=last
                        pose=c.truth[ROBOT]
                        result['track'].append([round(last,2),round(pose['x'],3),round(pose['y'],3)])
                        c.log('pose_sample',poses={r:v.pose() for r,v in c.peers.items()},truth=c.truth)

        try:
            wait(lambda:len(c.truth)==3 and all(v.ready() for v in c.peers.values()),55.)
            if any(math.dist((v['x'],v['y']),poses[r][:2])>.15 for r,v in c.truth.items()):
                raise ValueError('Measured spawn differs from the stated fixture')
            c.epoch = c.now()
            c.proto_pub.publish(String(data=json.dumps(station_snapshot)))
            wait(lambda:c.elapsed()>4.,15.)
            for candidate in candidates:
                goal = ComputePathToPose.Goal()
                goal.use_start = False
                goal.planner_id = 'GridBased'
                goal.goal.header.frame_id = 'map'
                goal.goal.header.stamp = b.get_clock().now().to_msg()
                x,y,yaw = candidate['pose']
                goal.goal.pose.position.x,goal.goal.pose.position.y = x,y
                goal.goal.pose.orientation.z,goal.goal.pose.orientation.w = math.sin(yaw/2),math.cos(yaw/2)
                future = b.path_action.send_goal_async(goal)
                wait(future.done,10.)
                handle = future.result()
                status, path = None, []
                if handle.accepted:
                    future = handle.get_result_async()
                    wait(future.done,15.)
                    reply = future.result()
                    status = reply.status
                    path = [(p.pose.position.x,p.pose.position.y) for p in reply.result.path.poses]
                length = sum(math.dist(a,d) for a,d in zip(path,path[1:]))
                endpoint = math.dist(path[-1],(x,y)) if path else None
                row = dict(candidate,status=status,points=len(path),length=length,endpoint=endpoint,
                    passed=screen_passed(status,len(path),endpoint,length),queryAt=c.elapsed())
                result['screen'].append(row)
                c.log('stand_path_screen', **row)
            selected = next((r for r in result['screen'] if r['kind']=='alternative' and r['passed']),None)
            if selected:
                name,pose = selected['id'],selected['pose']
                result.update(selected=name, execution_status='ATTEMPTED')
                # Trial-only anchor and measured route prior for the native navigation budget.
                c.cfg['anchors'][name] = pose
                c.cfg['tables']['event'][ORIGIN][name] = 12. + selected['length']/.22
                task = dict(kind='normal',anchor=name,duration=3.,capabilities=['move','camera'],
                    release=0.,deadline=350.,resources=[],dependencies=[],service_role='spatial_rehearsal',
                    nominal_owner=ROBOT,cycle_id=0,waypoint=1,energy_rate=0.)
                c.tasks={JOB:dt.phases(task,c.cfg)}
                c.ledger={}
                c.plan=dict(starts={JOB:0.},finishes={},owners={JOB:ROBOT})
                c.plan_revision=1
                c.queues={r:([JOB] if r==ROBOT else []) for r in c.peers}
                c.dispatch_dense(b)
                wait(lambda:JOB in c.completed,180.,move=True)
            else:
                result['failure'] = 'NO_PATH_SCREENED_ALTERNATIVE'
        except Exception as error:
            result['failure'] = repr(error)
        finally:
            if c.records:
                result['record'] = c.records[0]
            for peer in c.peers.values():
                if peer.nav_handle and peer.state!='IDLE':
                    peer.nav_handle.cancel_goal_async()
                ex.remove_node(peer)
                peer.destroy_node()
            c.file.close()
            ex.remove_node(c)
            c.destroy_node()
            ex.shutdown()
            rclpy.try_shutdown()
    if result['selected']:
        with (out/'trace.jsonl').open() as log:
            feedback = [r['feedback'] for r in map(json.loads,log) if r['phase']=='service_feedback']
        target = next(r['pose'] for r in candidates if r['id']==result['selected'])
        result['feedback'] = feedback
        result['execution_checks'] = execution_checks(result['record'],feedback,target)
        result['execution_checks']['cleanup'] = READ(out/'cleanup.json')['passed']
        result['execution_status'] = ('PASS' if all(result['execution_checks'].values()) else 'FAIL')
    WRITE(out/'summary.json',benchmark.json_finite(result))
    publish(out,READ(out/'summary.json'))
    print(out, result['execution_status'], result['failure'], flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--domain',type=int,default=96)
    args = parser.parse_args()
    run(args.out.resolve(), args.domain)
