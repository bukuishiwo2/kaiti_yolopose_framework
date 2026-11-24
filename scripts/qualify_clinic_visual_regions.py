#!/usr/bin/env python3
"""One bounded world: qualify finite service anchors using existing Nav2 guards.

Not a visual emergency experiment. A failed qualification blocks the subsequent
visual episode; it never relaxes arrival/resource guards or declares point-map
clearance sufficient. Original runtime modules/configuration are read only.
"""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import time

PROJECT=Path(__file__).resolve().parents[1]
WORKSPACE=Path('/home/yhc/clinic_planning_ws')
sys.path[:0]=[str(PROJECT/'src'),str(WORKSPACE),str(WORKSPACE/'tools')]
from kaiti_task_sim.event_protocol import canonical


def main():
    p=argparse.ArgumentParser();p.add_argument('--gate',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--domain',type=int,default=94);p.add_argument('--timeout',type=float,default=650.)
    args=p.parse_args()
    gate=json.loads((args.gate/'summary.json').read_text())
    if gate.get('passed') is not True:raise RuntimeError('offline causal gate must pass')
    args.out.mkdir(parents=True,exist_ok=False)
    from support.clinic_runtime.__main__ import require_static,world,runtime_gate,validate_smoke
    from support.clinic_runtime.config import prepare
    from support.clinic_runtime import episode as bed
    import dense_tasks as dt
    import rclpy
    from rclpy.executors import SingleThreadedExecutor
    from nav2_msgs.action import ComputePathToPose
    bed.configure_research_backend()
    cfg=dt.config()
    require_static(args.out)
    prepared=prepare(args.out/'prepared')
    opts=argparse.Namespace(reference=None,arrival='pose_handoff',parking='dense_cycle',localization='reference',mode='normal',policy='milp',changes='none')
    result=dict(passed=False,status='NOT_RUN',records=[],path_queries=[])
    with world(args.out,args.domain,args.out/'prepared'):
        runtime_gate(args.out,120.,pulse=False)
        rclpy.init()
        c=bed.Episode(args.out,opts)
        ex=SingleThreadedExecutor();ex.add_node(c)
        for rid in cfg['robots']:
            b=bed.Bot(rid,c);c.peers[rid]=b;ex.add_node(b)
        def until(predicate,seconds):
            deadline=time.monotonic()+seconds
            while not predicate():
                if c.failed:raise RuntimeError(c.failed)
                if time.monotonic()>deadline:raise TimeoutError('qualification wait timeout')
                ex.spin_once(timeout_sec=.02)
        try:
            until(lambda:len(c.truth)==3 and all(b.ready() for b in c.peers.values()),90.)
            c.epoch=c.now();c.publish()
            # Query real planners from each robot's current localized start.
            anchors=['V1','M1','H1','DL','CDL','ADL','G1']
            for rid,b in c.peers.items():
                for anchor in anchors:
                    goal=ComputePathToPose.Goal();goal.use_start=False;goal.planner_id='GridBased'
                    goal.goal.header.frame_id='map';goal.goal.header.stamp=b.get_clock().now().to_msg()
                    goal.goal.pose.position.x,goal.goal.pose.position.y=cfg['anchors'][anchor][:2]
                    goal.goal.pose.orientation.w=1.
                    f=b.path_action.send_goal_async(goal);until(f.done,10.)
                    handle=f.result()
                    if not handle.accepted:raise RuntimeError('planner query rejected')
                    f=handle.get_result_async();until(f.done,20.)
                    r=f.result();poses=r.result.path.poses
                    import math
                    endpoint=math.dist((poses[-1].pose.position.x,poses[-1].pose.position.y),cfg['anchors'][anchor][:2]) if poses else 1e9
                    length=sum(math.hypot(q.pose.position.x-z.pose.position.x,q.pose.position.y-z.pose.position.y) for q,z in zip(poses,poses[1:]))
                    item=dict(robot=rid,anchor=anchor,status=r.status,points=len(poses),endpoint_error=endpoint,length=length,passed=r.status==4 and bool(poses) and endpoint<=.12)
                    result['path_queries'].append(item)
                    (args.out/'path_queries.json').write_text(json.dumps(result['path_queries'],indent=2))
                    if not item['passed']:raise RuntimeError('actual Nav2 target not reachable: '+rid+':'+anchor)
            # Visit all mapped role points, preserve original path/admission and
            # stable arrival/freshness/resource acquisition/clearance/service ACK.
            owners={'V1':'r3','M1':'r3','H1':'r2','DL':'r1','CDL':'r1','ADL':'r2','G1':'r2'}
            c.tasks={};c.ledger={};c.queues={r:[] for r in cfg['robots']}
            for i,anchor in enumerate(anchors):
                rid=owners[anchor];j='Q_'+anchor
                spec=dict(kind='normal',anchor=anchor,duration=1.,capabilities=['move'],release=0.,deadline=1800.,resources=[anchor] if anchor in cfg['resource_phases'] else [],dependencies=[],service_role='navigation_qualification',nominal_owner=rid,cycle_id=0,waypoint=i,energy_rate=0.)
                c.tasks[j]=dt.phases(spec,cfg);c.queues[rid].append(j)
                c.ledger[j]=dict(state='READY',release=0.,cycle=0,nominal_owner=rid)
            c.plan=dict(starts={j:0. for j in c.tasks},finishes={},ends={},
                owners={'Q_'+a:r for a,r in owners.items()},routes=deepcopy(c.queues))
            c.plan_revision=1
            start=time.monotonic();last=-1
            # Sequential jobs intentionally avoid declaring untested concurrent
            # docking safe. Existing peer keepouts and FIFO remain enabled.
            for anchor in anchors:
                rid=owners[anchor];j='Q_'+anchor;b=c.peers[rid]
                while j not in c.completed:
                    ex.spin_once(timeout_sec=.02)
                    if c.failed:raise RuntimeError(c.failed)
                    if time.monotonic()-start>args.timeout:raise TimeoutError('bounded qualification deadline')
                    if c.elapsed()-last<.05:continue
                    last=c.elapsed();c.update_motion();c.update_neck()
                    for peer in c.peers.values():peer.step()
                    if b.state=='IDLE' and j not in c.completed:c.dispatch_dense(b)
            result.update(passed=True,status='PASS',records=c.records,resource_events=c.resource_events,
                config_sha256=hashlib.sha256(canonical(cfg).encode()).hexdigest(),
                validated_anchors=anchors,scope='sequential docking/service only; concurrent region occupation NOT qualified')
            guard=validate_smoke(result);result['arrival_audit']=guard
            result['passed']=guard['passed']
            # Do not authorize visual concurrent monitor/courier from sequential visits.
            result['concurrent_resource_qualification']=False
        except Exception as error:
            import traceback
            (args.out/'failure_traceback.txt').write_text(traceback.format_exc())
            result.update(status='FAIL',error=repr(error),records=c.records,resource_events=c.resource_events)
        finally:
            for b in c.peers.values():
                if b.nav_handle:b.nav_handle.cancel_goal_async()
            c.file.close()
            for b in c.peers.values():ex.remove_node(b);b.destroy_node()
            ex.remove_node(c);c.destroy_node();ex.shutdown();rclpy.try_shutdown()
            (args.out/'summary.json').write_text(json.dumps(result,indent=2))
    print(json.dumps({k:result[k] for k in ['passed','status']}))
    return 0 if result['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
