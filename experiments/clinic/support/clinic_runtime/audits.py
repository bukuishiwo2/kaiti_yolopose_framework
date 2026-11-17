"""Explicit reusable actual-execution audit; no runtime source patching.
Derived from the accepted common and bed audits, preserving the same checks.
"""
from .config import ROOT
from dense_validate import validate as original_validate
from bed_validate import validate as initial_validate
from bed_contract import validate as prefix_validate

def validate(p,plan,scope,claimed=None):
 if p['stage']=='bed_response':return initial_validate(p,plan,scope,claimed)
 if p['stage']=='active_repair':return prefix_validate(p,plan,scope,claimed)
 return original_validate(p,plan,scope,claimed)

def frozen_sources_valid(run):
 for path,h in json.loads((run/'source_manifest.json').read_text()).items():
  p=Path(path);copy=run/'source'/(p.relative_to(ROOT) if p.is_relative_to(ROOT) else Path('protocol_reference.py'))
  if not copy.is_file() or hashlib.sha256(copy.read_bytes()).hexdigest()!=h:return False
 return True

from pathlib import Path
import argparse, json, math, hashlib, csv
import numpy as np
from PIL import Image
from scipy.ndimage import distance_transform_edt

def _audit_common(run, destination=None):
    run = Path(run)
    destination = Path(destination) if destination is not None else run
    destination.mkdir(parents=True, exist_ok=True)
    r = json.loads((run / 'result.json').read_text())
    c = json.loads((run / 'runtime_scenario.json').read_text())
    trace = [json.loads(x) for x in (run / 'trace.jsonl').read_text().splitlines()]
    checks = []

    def ck(v, label):
        checks.append(dict(passed=bool(v), check=label))

    def dist(x, y):
        return math.hypot(x['x'] - y[0], x['y'] - y[1])

    def yaw(a, b):
        return abs(math.atan2(math.sin(a - b), math.cos(a - b)))
    ck(r['passed'] and (not r['failure']), 'controller success')
    ck(json.loads((run / 'namespace_audit.json').read_text())['passed'], 'namespace and TF isolation')
    from .experiment_modes import load_spec
    mode = json.loads((run/'experiment_mode.json').read_text()) if (run/'experiment_mode.json').exists() else load_spec('benchmark')
    expected = {f'C{k}_{rid}_W{n}' for k in [0,1] for rid in c['robots'] for n in range(1,(3 if k==0 else mode['next_cycle_waypoints'])+1)} | {'E1_'+v for v in ['verify','monitor','pickup','deliver']}
    ck(set(r['completed']) == expected and len(r['records']) == len(expected), 'configured unique services and no fake terminal actions')
    ck(all((q['status'] == 'SUCCEEDED' for q in r['records'])), 'all command outcomes success')
    maxpos = maxyaw = 0.0
    navigation = 0
    rows = []
    grants = {e['request']['lease_id']: e for e in r['resource_events'] if e['phase'] == 'granted' and e.get('request', {}).get('lease_id', '').startswith(run.name + ':')}
    releases = {e['request']['lease_id']: e for e in r['resource_events'] if e['phase'] == 'released' and e.get('request', {}).get('lease_id', '').startswith(run.name + ':')}
    intervals = []
    for q in r['records']:
        j = q['job_id']
        t = r['tasks'][j]
        applicable = [e for e in r['planning_records'] if e['returned_at'] <= q['begin'] + 0.06 and j in e['solver']['plan']['owners']]
        ck(bool(applicable), j + ' has accepted MILP before dispatch')
        if applicable:
            accepted = applicable[-1]['solver']['plan']
            ck(accepted['owners'][j] == q['robot'], j + ' actual owner matches latest applicable MILP')
            ck(q['service_started'] >= accepted['starts'][j] - 0.06, j + ' actual service respects accepted start bound')
        if t.get('start_deadline') is not None:
            ck(q['service_started'] <= t['start_deadline'] + 0.06, j + ' actual start deadline')
        target = c['anchors'][t['anchor']]
        v = q.get('arrival_ground_truth', {})
        position = dist(v, target)
        heading = yaw(v['yaw'], target[2])
        maxpos = max(maxpos, position)
        maxyaw = max(maxyaw, heading)
        ck(position <= 0.2 and heading <= 0.3, j + ' physical service pose')
        ck(q['stable_at'] - q['stable_since'] >= 0.7 - 1e-06, j + ' stable .7 seconds')
        ck(q['nav_end'] <= q['stable_at'] <= q['start_requested'] <= q['service_started'] + 0.06 < q['service_finished'], j + ' arrival before service ACK')
        phases = [z['feedback']['phase'] for z in trace if z['phase'] == 'service_feedback' and z['feedback']['task_id'] == q['task_id']]
        ck(phases.count('started') == phases.count('succeeded') == 1, j + ' one independent started/succeeded ACK')
        ck(set(t['capabilities']).issubset(c['capabilities'][q['robot']]), j + ' task capability')
        ck(q['service_started'] >= t['release'] - 0.06 and q['service_finished'] <= t['deadline'] + 0.06, j + ' actual release and finish deadline')
        for dep in t['dependencies']:
            ck(r['completed'][dep]['end'] <= q['service_started'] + 0.06, j + ' real predecessor clear ACK ' + dep)
        sample = [s['poses'][q['robot']] for s in r['truth_samples'] if q['service_started'] <= s['at'] - r['epoch'] <= q['service_finished']]
        ck(len(sample) >= 5 and all((dist(v, target) <= 0.2 and yaw(v['yaw'], target[2]) <= 0.3 for v in sample)), j + ' sampled service stability')
        for att in q['navigation_attempts']:
            navigation += 1
            h = att.get('handoff', {})
            d = h.get('detail', {})
            al = att.get('heading_alignment', {})
            safe = att.get('status') == 5 and d.get('position_error', 99) <= 0.12 and (max((d.get(k, 99) for k in ['tf_age', 'scan_age', 'odom_age'])) < 0.5) and (h.get('requested_at', 0) - h.get('near_since', 0) >= 0.7 - 1e-06) and (al.get('status') == 4) and att.get('arrival_guard_passed')
            recovery = att.get('recovery', {}).get('reason') == 'controller_abort_wait_then_replan' and any((n['leg'] == att['leg'] and (n.get('status') == 4 or n.get('handoff')) and (n['begin'] > att['end']) for n in q['navigation_attempts']))
            bedwait = bool(att.get('obstacle_wait')) and att.get('status') in [5, 6] and any((n['leg'] == att['leg'] and n['begin'] > att['end'] and n.get('arrival_guard_passed') for n in q['navigation_attempts']))
            ck(att.get('status') == 4 or safe or recovery or bedwait, j + ' Nav2/composite leg ' + att['leg'])
        for query in q.get('path_checks', []):
            if query['accepted']:
                ck(query['length'] <= query['limit'] + 1e-06 and query['endpoint_error'] <= 0.12, j + ' approved path length and true endpoint ' + query['leg'])
        if t['resources']:
            res = t['resources'][0]
            lease = f"{run.name}:{j}:{q['robot']}"
            ck(lease in grants and lease in releases, j + ' closed resource lease')
            if lease in grants and lease in releases:
                (g, z) = (grants[lease], releases[lease])
                (lo, hi) = (g['at'] - r['epoch'], z['at'] - r['epoch'])
                ck(q['gate_arrival'] <= lo + 0.06 <= q['service_started'] + 0.06 and q['service_finished'] <= q['clear_at'] and (q['clear_at'] <= hi + 0.06) and (hi <= q['end'] + 0.06) and (q['clear_at'] <= q['lease_released_at'] <= q['end']), j + ' entry/service/clear/release ACK ordering')
                ck(dist(q['clear_ground_truth'], c['anchors'][res]) >= 1.5 and dist(q['clear_ground_truth'], c['anchors'][t['clear_anchor']]) <= 0.3, j + ' physically cleared station')
                intervals.append(dict(job=j, robot=q['robot'], resource=res, start=lo, finish=hi))
        rows.append(dict(job=j, robot=q['robot'], cycle=t.get('cycle_id'), anchor=t['anchor'], begin=q['begin'], service_start=q['service_started'], service_finish=q['service_finished'], clear=q.get('clear_at'), end=q['end'], position_error=position))
    ck(len(grants) == len(releases) == sum(bool(t['resources']) for t in r['tasks'].values()), 'all configured station transactions complete')
    for (i, x) in enumerate(intervals):
        for y in intervals[i + 1:]:
            if x['resource'] == y['resource']:
                ck(x['finish'] + c['resource_buffer'] <= y['start'] + 0.06 or y['finish'] + c['resource_buffer'] <= x['start'] + 0.06, 'actual station exclusivity and buffer ' + x['job'] + y['job'])
    for rid in c['robots']:
        q = sorted([q for q in r['records'] if q['robot'] == rid], key=lambda q: q['begin'])
        ck(all((x['end'] <= y['begin'] + 0.06 for (x, y) in zip(q, q[1:]))), rid + ' serial actual execution')
    (v, m, pu, de) = (r['completed']['E1_' + x] for x in ['verify', 'monitor', 'pickup', 'deliver'])
    ck(v['end'] <= m['service_started'] and m['service_started'] <= pu['service_started'] + 0.06 and (m['service_finished'] >= de['service_finished'] - 0.06), 'actual monitoring covers pickup through delivery')
    ck(m['robot'] != pu['robot'] and pu['robot'] == de['robot'], 'distinct monitor and same courier')
    seq = [q['job_id'] for q in r['records'] if q['robot'] == pu['robot']]
    ck(seq.index('E1_deliver') == seq.index('E1_pickup') + 1, 'single-package adjacent pickup-delivery')
    ha = next((e for e in trace if e['phase'] == 'scripted_handover_ack'))
    stop = next((e for e in trace if e['phase'] == 'monitor_stop_requested_after_handover'))
    ck(ha['episode_time'] >= de['end'] and stop['episode_time'] >= ha['episode_time'] and (m['service_finished'] >= stop['episode_time']), 'monitor stop follows real delivery and scripted receiver ACK')
    ck(r['protocol']['event']['lifecycle'] == 'COMPLETED' and r['incident_closed_at'] >= max((q['end'] for (j, q) in r['completed'].items() if j.startswith('E1_'))) - 0.06, 'event closed only after actual emergency tasks')
    injected = next((e for e in trace if e['phase'] == 'fall_event_injected'))
    ck(all((r['completed'][f'C0_{rid}_W1']['end'] <= r['event_at'] + 0.06 for rid in c['robots'])) and sum((s == 'NAVIGATING' for s in injected['states'].values())) >= 2, 'fall during three real patrols and two active navigation commands')
    release = next((x for x in r['cycle_releases'] if x['cycle'] == 1))
    ck(release['actual_release'] >= r['incident_closed_at'] and abs(release['actual_release'] - (c['period_seconds'] if mode['name']=='benchmark' else max(mode['nominal_next_release'],r['incident_closed_at']+15.))) < 0.12, 'next period released by configured clock/actual closure rule')
    ck(all((q['begin'] >= release['actual_release'] - 0.06 for (j, q) in r['completed'].items() if j.startswith('C1_'))), 'cycle1 not dispatched before release')
    ck(all((r['ledger'][j]['state'] == 'SUCCEEDED' for j in r['ledger'])), 'patrol ledger drained without lost tasks')
    resumed = [j for j in r['deferred_at_event'] if r['completed'][j]['begin'] >= r['incident_closed_at']]
    ck(bool(resumed), 'deferred routine actually resumes after closure')
    parallel_normal = [j for (j, q) in r['completed'].items() if j.startswith('C0_') and q['begin'] >= r['event_at'] and (q['service_started'] < de['service_finished']) and (q['service_finished'] > m['service_started']) and (q['robot'] not in [m['robot'], pu['robot']])]
    ck(bool(parallel_normal), 'third robot routine work overlaps emergency monitor/courier')
    verify_entry = next((e for e in r['planning_records'] if e['stage'] == 'verify'))
    verify_input = json.loads(Path(verify_entry['problem_path']).read_text())
    issued = [x['job'] for pre in verify_input['prefixes'].values() for x in pre['schedule']]
    last_issued_clear = max((r['completed'][j]['end'] for j in issued), default=r['event_at'])
    verify_patrol_overlap = max(0.0, last_issued_clear - v['service_started'])
    forecasts = []
    for e in r['planning_records']:
        p = json.loads(Path(e['problem_path']).read_text())
        s = e['solver']
        v = validate(p, s['plan'], s['scope'], s['objective'])
        ck(v['passed'] and e['commit_validation']['passed'], e['stage'] + ' complete mathematical witness')
        if e['stage'] == 'response':
            for (j, t) in p['tasks'].items():
                if t['kind'] == 'normal' and j == p.get('necessary_normal'):
                    ck(s['plan']['owners'][j] not in [s['plan']['owners']['E1_monitor'], s['plan']['owners']['E1_pickup']], j + ' MILP third robot separation')
        for (rid, pre) in p['prefixes'].items():
            for x in pre['schedule']:
                actual = r['completed'][x['job']]
                ck(actual['robot'] == rid and actual['task_id'] == pre['record_task_id'], e['stage'] + ' preserved issued command ' + x['job'])
                ck(x['job'] not in p['actual_known_finishes'], e['stage'] + ' forecast is not actual completion')
                forecasts.append(dict(stage=e['stage'], job=x['job'], forecast=x['clear_forecast'], actual=actual['end'], overrun=max(0.0, actual['end'] - x['clear_forecast'])))
    min_pair = float('inf')
    min_static = float('inf')
    min_body = float('inf')
    inside_roi = 0
    roi_samples = 0
    distances = {rid: 0.0 for rid in c['robots']}
    previous = {}
    grid = distance_transform_edt(np.array(Image.open(run / 'source/config/hospital_dense/semantic_navigation.pgm')) > 200) * 0.05 if (run / 'source/config/hospital_dense/semantic_navigation.pgm').exists() else distance_transform_edt(np.array(Image.open(ROOT / 'config/hospital_aligned/semantic_navigation.pgm')) > 200) * 0.05
    for s in r['truth_samples']:
        if s['at'] < r['epoch']:
            continue
        for (rid, p) in s['poses'].items():
            roi_samples += 1
            inside_roi += bool(6 <= p['x'] <= 26 and -33.5 <= p['y'] <= -8.5)
            if r['event_at'] <= s['at'] - r['epoch'] <= r['incident_closed_at']:
                e = c['event']
                dx = p['x'] - e['center'][0]
                dy = p['y'] - e['center'][1]
                u = dx * math.cos(e['body_yaw']) + dy * math.sin(e['body_yaw'])
                v = -dx * math.sin(e['body_yaw']) + dy * math.cos(e['body_yaw'])
                min_body = min(min_body, math.hypot(max(0.0, abs(u) - e['body_length'] / 2), max(0.0, abs(v) - e['body_width'] / 2)) - 0.17)
            min_static = min(min_static, float(grid[999 - int((p['y'] + 50) / 0.05), int(p['x'] / 0.05)]))
            if rid in previous:
                distances[rid] += math.hypot(p['x'] - previous[rid]['x'], p['y'] - previous[rid]['y'])
            previous[rid] = p
        for (u, w) in [('r1', 'r2'), ('r1', 'r3'), ('r2', 'r3')]:
            min_pair = min(min_pair, math.hypot(s['poses'][u]['x'] - s['poses'][w]['x'], s['poses'][u]['y'] - s['poses'][w]['y']))
    ck(min_body >= 0.35, 'sampled robot-to-scripted-body footprint safety margin')
    cycle1_travel = {}
    for rid in c['robots']:
        jobs = [q for q in r['records'] if q['robot'] == rid and q['job_id'].startswith('C1_')]
        if not jobs:
            cycle1_travel[rid] = 0.0
            continue
        lo = min((q['begin'] for q in jobs))
        hi = max((q['end'] for q in jobs))
        pts = [z['poses'][rid] for z in r['truth_samples'] if lo <= z['at'] - r['epoch'] <= hi]
        cycle1_travel[rid] = sum((math.hypot(y['x'] - x['x'], y['y'] - x['y']) for (x, y) in zip(pts, pts[1:])))
        ck(cycle1_travel[rid] > 5.0, rid + ' actual new-cycle patrol movement')
    ck(inside_roi == roi_samples, 'all sampled centers inside original 20x25m ROI')
    ck(min_pair > 0.34 and min_static >= 0.17, 'sampled static/inter-robot circular clearance')
    ck(frozen_sources_valid(run), 'execution source files still match frozen manifest')
    summary = dict(passed=all((x['passed'] for x in checks)), checks=len(checks), failed=[x['check'] for x in checks if not x['passed']], services=len(r['completed']), normal_services=mode['expected_normal_services'], event_services=4, navigation_actions=navigation, controller_recoveries=sum((bool(att.get('recovery')) for q in r['records'] for att in q['navigation_attempts'])), path_wait_queries=sum((not x['accepted'] for q in r['records'] for x in q.get('path_checks', []))), episode_sim_seconds=max((q['end'] for q in r['records'])), event_at=r['event_at'], incident_closed_at=r['incident_closed_at'], response_seconds=r['incident_closed_at'] - r['event_at'], verify_started_before_last_issued_patrol_clear_seconds=verify_patrol_overlap, verify_plan_commit_before_last_issued_clear=verify_entry['returned_at'] < last_issued_clear, next_cycle_release=release, roles={x: r['completed']['E1_' + x]['robot'] for x in ['verify', 'monitor', 'pickup', 'deliver']}, parallel_normal_jobs=parallel_normal, resumed_deferred_jobs=resumed, max_position_error=maxpos, max_yaw_error=maxyaw, min_sampled_robot_center_distance=min_pair, min_sampled_static_center_clearance=min_static, distance_m=distances, cycle1_distance_m=cycle1_travel, roi_sample_fraction=inside_roi / roi_samples, min_sampled_body_surface_clearance=min_body, resource_intervals=intervals, prefix_forecasts=forecasts, prefix_forecast_overruns=[x for x in forecasts if x['overrun'] > 0.06], localization=r['localization'], scope='One no-disturbance physical patrol/incident/two-period validation; no beds, people, energy, AMCL or strategy superiority proof')
    initial = r['planning_records'][0]['solver']['plan']
    changes = []
    for (j, q) in r['completed'].items():
        if r['tasks'][j]['kind'] == 'normal':
            changes.append(dict(job=j, nominal_owner=r['tasks'][j]['nominal_owner'], actual_owner=q['robot'], cycle=r['tasks'][j]['cycle_id'], original_start=initial['starts'].get(j), actual_service_start=q['service_started'], shift_from_initial=q['service_started'] - initial['starts'][j] if j in initial['starts'] else None, after_incident_close=q['begin'] >= r['incident_closed_at']))
    summary['normal_owner_changes'] = sum((x['nominal_owner'] != x['actual_owner'] for x in changes))
    with (destination / 'patrol_changes.csv').open('w') as f:
        w = csv.DictWriter(f, fieldnames=list(changes[0]))
        w.writeheader()
        w.writerows(changes)
    (destination / 'independent_audit.json').write_text(json.dumps(summary, indent=2))
    (destination / 'audit_source.py').write_text(Path(__file__).read_text())
    with (destination / 'actual_services.csv').open('w') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    return summary

def audit(run, destination):
    run = Path(run)
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    r = json.loads((run / 'result.json').read_text())
    base = _audit_common(run, destination)
    if not base['passed']:
        return base
    trace = [json.loads(x) for x in (run / 'trace.jsonl').read_text().splitlines()]
    checks = []

    def ck(v, name):
        checks.append(dict(passed=bool(v), check=name))
    ck(r['injection_stage'] == 2, 'both scenario injections requested')
    ck(bool(r['active_repairs']), 'active-event repair actually committed')
    intervals = {}
    for phase in ['short', 'long']:
        items = [v for v in r['bed_truth'] if v.get('phase_id') == phase]
        start = next((v['at'] - r['epoch'] for v in items if v['action'] == 'inserted'))
        end = next((v['at'] - r['epoch'] for v in items if v['action'] == 'removed'))
        intervals[phase] = dict(start=start, finish=end, duration=end - start)
        obs = [v for v in r['bed_observations'] if start <= v['at'] <= end and v['hits'].get(phase, 0) >= 4 and (v['global_counts'].get(phase, 0) - v['baseline'].get(phase, 0) >= 4)]
        ck(bool(obs), phase + ' real laser and new global costmap occupancy')
        ck(any((v['local_counts'].get(phase, 0) > 0 for v in obs)), phase + ' actual local costmap evidence')
        if phase == 'short':
            next_start = next((v['at'] - r['epoch'] for v in r['bed_truth'] if v.get('phase_id') == 'long' and v['action'] == 'inserted'))
            next_block = min((v['at'] for v in r['bed_observations'] if v['at'] >= next_start and v['hits'].get('long', 0) >= 4 and (v['global_counts'].get('long', 0) - v['baseline'].get('long', 0) >= 4)))
            clear_witness = [v['at'] for v in r['bed_observations'] if end <= v['at'] < next_block and v['hits'].get('short', 0) < 3 and (v['global_counts'].get('short', 0) - v['baseline'].get('short', 0) < 4) and (v['local_counts'].get('short', 0) == 0)]
            base['short_historical_clear_sensor_times'] = clear_witness
            ck(bool(clear_witness), 'short real sensor clearance before next observed obstruction; historical flag may be superseded')
        else:
            ck(phase in r['observed_cleared'], phase + ' observed clear without hidden release time')
    ck(not any((intervals['short']['start'] <= e['requested_at'] <= intervals['short']['finish'] for e in r['active_repairs'])), 'short obstacle did not invoke task repair')
    ck(all((e['requested_at'] >= intervals['long']['start'] + 14.0 for e in r['active_repairs'])), 'persistent observation before task repair')
    ck(all((e['commit_validation']['commitments']['passed'] for e in r['active_repairs'])), 'all active goal/monitor/custody commitments preserved at commit')
    for e in r['active_repairs']:
        decision = next((d for d in r['repair_decisions'] if abs(d['at'] - e['requested_at']) < 1e-06))
        ck(not decision['old_validation']['passed'], 'each committed repair follows a measured old-plan constraint violation')
        p = json.loads(Path(e['problem_path']).read_text())
        cov = p['coverage_projection']
        ck(cov['monitor_release'] >= cov['delivery_finish'] + 3.0, 'projected monitor covers delivery and handover')
        ck(cov['observation_horizon'] in [0.0, 30.0], 'observation horizon not actual script remaining time')
        ck(p['actual_snapshot'][cov['courier']]['cargo'] == 'E1', 'actual carried package kept')
        ck(p['active_commitments'][cov['monitor']]['actual_service_started'] == r['completed']['E1_monitor']['service_started'], 'monitor original started ACK unchanged')
        ck(e['solver']['validation']['passed'], 'repair complete suffix MILP constraints')
    first = r['active_repairs'][0]
    routine = r['completed']['C0_r1_W3']
    ck(routine['begin'] <= first['requested_at'] and routine['end'] >= first['returned_at'], 'unaffected R1 current task continues through repair')
    ck(abs(routine['service_finished'] - routine['service_started'] - 90.0) < 0.12, 'unaffected routine stock-check not interrupted or shortened')
    ck(any((not d['old_validation']['passed'] for d in r['repair_decisions'])), 'old normal suffix actually violates projected constraints')
    ck(all((r['completed'][j]['robot'] == 'r2' for j in ['E1_pickup', 'E1_deliver'])), 'same courier before and after obstruction')
    if r['strategy'] == 'full_warm':
        ck(any((e['solver'].get('mip_start_accepted') for e in r['active_repairs'])), 'CBC actually accepted full-replan MIPStart')
    stops = [x['episode_time'] for x in trace if x['phase'] == 'bed_stopped']
    resumes = [x['episode_time'] for x in trace if x['phase'] == 'bed_observed_clear_resume']
    drifts = []
    for stop in stops:
        resume = next((x for x in resumes if x > stop))
        pts = [v['poses']['r2'] for v in r['truth_samples'] if stop + 1 <= v['at'] - r['epoch'] <= resume - 0.1]
        if pts:
            drifts.append(max((math.hypot(q['x'] - pts[0]['x'], q['y'] - pts[0]['y']) for q in pts)))
    for resume in resumes:
        prior = [v for v in r['bed_observations'] if resume - 0.95 <= v['at'] <= resume]
        ck(len(prior) >= 3 and all((v['hits'].get('long', 0) < 3 and v['global_counts'].get('long', 0) - v['baseline'].get('long', 0) < 4 and (v['local_counts'].get('long', 0) == 0 if 'local_raw_counts' in v else v['local_counts'].get('long', 0) < 4) for v in prior)), 'resume follows stable real laser/global/local clearance')
    ck(all((v['pose']['y'] <= -23.6 for v in trace if v['phase'] == 'bed_stopped')), 'northbound courier did not stop for an already passed bed region')
    ck(bool(drifts) and max(drifts) < 0.1, 'measured safe stationary waiting after cancellation')
    minimum = float('inf')
    for sample in r['truth_samples']:
        at = sample['at'] - r['epoch']
        for phase in ['short', 'long']:
            pose = [v for v in r['bed_truth'] if v.get('phase_id') == phase and v['at'] - r['epoch'] <= at]
            if not pose or pose[-1]['action'] == 'removed':
                continue
            v = pose[-1]
            angle = v.get('yaw', math.pi / 2)
            for q in sample['poses'].values():
                (dx, dy) = (q['x'] - v['x'], q['y'] - v['y'])
                u = dx * math.cos(angle) + dy * math.sin(angle)
                w = -dx * math.sin(angle) + dy * math.cos(angle)
                minimum = min(minimum, math.hypot(max(0.0, abs(u) - 1.02), max(0.0, abs(w) - 0.52)) - 0.17)
    ck(minimum >= 0.0, 'sampled robot footprint outside conservative bed rectangle')
    base['min_sampled_bed_surface_clearance_m'] = minimum
    base['bed_checks'] = checks
    base['bed_intervals'] = intervals
    base['bed_wait_drift_m'] = drifts
    base['active_repair_count'] = len(r['active_repairs'])
    base['checks'] += len(checks)
    base['failed'] += [q['check'] for q in checks if not q['passed']]
    base['passed'] = not base['failed']
    base['scope'] = 'Two actual short/sustained bed episodes; active monitor/custody kept; shared suffix MILP comparison, no pedestrians or real hardware'
    base['strategy'] = r['strategy']
    base['repair_metrics'] = [dict(requested=e['requested_at'], committed=e['returned_at'], wall=e['end_to_end_wall'], status=e['solver']['status'], objective=e['solver']['objective'], free=len(e['solver']['scope']['free']), suffix=len(e['solver']['plan']['owners']), mip_start=e['solver'].get('mip_start_accepted')) for e in r['active_repairs']]
    (destination / 'independent_audit.json').write_text(json.dumps(base, indent=2))
    (destination / 'bed_audit_source.py').write_text(Path(__file__).read_text())
    return base
