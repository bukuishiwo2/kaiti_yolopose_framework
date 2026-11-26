"""Isolate the shared EPW2 entry and execute the native service/clearance chain."""
import argparse
from copy import deepcopy
import json
import math
import os
from pathlib import Path
import sys
import time

from factorial import G1_HOLD, WORKSPACE, benchmark, READ, WRITE

JOB = 'C0_r3_W2'
SOURCE = WORKSPACE/'verification/online_pair_2026-11-26_07/fixed_a7'
ENTRY = 'EPW2'


def fixture(occupied):
    result = READ(SOURCE/'result.json')
    record, = [r for r in result['records'] if r['job_id'] == JOB]
    task = deepcopy(READ(SOURCE/'response/problem.json')['tasks'][JOB])
    task['dependencies'] = []  # Spawn at the measured clear pose after W1.
    with (SOURCE/'trace.jsonl').open() as log:
        samples = (json.loads(line) for line in log)
        sample = next(r for r in samples if r['phase']=='pose_sample' and r['episode_time'] >= record['begin'])
    poses = {r: [p[k] for k in ('x','y','yaw')] for r,p in sample['truth'].items()}
    if not occupied:
        poses['r1'] = READ(SOURCE/'runtime_scenario.json')['anchors']['V1']
    return task, poses, result['protocol'], sample['episode_time']


def execute(out, domain, occupied):
    sys.path[:0] = [str(WORKSPACE),str(WORKSPACE/'tools')]
    import rclpy
    from rclpy.executors import SingleThreadedExecutor
    from std_msgs.msg import String
    import yaml
    from audit_clinic_visual_positive import native_arrival
    from clinic_visual_world import visual_world
    from support.clinic_runtime import episode as bed
    from support.clinic_runtime.__main__ import require_static, runtime_gate
    from support.clinic_runtime.config import prepare

    task, poses, protocol, source_at = fixture(occupied)
    out.mkdir(parents=True, exist_ok=False)
    WRITE(out/'poses.json', poses)
    WRITE(out/'protocol.json', dict(occupied=occupied, snapshot_at=source_at, task=task,
        source=str(SOURCE), source_hashes={name:benchmark.sha(SOURCE/name) for name in
        ('trace.jsonl','result.json','runtime_scenario.json','response/problem.json')},
        event_space=protocol['event']['space'], reservation_seconds=G1_HOLD))
    bed.configure_research_backend()
    require_static(out)
    prepared = prepare(out/'prepared')
    for robot, path in prepared.items():
        path = Path(path)
        values = yaml.safe_load(path.read_text())
        x,y,yaw = poses[robot]
        values['amcl']['ros__parameters']['initial_pose'] = dict(x=x,y=y,z=0.,yaw=yaw)
        path.write_text(yaml.safe_dump(values,sort_keys=False))

    os.environ['CLINIC_PROBE_POSES'] = str(out/'poses.json')
    with visual_world(out,domain,out/'prepared'):
        try:
            runtime_gate(out,120.)
        except RuntimeError:
            checks = READ(out/'runtime_preflight.json')['robots']
            failed = [key for robot in checks.values() for key,passed in robot.items() if not passed]
            if not failed or any(not key.startswith('live:') for key in failed):
                raise
            retry = out/'runtime_recheck'
            retry.mkdir()
            runtime_gate(retry,120.)

        rclpy.init()
        args = argparse.Namespace(reference=None,arrival='pose_handoff',parking='dense_cycle',
                localization='reference',mode='event',policy='fixed',changes='reserved_G1')
        c = bed.Episode(out,args)
        c.tasks = {JOB:task}
        c.plan = dict(starts={JOB:0.},finishes={JOB:task['duration']},owners={JOB:'r3'})
        c.queues = {'r1':[],'r2':[],'r3':[JOB]}
        c.plan_revision = 1
        executor = SingleThreadedExecutor()
        executor.add_node(c)
        for robot, anchor in {'r1':'M1' if occupied else 'V1','r2':'CPW2','r3':'CTLR3'}.items():
            bot = bed.Bot(robot,c)
            bot.anchor = anchor
            c.peers[robot] = bot
            executor.add_node(bot)
        started = time.monotonic()
        reservation = dispatch_pose = None
        last = last_pose = -1.
        try:
            while time.monotonic()-started<250. and not c.failed and JOB not in c.completed:
                executor.spin_once(timeout_sec=.02)
                if c.epoch is None:
                    if len(c.truth)==3 and all(b.ready() for b in c.peers.values()):
                        if any(math.dist((v['x'],v['y']),poses[r][:2])>.15 for r,v in c.truth.items()):
                            raise ValueError('Gazebo spawn diverged from the fixture')
                        c.epoch=c.now()+1.
                        reservation=dict(action='block',resource='G1',start=c.epoch,
                                         finish=c.epoch+G1_HOLD,change_id='epw2-probe-G1')
                        c.pub.publish(String(data=json.dumps(reservation)))
                        # Keep the historical body mask; the probe does not issue emergency services.
                        c.proto_pub.publish(String(data=json.dumps(protocol)))
                        c.log('epw2_probe_ready',spawn_truth=c.truth,reservation=reservation)
                    continue
                now=c.elapsed()
                if now-last<.05:
                    continue
                last=now
                c.update_motion()
                c.update_neck()
                bot=c.peers['r3']
                bot.step()
                if now-last_pose>=.4:
                    c.log('pose_sample',poses={r:b.pose() for r,b in c.peers.items()},truth=c.truth)
                    last_pose=now
                if dispatch_pose is None and now>=4. and any(
                        b.get('change_id')==reservation['change_id'] and
                        all(b[k]==reservation[k] for k in ('start','finish','resource'))
                        for b in c.resource.get('blocked',[])):
                    dispatch_pose=deepcopy(c.truth)
                    c.dispatch_dense(bot)
        finally:
            record=c.records[0] if c.records else {}
            completed=c.completed.get(JOB)
            lease_ok=bool(completed and native_arrival(completed) and
                completed['gate_arrival'] <= completed['lease_granted_at'] <= completed['service_started'] <
                completed['service_finished'] < completed['clear_at'] <= completed['lease_released_at'] and
                not c.resource.get('owners'))
            WRITE(out/'result.json',benchmark.json_finite(dict(
                passed=lease_ok, occupied=occupied, reservation_ack=bool(dispatch_pose),
                failure=c.failed or (None if lease_ok else 'PROBE_UNFINISHED'),
                record=record, dispatch_pose=dispatch_pose, poses=poses, reservation=reservation)))
            c.file.close()
            for node in (*c.peers.values(),c):
                executor.remove_node(node)
                node.destroy_node()
            executor.shutdown()
            rclpy.try_shutdown()


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',required=True,type=Path)
    parser.add_argument('--domain',required=True,type=int)
    parser.add_argument('--condition',required=True,choices=('occupied','vacant'))
    args=parser.parse_args()
    execute(args.out.resolve(),args.domain,args.condition=='occupied')
