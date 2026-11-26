"""Controlled Clinic execution pair with an acknowledged G1 reservation."""
import argparse
from copy import deepcopy
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time

from factorial import Comparison, G1_HOLD, WORKSPACE, ROOT, allocation, benchmark, READ, WRITE
import feedback_repair
from feedback_repair import FeedbackComparison, check_prefix, path_checks, revised_problem

SOURCE = WORKSPACE/'runs/dense_loop_a13/00_normal'
FACTOR = WORKSPACE/'verification/factorial_2026-11-25_01'
CERT = WORKSPACE/'verification/visual_positive_2026-11-18_c1/a_qualification_audit/A.json'
SERVICE = FACTOR/'gazebo_fixed_reference/summary.json'
SERVICE_AUDIT = FACTOR/'gazebo_fixed_reference_standard_audit/summary.json'
ROLES = {'E1_verify': ['r1'], 'E1_monitor': ['r1'], 'E1_pickup': ['r2'], 'E1_deliver': ['r2']}
PREFIX_JOB = 'C0_r2_W2'
CROSS_JOB = 'C0_r1_W3'
THIRD_JOB = 'C0_r3_W2'
STAGED = {PREFIX_JOB, THIRD_JOB, 'C0_r1_W3', 'C0_r2_W3', 'C0_r3_W3'}


def qualification(cfg, tasks):
    from kaiti_task_sim.event_protocol import canonical

    cert, audit, service = READ(CERT), READ(SERVICE_AUDIT), READ(SERVICE)
    evidence = Path(cert['evidence'])
    if not (cert['passed'] and cert['concurrent_resource_qualification'] and
            cert['config_sha256'] == hashlib.sha256(canonical(cfg).encode()).hexdigest() and
            benchmark.sha(evidence) == cert['evidence_sha256'] and READ(evidence)['passed'] and
            all(cert['qualified_robots'][k[3:]] == v for k, v in ROLES.items())):
        raise ValueError('A emergency qualification mismatch')
    witness = service['completed']['C0_r2_W1']
    shape = ('anchor', 'entry_anchor', 'clear_anchor', 'resources', 'service_role', 'duration')
    if not (audit['passed'] and audit['summary_sha256'] == benchmark.sha(SERVICE) and
            audit['checks']['C0_r2_W1_native_guard_ACK'] and witness['robot'] == 'r2' and
            witness['lease_released_at'] >= witness['clear_at'] > witness['service_finished'] and
            all(tasks[CROSS_JOB][k] == service['tasks']['C0_r2_W1'][k] for k in shape)):
        raise ValueError('Cross-assignment DL service/lease witness mismatch')
    return {str(f): benchmark.sha(f) for f in (CERT, evidence, SERVICE, SERVICE_AUDIT)}


def task_domain(tasks, reference):
    domain = {j: [r] for j,r in reference['owners'].items()}
    if CROSS_JOB in domain:
        domain[CROSS_JOB].append('r2')
    domain.update({j: ROLES[j] for j in tasks if j in ROLES})
    return domain


def solve_worker(folder, policy):
    p = READ(folder/'problem.json')
    benchmark.ca = FeedbackComparison if 'rejected_transition' in p else Comparison
    result = benchmark.solve_worker(p, policy, folder/'solve', 5., 17)
    if result.get('plan') and not benchmark.ca.validate(p, result['plan'], policy, result['objective'])['passed']:
        raise ValueError('Returned plan failed independent validation')


def run(out, policy, domain, timeout, repair_path_rejection=False):
    sys.path[:0] = [str(WORKSPACE), str(WORKSPACE/'tools')]
    from clinic_visual_world import visual_world
    from support.clinic_runtime import episode as bed
    from support.clinic_runtime.__main__ import require_static, runtime_gate
    from support.clinic_runtime.config import prepare
    from kaiti_task_sim.clinic_visual import compile_tasks, registered_space
    from kaiti_task_sim.clinic_visual_repair import RegisteredVideoProtocol
    from nav2_msgs.action import ComputePathToPose
    from rclpy.executors import SingleThreadedExecutor
    from std_msgs.msg import String
    import rclpy
    import dense_tasks as dt

    bed.configure_research_backend()
    cfg = dt.config()
    initial_problem = READ(SOURCE/'problem.json')
    initial_plan = READ(SOURCE/'result.json')['plan']
    tasks, _ = dt.normal_tasks()
    # Reuse the candidate's actual phase geometry for the issued prefix and
    # the alternative DL visit. The current runtime accepts both clear gates.
    for job in (PREFIX_JOB, CROSS_JOB):
        tasks[job] = deepcopy(initial_problem['tasks'][job])
    if not all(tasks[j]['anchor'] == t['anchor'] and tasks[j]['duration'] == t['duration']
               for j,t in initial_problem['tasks'].items()):
        raise ValueError('Initial plan is not the saved three-robot dense patrol plan')
    sources = qualification(cfg, tasks)
    out.mkdir(parents=True, exist_ok=False)
    WRITE(out/'runtime_scenario.json', cfg)
    WRITE(out/'initial.json', dict(plan=initial_plan, tasks=tasks, sources=sources,
          initial_problem_sha256=benchmark.sha(SOURCE/'problem.json'),
          initial_plan_sha256=benchmark.sha(SOURCE/'result.json'),
          code={str(f): benchmark.sha(f) for f in
                (Path(__file__), Path(benchmark.__file__), Path(feedback_repair.__file__))},
          event_source='controlled fall verdict upon actual verify service ACK',
          repair_path_rejection=repair_path_rejection,
          reservation_seconds=G1_HOLD,
          trigger='all W1 and R1 W2 complete; issue R2 W2 on verify service start'))
    require_static(out)
    prepare(out/'prepared')

    class Episode(bed.Episode):
        def __init__(self, opts):
            super().__init__(out, opts)
            self.tasks = deepcopy(tasks)
            self.protocol = RegisteredVideoProtocol(position_ttl=10., supply=cfg['anchors']['G1'][:2])
            space = registered_space(cfg, 'A')
            self.protocol.set_registration(dict(schema='video-region-registration/v1',
                id='paired-registered-A', source='qualified_scenario_registration',
                config_sha256=READ(CERT)['config_sha256'], region='A', valid=True, issued_at=0.,
                valid_until=cfg['horizon'], event_xy=space['event_xy'],
                service_points=space['service_points'], evidence=str(CERT)), 0.)
            self.reservation = None
            self.confirmed = None
            self.commit = None
            self.path_queue = []
            self.path_witness = []
            self.path_pending = None
            self.next_protocol_publish = 0.

        def protocol_apply(self, msg):
            super().protocol_apply(msg)
            if msg['kind']=='feedback' and msg['task_id']=='E1:verify' and msg['phase']=='succeeded':
                self.confirmed = msg['at']
                self.reservation = dict(action='block', resource='G1', start=self.epoch+self.confirmed,
                                        finish=self.epoch+self.confirmed+G1_HOLD, change_id='online-pair-G1')
                self.pub.publish(String(data=json.dumps(self.reservation)))
                self.log('paired_event_confirmed', controlled_verdict=True, checkpoint=self.states(),
                         reservation=self.reservation, protocol=self.protocol.planning_view())

        def request_response(self, now):
            compiled = compile_tasks(self.protocol.planning_view(), self.confirmed, cfg, 'A', dt.phases)
            for task in compiled.values():
                task['spatial_source'] = 'scenario_registered_A'
            self.tasks.update(compiled)
            states = self.states()
            if states['r2']['job'] != PREFIX_JOB or any(states[r]['job'] for r in ('r1','r3')):
                raise ValueError('Common issued-task checkpoint diverged before solve')
            p = dt.problem(cfg, self.tasks, list(self.tasks), self.completed, states, self.plan,
                           now, self.event_at, 'response')
            for field in ('owners','starts','finishes'):
                p['reference'][field] = {j:v for j,v in initial_plan[field].items() if j in p['tasks']}
            p['reference']['routes'] = {r:[j for j in route if j in p['tasks']]
                                       for r,route in initial_plan['routes'].items()}
            ref = p['reference']
            p.update(accepted_reference=deepcopy(ref), nominal_owners=deepcopy(ref['owners']),
                     hard_owners={}, targeted_jobs=[], closure_jobs=[], necessary_normal=THIRD_JOB, region='A',
                     physical_certificate=READ(CERT), allowed_robots=task_domain(p['tasks'], ref),
                     assignment_weights=dict(allocation.WEIGHTS), immutable_projection={
                         r:{k:v[k] for k in ('source_anchor','ready')} for r,v in p['robots'].items()},
                     clocks=dict(candidate_at=self.event_at,confirmed_at=self.confirmed,
                                 actual_verify_started_at=self.completed['E1_verify']['service_started']))
            p['weights'] = {k:0. for k in p['weights']}
            p['weights'].update(normal_delay=.1,owner=2.,shift=.05,travel=.1)
            p['blocked_resources'].append(dict(resource='G1',start=self.confirmed,
                                               finish=self.confirmed+G1_HOLD))
            p = benchmark.json_finite(p)
            self.start_response_worker(out/'response', p)
            self.log('paired_plan_requested', task_graph=self.protocol.planning_view(), domains=p['allowed_robots'],
                     prefixes=p['prefixes'], reservation=p['blocked_resources'][-1], policy=policy)

        def start_response_worker(self, folder, p):
            WRITE(folder/'problem.json',p)
            with (folder/'worker.log').open('w') as log:
                worker = subprocess.Popen([sys.executable,str(Path(__file__).resolve()),'worker',
                                           '--out',str(folder),'--policy',policy], stdout=log,
                                          stderr=subprocess.STDOUT,
                                          env=dict(os.environ,OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1'))
            self.planning = dict(process=worker, p=p, folder=folder, wall=time.monotonic(),
                                 world_revision=self.protocol.world_revision,
                                 resource_blocks=deepcopy(self.resource.get('blocked', [])))

        def request_path(self, arc, edge):
            r, source, target = edge
            goal = ComputePathToPose.Goal()
            goal.use_start = True
            goal.planner_id = 'GridBased'
            b = self.peers[r]
            for stamp, anchor in ((goal.start,source),(goal.goal,target)):
                x,y,yaw = cfg['anchors'][anchor]
                stamp.header.frame_id = 'map'
                stamp.header.stamp = b.get_clock().now().to_msg()
                stamp.pose.position.x,stamp.pose.position.y = x,y
                stamp.pose.orientation.z,stamp.pose.orientation.w = math.sin(yaw/2),math.cos(yaw/2)
            self.path_pending = (arc, list(edge), b.path_action.send_goal_async(goal), False, time.monotonic())

        def qualify_paths(self):
            if self.path_pending:
                arc, edge, future, received, start = self.path_pending
                if time.monotonic()-start > 12.:
                    raise TimeoutError(f'Nav2 route qualification {edge}')
                if not future.done():
                    return False
                result = future.result()
                if not received:
                    if not result.accepted:
                        raise ValueError(f'Nav2 qualification rejected {edge}')
                    self.path_pending = arc, edge, result.get_result_async(), True, start
                    return False
                points = [(v.pose.position.x,v.pose.position.y) for v in result.result.path.poses]
                length = sum(math.dist(a,b) for a,b in zip(points,points[1:]))
                prior = max(0.,(cfg['tables']['event'][edge[1]][edge[2]]-12.)*.22)
                valid = (result.status==4 and len(points)>1 and
                         math.dist(points[-1],cfg['anchors'][edge[2]][:2])<=.12 and
                         length<=max(8.,1.5*prior+2.))
                witness = dict(edge=edge, at=self.elapsed(), length=length, points=len(points),
                               passed=valid, status=result.status, arc=arc,
                               attempt=self.planning['folder'].name)
                self.path_witness.append(witness)
                self.log('paired_route_qualification', witness=witness)
                self.path_pending = None
                if not valid:
                    p = self.planning['p']
                    if (repair_path_rejection and 'rejected_transition' not in p
                            and result.status == 6 and not points):
                        self.check_response_context(self.planning, self.planning['result']['plan'])
                        repaired = revised_problem(p, arc, witness)
                        self.path_queue.clear()
                        self.log('paired_feedback_repair_requested', rejection=repaired['rejected_transition'])
                        self.start_response_worker(out/'response_repair', repaired)
                        return False
                    raise ValueError(f'Nav2 route qualification failed {edge}: {witness}')
            if self.path_queue:
                self.request_path(*self.path_queue.pop(0))
                return False
            return True

        def check_response_context(self, job, plan):
            p = job['p']
            if self.elapsed()+1e-6 > min(r['ready'] for r in p['robots'].values()):
                raise ValueError('Plan window expired before qualified commit')
            if (self.protocol.world_revision != job['world_revision'] or
                    self.resource.get('blocked', []) != job['resource_blocks']):
                raise ValueError('Event or resource reservation changed before qualified commit')
            prefix_ids = {prefix['record_task_id'] for prefix in p['prefixes'].values() if prefix['jobs']}
            if any(owner.get('lease_id') not in prefix_ids for owner in self.resource.get('owners', {}).values()):
                raise ValueError('Unexpected active resource lease before qualified commit')
            check_prefix(p, plan, self.states(), self.completed)

        def poll_response(self):
            job = self.planning
            if job['process'].poll() is None:
                if time.monotonic()-job['wall'] > 20.:
                    raise TimeoutError('online response worker')
                return
            p = job['p']
            if 'result' not in job:
                if job['process'].returncode:
                    raise ValueError('Online response worker failed')
                q = READ(job['folder']/'solve/result.json')
                if not q.get('plan'):
                    raise ValueError('Online response: '+q['status'])
                job['result'] = q
                if (q['input_sha256'] != allocation.digest(p) or
                        not FeedbackComparison.validate(p, q['plan'], policy, q['objective'])['passed']):
                    raise ValueError('Response worker result does not match the current problem')
                self.path_queue.extend(path_checks(p, q['plan'], CROSS_JOB))
            if not self.qualify_paths():
                return
            q = job['result']
            plan = q['plan']
            self.check_response_context(job, plan)
            for field in ('owners','starts','finishes'):
                self.plan[field].update(plan[field])
            self.plan['routes'] = deepcopy(plan['routes'])
            self.plan['ends'] = deepcopy(plan['ends'])
            self.queues = deepcopy(plan['routes'])
            self.planned_owners.update({self.tasks[j]['protocol_task_id']:r for j,r in plan['owners'].items()
                                        if j.startswith('E1_')})
            self.plan_revision += 1
            self.commit = dict(at=self.elapsed(), policy=policy, plan=plan, prefixes=p['prefixes'],
                               objective=q['objective'], terms=q['validation']['objective_parts'],
                               rejected_transition=p.get('rejected_transition'),
                               changes={j:[r,plan['owners'][j]] for j,r in p['reference']['owners'].items()
                                        if r != plan['owners'][j]})
            self.planning = None
            self.publish()
            self.log('paired_plan_committed', **{k:v for k,v in self.commit.items() if k!='at'})

        def step_pair(self, now):
            if self.protocol.event and now >= self.next_protocol_publish:
                self.publish()
                self.next_protocol_publish = now + .25
            self.update_motion()
            self.update_neck()
            if self.planning:
                self.poll_response()
            if self.event_at is None:
                if {'C0_r1_W1','C0_r2_W1','C0_r3_W1','C0_r1_W2'} <= self.completed.keys():
                    self.event_at = now
                    self.protocol_apply(dict(schema='event-task/v1', kind='observation', event_id='E1',
                        message_id='controlled-paired-candidate', at=now, source_at=now,
                        status='confirmed', space=registered_space(cfg, 'A')))
                    self.tasks.update(compile_tasks(self.protocol.planning_view(), now, cfg, 'A', dt.phases))
                    verify = self.peers['r1']
                    t = self.tasks['E1_verify']
                    r2 = self.peers['r2']
                    staged = self.tasks[PREFIX_JOB]
                    dispatch_ready = (initial_plan['starts'][PREFIX_JOB]
                                      - cfg['tables']['event'][r2.anchor][staged['entry_anchor']]
                                      - staged['approach'])
                    verify_at = max(now + cfg['tables']['event'][verify.anchor][t['anchor']] + 1.,
                                         dispatch_ready + 1.)
                    self.plan['starts']['E1_verify'] = verify_at
                    self.plan['finishes']['E1_verify'] = verify_at + t['duration']
                    self.plan['owners']['E1_verify'] = 'r1'
                    self.planned_owners['E1:verify'] = 'r1'
                    self.plan_revision += 1
                    self.queues['r1'] = ['E1_verify']
                    self.publish()
                    self.log('paired_candidate_created', task_graph=self.protocol.planning_view())
                else:
                    for b in self.peers.values():
                        available = next((j for j in self.queues[b.rid] if j not in self.completed), None)
                        if available not in STAGED:
                            self.dispatch_dense(b)
                    return
            if self.commit is None:
                if not self.planning and self.confirmed is None:
                    self.dispatch_dense(self.peers['r1'])
                    verify = self.protocol.tasks['E1:verify']
                    if verify['state']=='RUNNING' and self.peers['r2'].job is None:
                        self.dispatch_dense(self.peers['r2'])
                if self.confirmed is not None and not self.planning and 'E1_verify' in self.completed:
                    matched = any(b.get('change_id')==self.reservation['change_id'] and
                                  b['start']==self.reservation['start'] and b['finish']==self.reservation['finish']
                                  for b in self.resource.get('blocked',[]))
                    if matched:
                        self.request_response(now)
                    elif now-self.confirmed > 6.:
                        raise ValueError('G1 reservation not acknowledged')
                return
            if 'E1_deliver' in self.completed and not self.handover_ack and now-self.completed['E1_deliver']['end']>=3.:
                self.handover_ack=True
                self.log('scripted_handover_ack',event_id='E1')
            for b in self.peers.values():
                self.dispatch_dense(b)
            self.finished = (self.completed.keys() >= self.tasks.keys() and
                             self.protocol.event['lifecycle']=='COMPLETED' and
                             not self.resource.get('owners') and all(b.state=='IDLE' for b in self.peers.values()))

    opts=argparse.Namespace(reference=None,arrival='pose_handoff',parking='dense_cycle',
                            localization='reference',mode='event',policy=policy,changes='reserved_G1')
    with visual_world(out,domain,out/'prepared'):
        try:
            runtime_gate(out,120.,pulse=False)
        except RuntimeError:
            first = READ(out/'runtime_preflight.json')
            failed = [(r,k) for r,checks in first['robots'].items() for k,v in checks.items() if not v]
            if not failed or any(not k.startswith('live:') for _,k in failed):
                raise
            retry = out/'runtime_recheck'
            WRITE(retry/'reason.json', dict(first_rpc_failures=failed))
            runtime_gate(retry,120.,pulse=False)
        rclpy.init()
        c = Episode(opts)
        ex = SingleThreadedExecutor()
        ex.add_node(c)
        for rid in cfg['robots']:
            b=bed.Bot(rid,c)
            c.peers[rid]=b
            ex.add_node(b)
        started = time.monotonic()
        last = -1.
        last_pose = -1.
        try:
            while not c.finished and not c.failed and time.monotonic()-started < timeout:
                ex.spin_once(timeout_sec=.02)
                if c.epoch is None:
                    if len(c.truth)==3 and all(b.ready() for b in c.peers.values()):
                        c.epoch = c.now()+1.
                        c.plan = deepcopy(initial_plan)
                        c.queues = deepcopy(initial_plan['routes'])
                        c.plan_revision = 1
                        c.publish()
                        c.log('plan_committed', stage='normal', plan=c.plan)
                    continue
                now = c.elapsed()
                if now < 0 or now-last < .05:
                    continue
                last = now
                for b in c.peers.values():
                    b.step()
                if now-last_pose >= .25:
                    c.log('pose_sample',poses={r:b.pose() for r,b in c.peers.items()},truth=c.truth)
                    last_pose = now
                c.step_pair(now)
            if not c.finished and not c.failed:
                c.failed='EPISODE_TIMEOUT'
        except Exception as exception:
            import traceback
            c.failed=repr(exception)
            (out/'failure_traceback.txt').write_text(traceback.format_exc())
        finally:
            if c.planning:
                if c.planning['process'].poll() is None:
                    c.planning['process'].terminate()
                    c.planning['process'].wait(timeout=5)
            for b in c.peers.values():
                if b.nav_handle:
                    b.nav_handle.cancel_goal_async()
            WRITE(out/'result.json',benchmark.json_finite(dict(
                passed=bool(c.finished and not c.failed),failure=c.failed,records=c.records,
                completed=c.completed,tasks=c.tasks,protocol=c.protocol.snapshot(),epoch=c.epoch,
                event_at=c.event_at,confirmed=c.confirmed,reservation=c.reservation,commit=c.commit,
                resource_events=c.resource_events,path_witness=c.path_witness,strategy=policy)))
            c.file.close()
            for node in [*c.peers.values(),c]:
                ex.remove_node(node)
                node.destroy_node()
            ex.shutdown()
            rclpy.try_shutdown()
    return 0 if c.finished and not c.failed else 1


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=['run','worker'])
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--policy',choices=['fixed','full'],required=True)
    parser.add_argument('--domain',type=int,default=96)
    parser.add_argument('--timeout',type=float,default=1050.)
    parser.add_argument('--repair-path-rejection', action='store_true',
                        help='Try one revised MILP after an aborted empty pre-dispatch path query')
    args=parser.parse_args()
    if args.mode=='worker':
        solve_worker(args.out,args.policy)
    else:
        raise SystemExit(run(args.out.resolve(),args.policy,args.domain,args.timeout,args.repair_path_rejection))
