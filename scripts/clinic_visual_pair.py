#!/usr/bin/env python3
"""Same saved physical snapshot, unchanged Clinic solver, equal hard budgets."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
W=Path('/home/yhc/clinic_planning_ws');sys.path.insert(0,str(W/'tools'))


def compare(problem,out,budget):
    import bed_contract as bc
    out.mkdir(parents=True,exist_ok=False)
    p=json.loads(problem.read_text());sha=hashlib.sha256(problem.read_bytes()).hexdigest()
    old=bc.validate(p,p['reference'],dict(free=list(p['tasks']),freeze_time=False))
    rows=[]
    for policy in ['local_impact','full_warm']:
        dest=out/policy;dest.mkdir();begin=time.monotonic()
        with (dest/'worker.log').open('w') as log:
            proc=subprocess.run([sys.executable,str(W/'tools/benchmark_sparse_repair.py'),'--worker',
                '--input',str(problem),'--output',str(dest/'result.json'),'--policy',policy,'--budget',str(budget)],
                stdout=log,stderr=subprocess.STDOUT,timeout=budget+30.)
        q=json.loads((dest/'result.json').read_text()) if (dest/'result.json').exists() else dict(status='NO_RESULT')
        feasible=q['status'] in ['OPTIMAL','FEASIBLE_BUDGET']
        check=bc.validate(p,q['plan'],q['scope'],q['objective']) if feasible else dict(passed=False)
        (dest/'independent_validation.json').write_text(json.dumps(check,indent=2))
        plan=q.get('plan',{});ref=p['reference']
        changed=[j for j in p['tasks'] if feasible and (plan['owners'][j]!=ref['owners'][j] or abs(plan['starts'][j]-ref['starts'][j])>1e-5)]
        rows.append(dict(policy=policy,budget=budget,input_sha256=sha,status=q['status'],exit=proc.returncode,
            passed=feasible and check['passed'],objective=q.get('objective'),solver_seconds=q.get('planning_seconds',q.get('worker_wall')),
            process_seconds=time.monotonic()-begin,changed=changed,unchanged=sorted(set(p['tasks'])-set(changed)),
            changed_owners=[j for j in p['tasks'] if feasible and plan['owners'][j]!=ref['owners'][j]],
            scope=q.get('scope'),impact=bc.impact_scope(p),validation=check,
            plan_finish=max(plan.get('finishes',{}).values(),default=None),result=str(dest/'result.json')))
    result=dict(passed=all(r['passed'] for r in rows),same_input=True,input_sha256=sha,
        old_plan_validation=old,policies=rows,comparison_scope='one actual snapshot; no statistical performance claim')
    (out/'summary.json').write_text(json.dumps(result,indent=2));return result


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--input',type=Path,required=True);ap.add_argument('--out',type=Path,required=True)
    ap.add_argument('--budget',type=float,default=5.);a=ap.parse_args()
    print(json.dumps(compare(a.input,a.out,a.budget)))
