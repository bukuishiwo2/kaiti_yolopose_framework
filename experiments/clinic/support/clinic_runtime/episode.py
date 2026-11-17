"""Independent a13 extension: physical bed observations and active commitment repair."""
from pathlib import Path
from copy import deepcopy
import os, argparse, json, hashlib, shutil, subprocess, time, sys, math
import numpy as np
import rclpy
from rclpy.executors import SingleThreadedExecutor
from rclpy.time import Time
from std_msgs.msg import String
from nav2_msgs.msg import Costmap
from nav2_msgs.srv import ClearEntireCostmap
import run_dense_episode as dense
import dense_tasks as dt
import bed_contract as bc
from bed_validate import validate as initial_validate
from dense_validate import validate as dense_validate
from bed_local_evidence import static_sampling_mask, local_delta
ROOT = dt.ROOT
PROJECT = dense.PROJECT
old = dense.old
STATIC = ROOT / 'config/hospital_aligned/semantic_navigation.pgm'
MASK = static_sampling_mask(STATIC)
ORIGINAL_CYCLE = dt.cycle_tasks
ORIGINAL_EVENT = dt.event_tasks

def cycle(cycle_id):
    (tasks, routes) = ORIGINAL_CYCLE(cycle_id)
    if cycle_id == 0:
        tasks['C0_r1_W3'].update(duration=90.0, service_role='routine_stock_check')
    return (tasks, routes)

def event(view, now):
    tasks = ORIGINAL_EVENT(view, now)
    for (j, role) in [('E1_pickup', 'pickup'), ('E1_deliver', 'drop')]:
        if j in tasks:
            tasks[j].update(cargo_role=role, cargo_group='E1')
    return tasks

def witness(p, plan, scope, claimed=None):
    if p['stage'] == 'bed_response':
        return initial_validate(p, plan, scope, claimed)
    if p['stage'] == 'active_repair':
        return bc.validate(p, plan, scope, claimed)
    return dense_validate(p, plan, scope, claimed)

def configure_research_backend():
    dt.config = bc.config
    dt.cycle_tasks = cycle
    dt.event_tasks = event
    old.config = bc.config
    dense.model_validate = witness

class Bot(dense.Bot):

    def __init__(self, rid, c):
        self.global_counts = {}
        self.local_counts = {}
        self.local_raw_counts = {}
        self.baseline = {}
        self.hits = {}
        self.next_sensor_log = 0.0
        super().__init__(rid, c)
        self.clear_global = self.create_client(ClearEntireCostmap, 'global_costmap/clear_entirely_global_costmap')
        self.clear_local = self.create_client(ClearEntireCostmap, 'local_costmap/clear_entirely_local_costmap')
        self.clear_local_future = None
        self.last_global_clear = -1000.0
        self.recovery_return = 'PATH_WAIT'
        self.laser_clear_since = None
        if rid == 'r2':
            self.create_subscription(Costmap, 'local_costmap/costmap_raw', self.local_map, 10)

    def grid_counts(self, m, local=False):
        if self.rid != 'r2':
            return
        meta = m.metadata
        (w, h) = (meta.size_x, meta.size_y)
        res = meta.resolution
        (ox, oy) = (meta.origin.position.x, meta.origin.position.y)
        counts = {}
        if local:
            try:
                t = self.buffer.lookup_transform('map', m.header.frame_id, Time())
                q = t.transform.rotation
                angle = math.atan2(2 * (q.w * q.z + q.x * q.y), 1 - 2 * (q.y * q.y + q.z * q.z))
                (tx, ty) = (t.transform.translation.x, t.transform.translation.y)
            except Exception:
                return
            (yy, xx) = np.indices((h, w))
            x = ox + (xx + 0.5) * res
            y = oy + (yy + 0.5) * res
            wx = tx + np.cos(angle) * x - np.sin(angle) * y
            wy = ty + np.sin(angle) * x + np.cos(angle) * y
            grid = np.asarray(m.data).reshape(h, w)
        for phase in ['short', 'long']:
            (x, y) = self.c.cfg['bed_experiment'][phase + '_center']
            if local:
                count = int(np.sum(((wx - x) ** 2 + (wy - y) ** 2 < 1.17 ** 2) & (grid >= 254)))
            else:
                (left, right) = (max(0, int((x - 1.17 - ox) / res)), min(w, int((x + 1.17 - ox) / res) + 1))
                (bottom, top) = (max(0, int((y - 1.17 - oy) / res)), min(h, int((y + 1.17 - oy) / res) + 1))
                count = sum((m.data[row * w + col] >= 254 and (ox + (col + 0.5) * res - x) ** 2 + (oy + (row + 0.5) * res - y) ** 2 < 1.17 ** 2 for row in range(bottom, top) for col in range(left, right)))
            counts[phase] = count
        if local:
            self.local_raw_counts = counts
            self.local_counts = {phase: local_delta(grid, [ox, oy], res, [tx, ty, angle], self.c.cfg['bed_experiment'][phase + '_center'], MASK)['new'] for phase in ['short', 'long']}
        else:
            self.global_counts = counts
            for (phase, n) in counts.items():
                self.baseline[phase] = min(n, self.baseline.get(phase, n))

    def map_cb(self, m):
        super().map_cb(m)
        self.grid_counts(m)

    def local_map(self, m):
        self.grid_counts(m, True)

    def scan(self, m):
        super().scan(m)
        if self.rid != 'r2':
            return
        try:
            t = self.buffer.lookup_transform('map', 'rplidar_link', Time())
            q = t.transform.rotation
            yaw = math.atan2(2 * (q.w * q.z + q.x * q.y), 1 - 2 * (q.y * q.y + q.z * q.z))
        except Exception:
            return
        ranges = np.asarray(m.ranges)
        angles = m.angle_min + np.arange(len(ranges)) * m.angle_increment + yaw
        valid = np.isfinite(ranges) & (ranges > max(m.range_min, 0.45)) & (ranges < min(m.range_max, 10.0))
        x = t.transform.translation.x + ranges * np.cos(angles)
        y = t.transform.translation.y + ranges * np.sin(angles)
        for phase in ['short', 'long']:
            (cx, cy) = self.c.cfg['bed_experiment'][phase + '_center']
            self.hits[phase] = int(np.sum(valid & ((x - cx) ** 2 + (y - cy) ** 2 < 1.17 ** 2)))
        now = self.c.elapsed()
        if now >= self.next_sensor_log and (self.job == 'E1_deliver' or self.state.startswith('BED_')):
            self.next_sensor_log = now + 0.2
            obs = dict(at=now, hits=deepcopy(self.hits), global_counts=deepcopy(self.global_counts), baseline=deepcopy(self.baseline), local_counts=deepcopy(self.local_counts), scan_age=self.now() - self.scan_at, pose=self.pose())
            self.c.observations.append(obs)
            self.c.log('corridor_observation', observation=obs)
            self.c.observations[-1]['local_raw_counts'] = deepcopy(self.local_raw_counts)
            self.c.log('local_static_evidence', raw=self.local_raw_counts, new=self.local_counts)
            if any(self.hits.values()) and len(self.c.scan_samples) < 500:
                self.c.scan_samples.append(dict(at=now, angle_min=m.angle_min, angle_increment=m.angle_increment, ranges=[float(v) if math.isfinite(v) else None for v in m.ranges], frame=m.header.frame_id))

    def corridor_ahead(self, phase):
        if self.job != 'E1_deliver' or not hasattr(self, 'approved_path') or (not self.approved_path.poses):
            return False
        pts = np.array([(p.pose.position.x, p.pose.position.y) for p in self.approved_path.poses])
        pose = self.pose()
        index = max(0, int(np.argmin(np.linalg.norm(pts - np.array([pose['x'], pose['y']]), axis=1))) - 1)
        center = np.array(self.c.cfg['bed_experiment'][phase + '_center'])
        return bool(np.any(np.linalg.norm(pts[index:] - center, axis=1) < 1.4))

    def blocked(self, phase):
        return self.corridor_ahead(phase) and self.hits.get(phase, 0) >= 4 and (self.global_counts.get(phase, 0) - self.baseline.get(phase, 0) >= 4)

    def step(self):
        t = self.c.elapsed()
        if self.state == 'BED_WAIT' and any((self.local_counts.get(k, 0) > 0 for k in ['short', 'long'])) and all((self.hits.get(k, 0) < 3 and self.global_counts.get(k, 0) - self.baseline.get(k, 0) < 4 for k in ['short', 'long'])):
            self.clear_since = None
            if self.laser_clear_since is None:
                self.laser_clear_since = t
            if t - self.laser_clear_since >= 2.0 and t - self.last_global_clear >= 15.0 and self.clear_global.service_is_ready() and self.clear_local.service_is_ready():
                self.last_global_clear = t
                self.recovery_return = 'BED_WAIT'
                self.clear_local_future = self.clear_local.call_async(ClearEntireCostmap.Request())
                self.clear_future = self.clear_global.call_async(ClearEntireCostmap.Request())
                self.state = 'COSTMAP_RECOVERY'
                self.phase_at = t
                self.c.log('nav2_global_costmap_recovery_requested', robot=self.rid, job=self.job, reason='unexplained local lethal cells; static sampling cells recorded separately; standard clear both')
            if t - self.bed_wait_at > 240:
                self.fail('BED_WAIT_LIMIT')
            return
        if self.state == 'COSTMAP_RECOVERY':
            if self.clear_future.done() and (self.clear_local_future is None or self.clear_local_future.done()):
                assert self.clear_future.result() is not None
                if self.clear_local_future is not None:
                    assert self.clear_local_future.result() is not None
                self.clear_local_future = None
                self.c.log('nav2_global_costmap_recovered', robot=self.rid, job=self.job, reason='stock Nav2 recovery for failed global path; static map/leases retained')
                self.state = self.recovery_return
                self.retry_at = t + 1.0
                self.phase_at = self.bed_wait_at if self.recovery_return == 'BED_WAIT' else t
            elif t - self.phase_at > 8:
                self.fail('COSTMAP_RECOVERY_TIMEOUT')
            return
        if self.job == 'E1_deliver' and self.state == 'NAVIGATING' and (self.c.injection_stage > 0) and any((self.blocked(p) for p in ['short', 'long'])):
            phase = 'short' if self.c.injection_stage < 2 else 'long'
            self.record['navigation_attempts'][-1]['obstacle_wait'] = dict(at=t, phase=phase, source='actual LaserScan endpoints AND global costmap new lethal cells')
            self.nav_handle.cancel_goal_async()
            self.state = 'BED_CANCEL'
            self.phase_at = t
            self.c.release_unentered_neck(self.rid, self.job, 'observed_bed_wait')
            self.c.log('bed_wait_requested', robot=self.rid, job=self.job, phase_id=phase)
            return
        if self.state == 'BED_CANCEL':
            if self.result_future.done():
                status = self.result_future.result().status
                self.record['navigation_attempts'][-1].update(status=status, end=t)
                assert status in [5, 6]
                self.state = 'BED_WAIT'
                self.bed_wait_at = self.phase_at
                self.clear_since = None
                self.laser_clear_since = None
                self.c.log('bed_stopped', robot=self.rid, pose=self.pose())
            elif t - self.phase_at > 8:
                self.fail('BED_CANCEL_TIMEOUT')
            return
        if self.state == 'BED_WAIT':
            clear = all((not self.blocked(p) and self.hits.get(p, 0) < 3 and (self.global_counts.get(p, 0) - self.baseline.get(p, 0) < 4) and (self.local_counts.get(p, 0) < 4) for p in ['short', 'long']))
            if clear:
                if self.clear_since is None:
                    self.clear_since = t
                if t - self.clear_since >= self.c.cfg['bed_experiment']['clear_stable_seconds']:
                    self.c.log('bed_observed_clear_resume', robot=self.rid, job=self.job)
                    self.send_navigation()
            else:
                self.clear_since = None
            laser_clear = all((self.hits.get(p, 0) < 3 for p in ['short', 'long']))
            if laser_clear:
                if self.laser_clear_since is None:
                    self.laser_clear_since = t
                if not clear and t - self.laser_clear_since >= 2.0 and (t - self.last_global_clear >= 15.0) and self.clear_global.service_is_ready() and self.clear_local.service_is_ready():
                    self.last_global_clear = t
                    self.recovery_return = 'BED_WAIT'
                    self.clear_local_future = self.clear_local.call_async(ClearEntireCostmap.Request())
                    self.clear_future = self.clear_global.call_async(ClearEntireCostmap.Request())
                    self.state = 'COSTMAP_RECOVERY'
                    self.phase_at = t
                    self.c.log('nav2_global_costmap_recovery_requested', robot=self.rid, job=self.job, reason='laser clear but stale global/local obstacle cells; standard Nav2 clear both then reobserve while stopped')
            else:
                self.laser_clear_since = None
            if t - self.bed_wait_at > 240:
                self.fail('BED_WAIT_LIMIT')
            return
        if self.state == 'NAVIGATING' and self.result_future.done():
            status = self.result_future.result().status
            if status not in [4, 5]:
                failures = 1 + sum((a.get('status') not in [None, 4, 5] and (not a.get('obstacle_wait')) and (a['leg'] == self.leg) for a in self.record['navigation_attempts']))
                self.record['navigation_attempts'][-1].update(status=status, end=t)
                if failures < 3:
                    self.record['navigation_attempts'][-1]['recovery'] = dict(reason='controller_abort_wait_then_replan', wait_seconds=3.0, actual_controller_failure_count=failures, expected_obstacle_cancel_excluded=True)
                    self.c.log('controller_recovery_wait', robot=self.rid, job=self.job, leg=self.leg, status=status)
                    self.state = 'PATH_WAIT'
                    self.retry_at = t + 3.0
                    return
                self.fail('NAV_FAILED')
                return
        before = self.state
        super().step()
        if before == 'PATH_RESULT' and self.state == 'PATH_WAIT' and (t - self.last_global_clear >= 15.0) and (not any((self.blocked(k) for k in ['short', 'long']))) and self.clear_global.service_is_ready():
            self.last_global_clear = t
            self.recovery_return = 'PATH_WAIT'
            self.clear_future = self.clear_global.call_async(ClearEntireCostmap.Request())
            self.state = 'COSTMAP_RECOVERY'
            self.phase_at = t
            self.c.log('nav2_global_costmap_recovery_requested', robot=self.rid, job=self.job)

class Episode(dense.Episode):

    def __init__(self, out, args):
        super().__init__(out, args)
        self.strategy = os.environ.get('CLINIC_BED_POLICY', 'local_impact')
        self.observations = []
        self.scan_samples = []
        self.bed_truth = []
        self.repairs = []
        self.decisions = []
        self.blocked_since = {}
        self.observed_cleared = {}
        self.seen_blocked = set()
        self.injection_stage = 0
        self.last_repair = -1000.0
        self.active_projection = None
        self.bed_trigger = self.create_publisher(String, '/clinic_bed/scenario_trigger', 10)
        self.create_subscription(String, '/clinic_bed/physical_truth', self.physical_truth, old.STATE_QOS)

    def sensor_graph(self):
        evidence = {}
        checks = {}
        for rid in self.peers:
            topic = '/' + rid + '/scan'
            subs = self.get_subscriptions_info_by_topic(topic)
            pubs = self.get_publishers_info_by_topic(topic)
            evidence[rid] = dict(topic=topic, publishers=[dict(name=v.node_name, namespace=v.node_namespace) for v in pubs], subscribers=[dict(name=v.node_name, namespace=v.node_namespace) for v in subs])
            for kind in ['local_costmap', 'global_costmap']:
                checks[rid + '_' + kind] = bool(pubs) and any((v.node_name == kind and v.node_namespace == '/' + rid + '/' + kind for v in subs))
        return dict(passed=all(checks.values()), checks=checks, evidence=evidence)

    def physical_truth(self, m):
        d = json.loads(m.data)
        self.bed_truth.append(d)
        self.log('physical_bed_truth', truth=d)

    def submit_dense(self, stage):
        if stage in ['resume', 'cycle1']:
            self.phase = 'RESUME'
            if stage == 'cycle1':
                self.cycle1_planned = True
            self.log('known_future_plan_released', stage=stage)
            return
        if stage != 'response':
            return super().submit_dense(stage)
        (future, routes) = dt.cycle_tasks(1)
        self.tasks.update(future)
        for (j, t) in future.items():
            self.ledger[j] = dict(state='FUTURE', release=t['release'], cycle=1, nominal_owner=t['nominal_owner'])
        now = self.elapsed()
        states = self.states()
        active = {b.job for b in self.peers.values() if b.job}
        pending = [j for j in self.normal_pending() if j not in active]
        candidates = []
        for rid in self.peers:
            q = sorted([j for j in pending if self.tasks[j]['nominal_owner'] == rid and self.tasks[j]['cycle_id'] == 0], key=lambda j: self.tasks[j]['waypoint'])
            if q:
                candidates.append(q[0])
        variants = []
        for necessary in candidates:
            p = dt.problem(self.cfg, self.tasks, pending + ['E1_monitor', 'E1_pickup', 'E1_deliver'], self.completed, states, self.plan, now, self.event_at, 'response')
            p.update(stage='bed_response', necessary_normal=necessary)
            variants.append(p)
        folder = self.out / f'{len(self.planning_records):02d}_response'
        folder.mkdir()
        req = folder / 'request.json'
        req.write_text(json.dumps(dict(variants=variants), indent=2))
        output = folder / 'result.json'
        log = (folder / 'worker.log').open('w')
        proc = subprocess.Popen([str(PROJECT / '.venv/bin/python'), str(ROOT / 'tools/bed_initial_solver.py'), str(req), str(output)], stdout=log, stderr=subprocess.STDOUT)
        self.planning = dict(stage='response', folder=folder, output=output, process=proc, log=log, at=now, wall=time.monotonic(), states=states)
        self.log('planning_requested', stage='response', active_prefix=sorted(active), known_future_tasks=list(future))

    def poll_dense(self):
        q = self.planning
        if not q or not q.get('bed_repair'):
            return super().poll_dense()
        if q['process'].poll() is None:
            if time.monotonic() - q['wall'] > 40:
                self.failed = 'BED_SOLVER_TIMEOUT'
            return
        q['log'].close()
        if not q['output'].exists():
            self.failed = 'BED_SOLVER_NO_RESULT_EXIT_' + str(q['process'].returncode)
            return
        r = json.loads(q['output'].read_text())
        check = bc.commitment_check(q['problem'], self.completed, self.states())
        assert check['passed'], check
        if r['status'] not in ['OPTIMAL', 'FEASIBLE_BUDGET']:
            self.failed = 'BED_MILP_' + r['status']
            return
        assert witness(q['problem'], r['plan'], r['scope'], r['objective'])['passed']
        self.plan['owners'].update(r['plan']['owners'])
        self.plan['starts'].update(r['plan']['starts'])
        self.plan['finishes'].update(r['plan']['finishes'])
        merged = {}
        for rid in self.peers:
            head = [j for j in q['old_routes'][rid] if j not in self.completed and j not in q['problem']['tasks']]
            merged[rid] = head + r['plan']['routes'][rid]
        self.plan['routes'] = merged
        self.plan['ends'] = r['plan']['ends']
        self.queues = deepcopy(merged)
        self.plan_revision += 1
        self.active_projection = q['problem']
        entry = dict(stage=q['stage'], requested_at=q['at'], returned_at=self.elapsed(), end_to_end_wall=time.monotonic() - q['wall'], problem_path=str(q['folder'] / 'problem.json'), solver=r, commit_validation=dict(passed=True, commitments=check))
        self.planning_records.append(entry)
        self.repairs.append(entry)
        self.planning = None
        self.publish()
        self.log('active_repair_committed', strategy=self.strategy, scope=r['scope'], commitments=check, plan=deepcopy(self.plan))

    def request_repair(self, obs):
        now = self.elapsed()
        p = bc.project(self.cfg, self.tasks, self.plan, self.completed, self.states(), now, obs.get('blocked', True))
        inc = bc.trim(self.plan, p['tasks'])
        invalid = bc.validate(p, inc, dict(free=list(p['tasks']), freeze_time=False))
        coverage = p['coverage_projection']
        old_bound = self.active_projection['coverage_projection']['delivery_finish'] if self.active_projection else self.plan['finishes']['E1_monitor'] - 4.0
        reasons = []
        if coverage['delivery_finish'] > old_bound + 2.0:
            reasons.append('projected_delivery_exceeds_monitor_or_corridor_reservation')
        if not invalid['passed']:
            reasons.append('normal_suffix_source_or_resource_constraint_violation')
        self.decisions.append(dict(at=now, observation=obs, reasons=reasons, old_validation=invalid, coverage=coverage))
        if not reasons:
            return
        folder = self.out / f'{len(self.planning_records):02d}_active_repair'
        folder.mkdir()
        (folder / 'problem.json').write_text(json.dumps(p, indent=2))
        output = folder / 'result.json'
        log = (folder / 'worker.log').open('w')
        proc = subprocess.Popen([str(PROJECT / '.venv/bin/python'), str(ROOT / 'tools/bed_solver.py'), str(folder / 'problem.json'), str(output), '--policy', self.strategy], stdout=log, stderr=subprocess.STDOUT)
        self.planning = dict(stage='active_repair', bed_repair=True, problem=p, folder=folder, output=output, process=proc, log=log, at=now, wall=time.monotonic(), old_routes=deepcopy(self.plan['routes']))
        self.last_repair = now
        self.log('active_plan_invalidated', reasons=reasons, old_validation=invalid, coverage=coverage, states=self.states())
        self.log('planning_requested', stage='active_repair', strategy=self.strategy)

    def dispatch_dense(self, b):
        q = [j for j in self.queues.get(b.rid, []) if j not in self.completed]
        if q and self.tasks[q[0]]['release'] > self.elapsed():
            return
        super().dispatch_dense(b)

    def clear_unresolved_flags(self):
        b = self.peers.get('r2')
        if b:
            for k in ['short', 'long']:
                if b.local_counts.get(k, 0) > 0:
                    self.observed_cleared.pop(k, None)

    def tick(self):
        self.clear_unresolved_flags()
        super().tick()
        if self.failed:
            return
        b = self.peers['r2']
        p = b.pose()
        now = self.elapsed()
        if b.job == 'E1_deliver' and b.cargo == 'E1':
            if self.injection_stage == 0 and b.state == 'NAVIGATING' and (-27.8 < p['y'] < -27.4):
                self.seen_blocked.discard('short')
                self.observed_cleared.pop('short', None)
                self.blocked_since.pop('short', None)
                self.bed_trigger.publish(String(data=json.dumps(dict(phase='short'))))
                self.injection_stage = 1
                self.log('bed_scenario_requested', phase_id='short')
            elif self.injection_stage == 1 and self.observed_cleared.get('short'):
                self.seen_blocked.discard('long')
                self.observed_cleared.pop('long', None)
                self.blocked_since.pop('long', None)
                self.bed_trigger.publish(String(data=json.dumps(dict(phase='long'))))
                self.injection_stage = 2
                self.log('bed_scenario_requested', phase_id='long')
        if self.active_projection and b.job == 'E1_deliver' and (b.cargo == 'E1') and (now > self.active_projection['coverage_projection']['delivery_finish']) and (now - self.last_repair >= 10.0) and (not self.planning):
            self.request_repair(dict(phase='forecast_expired', blocked=any((b.blocked(k) for k in ['short', 'long']))))
        for phase in ['short', 'long']:
            if self.injection_stage == 0 or (phase == 'long' and self.injection_stage < 2) or (phase == 'short' and self.injection_stage >= 2):
                continue
            if b.blocked(phase):
                self.seen_blocked.add(phase)
                self.blocked_since.setdefault(phase, now)
                if now - self.blocked_since[phase] >= self.cfg['bed_experiment']['persistence_seconds'] and now - self.last_repair >= 30.0 and (not self.planning) and (b.cargo == 'E1') and (b.job == 'E1_deliver'):
                    self.request_repair(dict(phase=phase, blocked_since=self.blocked_since[phase], laser_hits=b.hits.get(phase), global_new=b.global_counts.get(phase, 0) - b.baseline.get(phase, 0), local_cells=b.local_counts.get(phase)))
            elif phase in self.seen_blocked and b.hits.get(phase, 0) < 3 and (b.global_counts.get(phase, 0) - b.baseline.get(phase, 0) < 4) and (b.local_counts.get(phase, 0) < 4):
                self.observed_cleared[phase] = now
        self.clear_unresolved_flags()

class Probe(Episode):

    def __init__(self, out, args):
        super().__init__(out, args)
        self.probe = args.probe
        self.tasks = {}
        if self.probe == 'clearance':
            assignment = {'first': 'r1', 'second': 'r2', 'third': 'r3', 'dependent': 'r1'}
            for (j, rid) in assignment.items():
                t = dict(kind='normal', anchor='G1' if j == 'dependent' else 'PW2', duration=2.0, capabilities=['move'], release=0.0, deadline=800.0, resources=[] if j == 'dependent' else ['PW2'], dependencies=['second'] if j in ['third', 'dependent'] else ['first'] if j == 'second' else [], service_role='clearance_dependency_probe', nominal_owner=rid)
                self.tasks[j] = dt.phases(t, self.cfg)
            routes = {'r1': ['first', 'dependent'], 'r2': ['second'], 'r3': ['third']}
        else:
            specs = {'quick': [('park', 'r1', 'BDL')], 'corridor': [('park', 'r1', 'BDL'), ('monitor_pose', 'r3', 'M1'), ('pass', 'r2', 'H1')], 'sensor': [('park', 'r1', 'BDL'), ('monitor_pose', 'r3', 'M1'), ('E1_deliver', 'r2', 'H1')], 'source': [('park', 'r1', 'DL'), ('monitor_pose', 'r3', 'M1'), ('prepare', 'r2', 'CG1'), ('pass', 'r2', 'H1')]}
            assignment = {}
            routes = {r: [] for r in self.cfg['robots']}
            for (j, rid, anchor) in specs[self.probe]:
                dep = ['prepare', 'park', 'monitor_pose'] if j == 'pass' and self.probe == 'source' else ['park', 'monitor_pose'] if j in ['pass', 'E1_deliver'] else []
                self.tasks[j] = dict(kind='normal', anchor=anchor, entry_anchor=anchor, clear_anchor=anchor, duration=2.0, capabilities=['move'], release=0.0, deadline=800.0, resources=[], dependencies=dep, service_role='runtime_probe', approach=0.0, egress=0.0)
                assignment[j] = rid
                routes[rid].append(j)
        self.plan = dict(owners=assignment, starts={j: 0.0 for j in self.tasks}, finishes={j: 800.0 for j in self.tasks}, routes=routes, ends={r: 800.0 for r in self.cfg['robots']})
        self.plan_revision = 1

    def tick(self):
        self.update_motion()
        self.update_neck()
        for (rid, b) in self.peers.items():
            pending = [j for j in self.plan['routes'][rid] if j not in self.completed]
            if b.state == 'IDLE' and pending and all((j in self.completed for j in self.tasks[pending[0]]['dependencies'])):
                if self.probe == 'sensor' and pending[0] == 'E1_deliver':
                    b.cargo = 'E1'
                b.dispatch(pending[0])
        if self.probe == 'sensor':
            b = self.peers['r2']
            if b.job == 'E1_deliver' and b.state == 'NAVIGATING' and (self.injection_stage == 0) and (-27.8 < b.pose()['y'] < -27.3):
                self.injection_stage = 1
                self.bed_trigger.publish(String(data=json.dumps(dict(phase='short'))))
            if self.injection_stage and b.blocked('short' if self.injection_stage == 1 else 'long'):
                self.seen_blocked.add('short' if self.injection_stage == 1 else 'long')
            if self.injection_stage == 1 and 'short' in self.seen_blocked and (b.hits.get('short', 0) < 3) and (b.global_counts.get('short', 0) - b.baseline.get('short', 0) < 4) and (b.local_counts.get('short', 0) == 0):
                self.injection_stage = 2
                self.bed_trigger.publish(String(data=json.dumps(dict(phase='long'))))
        self.finished = len(self.completed) == len(self.tasks)

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--probe', choices=['quick', 'corridor', 'sensor', 'source', 'clearance'])
    args = p.parse_args()
    configure_research_backend()
    from .experiment_modes import install
    install(sys.modules[__name__], args.probe)
    args.arrival = 'pose_handoff'
    args.parking = 'dense_cycle'
    args.localization = 'reference'
    args.mode = 'event'
    args.reference = None
    args.policy = 'milp'
    args.changes = 'physical_bed'
    args.out.mkdir(parents=True, exist_ok=False)
    (args.out / 'runtime_scenario.json').write_text(json.dumps(dt.config(), indent=2))
    from support.clinic_runtime.config import source_manifest
    manifest = source_manifest()
    for (path, h) in manifest.items():
        f = Path(path)
        rel = f.relative_to(ROOT) if f.is_relative_to(ROOT) else Path('protocol_reference.py')
        dst = args.out / 'source' / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, dst)
    (args.out / 'source_manifest.json').write_text(json.dumps(manifest, indent=2))
    rclpy.init()
    c = (Probe if args.probe else Episode)(args.out, args)
    ex = SingleThreadedExecutor()
    ex.add_node(c)
    for rid in c.cfg['robots']:
        b = Bot(rid, c)
        c.peers[rid] = b
        ex.add_node(b)
    begin = time.monotonic()
    ready = False
    last = -1.0
    last_step = -1.0
    try:
        while time.monotonic() - begin < 3600 and (not c.failed) and (not c.finished):
            ex.spin_once(timeout_sec=0.02)
            if not ready:
                if all((b.ready() for b in c.peers.values())) and len(c.truth) == 3:
                    sensor = c.sensor_graph()
                    if not sensor['passed']:
                        if time.monotonic() - begin > 240:
                            c.failed = 'COSTMAP_SCAN_GRAPH_TIMEOUT'
                        continue
                    audit = old.Coordinator.graph_audit(c)
                    audit['costmap_sensor_graph'] = sensor
                    audit['passed'] = audit['passed'] and sensor['passed']
                    (args.out / 'namespace_audit.json').write_text(json.dumps(audit, indent=2))
                    assert audit['passed']
                    c.epoch = c.now() + 1.0
                    ready = True
                    c.publish()
                    c.log('episode_ready', mode='dense_patrol_incident_two_periods')
                elif time.monotonic() - begin > 240:
                    c.failed = 'READY_TIMEOUT'
                continue
            if c.elapsed() < 0:
                continue
            if c.elapsed() - last_step < 0.05:
                continue
            last_step = c.elapsed()
            if c.plan is None and c.planning is None:
                c.cycle_releases.append(dict(cycle=0, nominal_release=0.0, actual_release=c.elapsed(), jobs=sorted(c.tasks)))
                c.log('periodic_release', cycle=0, nominal_release=0.0, jobs=sorted(c.tasks))
                c.submit_dense('normal')
            for b in c.peers.values():
                b.step()
            if c.elapsed() - last >= 0.2:
                c.log('pose_sample', poses={r: b.pose() for (r, b) in c.peers.items()}, truth=c.truth)
                last = c.elapsed()
            c.tick()
        if not c.finished and (not c.failed):
            c.failed = 'EPISODE_TIMEOUT'
    except KeyboardInterrupt:
        c.failed = 'USER_INTERRUPTED'
    except Exception as error:
        c.failed = repr(error)
        c.log('controller_exception', error=repr(error))
        raise
    finally:
        if c.planning and c.planning['process'].poll() is None:
            c.planning['process'].terminate()
        if c.failed:
            for b in c.peers.values():
                if b.nav_handle:
                    b.nav_handle.cancel_goal_async()
        result = dict(passed=c.finished and (not c.failed), failure=c.failed, records=c.records, completed=c.completed, tasks=c.tasks, ledger=c.ledger, protocol=c.protocol.snapshot(), protocol_records=c.protocol_records, planning_records=c.planning_records, truth_samples=c.truth_samples, resource_events=c.resource_events, neck_events=c.neck_events, cycle_releases=c.cycle_releases, event_at=c.event_at, incident_closed_at=c.incident_closed_at, handover_ack=c.handover_ack, deferred_at_event=c.deferred, epoch=c.epoch, wall_seconds=time.monotonic() - begin, localization='gazebo_reference_pose', arrival='pose_handoff', disturbances='physical NormalBed short+sustained; no people', strategy=c.strategy, bed_truth=c.bed_truth, bed_observations=c.observations, scan_samples=c.scan_samples, repair_decisions=c.decisions, active_repairs=c.repairs, observed_cleared=c.observed_cleared, injection_stage=c.injection_stage, obstacle_policy=c.cfg['obstacle_policy'], probe=args.probe)
        (args.out / 'result.json').write_text(json.dumps(result, indent=2))
        c.file.close()
        print('RESULT', args.out, result['passed'], c.failed, flush=True)
        for b in list(c.peers.values()) + [c]:
            ex.remove_node(b)
            b.destroy_node()
        ex.shutdown()
        if rclpy.ok():
            rclpy.shutdown()
    return 0 if result['passed'] else 1
if __name__ == '__main__':
    raise SystemExit(main())
