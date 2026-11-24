#!/usr/bin/env python3
"""Controlled physical TL/V3 clearance probe with courier held at actual H1.

Simulator placement is a labelled qualification setup, never a visual event or
restored execution ACK. Reuses original workers, guards, paths, leases and masks.
"""
import argparse
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
import time

P=Path(__file__).resolve().parents[1];W=Path('/home/yhc/clinic_planning_ws')
sys.path[:0]=[str(P/'src'),str(W),str(W/'tools')]


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--snapshot-run',type=Path,required=True);ap.add_argument('--out',type=Path,required=True)
    ap.add_argument('--domain',type=int,default=97);a=ap.parse_args();a.out.mkdir(parents=True,exist_ok=False)
    from support.clinic_runtime import episode as bed
    from support.clinic_runtime.__main__ import require_static,runtime_gate
    from support.clinic_runtime.config import prepare
    from clinic_visual_world import visual_world
    from kaiti_task_sim.clinic_visual_repair import monitor_clearance_task
    from kaiti_task_sim.event_protocol import canonical
    from audit_clinic_visual_positive import native_arrival
    import dense_tasks as dt
    import rclpy
    from rclpy.executors import SingleThreadedExecutor
    bed.configure_research_backend();cfg=dt.config()
    prior=json.loads((a.snapshot_run/'summary.json').read_text())
    if not all(prior['completed'].get(j,{}).get('status')=='SUCCEEDED' for j in ['E1_monitor','E1_deliver']):raise RuntimeError('real completed monitor/courier evidence required')
    poses={r:deepcopy(prior['completed'][j]['arrival_ground_truth']) for r,j in [('r1','E1_monitor'),('r2','E1_deliver')]}
    x,y,yaw=cfg['anchors']['CPW2C'];poses['r3']=dict(x=x,y=y,yaw=yaw)
    task=monitor_clearance_task(cfg);task['dependencies']=[]
    table=cfg['tables']['event'];pred=table['M1'][task['entry_anchor']]+task['approach']+task['duration']+task['egress']+8
    (a.out/'offline.json').write_text(json.dumps(dict(passed=math.isfinite(pred) and pred>0,task=task,projected_clear_duration=pred,
        placement=poses,scope='controlled qualification placement, not event injection or prior-state ACK restoration'),indent=2))
    require_static(a.out);prepare(a.out/'prepared')
    opts=argparse.Namespace(reference=None,arrival='pose_handoff',parking='dense_cycle',localization='reference',mode='normal',policy='milp',changes='none')
    result=dict(passed=False,status='NOT_RUN')
    with visual_world(a.out,a.domain,a.out/'prepared'):
        try:
            runtime_gate(a.out,120.,pulse=False)
        except RuntimeError:
            report=json.loads((a.out/'runtime_preflight.json').read_text())
            failed=[(r,k) for r,checks in report['robots'].items() for k,v in checks.items() if not v]
            if not failed or any(not k.startswith('live:') for _,k in failed):raise
            retry=a.out/'runtime_recheck_01';retry.mkdir()
            (retry/'reason.json').write_text(json.dumps(dict(failed=failed,action='one fresh-process full original gate; no weakened checks'),indent=2))
            runtime_gate(retry,60.,pulse=False)
        rclpy.init();c=bed.Episode(a.out,opts);ex=SingleThreadedExecutor();ex.add_node(c)
        for rid in cfg['robots']:
            b=bed.Bot(rid,c);c.peers[rid]=b;ex.add_node(b)
        begin=time.monotonic();last=-1.;witness=[]
        def spin_until(predicate,seconds,move=False):
            nonlocal last
            deadline=time.monotonic()+seconds
            while not predicate():
                if c.failed:raise RuntimeError(c.failed)
                if time.monotonic()>deadline:raise TimeoutError('bounded clearance probe')
                ex.spin_once(timeout_sec=.02)
                if not move or c.elapsed()-last<.05:continue
                last=c.elapsed();c.update_motion();c.update_neck()
                for b in c.peers.values():b.step()
                witness.append(dict(at=c.elapsed(),poses=deepcopy(c.truth),courier_state=c.peers['r2'].state))
        try:
            spin_until(lambda:len(c.truth)==3 and all(b.ready() for b in c.peers.values()),60.)
            # Setup only: no service/fall/semantic messages are sent here.
            placement=[]
            for rid,q in poses.items():
                req=f'name: "{rid}" position: {{x: {q["x"]} y: {q["y"]} z: 0.0}} orientation: {{z: {math.sin(q["yaw"]/2)} w: {math.cos(q["yaw"]/2)}}}'
                proc=subprocess.run(['ign','service','-s','/world/clinic_l1_three/set_pose','--reqtype','ignition.msgs.Pose','--reptype','ignition.msgs.Boolean','--timeout','5000','--req',req],capture_output=True,text=True,timeout=7.)
                ok=proc.returncode==0 and 'true' in proc.stdout;placement.append(dict(robot=rid,passed=ok,request=req,response=proc.stdout))
                if not ok:raise RuntimeError('qualification placement not ACKed')
            (a.out/'placement.json').write_text(json.dumps(placement,indent=2))
            spin_until(lambda:all(math.dist([c.truth[r]['x'],c.truth[r]['y']],[p['x'],p['y']])<.05 and
                c.peers[r].pose() and math.dist([c.peers[r].pose()['x'],c.peers[r].pose()['y']],[p['x'],p['y']])<.05 for r,p in poses.items()),20.)
            c.epoch=c.now();c.peers['r1'].anchor='M1';c.peers['r2'].anchor='H1';c.peers['r3'].anchor='CPW2C'
            c.tasks={'CLEAR_M1':task};c.ledger={};c.plan_revision=1
            c.plan=dict(starts={'CLEAR_M1':0.},finishes={'CLEAR_M1':pred},ends={},owners={'CLEAR_M1':'r1'},routes=dict(r1=['CLEAR_M1'],r2=[],r3=[]))
            c.queues=deepcopy(c.plan['routes']);c.publish();c.dispatch_dense(c.peers['r1'])
            spin_until(lambda:'CLEAR_M1' in c.completed,240.,move=True)
            rec=c.completed['CLEAR_M1']
            checks=dict(original_native_arrival_and_ACK=native_arrival(rec),
                real_TL_entry_clear_lease=rec.get('lease_released_at',-1)>=rec.get('clear_at',0)>rec.get('service_finished',1e9),
                final_V3=rec.get('final_anchor')=='V3',courier_stationary=bool(witness) and all(v['courier_state']=='IDLE' and math.dist([v['poses']['r2']['x'],v['poses']['r2']['y']],[poses['r2']['x'],poses['r2']['y']])<.05 for v in witness),
                resources_clear=not c.resource.get('owners'),no_event=c.protocol.event is None)
            result.update(passed=all(checks.values()),status='PASS' if all(checks.values()) else 'FAIL',checks=checks)
        except Exception as e:
            import traceback
            (a.out/'failure_traceback.txt').write_text(traceback.format_exc());result.update(status='FAIL',error=repr(e))
        finally:
            result.update(records=c.records,completed=c.completed,tasks=c.tasks,resource_events=c.resource_events,witness=witness,placement=poses,
                config_sha256=hashlib.sha256(canonical(cfg).encode()).hexdigest(),source_run=str(a.snapshot_run),wall_seconds=time.monotonic()-begin)
            c.file.close()
            for b in c.peers.values():
                if b.nav_handle:b.nav_handle.cancel_goal_async()
                ex.remove_node(b);b.destroy_node()
            ex.remove_node(c);c.destroy_node();ex.shutdown();rclpy.try_shutdown()
            (a.out/'summary.json').write_text(json.dumps(result,indent=2))
    if result['passed'] and json.loads((a.out/'cleanup.json').read_text()).get('passed'):
        cert=dict(passed=True,role='post_monitor_TL_V3_clearance',owner='r1',courier_held_at='H1',config_sha256=result['config_sha256'],
            evidence=str(a.out/'summary.json'),evidence_sha256=hashlib.sha256((a.out/'summary.json').read_bytes()).hexdigest(),
            scope='controlled physical TL/V3 service/clear sequence with r2 held at saved H1 pose; not general collision safety')
        (a.out/'certificate.json').write_text(json.dumps(cert,indent=2))
    print(json.dumps(dict(passed=result['passed'],status=result['status'])));return 0 if result['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
