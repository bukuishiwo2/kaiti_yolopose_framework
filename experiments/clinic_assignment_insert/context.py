#!/usr/bin/env python3
"""Supplement: unavoidable accepted-plan drift without this stage's event bundle.

Same saved state/ordinary tasks, no new role tasks. Not a same-task superiority
comparison; supplies context for attributing shift/wait to event insertion.
"""
import argparse
from copy import deepcopy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE));import run as experiment
read=experiment.read;write=experiment.write;sha=experiment.sha


def execute(formal,out):
    out.mkdir(parents=True,exist_ok=False);cases=[];protocol=read(formal/'protocol.json')
    for name,s in protocol['cases'].items():
        p=read(formal/'cases'/name/'problem.json')
        if not p['reference_cost_enabled']:continue
        q=deepcopy(p);q['tasks']={j:t for j,t in p['tasks'].items() if t['kind']=='normal'};q['events']={};q['cargo_pairs']=[];q.pop('necessary_normal',None)
        q['case_id']=name+'__without_stage_bundle';q['methods']=['B0'];q['context_only']=True
        cases.append(q);write(out/'cases'/q['case_id']/'problem.json',q)
    write(out/'protocol.json',dict(frozen_before_context_solves=True,purpose='fixed accepted owner retiming without current-stage event bundle; no cross-task objective rank claim',
        source_formal_protocol_sha256=sha(formal/'protocol.json'),source_manifest={str(p):sha(p) for p in [Path(__file__),Path(experiment.old.__file__),experiment.ROOT/'src/kaiti_task_sim/clinic_assignment.py']},
        cases={p['case_id']:experiment.ca.digest(p) for p in cases},budget_seconds=5.,solver_seed=17))
    for q in cases:
        folder=out/'cases'/q['case_id'];target=folder/'B0'
        proc=subprocess.run([sys.executable,str(Path(experiment.old.__file__)),'worker','--input',str(folder/'problem.json'),'--output',str(target),'--policy','B0','--budget','5','--solver-seed','17'],
            env=dict(os.environ,OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1'),capture_output=True,text=True,timeout=20.)
        (target/'worker.log').write_text(proc.stdout+proc.stderr)
        if proc.returncode:raise RuntimeError(proc.stderr[-2000:])
    print('context calls',len(cases))


def audit(formal,context,out):
    spec=importlib.util.spec_from_file_location('allocation_audit',experiment.ROOT/'scripts/audit_clinic_assignment.py');a=importlib.util.module_from_spec(spec);spec.loader.exec_module(a)
    out.mkdir(parents=True,exist_ok=False);protocol=read(context/'protocol.json');rows=[];errors=[];checks=0
    def ck(name,ok):
        nonlocal checks
        checks+=1
        if not ok:errors.append(name)
    for path,s in protocol['source_manifest'].items():ck('source:'+path,sha(Path(path))==s)
    for name,s in protocol['cases'].items():
        p=read(context/'cases'/name/'problem.json');base_name=name.removesuffix('__without_stage_bundle');original=read(formal/'cases'/base_name/'problem.json');q=read(context/'cases'/name/'B0/result.json')
        ck(name+':input_hash',experiment.ca.digest(p)==s==q['input_sha256'])
        ck(name+':unchanged_state',all(p[k]==original[k] for k in ('robots','prefixes','reference','known_finishes','blocked_resources','fixed_resources','assignment_weights','weights')))
        ck(name+':only_ordinary_tasks',p['tasks']=={j:t for j,t in original['tasks'].items() if t['kind']=='normal'})
        ck(name+':no_roles',not p['events'] and not p['cargo_pairs'])
        ck(name+':budget',q['total_seconds']<=5.15)
        row=dict(case_id=base_name,status=q['status'],total_seconds=q['total_seconds'],feasible='plan' in q)
        if 'plan' in q:
            plan=q['plan'];ck(name+':native',a.contract.validate(p,plan,dict(free=list(p['tasks']),freeze_time=False))['passed'])
            ck(name+':retained_owners',plan['owners']==p['accepted_reference']['owners'])
            ck(name+':objective',abs(sum(a.independent_cost(p,plan).values())-q['objective'])<1e-4)
            row.update({k:q['metrics'][k] for k in ('normal_wait','accepted_time_shift','planned_remaining_completion')});row['starts']=plan['starts'];row['routes']=plan['routes']
        rows.append(row)
    summary=dict(passed=not errors,checks=checks,errors=errors,cases=len(rows),feasible=sum(r['feasible'] for r in rows),use='context for unavoidable shift; not same-task benchmark')
    write(out/'summary.json',summary);write(out/'per_instance.json',rows);a.csvwrite(out/'per_instance.csv',rows);print(summary)
    return summary

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['run','audit']);p.add_argument('formal',type=Path);p.add_argument('--output',type=Path,required=True);p.add_argument('--context',type=Path);v=p.parse_args()
    if v.mode=='run':execute(v.formal,v.output)
    else:sys.exit(0 if audit(v.formal,v.context,v.output)['passed'] else 1)
