#!/usr/bin/env python3
"""A-only physical sequence/occupied-monitor qualification, original guards.

This is a spatial service rehearsal, not a visual fall or MILP experiment.
The monitor witness stays physically at M1 while the courier visits G1/H1.
No event or fall confirmation is injected. Original workers and leases execute.
"""
import argparse
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import sys
import time

P = Path(__file__).resolve().parents[1]
W = Path('/home/yhc/clinic_planning_ws')
sys.path[:0] = [str(P/'src'), str(W), str(W/'tools')]


def offline_check(cfg):
    from kaiti_task_sim.event_protocol import canonical
    anchors = ['V1', 'M1', 'H1', 'G1', 'AG1', 'CG1', 'TL', 'ETL', 'CTLR3']
    checks = {
        'all_anchors': all(a in cfg['anchors'] for a in anchors),
        'finite_directed_travel': all(math.isfinite(cfg['tables']['event'][a][b]) and
            cfg['tables']['event'][a][b] >= 0 for a in anchors for b in anchors),
        'G1_entry_clear': cfg['resource_phases']['G1']['entry'] == 'AG1' and
            cfg['resource_phases']['G1']['clear'] == 'CG1',
        'monitor_handoff_separation': math.dist(cfg['anchors']['M1'][:2], cfg['anchors']['H1'][:2]) > .75,
        'G1_phase_allowances': cfg['resource_phases']['G1']['approach'] > 0 and cfg['resource_phases']['G1']['egress'] > 0,
        'capabilities': 'camera' in cfg['capabilities']['r1'] and 'carry' in cfg['capabilities']['r2'],
    }
    return dict(passed=all(checks.values()), checks=checks,
        config_sha256=hashlib.sha256(canonical(cfg).encode()).hexdigest(),
        scope='structural/resource/travel checks; actual Nav2 queries precede movement')


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--gate', type=Path, required=True)
    ap.add_argument('--domain', type=int, default=97)
    ap.add_argument('--timeout', type=float, default=900.)
    ap.add_argument('--offline-only', action='store_true')
    a = ap.parse_args()
    from support.clinic_runtime import episode as bed
    from support.clinic_runtime.__main__ import require_static, runtime_gate, validate_smoke
    from support.clinic_runtime.config import prepare
    from clinic_visual_world import visual_world
    import dense_tasks as dt
    import rclpy
    from rclpy.executors import SingleThreadedExecutor
    from nav2_msgs.action import ComputePathToPose
    bed.configure_research_backend()
    cfg = dt.config()
    if json.loads((a.gate/'summary.json').read_text()).get('passed') is not True:
        raise RuntimeError('offline visual causal gate must pass')
    a.out.mkdir(parents=True, exist_ok=False)
    static = require_static(a.out)
    off = offline_check(cfg)
    (a.out/'offline.json').write_text(json.dumps(off, indent=2))
    if not off['passed']: raise RuntimeError('A structural qualification failed')
    if a.offline_only:
        print(json.dumps(off)); return 0
    prepare(a.out/'prepared')
    opts = argparse.Namespace(reference=None, arrival='pose_handoff', parking='dense_cycle',
        localization='reference', mode='normal', policy='milp', changes='none')
    result = dict(passed=False, status='NOT_RUN', path_queries=[], monitor_witness=[])
    with visual_world(a.out, a.domain, a.out/'prepared'):
        runtime_gate(a.out, 120., pulse=False)
        rclpy.init(); c = bed.Episode(a.out, opts)
        ex = SingleThreadedExecutor(); ex.add_node(c)
        for rid in cfg['robots']:
            b = bed.Bot(rid, c); c.peers[rid] = b; ex.add_node(b)
        begin = time.monotonic(); last = -1.
        def spin_until(predicate, seconds, move=False, monitor=False):
            nonlocal last
            deadline = time.monotonic()+seconds
            while not predicate():
                if c.failed: raise RuntimeError(c.failed)
                if time.monotonic()>deadline or time.monotonic()-begin>a.timeout:
                    raise TimeoutError('bounded A qualification')
                ex.spin_once(timeout_sec=.02)
                if not move or c.elapsed()-last<.05: continue
                last = c.elapsed(); c.update_motion(); c.update_neck()
                for peer in c.peers.values(): peer.step()
                if monitor:
                    b = c.peers['r1']; p = b.pose()
                    row = dict(at=c.elapsed(), pose=p, job=c.peers['r2'].job,
                        distance=math.dist([p['x'], p['y']], cfg['anchors']['M1'][:2]),
                        state=b.state, anchor=b.anchor)
                    result['monitor_witness'].append(row)
                    if row['distance']>.20: raise RuntimeError('monitor station drift')
        try:
            spin_until(lambda: len(c.truth)==3 and all(b.ready() for b in c.peers.values()), 90.)
            c.epoch=c.now(); c.publish()
            # Real planners, current occupancy. These are NOT service qualification.
            for rid, anchor in [('r1','V1'),('r1','M1'),('r2','AG1'),('r2','G1'),
                    ('r2','CG1'),('r2','H1'),('r1','TL'),('r2','G1'),('r3','TL')]:
                b=c.peers[rid]; goal=ComputePathToPose.Goal(); goal.use_start=False; goal.planner_id='GridBased'
                goal.goal.header.frame_id='map'; goal.goal.header.stamp=b.get_clock().now().to_msg()
                goal.goal.pose.position.x, goal.goal.pose.position.y=cfg['anchors'][anchor][:2]
                goal.goal.pose.orientation.w=1.
                f=b.path_action.send_goal_async(goal); spin_until(f.done,10.)
                h=f.result()
                if not h.accepted: raise RuntimeError('Nav2 query rejected')
                f=h.get_result_async(); spin_until(f.done,20.); r=f.result(); poses=r.result.path.poses
                error=math.dist([poses[-1].pose.position.x,poses[-1].pose.position.y],cfg['anchors'][anchor][:2]) if poses else None
                row=dict(robot=rid,anchor=anchor,status=r.status,points=len(poses),endpoint_error=error,
                    passed=r.status==4 and bool(poses) and error<=.12)
                result['path_queries'].append(row)
                if not row['passed']: raise RuntimeError('initial actual Nav2 path failure '+rid+':'+anchor)
            # First reproduce the proven three initial services/clear poses.
            initial,_=dt.cycle_tasks(0)
            c.tasks={j:t for j,t in initial.items() if t['waypoint']==1}
            sequence=[(j,t['nominal_owner'],False) for j,t in c.tasks.items()]
            def add(j,r,anchor,duration=1.,cargo=None):
                spec=dict(kind='normal', anchor=anchor,duration=duration,capabilities=['move'],release=0.,
                    deadline=1800.,resources=[anchor] if anchor in cfg['resource_phases'] else [],
                    dependencies=[],service_role='spatial_rehearsal',nominal_owner=r,cycle_id=0,waypoint=9,energy_rate=0.)
                if cargo: spec.update(cargo_role=cargo,cargo_group='A_qualification')
                c.tasks[j]=dt.phases(spec,cfg)
            add('QA_verify','r1','V1',3.)
            add('QA_monitor_station','r1','M1',2.)
            add('QA_pickup','r2','G1',8.,'pickup')
            add('QA_deliver','r2','H1',6.,'drop')
            add('QA_courier_return','r2','G1')
            add('QA_monitor_return','r1','TL')
            add('QA_peer_return','r3','PW1')
            sequence += [('QA_verify','r1',False),('QA_monitor_station','r1',False),
                ('QA_pickup','r2',True),('QA_deliver','r2',True),('QA_courier_return','r2',True),
                ('QA_monitor_return','r1',False),('QA_peer_return','r3',False)]
            c.ledger={j:dict(state='READY',release=0.,cycle=0,nominal_owner=t['nominal_owner']) for j,t in c.tasks.items()}
            c.plan=dict(starts={j:0. for j in c.tasks},finishes={},ends={},owners={j:t['nominal_owner'] for j,t in c.tasks.items()},routes={r:[] for r in cfg['robots']})
            c.plan_revision=1
            for j,r,monitor in sequence:
                c.queues={rid:([j] if rid==r else []) for rid in cfg['robots']}
                c.dispatch_dense(c.peers[r])
                spin_until(lambda:j in c.completed, a.timeout, move=True,monitor=monitor)
                (a.out/'progress.json').write_text(json.dumps(dict(completed=list(c.completed),latest=c.completed[j]),indent=2))
            result.update(records=c.records,resource_events=c.resource_events,
                config_sha256=off['config_sha256'], tasks=c.tasks, completed=c.completed)
            result['arrival_audit']=validate_smoke(dict(result,passed=True))
            result['passed']=result['arrival_audit']['passed'] and bool(result['monitor_witness']) and not c.resource.get('owners') and not any(b.cargo for b in c.peers.values())
            result['status']='PASS' if result['passed'] else 'FAIL'
            # Only the separate saved-evidence auditor issues certificates,
            # after world cleanup and immutable summary/hash verification.
        except Exception as error:
            import traceback
            (a.out/'failure_traceback.txt').write_text(traceback.format_exc())
            result.update(status='FAIL',error=repr(error),records=c.records,resource_events=c.resource_events)
        finally:
            for b in c.peers.values():
                if b.nav_handle:b.nav_handle.cancel_goal_async()
            c.file.close()
            for b in c.peers.values():ex.remove_node(b);b.destroy_node()
            ex.remove_node(c);c.destroy_node();ex.shutdown();rclpy.try_shutdown()
            (a.out/'summary.json').write_text(json.dumps(result,indent=2))
    print(json.dumps({k:result[k] for k in ['passed','status']}));return 0 if result['passed'] else 1


if __name__=='__main__': raise SystemExit(main())
