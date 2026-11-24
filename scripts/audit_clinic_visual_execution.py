#!/usr/bin/env python3
"""Independent bounded audit of actual negative visual verification execution."""
import argparse
import json
from pathlib import Path


def main():
    p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True);p.add_argument('--mask',type=Path);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();a.out.mkdir(parents=True,exist_ok=False)
    result=json.loads((a.run/'summary.json').read_text());checks=[];candidate=None;sample=None;phases=[];feedback=[];verdicts=[]
    def check(name,value):checks.append(dict(name=name,passed=bool(value)))
    with (a.run/'trace.jsonl').open() as f:
        for l in f:
            row=json.loads(l);phases.append(row['phase'])
            if row['phase']=='visual_candidate_created':candidate=row
            elif row['phase']=='visual_model_transition' and row['sample']['stable'] and row['sample']['window_ready']:
                if sample is None:sample=row['sample']
            elif row['phase']=='service_feedback':feedback.append(row)
            elif row['phase']=='visual_execution_protocol_feedback':verdicts.append(row)
    check('controller_passed',result.get('passed') is True)
    check('actual_stable_model_sample_caused_candidate',candidate is not None and sample is not None and candidate['caused_by']==sample['sample_id'])
    check('no_legacy_script_event_injection','fall_event_injected' not in phases)
    check('all_three_robots_executed',set(r['robot'] for r in result.get('records',[]) if r['status']=='SUCCEEDED')=={'r1','r2','r3'})
    records=result.get('records',[])
    for rec in records:
        arrival=rec.get('arrival',{})
        check(rec['job_id']+'_native_arrival_and_ACK',rec['status']=='SUCCEEDED' and
            arrival.get('position_error',999)<=.20 and arrival.get('yaw_error',999)<=.30 and
            rec.get('stable_at',0)-rec.get('stable_since',999)>=.7-1e-6 and
            all(0<=arrival.get(k,999)<=.5 for k in ['tf_age','scan_age','odom_age']) and
            rec.get('service_started',0)>=rec.get('stable_at',999) and rec.get('service_finished',0)>=rec.get('service_started',999))
    verify=next((r for r in records if r['job_id']=='E1_verify'),None)
    planning=next((r for r in result.get('planning_records',[]) if r['stage']=='verify'),None)
    if verify and planning:
        problem=json.loads(Path(planning['problem_path']).read_text());task=problem['tasks']['E1_verify']
        check('MILP_task_target_matches_actual_Nav2_target',task['location']==[verify['target']['x'],verify['target']['y']])
        check('MILP_owner_matches_actual_robot',planning['solver']['plan']['owners']['E1_verify']==verify['robot'])
        check('MILP_independent_validation',planning['commit_validation']['passed'])
        acknowledgements=[r['feedback'] for r in feedback if r['feedback']['task_id']==verify['task_id']]
        check('actual_started_and_success_ACK_tokens_match',{'started','succeeded'}.issubset({r['phase'] for r in acknowledgements}) and all(r['attempt']==1 and r['task_revision']==verify['sent_revision'] for r in acknowledgements))
        check('explicit_verdict_has_review_provenance',any(r['message']['phase']=='succeeded' and r['verdict_source']=='operator_review' for r in verdicts) and (a.run/'review.json').is_file())
    else:check('verify_and_solver_records_present',False)
    protocol=result.get('protocol',{})
    check('false_alarm_closed_without_monitor_or_courier',protocol.get('event',{}).get('closed_reason')=='no_fall' and set(protocol.get('tasks',{}))=={'E1:verify'})
    cleanup=json.loads((a.run/'cleanup.json').read_text());check('owned_process_cleanup',cleanup['passed'])
    if a.mask:
        mask=json.loads((a.mask/'summary.json').read_text());check('native_mask_no_phantom_candidate_or_closed_body',mask.get('passed') is True)
    audit=dict(passed=all(c['passed'] for c in checks),checks=checks,
        scope='actual negative-clip visual event -> original MILP -> Nav2/service ACK -> explicit no_fall closure',
        positive_emergency_closed_loop=False,bed_disturbance_tested=False)
    (a.out/'summary.json').write_text(json.dumps(audit,indent=2));print(json.dumps(dict(passed=audit['passed'],checks=len(checks))))
    return 0 if audit['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
