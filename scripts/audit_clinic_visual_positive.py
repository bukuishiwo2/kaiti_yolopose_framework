#!/usr/bin/env python3
"""Audit saved native evidence; never substitutes fixture ACKs for execution."""
import argparse
import hashlib
import json
import math
from pathlib import Path


def native_arrival(r):
    d=r.get('arrival',{})
    return (r.get('status')=='SUCCEEDED' and d.get('position_error',999)<=.20 and
        d.get('yaw_error',999)<=.30 and r.get('stable_at',0)-r.get('stable_since',999)>=.7-1e-6 and
        all(0<=d.get(k,999)<=.5 for k in ['tf_age','scan_age','odom_age']) and
        r.get('service_started',-1)>=r.get('stable_at',0) and
        r.get('service_finished',-1)>=r.get('service_started',0))


def qualification(run):
    s=json.loads((run/'summary.json').read_text());records={r['job_id']:r for r in s.get('records',[])}
    feedback=[q['feedback'] for q in (json.loads(l) for l in (run/'trace.jsonl').open()) if q['phase']=='service_feedback']
    checks={}
    expected=['C0_r1_W1','C0_r2_W1','C0_r3_W1','QA_verify','QA_monitor_station',
        'QA_pickup','QA_deliver','QA_courier_return','QA_monitor_return','QA_peer_return']
    checks['exact_completed_sequence']=set(records)==set(expected) and all(j in s.get('completed',{}) for j in expected)
    checks['no_runtime_exception']=not s.get('error')
    checks['real_initial_Nav2_queries']=len(s.get('path_queries',[]))==9 and all(q['passed'] for q in s['path_queries'])
    for j in expected:
        rec=records.get(j,{})
        checks[j+'_native_guard_ACK']=native_arrival(rec) and {'started','succeeded'}.issubset(
            {q['phase'] for q in feedback if q['task_id']==rec.get('task_id') and q['robot']==rec.get('robot')})
    checks['strict_sequence']=all(records.get(b,{}).get('begin',-1)>=records.get(a,{}).get('end',99999) for a,b in zip(expected,expected[1:]))
    for j in ['C0_r1_W1','C0_r2_W1','C0_r3_W1','QA_pickup','QA_courier_return','QA_monitor_return','QA_peer_return']:
        r=records.get(j,{})
        checks[j+'_lease_clear']=r.get('lease_released_at',-1)>=r.get('clear_at',0)>r.get('service_finished',99999)
    witness=s.get('monitor_witness',[])
    checks['M1_occupied_during_pickup_deliver_return']=(bool(witness) and
        {'QA_pickup','QA_deliver','QA_courier_return'}.issubset({v['job'] for v in witness}) and
        all(v['distance']<=.20 and v['state']=='IDLE' and v['anchor']=='M1' for v in witness))
    checks['return_anchors']=all(records.get(j,{}).get('final_anchor')==a for j,a in [
        ('QA_courier_return','CG1'),('QA_monitor_return','V3'),('QA_peer_return','CPW1')])
    static=json.loads((run/'static_preflight.json').read_text())
    checks['runtime_sources_unchanged']=all(Path(p).is_file() and hashlib.sha256(Path(p).read_bytes()).hexdigest()==h for p,h in static['source_hashes'].items())
    checks['cleanup']=json.loads((run/'cleanup.json').read_text()).get('passed') is True
    return s,checks


def positive(run):
    s=json.loads((run/'summary.json').read_text());rows=[json.loads(l) for l in (run/'trace.jsonl').open()]
    records={r['job_id']:r for r in s.get('records',[])};checks={}
    checks['controller_completed']=s.get('passed') is True
    candidates=[r for r in rows if r['phase']=='visual_candidate_created']
    models={r['sample']['sample_id']:r['sample'] for r in rows if r['phase']=='visual_model_transition'}
    checks['unique_candidate_real_model_cause']=len(candidates)==1 and candidates[0]['caused_by'] in models and all(models[c['caused_by']]['stable'] and models[c['caused_by']]['window_ready'] for c in candidates)
    checks['legacy_injection_absent']=all(r['phase']!='fall_event_injected' for r in rows)
    checks['three_actual_robots']={r['robot'] for r in records.values() if r['status']=='SUCCEEDED'}=={'r1','r2','r3'}
    for j,r in records.items():checks[j+'_native_guard_ACK']=native_arrival(r)
    proto=s.get('protocol',{});pt=proto.get('tasks',{});event=proto.get('event') or {}
    checks['four_services_completed']=all(j in records and records[j]['status']=='SUCCEEDED' and pt.get('E1:'+role,{}).get('state')=='SUCCEEDED' for role in ['verify','monitor','pickup','deliver'] for j in ['E1_'+role])
    checks['event_completed']=event.get('lifecycle')=='COMPLETED'
    plans={q['stage']:q for q in s.get('planning_records',[])}
    checks['original_verify_response_MILP']=all(k in plans and plans[k]['commit_validation']['passed'] and plans[k]['solver']['status'] in ['OPTIMAL','FEASIBLE_BUDGET'] for k in ['verify','response'])
    for role in ['verify','monitor','pickup','deliver']:
        j='E1_'+role;r=records.get(j,{});plan=plans.get('verify' if role=='verify' else 'response',{})
        problem=json.loads(Path(plan['problem_path']).read_text()) if plan.get('problem_path') else {}
        task=problem.get('tasks',{}).get(j,{})
        checks[j+'_MILP_target_owner']=bool(task) and r.get('robot')==plan.get('solver',{}).get('plan',{}).get('owners',{}).get(j) and task['location']==[r.get('target',{}).get('x'),r.get('target',{}).get('y')]
        feedback=[q['feedback'] for q in rows if q['phase']=='service_feedback' and q['feedback']['task_id']==r.get('task_id')]
        checks[j+'_actual_ACK_token']={'started','succeeded'}.issubset({q['phase'] for q in feedback}) and all(q['attempt']==pt.get('E1:'+role,{}).get('attempt') and q['task_revision']==r.get('sent_revision') for q in feedback)
    review=json.loads((run/'review.json').read_text())
    checks['explicit_saved_review']=Path(review.get('evidence_id','')).is_file() and review.get('source') in ['operator_review','independent_sensor_review','controlled_visual_review'] and review.get('result')=='fall'
    verdicts=[q for q in rows if q['phase']=='visual_execution_protocol_feedback' and q.get('verdict_source')]
    checks['fall_review_only_on_verify_success']=len(verdicts)==1 and verdicts[0]['message']['task_id']=='E1:verify' and verdicts[0]['message']['phase']=='succeeded'
    mon=records.get('E1_monitor',{});pick=records.get('E1_pickup',{});deliver=records.get('E1_deliver',{})
    checks['monitor_covers_actual_pickup_delivery']=mon.get('service_started',99999)<=pick.get('service_started',-1) and mon.get('service_finished',-1)>=deliver.get('service_finished',99999)
    checks['same_robot_cargo']=pick.get('robot') is not None and pick.get('robot')==deliver.get('robot') and mon.get('robot')!=pick.get('robot')
    checks['pickup_resource_entry_clear_ACK']=(pick.get('lease_granted_at',99999)<=pick.get('service_started',-1) and
        pick.get('lease_released_at',-1)>=pick.get('clear_at',0)>pick.get('service_finished',99999))
    checks['carry_then_deliver']=deliver.get('begin',-1)>=pick.get('end',99999)
    checks['handover_before_monitor_release']=s.get('handover_ack') is True and any(q['phase']=='scripted_handover_ack' for q in rows)
    checks['online_checks']=bool(s.get('online_checks')) and all(q['passed'] for q in s['online_checks'])
    checks['monitor_protection_exercised']=any(q.get('monitor_release_guard',{}).get('allowed') is False for q in s.get('online_checks',[]) if q.get('monitor_release_guard'))
    checks['real_nav_cancel_ACK_retry']=s.get('nav_cancel_tested') is True and any(q['phase']=='visual_navigation_cancel_ack' and q['passed'] for q in rows)
    req=[(i,q) for i,q in enumerate(rows) if q['phase']=='visual_navigation_cancel_requested']
    ack=[(i,q) for i,q in enumerate(rows) if q['phase']=='visual_navigation_cancel_ack']
    if len(req)==len(ack)==1:
        i,q=req[0];k,v=ack[0]
        checks['issued_goal_preserved_until_cancel_ACK']=(i<k and q['action_goal_id']==v['action_goal_id'] and
            q['task_id']==v['task_id'] and not any(row['phase']=='motion_path_released' and row.get('robot')==q['robot'] for row in rows[i:k]))
        nav=records.get('E1_verify',{}).get('navigation_attempts',[])
        checks['cancelled_navigation_actually_retried']=any(n.get('controlled_cancel') and n.get('status')==5 for n in nav) and len(nav)>=2 and nav[-1].get('status') in [4,5]
    else: checks['issued_goal_preserved_until_cancel_ACK']=False
    checks['cleanup']=json.loads((run/'cleanup.json').read_text()).get('passed') is True
    return s,checks


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--run',type=Path,required=True)
    ap.add_argument('--out',type=Path,required=True);ap.add_argument('--qualification',action='store_true')
    a=ap.parse_args();a.out.mkdir(parents=True,exist_ok=False)
    s,checks=qualification(a.run) if a.qualification else positive(a.run)
    passed=all(checks.values());result=dict(passed=passed,checks=checks,run=str(a.run),
        summary_sha256=hashlib.sha256((a.run/'summary.json').read_bytes()).hexdigest(),
        scope='A spatial service sequence and stationary monitor occupancy' if a.qualification else 'real video full positive emergency with native execution feedback',
        quantitative_performance=False,independent_generalization=False,novelty_established=False)
    (a.out/'summary.json').write_text(json.dumps(result,indent=2))
    if passed and a.qualification:
        anchors=sorted({v for t in s['tasks'].values() for v in [t['anchor'],t['entry_anchor'],t['clear_anchor']]})
        cert=dict(passed=True,region='A',config_sha256=s['config_sha256'],validated_anchors=anchors,
            qualified_roles=['verify','monitor','pickup','deliver'],qualified_robots=dict(verify=['r1'],monitor=['r1'],pickup=['r2'],deliver=['r2']),
            concurrent_resource_qualification=True,evidence=str(a.out/'summary.json'),
            evidence_sha256=hashlib.sha256((a.out/'summary.json').read_bytes()).hexdigest(),
            scope=result['scope']+'; actual continuous monitor lifecycle must pass positive run separately')
        (a.out/'A.json').write_text(json.dumps(cert,indent=2))
    print(json.dumps(dict(passed=passed,checks=len(checks),failed=[k for k,v in checks.items() if not v])))
    return 0 if passed else 1


if __name__=='__main__':raise SystemExit(main())
