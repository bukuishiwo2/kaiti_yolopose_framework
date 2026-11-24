#!/usr/bin/env python3
"""Predeclared capability-availability supplement; no deployment changes.

Removes only r3 camera capability, leaving carry/move, source, ready, workload,
physical domain and objective unchanged. Not a new observation or certified role.
"""
import argparse
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sys

spec=importlib.util.spec_from_file_location('allocation_bench',Path(__file__).with_name('benchmark_clinic_assignment.py'))
b=importlib.util.module_from_spec(spec);spec.loader.exec_module(b)

def generate(out):
    out.mkdir(parents=True,exist_ok=False);cases=[]
    for seed in (113,229):
        for level in (0,1):
            p=b.make_case('ready',0,seed)
            p['case_id']=f'camera_l{level}_s{seed}';p['sample_unit'].update(family='camera',level=level)
            p['scenario_parameters']['r3_camera_removed']=bool(level)
            if level:p['robots']['r3']['capabilities'].remove('camera')
            b.write(out/'cases'/p['case_id']/'problem.json',p);cases.append(p)
    protocol=dict(schema='clinic-allocation-capability-supplement/v1',created_before_measured_solves=True,
        seeds=[113,229],budget_seconds=5.,policies=list(b.ca.POLICIES),cases={p['case_id']:b.ca.digest(p) for p in cases},
        source_manifest={str(f):b.sha(f) for f in (Path(__file__),Path(b.__file__),b.ROOT/'src/kaiti_task_sim/clinic_assignment.py')},
        mechanism='paired r3 camera availability only, on ready_l0 base; unchanged carry/move and immutable prefix projection',
        population='four dependent model fixtures, not independent robot trials; supplement not pooled into formal_01',
        selection='all two-level camera cases with same preset seeds; no outcome filter')
    b.write(out/'protocol.json',protocol)

def audit(run,out):
    # Original checker and independent shared objective; no adapter.validate shortcut.
    spec=importlib.util.spec_from_file_location('allocation_audit',Path(__file__).with_name('audit_clinic_assignment.py'))
    a=importlib.util.module_from_spec(spec);spec.loader.exec_module(a)
    out.mkdir(parents=True,exist_ok=False);protocol=b.read(run/'protocol.json');rows=[];errors=[];checks=0
    def ck(label,ok):
        nonlocal checks
        checks+=1
        if not ok:errors.append(label)
    for path,s in protocol['source_manifest'].items():ck('source:'+path,b.sha(Path(path))==s)
    for case_id,s in protocol['cases'].items():
        p=b.read(run/'cases'/case_id/'problem.json');ck(case_id+':frozen',b.ca.digest(p)==s)
        base=b.make_case('ready',0,p['sample_unit']['seed']);expected=deepcopy(base)
        expected['case_id']=case_id;expected['sample_unit'].update(family='camera',level=p['sample_unit']['level']);expected['scenario_parameters']['r3_camera_removed']=bool(p['sample_unit']['level'])
        if p['sample_unit']['level']:expected['robots']['r3']['capabilities'].remove('camera')
        ck(case_id+':single_factor',p==expected)
        for method in b.ca.POLICIES:
            q=b.read(run/'cases'/case_id/method/'result.json');ck(case_id+method+':input',q['input_sha256']==s)
            ck(case_id+method+':budget',q['total_seconds']<=5.15)
            row=dict(case_id=case_id,seed=p['sample_unit']['seed'],camera_available=not bool(p['sample_unit']['level']),policy=method,status=q['status'],feasible='plan' in q,total_seconds=q['total_seconds'])
            if 'plan' in q:
                plan=q['plan'];ck(case_id+method+':native',a.contract.validate(p,plan,dict(free=list(p['tasks']),freeze_time=False))['passed'])
                ck(case_id+method+':objective',abs(sum(a.independent_cost(p,plan).values())-q['objective'])<1e-4)
                for j,r in plan['owners'].items():
                    ck(case_id+method+':domain_'+j,r in b.ca.domains(p,method)[j])
                    if method=='B1' and j in p['nominal_owners']:ck(case_id+method+':greedy_retained_'+j,r==p['nominal_owners'][j])
                if method=='B2':ck(case_id+method+':third_role',plan['owners'][p['necessary_normal']] not in (plan['owners']['E1_monitor'],plan['owners']['E1_pickup']))
                ck(case_id+method+':handover',plan['finishes']['E1_monitor']>=plan['finishes']['E1_deliver']+4.-1e-5)
                row.update({k:v for k,v in q['metrics'].items() if k not in ('objective_parts','robot_normal_service_load','qualification')});row['owners']=plan['owners']
            rows.append(row)
    a.csvwrite(out/'per_instance.csv',rows);b.write(out/'per_instance.json',rows)
    summary=dict(passed=not errors,checks=checks,errors=errors,cases=4,calls=16);b.write(out/'summary.json',summary);print(summary)
    return summary

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('mode',choices=['generate','run','audit']);parser.add_argument('run',type=Path);parser.add_argument('--output',type=Path);v=parser.parse_args()
    if v.mode=='generate':generate(v.run)
    elif v.mode=='run':b.run(v.run)
    else:sys.exit(0 if audit(v.run,v.output)['passed'] else 1)
