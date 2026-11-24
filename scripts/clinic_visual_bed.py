"""Opt-in physical bed extension; no original runtime writes or event injection."""
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import subprocess
import time

P=Path(__file__).resolve().parents[1];W=Path('/home/yhc/clinic_planning_ws')


def extend(BaseEpisode,BaseBot,args,manifest):
    import dense_tasks as dt
    import bed_contract as bc
    from std_msgs.msg import String
    from kaiti_task_sim.clinic_visual import execution_tokens,execution_fence,action_uuid_bytes
    from kaiti_task_sim.clinic_visual_repair import project_before_pickup,project_initial_clearance,resource_fence,before_pickup_scope
    manifest[str(Path(__file__))]=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()

    class BedEpisode(BaseEpisode):
        def __init__(self,*a,**kw):
            super().__init__(*a,**kw)
            self.bed_requested=False;self.cancel_acks=[];self.repair_cases=[]
            self.next_pose=0.;self.next_evidence=0.;self.next_expired=0.;self.pose_records=[]
            (self.out/'runtime_scenario.json').write_text(json.dumps(self.cfg,indent=2))

        def submit_dense(self,stage):
            if stage=='response':
                future,_=dt.cycle_tasks(0)
                for j,t in future.items():
                    if t['waypoint']>1:
                        self.tasks[j]=t
                        self.ledger[j]=dict(state='READY',release=t['release'],cycle=0,nominal_owner=t['nominal_owner'])
            return super().submit_dense(stage)

        def dispatch_dense(self,b):
            q=[j for j in self.queues.get(b.rid,[]) if j not in self.completed]
            # The original monitor and peer keepout remain physically present
            # after service completion. No courier normal departure before a
            # real qualified TL/V3 clearance ACK, regardless of forecast time.
            if b.rid=='r2' and q and self.tasks[q[0]]['kind']=='normal' and 'E1_monitor_clear' in self.tasks and 'E1_monitor_clear' not in self.completed:return
            return super().dispatch_dense(b)

        def submit_initial_clearance(self):
            now=self.elapsed();snap=self.snapshot_bed('initial policy before physical disturbance')
            p=project_initial_clearance(self.cfg,self.tasks,self.plan,self.completed,snap['states'],now)
            folder=self.out/'initial_clearance';folder.mkdir()
            (folder/'snapshot.json').write_text(json.dumps(snap,indent=2))
            (folder/'problem.json').write_text(json.dumps(p,indent=2))
            log=(folder/'worker.log').open('w');output=folder/'result.json'
            proc=subprocess.Popen([str(P/'.venv/bin/python'),str(W/'tools/benchmark_sparse_repair.py'),
                '--worker','--input',str(folder/'problem.json'),'--output',str(output),
                '--policy','full_warm','--budget',str(args.repair_budget)],stdout=log,stderr=subprocess.STDOUT)
            ids=[k for k,t in self.protocol.tasks.items() if t['state'] in {'READY','PENDING'}]
            self.planning=dict(stage='initial_clearance',initial_clearance=True,process=proc,log=log,
                output=output,folder=folder,at=now,wall=time.monotonic(),problem=p,snapshot=snap,
                visual_tokens=execution_tokens(self.protocol,ids))
            self.log('initial_clearance_requested',problem=str(folder/'problem.json'),plan_revision=self.plan_revision)

        def snapshot_bed(self,reason):
            return dict(at=self.elapsed(),reason=reason,states=self.states(),tasks=deepcopy(self.tasks),
                completed=deepcopy(self.completed),plan=deepcopy(self.plan),plan_revision=self.plan_revision,
                protocol=self.protocol.snapshot(),resources=deepcopy(self.resource),
                evidence=self.protocol.evidence_state(),observations=deepcopy(self.observations[-5:]),
                bed_truth=deepcopy(self.bed_truth))

        def request_visual_repair(self):
            if self.planning:return
            b=self.peers['r2'];now=self.elapsed()
            obs=dict(blocked=True,source='actual LaserScan + new global lethal cells, persisted',
                at=now,hits=b.hits.get('long'),global_new=b.global_counts.get('long',0)-b.baseline.get('long',0),
                local_new=b.local_counts.get('long'),blocked_since=self.blocked_since['long'])
            states=self.states()
            if not before_pickup_scope(b.job,b.cargo,(b.record or {}).get('service_started')):
                raise RuntimeError('this instance has no post-pickup repair/cancellation authority')
            p=project_before_pickup(self.cfg,self.tasks,self.plan,self.completed,states,now,obs)
            p['observation']=obs
            invalid=bc.validate(p,p['reference'],dict(free=list(p['tasks']),freeze_time=False))
            snap=self.snapshot_bed('persisted actual physical bed observation')
            folder=self.out/f'repair_{len(self.repair_cases):02d}';folder.mkdir()
            (folder/'snapshot.json').write_text(json.dumps(snap,indent=2))
            (folder/'problem.json').write_text(json.dumps(p,indent=2))
            (folder/'old_plan_validation.json').write_text(json.dumps(invalid,indent=2))
            self.repair_cases.append(dict(folder=str(folder),old_invalid=not invalid['passed'],at=now))
            self.last_repair=now
            if invalid['passed']:
                self.log('NO_INVALIDATION',observation=obs,validation=invalid);return
            log=(folder/'pair.log').open('w')
            proc=subprocess.Popen([str(P/'.venv/bin/python'),str(P/'scripts/clinic_visual_pair.py'),
                '--input',str(folder/'problem.json'),'--out',str(folder/'pair'),'--budget',str(args.repair_budget)],stdout=log,stderr=subprocess.STDOUT)
            ids=[k for k,t in self.protocol.tasks.items() if t['state'] in {'READY','PENDING'}]
            self.planning=dict(stage='visual_bed_repair',paired_visual=True,process=proc,log=log,
                folder=folder,at=now,wall=time.monotonic(),problem=p,snapshot=snap,
                visual_tokens=execution_tokens(self.protocol,ids))
            self.log('actual_plan_invalidated',observation=obs,old_validation=invalid,problem=str(folder/'problem.json'))

        def poll_dense(self):
            q=self.planning
            if not q or not (q.get('paired_visual') or q.get('initial_clearance')):
                super().poll_dense()
                if q and q['stage']=='response' and self.planning is None and not self.failed:
                    self.submit_initial_clearance()
                return
            if q['process'].poll() is None:
                if time.monotonic()-q['wall']>2*args.repair_budget+65:self.failed='PAIR_TIMEOUT'
                return
            initial=q.get('initial_clearance',False)
            q['log'].close();path=q['output'] if initial else q['folder']/'pair/summary.json'
            if not path.exists():self.failed='PAIR_NO_RESULT';return
            p=q['problem']
            local=json.loads((q['output'] if initial else q['folder']/'pair/local_impact/result.json').read_text())
            if local['status'] not in ['OPTIMAL','FEASIBLE_BUDGET']:
                self.failed='LOCAL_REPAIR_'+local['status'];return
            checks=dict(model=bc.validate(p,local['plan'],local['scope'],local['objective']),
                commitments=bc.commitment_check(p,self.completed,self.states()),
                tasks=execution_fence(self.protocol,q['visual_tokens']),
                resources=resource_fence(q['snapshot']['resources'],self.resource,
                    [s['job'] for s in q['snapshot']['states'].values() if s['job'] and s['job'] not in self.completed]),
                plan_revision=dict(passed=self.plan_revision==q['snapshot']['plan_revision']),
                starts=dict(passed=all(v>=self.elapsed()-1e-6 for v in local['plan']['starts'].values())))
            for tid,t in q['snapshot']['protocol']['tasks'].items():
                if t['state']=='RUNNING':
                    current=self.protocol.tasks[tid]
                    checks['active_token_'+tid]=dict(passed=all(current[k]==t[k] for k in
                        ['owner','attempt','execution_revision','execution_target','started_at','state']))
            for rid,s in q['snapshot']['states'].items():
                if s['job'] and rid not in p['active_commitments']:
                    current=self.peers[rid]
                    if current.job not in [s['job'],None]:checks['issued_prefix_'+rid]=dict(passed=False)
            accepted=all(v['passed'] for v in checks.values())
            (q['folder']/'commit_fence.json').write_text(json.dumps(dict(passed=accepted,at=self.elapsed(),checks=checks,current=self.snapshot_bed('precommit')),indent=2))
            if not accepted:self.failed='STALE_OR_INVALID_VISUAL_REPAIR';return
            oldroutes=deepcopy(self.plan['routes']);new=local['plan']
            for field in ['owners','starts','finishes']:self.plan[field].update(new[field])
            for rid in self.peers:
                head=[j for j in oldroutes[rid] if j not in self.completed and j not in p['tasks']]
                self.plan['routes'][rid]=head+new['routes'][rid]
            self.plan['ends']=deepcopy(new['ends']);self.queues=deepcopy(self.plan['routes'])
            cov=p['coverage_projection']
            clearance=p['committed_future']['E1_monitor_clear']
            self.tasks['E1_monitor_clear']=deepcopy(clearance['task'])
            self.plan['owners']['E1_monitor_clear']='r1'
            self.plan['starts']['E1_monitor_clear']=cov['clearance_start']
            self.plan['finishes']['E1_monitor_clear']=cov['clearance_finish']
            route=self.plan['routes']['r1']
            if 'E1_monitor_clear' not in route:
                index=route.index('E1_monitor')+1 if 'E1_monitor' in route else 0
                route.insert(index,'E1_monitor_clear')
            self.queues=deepcopy(self.plan['routes'])
            # Retiming predictions only. No service, task, protocol or resource ACK.
            self.plan['finishes']['E1_monitor']=cov['monitor_release']
            if 'pickup_start' in cov:
                self.plan['starts']['E1_pickup']=cov['pickup_start'];self.plan['finishes']['E1_pickup']=cov['pickup_finish']
                self.plan['starts']['E1_deliver']=cov['delivery_start'];self.plan['finishes']['E1_deliver']=cov['delivery_finish']
            self.active_projection=p;self.plan_revision+=1
            entry=dict(stage=q['stage'],requested_at=q['at'],returned_at=self.elapsed(),
                end_to_end_wall=time.monotonic()-q['wall'],problem_path=str(q['folder']/'problem.json'),
                solver=local,commit_validation=dict(passed=True,checks=checks))
            self.planning_records.append(entry)
            if not initial:self.repairs.append(entry)
            self.planning=None;self.publish()
            self.log('initial_clearance_committed' if initial else 'visual_repair_committed',pair=str(path),checks=checks,plan=deepcopy(self.plan),plan_revision=self.plan_revision)

        def tick(self):
            super().tick()
            if self.failed:return
            now=self.elapsed();b=self.peers['r2'];mon=self.protocol.tasks.get('E1:monitor',{})
            if now>=self.next_pose:
                self.next_pose=now+.2;row=dict(at=now,poses=deepcopy(self.truth),states={r:dict(job=v.job,state=v.state,cargo=v.cargo) for r,v in self.peers.items()})
                self.pose_records.append(row);self.log('measured_pose_sample',sample=row)
            if now>=self.next_evidence:
                self.next_evidence=now+1.;self.log('separate_evidence_validity',evidence=self.protocol.evidence_state())
            if not self.bed_requested and mon.get('state')=='RUNNING' and b.job=='E1_pickup' and b.state=='NAVIGATING' and b.pose()['y']>-23.:
                # Dedicated trigger is independent of the old delivery-bed
                # scenario's injection_stage. Do not arm that second scenario.
                self.bed_requested=True
                snap=self.snapshot_bed('before physical long-bed insertion')
                (self.out/'before_bed.json').write_text(json.dumps(snap,indent=2))
                self.bed_trigger.publish(String(data=json.dumps(dict(phase='long'))))
                self.log('bed_scenario_requested',phase_id='long',timing='before pickup service, original physical object')
            if self.bed_requested and b.blocked('long'):
                self.blocked_since.setdefault('long',now)
                if b.state=='BED_WAIT' and now-self.blocked_since['long']>=self.cfg['bed_experiment']['persistence_seconds'] and not self.planning and now-self.last_repair>=30.:
                    self.request_visual_repair()

        def extra_evidence(self):
            return dict(bed_requested=self.bed_requested,bed_truth=self.bed_truth,
                observations=self.observations,scan_samples=self.scan_samples,repairs=self.repairs,
                repair_cases=self.repair_cases,cancel_acks=self.cancel_acks,pose_records=self.pose_records,
                evidence_state=self.protocol.evidence_state(),disturbance='actual existing NormalBed long, before pickup',
                video_repeats=1,changes_to_original_workers=False,bed_scope='BEFORE_PICKUP_ONLY',
                postpickup_bed_experiment_enabled=False,post_monitor_clearance_required=True)

    class BedBot(BaseBot):
        def corridor_ahead(self,phase):
            if not before_pickup_scope(self.job,self.cargo,(self.record or {}).get('service_started')):return False
            if not hasattr(self,'approved_path') or not self.approved_path.poses:return False
            pts=[(p.pose.position.x,p.pose.position.y) for p in self.approved_path.poses];pose=self.pose()
            index=min(range(len(pts)),key=lambda i:math.dist(pts[i],(pose['x'],pose['y'])))
            center=self.c.cfg['bed_experiment'][phase+'_center']
            return any(math.dist(p,center)<1.4 for p in pts[max(0,index-1):])

        def step(self):
            if getattr(self,'bed_cancel_pending',False):
                if self.bed_cancel_future.done() and self.result_future.done():
                    response=self.bed_cancel_future.result();status=self.result_future.result().status
                    goal=action_uuid_bytes(self.nav_handle.goal_id.uuid)
                    accepted=goal in [action_uuid_bytes(g.goal_id.uuid) for g in response.goals_canceling] and status==5
                    row=dict(at=self.c.elapsed(),robot=self.rid,job=self.job,task_id=self.record['task_id'],
                        goal_uuid=goal,status=status,passed=accepted,kind='actual FollowPath cancellation, no service cancellation')
                    self.c.cancel_acks.append(row);self.c.log('bed_navigation_cancel_ACK',ack=row)
                    if not accepted:self.fail('BED_PREPICKUP_CANCEL_ACK');return
                    self.record['navigation_attempts'][-1].update(status=status,end=self.c.elapsed(),obstacle_wait=True)
                    self.bed_cancel_pending=False;self.state='BED_WAIT';self.bed_wait_at=self.c.elapsed()
                    self.clear_since=None;self.laser_clear_since=None
                    self.c.log('bed_stopped',robot=self.rid,job=self.job,pose=self.pose())
                elif self.c.elapsed()-self.bed_cancel_at>8:self.fail('BED_CANCEL_ACK_TIMEOUT')
                return
            if self.job=='E1_pickup' and self.state=='NAVIGATING' and self.c.bed_requested and self.blocked('long') and not self.result_future.done():
                self.bed_cancel_at=self.c.elapsed();self.bed_cancel_pending=True
                self.bed_cancel_future=self.nav_handle.cancel_goal_async()
                self.c.log('bed_navigation_cancel_requested',robot=self.rid,job=self.job,
                    task_id=self.record['task_id'],goal_uuid=action_uuid_bytes(self.nav_handle.goal_id.uuid),target=deepcopy(self.record['target']))
                return
            return super().step()

    return BedEpisode,BedBot
