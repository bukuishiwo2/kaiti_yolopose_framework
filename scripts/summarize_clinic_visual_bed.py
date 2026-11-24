#!/usr/bin/env python3
"""Compact causal index of saved evidence; never changes original run files."""
import argparse
import hashlib
import json
from pathlib import Path


def summarize(run,audit,degradation,out):
    out.mkdir(parents=True,exist_ok=False)
    s=json.loads((run/'summary.json').read_text())
    check=json.loads((audit/'summary.json').read_text())
    deg=json.loads((degradation/'summary.json').read_text())
    rows=[json.loads(l) for l in (run/'trace.jsonl').open()]
    phases={'visual_candidate_created','initial_clearance_committed','bed_scenario_requested',
        'bed_navigation_cancel_requested','bed_navigation_cancel_ACK','actual_plan_invalidated',
        'visual_repair_committed','bed_observed_clear_resume','scripted_handover_ack'}
    milestones=[dict(line=i+1,at=r['episode_time'],phase=r['phase']) for i,r in enumerate(rows) if r['phase'] in phases]
    tasks=[]
    for r in s.get('records',[]):
        tasks.append({k:r.get(k) for k in ['job_id','task_id','robot','status','begin','service_started',
            'service_finished','clear_at','lease_granted_at','lease_released_at','end','sent_revision','target','navigation_attempts']})
    pairs=[]
    for case in s.get('repair_cases',[]):
        folder=Path(case['folder']);p=json.loads((folder/'problem.json').read_text());pair=json.loads((folder/'pair/summary.json').read_text())
        online=next((q for q in s.get('planning_records',[]) if q.get('problem_path')==str(folder/'problem.json')), {})
        policies=[]
        for q in pair['policies']:
            row={k:q.get(k) for k in ['policy','budget','status','objective','solver_seconds','process_seconds',
                'changed','unchanged','changed_owners','plan_finish','impact','scope']}
            raw=json.loads(Path(q['result']).read_text())
            row['planned_route_end']=max(raw.get('plan',{}).get('ends',{}).values(),default=None)
            row.update({k:raw.get(k) for k in ['seed_seconds','seed_objective','seed_status','mip_start_accepted',
                'scope_expansions','best_bound','first_feasible','worker_wall']})
            policies.append(row)
        pairs.append(dict(snapshot=str(folder/'snapshot.json'),problem=str(folder/'problem.json'),
            at=case['at'],problem_sha256=hashlib.sha256((folder/'problem.json').read_bytes()).hexdigest(),
            online_commit={k:online.get(k) for k in ['requested_at','returned_at','end_to_end_wall','commit_validation']},
            old_validation=pair['old_plan_validation'],free_tasks=list(p['tasks']),
            active_commitments=p['active_commitments'],coverage_projection=p['coverage_projection'],
            policies=policies,
            commit_fence=str(folder/'commit_fence.json')))
    ledger=dict(run=str(run),trace=str(run/'trace.jsonl'),summary_sha256=hashlib.sha256((run/'summary.json').read_bytes()).hexdigest(),
        model_video=str(run/'video'),review=str(run/'review.json'),registration_provenance='video_source_registered',
        milestones=milestones,execution=tasks,paired_snapshots=pairs,
        protocol_final=s.get('protocol'),online_check_count=len(s.get('online_checks',[])),
        audit=str(audit/'summary.json'),degradation=str(degradation/'summary.json'))
    (out/'causal_ledger.json').write_text(json.dumps(ledger,indent=2))
    acceptance=dict(
        physical_closed_loop='PASS' if s.get('passed') and check['passed'] else 'FAIL',
        actual_invalidation='PASS' if pairs and all(not q['old_validation']['passed'] for q in pairs) else 'FAIL',
        same_snapshot_solver_comparison='PASS' if check.get('cases') and all(c['pair']['passed'] for c in check['cases']) else 'FAIL',
        actual_EOF_with_valid_registration='PASS' if check['checks'].get('EOF_behavior_expired_registration_valid_monitor_kept') else 'FAIL',
        independent_offline_degradation='PASS' if deg['passed'] else 'FAIL',
        physical_active_service_revocation_recovery='BLOCKED',
        physical_cargo_handover='NOT_RUN',full_policy_physical_run='NOT_RUN',
        quantitative_advantage='NOT_RUN',academic_novelty='NOT_RUN',independent_generalization='NOT_RUN',RGBD_localization='NOT_RUN',
        scope='one physical before-pickup bed episode; rolling snapshots are not independent trials; only local result executed',
        guards_modified=False,fast_standard='functional pass; timing targets not met (historical result unchanged)')
    (out/'acceptance.json').write_text(json.dumps(acceptance,indent=2))
    return acceptance


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    for name in ['run','audit','degradation','out']:ap.add_argument('--'+name,type=Path,required=True)
    a=ap.parse_args();print(json.dumps(summarize(a.run,a.audit,a.degradation,a.out)))
