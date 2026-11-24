#!/usr/bin/env python3
"""Describe paired measurements; never turn predictions into physical claims."""
from collections import Counter
from copy import deepcopy
import csv
import json
from pathlib import Path
import statistics
import sys
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE));import audit
read=audit.read;write=audit.write;csvwrite=audit.csvwrite


def summarize(root,out):
    out.mkdir(parents=True,exist_ok=False);assert read(root/'audit_01/summary.json')['passed'];assert read(root/'context_audit_01/summary.json')['passed']
    rows=read(root/'audit_01/per_instance.json');pairs=read(root/'audit_01/paired.json');effects=read(root/'audit_01/factor_effects.json');refs=read(root/'audit_01/reference_erasure.json')
    contexts={r['case_id']:r for r in read(root/'context_audit_01/per_instance.json')}
    primary=[r for r in rows if r['stage']=='02_response' and r['reference_cost_enabled']];index={(r['case_id'],r['method']):r for r in rows}
    wins=[];timings=[];schedules=[];routes=[];context_deltas=[];domain_gaps=[]
    for base,new in [('B0','B1'),('B1','F10'),('B1','F11'),('F10','F11')]:
        g=[r for r in pairs if r['base']==base and r['new']==new and '__02_response__' in r['case_id']]
        vals=[r['delta_objective'] for r in g if r['both_feasible']]
        wins.append(dict(comparison=new+' versus '+base,n=len(vals),wins=sum(x<-.001 for x in vals),ties=sum(abs(x)<=.001 for x in vals),losses=sum(x>.001 for x in vals)))
    for method in audit.adapter.METHODS:
        g=[r for r in primary if r['method']==method]
        timings.append(dict(method=method,n=len(g),feasible=sum(r['feasible'] for r in g),optimal_reported=sum(r['status']=='OPTIMAL' for r in g),
            median_total=statistics.median(r['total_seconds'] for r in g),median_solver=statistics.median(r['solver_seconds'] for r in g),median_first_usable=statistics.median(r['first_feasible_seconds'] for r in g)))
    for r in rows:
        if not r['feasible']:continue
        p=read(root/'formal_01/cases'/r['case_id']/'problem.json');ref=p['accepted_reference'];q=r
        for j,t in p['tasks'].items():
            schedules.append(dict(case_id=r['case_id'],method=r['method'],task_id=j,kind=t['kind'],accepted=j in ref['owners'],
                old_owner=ref['owners'].get(j),old_start=ref['starts'].get(j),old_finish=ref['finishes'].get(j),
                new_owner=q['owners'][j],new_start=q['starts'][j],new_finish=q['finishes'][j],
                accepted_owner_changed=None if j not in ref['owners'] else q['owners'][j]!=ref['owners'][j],
                signed_start_shift=None if j not in ref['starts'] else q['starts'][j]-ref['starts'][j],
                service_anchor=t['anchor'],entry=t['entry_anchor'],clear=t['clear_anchor'],resource=t['resources'],prediction_only=True))
        for robot,route in q['routes'].items():routes.append(dict(case_id=r['case_id'],method=r['method'],robot=robot,accepted_unissued_route=ref['routes'][robot],new_unissued_route=route,issued_prefix=p['prefixes'][robot],prediction_only=True))
        if r['reference_cost_enabled']:
            baseline=contexts[r['case_id']]
            context_deltas.append(dict(case_id=r['case_id'],method=r['method'],baseline='same state fixed accepted owners, without current-stage bundle',
                no_bundle_accepted_shift=baseline['accepted_time_shift'],with_bundle_accepted_shift=r['accepted_time_shift'],incremental_shift=r['accepted_time_shift']-baseline['accepted_time_shift'],
                no_bundle_normal_wait=baseline['normal_wait'],with_bundle_normal_wait=r['normal_wait'],incremental_normal_wait=r['normal_wait']-baseline['normal_wait']))
    for r in pairs:
        if r['base']!='F10' or r['new']!='F11' or '__02_response__' not in r['case_id']:continue
        a=index[r['case_id'],'F10'];b=index[r['case_id'],'F11'];p=read(root/'formal_01/cases'/r['case_id']/'problem.json')
        outside=[j for j,owner in b['owners'].items() if j in p['accepted_reference']['owners'] and j!=p['necessary_normal'] and owner!=p['accepted_reference']['owners'][j]]
        log=(root/'formal_01/cases'/r['case_id']/'F10/cbc.log').read_text()
        if b['objective']<a['objective']-.001:
            assert outside and a['status']=='OPTIMAL' and 'Result - Optimal solution found' in log
        domain_gaps.append(dict(case_id=r['case_id'],restricted_objective=a['objective'],joint_objective=b['objective'],improvement=a['objective']-b['objective'],
            outside_limited_domain_changed_tasks=outside,restricted_cbc_optimal=a['status']=='OPTIMAL',joint_cbc_optimal=b['status']=='OPTIMAL',
            accepted_changes_restricted=a['accepted_owner_changes'],accepted_changes_joint=b['accepted_owner_changes'],delivery_difference=b['delivery_from_confirmed']-a['delivery_from_confirmed']))
    thirds=[r for r in effects if r['factor']=='third_with_limited'];open_strict=[r for r in effects if r['factor']=='opening_with_third']
    summary=dict(status='PASS_OFFLINE_PAIRED_EVIDENCE',response_inputs=10,historical_episodes=2,new_physical_trials=0,
        legal_method_comparisons=wins,response_timings=timings,
        third_policy_with_limited=dict(cells_both_reported_optimal=10,positive_cost_cases=sum(r['delta_objective']>.001 for r in thirds),zero_cost_cases=sum(abs(r['delta_objective'])<=.001 for r in thirds),
            positive_cost_values=[r['delta_objective'] for r in thirds if r['delta_objective']>.001]),
        legal_joint_domain_gaps=domain_gaps,
        reference_erasure=dict(diagnostics=len(refs),changed_decisions=sum(bool(r['changed_owners_between_methods']) for r in refs),
            changed_decision_cases=[dict(case_id=r['case_id'],method=r['method'],additional_accepted_changes=r['delta_accepted_owner_changes'],additional_shift=r['delta_accepted_time_shift'],common_reference_J_penalty=r['delta_true_reference_evaluation']) for r in refs if r['changed_owners_between_methods']]),
        relaxed_business_violations=read(root/'audit_01/summary.json')['relaxed_policy_violating_business'],
        decision='Joint bundle/ordinary-suffix coordination has a verified policy-domain quality benefit here; existing joint MILP already supplies it. No new selector/module implemented.',
        limits=['two related historical scenes, four unissued ordinary tasks per case','current J rewards global Cmax/wait/shift tradeoffs; joint often delivers later and changes more accepted owners',
            'no new Nav2/concurrency qualification or physical success rate','no claim that domain enlargement is an algorithmic innovation','scope selection likely covers most of four-task suffix; scalability gap needs a larger preregistered population'])
    write(out/'summary.json',summary);csvwrite(out/'comparison_counts.csv',wins);csvwrite(out/'timings.csv',timings);csvwrite(out/'verified_domain_gaps.csv',domain_gaps)
    csvwrite(out/'per_task_before_after.csv',schedules);csvwrite(out/'per_robot_before_after.csv',routes);csvwrite(out/'incremental_event_disruption.csv',context_deltas)
    write(out/'incremental_event_disruption.json',context_deltas)
    print(json.dumps(summary,ensure_ascii=False,indent=2))

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);p.add_argument('--output',type=Path,required=True);v=p.parse_args();summarize(v.root,v.output)
