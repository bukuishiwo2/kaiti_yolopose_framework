#!/usr/bin/env python3
"""Read-only audit of saved measured visual/bed execution and paired solves."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

P = Path(__file__).resolve().parents[1]
W = Path('/home/yhc/clinic_planning_ws')
sys.path[:0] = [str(P/'src'), str(W/'tools')]
from audit_clinic_visual_positive import native_arrival


def audit(run):
    import bed_contract as bc
    s = json.loads((run/'summary.json').read_text())
    rows = [json.loads(line) for line in (run/'trace.jsonl').open()]
    checks = {}
    records = {r['job_id']: r for r in s.get('records', [])}
    proto = s.get('protocol', {}); pt = proto.get('tasks', {})
    checks['controller_completed'] = s.get('passed') is True
    checks['event_completed'] = (proto.get('event') or {}).get('lifecycle') == 'COMPLETED'
    expected=14 if s.get('post_monitor_clearance_required') else 13
    checks['exact_finite_backlog_completed'] = set(records) == set(s['tasks']) and len(records) == expected and set(s['completed']) == set(s['tasks'])
    checks['three_real_robots'] = {r['robot'] for r in records.values()} == {'r1','r2','r3'}
    checks['no_injected_fall_or_failure'] = not any(r['phase'] in {'fall_event_injected','injected_task_failure'} for r in rows)
    models = {r['sample']['sample_id']: r['sample'] for r in rows if r['phase'] == 'visual_model_transition'}
    candidates = [r for r in rows if r['phase'] == 'visual_candidate_created']
    checks['unique_real_model_candidate'] = len(candidates) == 1 and all(
        c['caused_by'] in models and models[c['caused_by']]['stable'] and models[c['caused_by']]['window_ready'] for c in candidates)
    checks['one_video_pass_only'] = s.get('video_repeats') == 1 and bool(models) and all(':A:0:' in k for k in models)
    video = json.loads((run/'video/summary.json').read_text()) if (run/'video/summary.json').exists() else {}
    checks['replay_finished'] = video.get('status') == 'PASS' and len(video.get('cases',[])) == 1 and video['cases'][0]['frames_per_replay'] == [160]
    review = json.loads((run/'review.json').read_text())
    checks['explicit_review_source_not_service_invention'] = (review.get('result') == 'fall' and
        review.get('source') == 'controlled_visual_review' and Path(review.get('evidence_id','')).is_file() and
        hashlib.sha256(Path(review['evidence_id']).read_bytes()).hexdigest() == review.get('evidence_sha256'))
    plans = {q['stage']: q for q in s.get('planning_records', [])}
    checks['native_verify_response_solver'] = all(k in plans and plans[k]['commit_validation']['passed'] and
        plans[k]['solver']['status'] in {'OPTIMAL','FEASIBLE_BUDGET'} for k in ['verify','response'])
    for j,r in records.items():
        checks[j+'_arrival_fresh_stable_ACK'] = native_arrival(r)
        fb = [q['feedback'] for q in rows if q['phase']=='service_feedback' and q['feedback']['task_id']==r['task_id']]
        checks[j+'_worker_token'] = {'started','succeeded'}.issubset({q['phase'] for q in fb}) and all(
            q.get('robot') == r['robot'] and q.get('attempt') == 1 and
            (not s['tasks'][j].get('protocol_task_id') or q.get('task_revision') == r.get('sent_revision')) for q in fb)
    mon = records.get('E1_monitor',{}); pick = records.get('E1_pickup',{}); drop = records.get('E1_deliver',{})
    checks['four_protocol_services_succeeded'] = all(pt.get('E1:'+role,{}).get('state')=='SUCCEEDED' for role in ['verify','monitor','pickup','deliver'])
    checks['continuous_monitor_covers_pickup_and_drop'] = (mon.get('robot')=='r1' and
        mon.get('service_started',1e9) <= pick.get('service_started',-1) and
        mon.get('service_finished',-1) >= drop.get('service_finished',1e9))
    cfg=json.loads((run/'runtime_scenario.json').read_text())
    witness=[r for r in s.get('pose_records',[]) if mon.get('service_started',1e9)<=r['at']<=mon.get('service_finished',-1)]
    distances=[math.hypot(r['poses']['r1']['x']-cfg['anchors']['M1'][0],r['poses']['r1']['y']-cfg['anchors']['M1'][1]) for r in witness]
    checks['measured_monitor_occupancy_continuous'] = bool(distances) and max(distances)<=.20 and all(r['states']['r1']['job']=='E1_monitor' for r in witness)
    checks['same_courier_custody'] = pick.get('robot') == drop.get('robot') == 'r2' and drop.get('begin',-1) >= pick.get('end',1e9)
    checks['no_overlapping_robot_jobs'] = all(
        all(a.get('end',1e9) <= b['begin']+1e-6 for a,b in zip(sequence,sequence[1:]))
        for rid in ['r1','r2','r3']
        for sequence in [sorted([r for r in records.values() if r['robot']==rid],key=lambda r:r['begin'])])
    checks['actual_dependencies_and_deadlines'] = all(
        r.get('service_finished',1e9) <= s['tasks'][j]['deadline']+1e-6 and
        all(records.get(dep,{}).get('end',1e9) <= r['begin']+1e-6 for dep in s['tasks'][j]['dependencies'])
        for j,r in records.items())
    checks['pickup_lease_clear_before_release'] = (pick.get('lease_granted_at',1e9) <= pick.get('service_started',-1) and
        pick.get('lease_released_at',-1) >= pick.get('clear_at',0) > pick.get('service_finished',1e9))
    handovers=[r for r in rows if r['phase']=='scripted_handover_ack']
    checks['actual_drop_then_receiver_handover_then_monitor_release'] = (s.get('handover_ack') is True and
        len(handovers)==1 and drop.get('end',1e9)<=handovers[0]['episode_time']<=mon.get('service_finished',-1))
    resources=[r['resource'] for r in rows if r['phase']=='resource_feedback']
    checks['final_resource_owners_and_queue_clear'] = bool(resources) and not resources[-1]['owners'] and not any(resources[-1].get('queue',{}).values())
    leases={}
    for j,r in records.items():
        for resource in s['tasks'][j]['resources']:
            leases.setdefault(resource,[]).append((r.get('lease_granted_at',-1),r.get('lease_released_at',1e9),j))
    checks['physical_shared_resource_intervals_disjoint'] = all(
        all(a[1]<=b[0]+1e-6 for a,b in zip(seq,seq[1:])) for seq in [sorted(v) for v in leases.values()])
    checks['every_shared_resource_lease_cleared_legally'] = all(
        r.get('lease_granted_at',1e9)<=r.get('service_started',-1) and r.get('lease_released_at',-1)>=r.get('clear_at',0)>r.get('service_finished',1e9)
        for j,r in records.items() if s['tasks'][j]['resources'])
    checks['all_online_commitment_checks_pass'] = bool(s.get('online_checks')) and all(q['passed'] for q in s['online_checks'])
    checks['monitor_release_guard_exercised'] = any(q.get('monitor_release_guard',{}).get('allowed') is False for q in s.get('online_checks',[]) if q.get('monitor_release_guard'))
    checks['no_activity_service_cancel'] = not any(q['phase']=='service_feedback' and q['feedback']['phase']=='cancelled' for q in rows)
    before = json.loads((run/'before_bed.json').read_text()) if (run/'before_bed.json').exists() else {}
    states = before.get('states',{})
    checks['bed_before_pickup_with_live_monitor_peer'] = (states.get('r1',{}).get('job')=='E1_monitor' and
        states.get('r1',{}).get('record',{}).get('service_started') is not None and
        states.get('r2',{}).get('job')=='E1_pickup' and states.get('r2',{}).get('cargo') is None and
        states.get('r2',{}).get('record',{}).get('service_started') is None and
        str(states.get('r3',{}).get('job','')).startswith('C0_'))
    if s.get('post_monitor_clearance_required'):
        initial=[r for r in rows if r['phase']=='initial_clearance_committed']
        checks['same_clearance_policy_before_any_bed'] = (len(initial)==1 and
            initial[0]['episode_time']<before.get('at',-1) and
            'E1_monitor_clear' in initial[0]['plan']['routes']['r1'])
        folder=run/'initial_clearance'
        ip=json.loads((folder/'problem.json').read_text()) if (folder/'problem.json').exists() else {}
        ir=json.loads((folder/'result.json').read_text()) if (folder/'result.json').exists() else {}
        checks['initial_clearance_native_independent_validation'] = bool(ip) and ir.get('status') in ['OPTIMAL','FEASIBLE_BUDGET'] and bc.validate(ip,ir['plan'],ir['scope'],ir['objective'])['passed']
        checks['initial_forecasts_not_actual_ACKs'] = bool(ip) and not ip['active_commitments'] and 'E1_monitor_clear' not in ip['actual_known_finishes']
        clear=records.get('E1_monitor_clear',{})
        checks['real_monitor_TL_V3_clearance'] = (clear.get('robot')=='r1' and
            clear.get('begin',-1)>=mon.get('end',1e9) and
            s['tasks'].get('E1_monitor_clear',{}).get('clear_anchor')=='V3' and native_arrival(clear))
        checks['courier_normal_waits_actual_clearance_ACK'] = bool(clear) and all(
            r['begin']>=clear.get('end',1e9) for j,r in records.items() if r['robot']=='r2' and s['tasks'][j]['kind']=='normal' and r['begin']>mon.get('begin',1e9))
        checks['clearance_certificate_matches_actual_evidence'] = False
        if (run/'clearance_certificate.json').exists():
            cert=json.loads((run/'clearance_certificate.json').read_text());source=Path(cert.get('evidence',''))
            checks['clearance_certificate_matches_actual_evidence'] = cert.get('passed') is True and source.is_file() and hashlib.sha256(source.read_bytes()).hexdigest()==cert.get('evidence_sha256')
    actions = {v['action'] for v in s.get('bed_truth',[])}
    checks['physical_gazebo_bed_insert_pose_remove_ACK'] = {'inserted','pose','removed'}.issubset(actions)
    removals=[v['at']-s.get('epoch',0) for v in s.get('bed_truth',[]) if v['action']=='removed']
    resumes=[r['episode_time'] for r in rows if r['phase']=='bed_observed_clear_resume' and r.get('job')=='E1_pickup']
    checks['actual_object_removal_before_observed_clear_resume'] = bool(removals) and bool(resumes) and min(removals)<=min(resumes)
    req = [(i,r) for i,r in enumerate(rows) if r['phase']=='bed_navigation_cancel_requested']
    acks = [(i,r['ack']) for i,r in enumerate(rows) if r['phase']=='bed_navigation_cancel_ACK']
    checks['real_cancel_ACK_before_wait_or_release'] = len(req)==len(acks)==1
    if checks['real_cancel_ACK_before_wait_or_release']:
        i,r = req[0]; k,a = acks[0]
        checks['real_cancel_ACK_before_wait_or_release'] = (i<k and a['passed'] and a['status']==5 and
            r['goal_uuid']==a['goal_uuid'] and r['task_id']==a['task_id'] and not any(
                q['phase'] in {'motion_path_released','bed_stopped','bed_observed_clear_resume'} and q.get('robot')=='r2' for q in rows[i:k]))
    checks['actual_cancelled_navigation_retried'] = (len(pick.get('navigation_attempts',[]))>=2 and
        any(n.get('status')==5 and n.get('obstacle_wait') for n in pick.get('navigation_attempts',[])))
    checks['real_observed_clear_resume'] = any(r['phase']=='bed_observed_clear_resume' and r.get('job')=='E1_pickup' for r in rows)
    cases = []; checks['at_least_one_real_invalid_snapshot'] = bool(s.get('repair_cases'))
    for i,case in enumerate(s.get('repair_cases',[])):
        folder = Path(case['folder']); p = json.loads((folder/'problem.json').read_text())
        old = bc.validate(p,p['reference'],dict(free=list(p['tasks']),freeze_time=False))
        snap = json.loads((folder/'snapshot.json').read_text()); obs = p['observation']
        checks[f'repair{i}_real_sensor_invalidation'] = (not old['passed'] and obs['hits']>=4 and obs['global_new']>=4 and
            obs['at']-obs['blocked_since']>=15. and snap['states']['r2']['state']=='BED_WAIT' and
            snap['states']['r2']['cargo'] is None)
        pair = json.loads((folder/'pair/summary.json').read_text()); policies = pair['policies']
        checks[f'repair{i}_same_input_budget'] = (len(policies)==2 and
            {r['input_sha256'] for r in policies}=={hashlib.sha256((folder/'problem.json').read_bytes()).hexdigest()} and
            len({r['budget'] for r in policies})==1)
        checks[f'repair{i}_no_hidden_bed_removal_input'] = not any(k in p for k in ['bed_truth','long_hold','removal_time','hold']) and p['coverage_projection']['observation_horizon']==30.
        for r in policies:
            result=json.loads(Path(r['result']).read_text())
            validation=bc.validate(p,result['plan'],result['scope'],result['objective']) if result['status'] in {'OPTIMAL','FEASIBLE_BUDGET'} else {'passed':False}
            checks[f'repair{i}_{r["policy"]}_independent_constraints'] = validation['passed']
        fence = json.loads((folder/'commit_fence.json').read_text()) if (folder/'commit_fence.json').exists() else {}
        checks[f'repair{i}_fresh_commit_fence'] = fence.get('passed') is True and all(v['passed'] for v in fence.get('checks',{}).values())
        if s.get('post_monitor_clearance_required'):
            checks[f'repair{i}_old_plan_includes_same_clearance_policy'] = ('E1_monitor_clear' in snap['plan']['routes']['r1'] and
                snap['tasks']['E1_monitor_clear']==p['committed_future']['E1_monitor_clear']['task'])
        cases.append(dict(folder=str(folder),old_validation=old,pair=pair,commit_passed=fence.get('passed')))
    committed = [r for r in rows if r['phase']=='visual_repair_committed']
    checks['local_result_actually_committed'] = bool(committed)
    checks['monitor_and_courier_not_reassigned'] = all(r['plan']['owners']['E1_monitor']=='r1' and
        r['plan']['owners']['E1_pickup']==r['plan']['owners']['E1_deliver']=='r2' for r in committed)
    prefix_checks=[]
    for c in cases:
        snap=json.loads((Path(c['folder'])/'snapshot.json').read_text())
        fence_path=Path(c['folder'])/'commit_fence.json'
        if not fence_path.exists():prefix_checks.append(False);continue
        current=json.loads(fence_path.read_text())['current']
        issued=snap['states']['r3'];job=issued['job']
        later=current['completed'].get(job) or current['states']['r3']['record']
        prefix_checks.append(job is not None and issued.get('record',{}).get('task_id')==later.get('task_id'))
    checks['issued_r3_prefix_preserved'] = bool(prefix_checks) and all(prefix_checks)
    degraded = [r['evidence'] for r in rows if r['phase']=='separate_evidence_validity' and r['evidence'].get('verified') and not r['evidence']['behavior_valid']]
    checks['EOF_behavior_expired_registration_valid_monitor_kept'] = bool(degraded) and all(e['position_valid'] for e in degraded)
    checks['model_timestamps_not_refreshed_by_ticks'] = bool(degraded) and len({e['behavior_last_observation'] for e in degraded})==1
    checks['cleanup'] = json.loads((run/'cleanup.json').read_text()).get('passed') is True
    manifest = json.loads((run/'visual_source_manifest.json').read_text())
    static = json.loads((run/'static_preflight.json').read_text())
    checks['current_sources_match_saved_run_manifest'] = all(Path(f).is_file() and hashlib.sha256(Path(f).read_bytes()).hexdigest()==h for f,h in {**manifest,**static['source_hashes']}.items())
    return dict(passed=all(checks.values()),checks=checks,cases=cases,run=str(run),
        monitor_occupancy=dict(samples=len(witness),max_distance=max(distances,default=None)),
        measured_resource_intervals=leases,
        summary_sha256=hashlib.sha256((run/'summary.json').read_bytes()).hexdigest(),
        scope='one physical pre-pickup bed instance; only local policy executed online; full policy same-snapshot solve only',
        performance_gain_established=False,independent_generalization=False,novelty_established=False)


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--run',type=Path,required=True);ap.add_argument('--out',type=Path,required=True)
    a=ap.parse_args();a.out.mkdir(parents=True,exist_ok=False)
    result=audit(a.run);(a.out/'summary.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(dict(passed=result['passed'],checks=len(result['checks']),failed=[k for k,v in result['checks'].items() if not v])))
    raise SystemExit(0 if result['passed'] else 1)
