#!/usr/bin/env python3
"""Isolated real-video -> MILP -> real Nav2/ACK verification experiment.

Original Episode.tick/observe and Bot.feedback are deliberately not called in
visual mode. Positive response requires a separate concurrent-resource certificate.
"""
import argparse
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

P=Path(__file__).resolve().parents[1];W=Path('/home/yhc/clinic_planning_ws')
sys.path[:0]=[str(P/'src'),str(W),str(W/'tools')]


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--gate',type=Path,required=True);ap.add_argument('--certificate',type=Path,required=True)
    ap.add_argument('--region',choices=['A','B'],required=True);ap.add_argument('--video',required=True)
    ap.add_argument('--verdict',type=Path,required=True)
    ap.add_argument('--out',type=Path,required=True);ap.add_argument('--domain',type=int,default=93)
    ap.add_argument('--timeout',type=float,default=420.)
    ap.add_argument('--cancel-verify-once',action='store_true',help='one actual FollowPath cancel/ACK/retry before verify service')
    ap.add_argument('--bed-repair',action='store_true',help='opt-in observed before-pickup bed disturbance and paired repair')
    ap.add_argument('--repair-budget',type=float,default=5.)
    ap.add_argument('--clearance-certificate',type=Path,help='actual post-monitor TL/V3 clearance with courier held at H1')
    a=ap.parse_args()
    from kaiti_task_sim.clinic_visual import (VisualEventBridge,compile_tasks,
        execution_tokens,execution_fence,transfer_guard,action_uuid_bytes)
    from kaiti_task_sim.event_protocol import canonical
    from support.clinic_runtime.__main__ import require_static,runtime_gate
    from clinic_visual_world import visual_world as world
    from support.clinic_runtime.config import prepare
    from support.clinic_runtime import episode as bed
    import dense_tasks as dt
    import rclpy
    from rclpy.executors import SingleThreadedExecutor
    from std_msgs.msg import String
    bed.configure_research_backend();cfg=dt.config()
    gate=json.loads((a.gate/'summary.json').read_text());cert=json.loads(a.certificate.read_text());review=json.loads(a.verdict.read_text())
    if gate.get('passed') is not True:raise RuntimeError('offline causal gate must pass')
    if not (cert.get('passed') is True and cert.get('region')==a.region and cert.get('config_sha256')==hashlib.sha256(canonical(cfg).encode()).hexdigest()):
        raise RuntimeError('navigation/service certificate does not match configuration and region')
    if review.get('video')!=a.video or review.get('result') not in {'fall','no_fall'} or not Path(review.get('evidence_id','')).is_file():
        raise RuntimeError('explicit matching review and saved evidence required')
    positive=review['result']=='fall'
    if positive and not cert.get('concurrent_resource_qualification'):
        raise RuntimeError('positive response requires full spatial rehearsal qualification')
    if positive:
        evidence=Path(cert['evidence'])
        if not (json.loads(evidence.read_text()).get('passed') is True and
                hashlib.sha256(evidence.read_bytes()).hexdigest()==cert.get('evidence_sha256')):
            raise RuntimeError('positive qualification audit missing or changed')
        if hashlib.sha256(Path(review['evidence_id']).read_bytes()).hexdigest()!=review.get('evidence_sha256'):
            raise RuntimeError('explicit reviewed frames changed')
    clearance_cert=None
    if a.bed_repair:
        if not a.clearance_certificate:raise RuntimeError('bed mode requires actual post-monitor clearance qualification')
        clearance_cert=json.loads(a.clearance_certificate.read_text())
        evidence=Path(clearance_cert['evidence'])
        if not (clearance_cert.get('passed') and clearance_cert.get('config_sha256')==cert['config_sha256'] and
            clearance_cert.get('owner')=='r1' and clearance_cert.get('courier_held_at')=='H1' and
            hashlib.sha256(evidence.read_bytes()).hexdigest()==clearance_cert['evidence_sha256'] and json.loads(evidence.read_text()).get('passed')):
            raise RuntimeError('post-monitor clearance certificate missing, changed or mismatched')
    a.out.mkdir(parents=True,exist_ok=False)
    (a.out/'review.json').write_text(json.dumps(review,indent=2))
    (a.out/'certificate.json').write_text(json.dumps(cert,indent=2))
    if clearance_cert:(a.out/'clearance_certificate.json').write_text(json.dumps(clearance_cert,indent=2))
    paths=[Path(__file__),P/'src/kaiti_task_sim/clinic_visual.py',P/'src/kaiti_task_sim/event_protocol.py']+list((P/'scripts').glob('clinic_visual_*.py'))
    if a.bed_repair:paths.append(P/'src/kaiti_task_sim/clinic_visual_repair.py')
    manifest={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    (a.out/'visual_source_manifest.json').write_text(json.dumps(manifest,indent=2))

    class VisualEpisode(bed.Episode):
        def __init__(self,out,opts):
            super().__init__(out,opts)
            if a.bed_repair:
                from kaiti_task_sim.clinic_visual_repair import RegisteredVideoProtocol
                from kaiti_task_sim.clinic_visual import registered_space
                self.bridge=VisualEventBridge(self.cfg,a.region,source_id=a.video,protocol_type=RegisteredVideoProtocol)
                space=registered_space(self.cfg,a.region)
                reg=dict(schema='video-region-registration/v1',id=a.out.name+':A:v1',source='qualified_scenario_registration',
                    config_sha256=cert['config_sha256'],region=a.region,valid=True,issued_at=0.,valid_until=float(self.cfg['horizon']),
                    event_xy=space['event_xy'],service_points=space['service_points'],evidence=str(a.certificate))
                self.bridge.protocol.set_registration(reg,0.)
                self.log('explicit_spatial_registration',registration=reg)
            else:self.bridge=VisualEventBridge(self.cfg,a.region,source_id=a.video)
            self.protocol=self.bridge.protocol  # exactly one event-task owner
            self.meta={};self.model_seen=set();self.pending_visual=False;self.model_rows=[]
            self.response_submitted=False;self.online_checks=[];self.next_online_check=0.;self.nav_cancel_tested=False
            self.tasks={j:t for j,t in self.tasks.items() if t['waypoint']==1}
            self.ledger={j:v for j,v in self.ledger.items() if j in self.tasks}
            self.create_subscription(String,'/clinic_visual/replay_metadata',self.on_meta,100)
            self.create_subscription(String,'/clinic_visual/model',self.on_model,100)
        def inject_event(self):raise RuntimeError('direct event injection disabled in visual mode')
        def observe(self):raise RuntimeError('fabricated periodic observation disabled in visual mode')
        def on_meta(self,msg):
            m=json.loads(msg.data)
            if m['source_id']==a.video and m['region']==a.region:
                self.meta[m['ros_stamp_ns']]=m
                while len(self.meta)>1000:self.meta.pop(next(iter(self.meta)))
        def on_model(self,msg):
            r=json.loads(msg.data);stamp=r.get('source_ros_stamp_ns')
            if self.epoch is None or self.elapsed()<0 or stamp not in self.meta or stamp in self.model_seen:return
            m=self.meta.pop(stamp);self.model_seen.add(stamp);now=self.elapsed()
            age=time.monotonic()-m['published_monotonic']
            s=dict(sample_id=m['sample_id'],source_id=a.video,source_at=now-age,
                score=r['seq_fall_score'],stable=r['seq_stable_fall_detected'],window_ready=r['seq_window_ready'],
                video_time=m['video_time'],ros_stamp_ns=stamp,registration_mode=m['registration_mode'])
            transition=self.bridge.observe(s,now)
            self.log('visual_model_transition',sample=s,model_latency=age,transition=transition)
            self.model_rows.append(s)
            if self.protocol.event and self.event_at is None:
                self.event_at=now;self.pending_visual=True
                active={b.job for b in self.peers.values() if b.job}
                self.deferred=[j for j in self.normal_pending() if j not in active]
                self.log('visual_candidate_created',event_id='E1',caused_by=s['sample_id'],deferred=self.deferred)
            self.tasks.update(compile_tasks(self.protocol.planning_view(),now,self.cfg,a.region,dt.phases,cert))
            self.publish()
        def submit_dense(self,stage):
            if stage!='response':
                super().submit_dense(stage)
            else:
                # Same original bed MILP/constraints, finite short-mode backlog.
                # No 900s future cycle is inserted into frozen original modes.
                future,_=dt.cycle_tasks(0)
                j='C0_r3_W2';self.tasks[j]=future[j]
                self.ledger[j]=dict(state='READY',release=self.tasks[j]['release'],cycle=0,nominal_owner='r3')
                now=self.elapsed();states=self.states();active={b.job for b in self.peers.values() if b.job}
                pending=[j for j in self.normal_pending() if j not in active]
                p=dt.problem(self.cfg,self.tasks,pending+['E1_monitor','E1_pickup','E1_deliver'],self.completed,states,self.plan,now,self.event_at,'response')
                p.update(stage='bed_response',necessary_normal='C0_r3_W2')
                folder=self.out/f'{len(self.planning_records):02d}_response';folder.mkdir()
                req=folder/'request.json';req.write_text(json.dumps(dict(variants=[p]),indent=2))
                output=folder/'result.json';log=(folder/'worker.log').open('w')
                proc=subprocess.Popen([str(P/'.venv/bin/python'),str(W/'tools/bed_initial_solver.py'),str(req),str(output)],stdout=log,stderr=subprocess.STDOUT)
                self.planning=dict(stage=stage,folder=folder,output=output,process=proc,log=log,at=now,wall=time.monotonic(),states=states)
                self.log('planning_requested',stage=stage,active_prefix=sorted(active),known_future_tasks=[],short_backlog=pending)
            if self.planning:
                ids=[t['protocol_task_id'] for t in self.tasks.values() if t.get('protocol_task_id') and self.protocol.tasks[t['protocol_task_id']]['state'] in {'READY','PENDING'}]
                self.planning['visual_tokens']=execution_tokens(self.protocol,ids)
        def poll_dense(self):
            q=self.planning
            if q and q['process'].poll() is not None:
                check=execution_fence(self.protocol,q.get('visual_tokens',{}))
                self.log('visual_plan_fence',check=check,tokens=q.get('visual_tokens',{}))
                if not check['passed']:
                    q['log'].close();self.failed='STALE_VISUAL_PLAN';return
            return super().poll_dense()
        def dispatch_dense(self,b):
            if any(hashlib.sha256(Path(path).read_bytes()).hexdigest()!=h for path,h in manifest.items()):
                self.failed='VISUAL_SOURCE_CHANGED_AFTER_GATE';return
            q=[j for j in self.queues.get(b.rid,[]) if j not in self.completed]
            if q and self.tasks[q[0]].get('protocol_task_id'):
                spec=self.tasks[q[0]];proto=self.protocol.tasks[spec['protocol_task_id']]
                if not spec.get('execution_authorized'):self.failed='SPATIAL_EXECUTION_NOT_QUALIFIED';return
                if b.rid not in cert.get('qualified_robots',{}).get(spec['kind'],[b.rid]):
                    self.failed='SPATIAL_ROBOT_NOT_QUALIFIED';return
                if proto['state']!='READY' or proto['revision']!=spec['protocol_revision']:return
            return super().dispatch_dense(b)
        def tick(self):
            now=self.elapsed();self.update_motion();self.update_neck();self.bridge.tick(now);self.publish()
            self.poll_dense()
            if self.failed:return
            if any(t['state']=='CANCEL_REQUESTED' for t in self.protocol.tasks.values()):
                # Never fake an ACK or release monitor/custody. This first mode
                # stops safely for an explicit cancellation/recovery experiment.
                self.failed='OBSERVATION_EXPIRED_REQUIRES_CANCELLATION_ACK';return
            if self.pending_visual and not self.planning:
                self.pending_visual=False;self.submit_dense('verify')
            if 'E1_verify' in self.completed and not self.planning:
                if self.protocol.event['lifecycle']=='CLOSED':
                    self.finished=all(b.state=='IDLE' for b in self.peers.values())
                elif self.protocol.event['verified'] and not self.response_submitted:
                    if not cert.get('concurrent_resource_qualification'):
                        self.failed='RESPONSE_REQUIRES_CONCURRENT_RESOURCE_QUALIFICATION';return
                    self.response_submitted=True;self.submit_dense('response')
            if positive and 'E1_deliver' in self.completed and not self.handover_ack and now-self.completed['E1_deliver']['end']>=3.:
                self.handover_ack=True
                self.log('scripted_handover_ack',event_id='E1',source='controlled scenario service receiver after actual delivery ACK; not fall inference')
            if positive and self.protocol.event and now>=self.next_online_check:
                self.next_online_check=now+.5;errors=[];snap=self.protocol.snapshot()
                monitor=snap['tasks'].get('E1:monitor',{})
                if monitor.get('state')=='RUNNING':
                    owner=monitor['owner'];b=self.peers[owner]
                    if b.job!='E1_monitor':errors.append('MONITOR_EXECUTION_LOST')
                    protection=transfer_guard(snap,'monitor',cancel_ack=True,handover_ack=self.handover_ack)
                    if snap['tasks'].get('E1:deliver',{}).get('state')!='SUCCEEDED' and protection['allowed']:errors.append('EARLY_MONITOR_RELEASE_ALLOWED')
                else:protection=None
                for rid,b in self.peers.items():
                    if b.cargo=='E1' and snap['event']['cargo_owner']!=rid:errors.append('CARGO_OWNER_MISMATCH')
                row=dict(at=now,passed=not errors,errors=errors,monitor_release_guard=protection,
                    protocol=snap,states=self.states(),plan_revision=self.plan_revision)
                self.online_checks.append(row);self.log('online_commitment_check',check=row)
                if errors:self.failed='ONLINE_COMMITMENT:'+','.join(errors);return
            if positive and self.protocol.event and self.protocol.event['lifecycle']=='COMPLETED':
                self.finished=all(j in self.completed for j in self.tasks) and all(b.state=='IDLE' for b in self.peers.values()) and not self.resource.get('owners')
            for b in self.peers.values():self.dispatch_dense(b)

    class VisualBot(bed.Bot):
        def step(self):
            # Controlled executor test: cancel a real issued navigation, retain
            # task/owner/target until terminal action ACK, then retry same action.
            if getattr(self,'visual_cancel_pending',False):
                if self.visual_cancel_future.done() and self.result_future.done():
                    reply=self.visual_cancel_future.result();status=self.result_future.result().status
                    goal_id=action_uuid_bytes(self.nav_handle.goal_id.uuid)
                    accepted=[action_uuid_bytes(g.goal_id.uuid) for g in reply.goals_canceling]
                    ack=goal_id in accepted and status==5
                    self.c.log('visual_navigation_cancel_ack',robot=self.rid,job=self.job,
                        task_id=self.record['task_id'],action_goal_id=goal_id,
                        accepted_goal_ids=accepted,accepted_goals=len(reply.goals_canceling),terminal_status=status,passed=ack)
                    if not ack:self.fail('VISUAL_CANCEL_ACK_FAILED');return
                    self.record['navigation_attempts'][-1].update(status=status,end=self.c.elapsed(),controlled_cancel=True)
                    self.visual_cancel_pending=False;self.c.nav_cancel_tested=True;self.send_navigation()
                elif self.c.elapsed()-self.visual_cancel_at>8:self.fail('VISUAL_CANCEL_ACK_TIMEOUT')
                return
            if a.cancel_verify_once and not self.c.nav_cancel_tested and self.job=='E1_verify' and self.state=='NAVIGATING' and not self.result_future.done():
                self.visual_cancel_at=self.c.elapsed();self.visual_cancel_future=self.nav_handle.cancel_goal_async()
                # Keep NAVIGATING/motion reservation until actual terminal ACK.
                self.visual_cancel_pending=True
                self.c.log('visual_navigation_cancel_requested',robot=self.rid,job=self.job,
                    task_id=self.record['task_id'],target=deepcopy(self.record['target']),
                    action_goal_id=action_uuid_bytes(self.nav_handle.goal_id.uuid),
                    task_revision=self.c.protocol.tasks['E1:verify']['revision'],
                    attempt=self.c.protocol.tasks['E1:verify']['attempt'],
                    protocol=self.c.protocol.snapshot(),reason='controlled issued-navigation cancellation test before any service start')
                return
            return super().step()
        def feedback(self,msg):
            d=json.loads(msg.data);self.phases[d['task_id'],d['phase']]=d
            self.c.log('service_feedback',robot=self.rid,feedback=d)
            if d.get('protocol_task_id') and d['phase'] in {'started','succeeded','cancelled'}:
                rec=self.c.commands[d['task_id']]
                if d['task_revision']!=rec['sent_revision']:self.c.failed='TOKEN_MISMATCH';return
                m=dict(schema='event-task/v1',kind='feedback',message_id=f"fb:{d['task_id']}:a{d['attempt']}:r{d['task_revision']}:{d['phase']}",event_id='E1',
                    task_id=d['protocol_task_id'],task_revision=d['task_revision'],attempt=d['attempt'],
                    robot_id=self.rid,phase=d['phase'],at=max(self.c.elapsed(),self.c.protocol.now))
                try:
                    explicit=review if rec['job_id']=='E1_verify' and d['phase']=='succeeded' else None
                    result=self.c.bridge.feedback(m,explicit)
                    self.c.protocol_records.append(dict(message=m,verdict=explicit,output=result))
                    self.c.log('visual_execution_protocol_feedback',message=m,verdict_source=explicit['source'] if explicit else None,output=result)
                    self.c.tasks.update(compile_tasks(self.c.protocol.planning_view(),self.c.elapsed(),self.c.cfg,a.region,dt.phases,cert))
                    self.c.publish()
                except Exception as error:self.c.failed='PROTOCOL_FEEDBACK:'+repr(error)

    if a.bed_repair:
        if a.region!='A' or not positive:raise RuntimeError('bed mode requires qualified A positive source')
        from clinic_visual_bed import extend
        VisualEpisode,VisualBot=extend(VisualEpisode,VisualBot,a,manifest)
    require_static(a.out);prepare(a.out/'prepared')
    opts=argparse.Namespace(reference=None,arrival='pose_handoff',parking='dense_cycle',localization='reference',mode='event',policy='milp',changes='none')
    result=dict(passed=False,status='NOT_RUN')
    with world(a.out,a.domain,a.out/'prepared'):
        try:
            runtime_gate(a.out,120.,pulse=False)
        except RuntimeError:
            # The unchanged native checker retains pending service futures
            # indefinitely. One bounded, fresh-process FULL check is allowed
            # for lifecycle/parameter RPC-only failures; never ignore a guard.
            report=json.loads((a.out/'runtime_preflight.json').read_text())
            failed=[(rid,k) for rid,checks in report['robots'].items() for k,v in checks.items() if not v]
            if not a.bed_repair or not failed or any(not k.startswith('live:') for _,k in failed):raise
            retry=a.out/'runtime_recheck_01';retry.mkdir()
            (retry/'reason.json').write_text(json.dumps(dict(failed=failed,action='one fresh-process full original check; no guard weakened',first_report=str(a.out/'runtime_preflight.json')),indent=2))
            runtime_gate(retry,60.,pulse=False)
        rclpy.init();c=VisualEpisode(a.out,opts);ex=SingleThreadedExecutor();ex.add_node(c)
        for rid in cfg['robots']:b=VisualBot(rid,c);c.peers[rid]=b;ex.add_node(b)
        video_proc=None;video_log=None
        try:
            begin=time.monotonic();last_step=-1.
            while time.monotonic()-begin<a.timeout and not c.failed and not c.finished:
                ex.spin_once(timeout_sec=.02)
                if c.epoch is None:
                    if not all(b.ready() for b in c.peers.values()) or len(c.truth)!=3:continue
                    c.epoch=c.now()+1.;c.publish()
                if c.elapsed()<0:continue
                if c.elapsed()-last_step<.05:continue
                last_step=c.elapsed()
                if c.plan is None and c.planning is None:c.submit_dense('normal')
                if video_proc is None and c.plan and any(b.state=='NAVIGATING' for b in c.peers.values()):
                    video_log=(a.out/'video.log').open('w')
                    video_proc=subprocess.Popen([str(P/'.venv/bin/python'),str(P/'scripts/run_clinic_video_ros.py'),
                        '--videos',a.video,'--regions',a.region,'--repeats','1' if a.bed_repair else '200','--silence-seconds','0',
                        '--perception-only','--out',str(a.out/'video')],stdout=video_log,stderr=subprocess.STDOUT,start_new_session=True)
                for b in c.peers.values():b.step()
                c.tick()
            result.update(passed=c.finished and not c.failed,status='PASS' if c.finished and not c.failed else 'FAIL',
                failure=c.failed or (None if c.finished else 'BOUNDED_TIMEOUT'),records=c.records,
                protocol=c.protocol.snapshot(),planning_records=c.planning_records,
                resource_events=c.resource_events,model_frames=len(c.model_rows),
                tasks=c.tasks,completed=c.completed,protocol_records=c.protocol_records,
                online_checks=c.online_checks,nav_cancel_tested=c.nav_cancel_tested,
                handover_ack=c.handover_ack,epoch=c.epoch,
                scope='real visual positive response' if positive else 'real visual verify and explicit no_fall closure')
            if a.bed_repair:result.update(c.extra_evidence())
        except Exception as error:
            import traceback
            (a.out/'failure_traceback.txt').write_text(traceback.format_exc());result.update(status='FAIL',error=repr(error),
                records=c.records,completed=c.completed,tasks=c.tasks,protocol=c.protocol.snapshot(),
                protocol_records=c.protocol_records,planning_records=c.planning_records,
                resource_events=c.resource_events,online_checks=c.online_checks,model_frames=len(c.model_rows))
            if a.bed_repair:result.update(c.extra_evidence())
        finally:
            if c.planning and c.planning['process'].poll() is None:
                c.planning['process'].terminate();c.planning['process'].wait(timeout=5);c.planning['log'].close()
            if video_proc and video_proc.poll() is None:
                os.killpg(video_proc.pid,signal.SIGINT)
                try:video_proc.wait(timeout=10)
                except subprocess.TimeoutExpired:os.killpg(video_proc.pid,signal.SIGTERM);video_proc.wait(timeout=5)
            if video_log:video_log.close()
            for b in c.peers.values():
                if b.nav_handle:b.nav_handle.cancel_goal_async()
            c.file.close()
            for b in c.peers.values():ex.remove_node(b);b.destroy_node()
            ex.remove_node(c);c.destroy_node();ex.shutdown();rclpy.try_shutdown()
            (a.out/'summary.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(dict(passed=result['passed'],status=result['status'])))
    return 0 if result['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
