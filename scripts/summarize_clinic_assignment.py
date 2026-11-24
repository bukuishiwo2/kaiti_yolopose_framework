#!/usr/bin/env python3
"""Summarize audited measured results, not solver predictions as physical runs."""
import argparse
from collections import Counter
import csv
import json
from pathlib import Path
import re
import statistics
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from kaiti_task_sim import clinic_assignment as ca


def read(p):return json.loads(p.read_text())
def write(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
def csvwrite(p,rows):
    keys=list(dict.fromkeys(k for r in rows for k in r))
    with p.open('w') as f:
        w=csv.DictWriter(f,fieldnames=keys);w.writeheader();w.writerows(rows)

def summarize(root,out):
    out.mkdir(parents=True,exist_ok=False)
    audit=read(root/'audit_01/summary.json');assert audit['passed']
    rows=read(root/'audit_01/per_instance.json');pairs=read(root/'audit_01/paired.json')
    primary=lambda r:r['family'] not in ('hard','control_verify','control_response')
    timings=[];paired=[];presolve=[]
    for method in ca.POLICIES:
        group=[r for r in rows if r['policy']==method and primary(r)]
        timings.append(dict(policy=method,n=len(group),feasible=sum(r['feasible'] for r in group),
            optimal=sum(r['status']=='OPTIMAL' for r in group),
            total_median=statistics.median(r['total_seconds'] for r in group),
            solver_median=statistics.median(r['solver_seconds'] for r in group),
            first_validated_median=statistics.median(r['first_feasible_seconds'] for r in group)))
    for base in ('B0','B1','B2'):
        group=[r for r in pairs if r['base']==base and primary(r) and r['both_feasible']]
        paired.append(dict(comparison='B3 versus '+base,n=len(group),wins=sum(r['delta_objective']<-.001 for r in group),
            ties=sum(abs(r['delta_objective'])<=.001 for r in group),losses=sum(r['delta_objective']>.001 for r in group),
            mean_delta_objective=statistics.mean(r['delta_objective'] for r in group),
            note='descriptive counts of dependent fixtures, not independent physical success rates'))
    for row in rows:
        p=read(root/'formal_01/cases'/row['case_id']/'problem.json');method=row['policy'];domain=ca.domains(p,method)
        if method=='B1':
            for j,r in p['nominal_owners'].items():domain[j]=[x for x in domain[j] if x==r]
        info=dict(case_id=row['case_id'],policy=method,legal_owner_choices=sum(len(x) for x in domain.values()),
            raw_variables=row.get('variables'),raw_constraints=row.get('constraints'))
        log=root/'formal_01/cases'/row['case_id']/method/'cbc.log'
        if log.exists():
            text=log.read_text();m=re.search(r'processed model has (\d+) rows, (\d+) columns \((\d+) integer',text)
            if m:info.update(presolved_rows=int(m[1]),presolved_columns=int(m[2]),presolved_integers=int(m[3]))
        presolve.append(info)
    qualification=Counter(r.get('qualification') for r in rows if r['feasible'])
    result=dict(status='PASS_AUDITED_OFFLINE_MEASUREMENTS',audit_checks=audit['checks'],primary_case_count=24,
        all_case_count=30,all_call_count=120,all_feasible_calls=audit['feasible_calls'],expected_no_plan_calls=8,
        primary_pairwise=paired,primary_timings=timings,qualification=dict(qualification),
        B3_better_than_B1_cases=[r['case_id'] for r in pairs if r['base']=='B1' and primary(r) and r['delta_objective']<-.001],
        B3_worse_than_B2_cases=[r['case_id'] for r in pairs if r['base']=='B2' and primary(r) and r['delta_objective']>.001],
        conclusions=dict(dynamic_role_choice_needed='supported on explicit ready/busy fixtures; greedy already captures most response improvement',
            ordinary_owner_change_necessary_for_feasibility='not established; fixed owner B0 feasible on all 24 primary fixtures',
            ordinary_owner_change_can_improve_shared_objective='one B3 nominal-backlog case, plus B2 tradeoffs; not proof for changing already accepted plans',
            B3_superiority='not supported; one win over greedy and six losses against B2 within fixed budget',
            next_method_hypothesis='structured joint event-role and small ordinary-suffix insertion with accepted-plan continuity constraints; compare against B1/B2 before new online mechanisms',
            innovation='not established by widening feasible domain or changing weights',
            physical_comparison='NOT_RUN; new assignments require qualification; region B full roles BLOCKED'))
    write(out/'summary.json',result);csvwrite(out/'primary_timings.csv',timings);csvwrite(out/'primary_pairwise.csv',paired);csvwrite(out/'presolve.csv',presolve)
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);p.add_argument('--output',type=Path,required=True);v=p.parse_args();summarize(v.root,v.output)
