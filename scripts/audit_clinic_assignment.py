#!/usr/bin/env python3
"""Read-only revalidation of frozen allocation runs, without trusting solver status.

Calls unchanged original phase-aware checker, independently checks legal domains,
prefix/source identity and reconstructs the shared objective from plan JSON.
Writes only a new audit directory; never repairs/replaces an algorithm result.
"""
import argparse
from collections import Counter,defaultdict
import csv
import hashlib
import json
from pathlib import Path
import statistics
import sys

ROOT=Path(__file__).resolve().parents[1];W=Path('/home/yhc/clinic_planning_ws')
sys.path.insert(0,str(W/'tools'))
import aligned_contract as contract
POLICIES=('B0','B1','B2','B3')

def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def digest(v):return hashlib.sha256(json.dumps(v,sort_keys=True,allow_nan=False).encode()).hexdigest()
def finite(v):
    import math
    if isinstance(v,dict):return {k:finite(x) for k,x in v.items()}
    if isinstance(v,list):return [finite(x) for x in v]
    return None if isinstance(v,float) and not math.isfinite(v) else v

def write(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
def csvwrite(p,rows):
    keys=list(dict.fromkeys(k for row in rows for k in row))
    with p.open('w') as f:
        writer=csv.DictWriter(f,fieldnames=keys);writer.writeheader();writer.writerows([{k:json.dumps(v,ensure_ascii=False,sort_keys=True) if isinstance(v,(dict,list)) else v for k,v in row.items()} for row in rows])

def independent_cost(p,q):
    normal=[j for j,t in p['tasks'].items() if t['kind']=='normal'];w=p['assignment_weights'];ref=p['reference'];cl=p['clocks']
    role='E1_verify' if 'E1_verify' in p['tasks'] else 'E1_monitor' if 'E1_monitor' in p['tasks'] else None
    response=0. if role is None else q['starts'][role]-cl['candidate_at' if role=='E1_verify' else 'confirmed_at']
    travel=0.
    for r,route in q['routes'].items():
        for u,v in zip(['src']+route,route+['end']):travel+=contract.tau(p,r,u,v)
    return dict(response=w['response']*response,completion=w['completion']*(max(q['ends'].values())-p['time']),
        normal_wait=w['normal_wait']*sum(q['starts'][j]-p['tasks'][j]['release'] for j in normal),
        owner=w['owner']*sum(q['owners'][j]!=r for j,r in ref['owners'].items()),
        shift=w['shift']*sum(abs(q['starts'][j]-s) for j,s in ref['starts'].items()),travel=w['travel']*travel)

def audit(run,out):
    out.mkdir(parents=True,exist_ok=False);protocol=read(run/'protocol.json');errors=[];checks=0;rows=[];percase={};all_audits={}
    def ck(label,ok):
        nonlocal checks
        checks+=1
        if not ok:errors.append(label)
    for f,expected in protocol['source_manifest'].items():ck('frozen_source:'+f,sha(Path(f))==expected)
    for case_id,expected in protocol['cases'].items():
        folder=run/'cases'/case_id;p=read(folder/'problem.json');src=read(Path(p['source_path']));family=p['sample_unit']['family'];percase[case_id]={}
        ck(case_id+':input_hash',digest(p)==expected)
        ck(case_id+':source_hash',sha(Path(p['source_path']))==p['source_sha256'])
        ck(case_id+':prefix_exact',finite(p['prefixes'])==finite(src['prefixes']))
        for key in ('snapshot_states','actual_snapshot','active_commitments','committed_future','committed_finishes','coverage_projection'):
            ck(case_id+':preserve_'+key,finite(p.get(key))==finite(src.get(key)))
        ck(case_id+':active_jobs_not_released',not ({j for pre in src['prefixes'].values() for j in pre['jobs']}&set(p['tasks'])))
        ck(case_id+':accepted_basis',(p['reference']==src['reference']) if family=='hard' else not p['reference']['owners'] and not p['reference']['starts'])
        ck(case_id+':native_objective_terms',p['weights']=={k:dict(normal_delay=.1,owner=2.,shift=.05,travel=.1).get(k,0.) for k in src['weights']})
        for r,v in src['robots'].items():
            ck(case_id+':immutable_source_'+r,p['robots'][r]['source_anchor']==v['source_anchor'])
            ck(case_id+':ready_not_released_'+r,p['robots'][r]['ready']>=v['ready'])
        for j,t in p['tasks'].items():
            if j in src['tasks']:ck(case_id+':release_and_deadline_'+j,all(t.get(k)==src['tasks'][j].get(k) for k in ('release','deadline','start_deadline')))
            ck(case_id+':no_dispatch_'+j,t.get('execution_authorized') is False)
        for policy in POLICIES:
            result=read(folder/policy/'result.json');ck(case_id+policy+':same_input',result['input_sha256']==expected)
            ck(case_id+policy+':budget',result['budget_seconds']==protocol['budget_seconds'] and result['total_seconds']<=protocol['budget_seconds']+.15)
            plan=result.get('plan');row=dict(case_id=case_id,family=family,level=p['sample_unit']['level'],seed=p['sample_unit']['seed'],policy=policy,
                stage='verify' if 'E1_verify' in p['tasks'] else 'response' if p['events'] else 'committed_suffix',region=p['region'],task_count=len(p['tasks']),
                status=result['status'],feasible=bool(plan),total_seconds=result['total_seconds'],solver_seconds=result['solver_seconds'],
                first_feasible_seconds=result['first_feasible_seconds'],cbc_first_integer_seconds=result.get('cbc_first_integer_seconds'),
                variables=result.get('model_size',{}).get('variables'),constraints=result.get('model_size',{}).get('constraints'),
                physical_trial=False,actual_nav2_completion=None,accepted_reference_basis=p['accepted_reference_basis'])
            if plan:
                a=contract.validate(p,plan,dict(free=list(p['tasks']),freeze_time=False),None);ck(case_id+policy+':original_full_constraints',a['passed']);all_audits[case_id+'/'+policy]=a
                for j,r in plan['owners'].items():
                    ck(case_id+policy+':qualification_'+j,r in p['allowed_robots'][j])
                    if j in p['hard_owners']:ck(case_id+policy+':hard_owner_'+j,r==p['hard_owners'][j])
                    if policy=='B0':ck(case_id+policy+':fixed_'+j,r==p['static_owners'][j])
                    if policy in ('B1','B2') and j in p['nominal_owners'] and (policy=='B1' or j!=p.get('necessary_normal')):ck(case_id+policy+':retained_'+j,r==p['nominal_owners'][j])
                if policy=='B2' and p.get('necessary_normal') and p['events']:
                    ck(case_id+policy+':legacy_third_role',plan['owners'][p['necessary_normal']] not in (plan['owners']['E1_monitor'],plan['owners']['E1_pickup']))
                if 'E1_monitor' in plan['starts']:ck(case_id+policy+':handover_margin',plan['finishes']['E1_monitor']+1e-5>=plan['finishes']['E1_deliver']+4.)
                cost=independent_cost(p,plan);ck(case_id+policy+':objective',abs(sum(cost.values())-result['objective'])<1e-4)
                for k,v in cost.items():ck(case_id+policy+':term_'+k,abs(result['metrics']['objective_parts'][k]-v)<1e-4)
                row.update({k:v for k,v in result['metrics'].items() if k not in ('objective_parts','qualification','actual_nav2_completion')})
                row.update(hard_commitment_violations=0 if a['passed'] and all(plan['owners'][j]==r for j,r in p['hard_owners'].items()) else 1,
                    qualification=result['metrics']['qualification']['status'],owners=plan['owners'],routes=plan['routes'],objective_parts=cost)
            else:
                row['failure_reason']=result.get('construction',{}).get('reasons',{})
                ck(case_id+policy+':no_fabricated_metrics','metrics' not in result)
            rows.append(row);percase[case_id][policy]=row
    pairs=[]
    numeric=['objective','verify_response','monitor_response','delivery_from_confirmed','planned_remaining_completion','normal_wait','accepted_owner_changes','accepted_time_shift','nominal_owner_deviations','total_seconds','first_feasible_seconds']
    for case_id,methods in percase.items():
        for base in ('B0','B1','B2'):
            a,b=methods[base],methods['B3'];row=dict(case_id=case_id,family=b['family'],stage=b['stage'],region=b['region'],base=base,comparison='B3 minus baseline',both_feasible=a['feasible'] and b['feasible'],base_status=a['status'],B3_status=b['status'])
            if row['both_feasible']:
                for key in numeric:
                    if isinstance(a.get(key),(int,float)) and isinstance(b.get(key),(int,float)):row['delta_'+key]=b[key]-a[key]
                row['changed_owners_between_methods']=[j for j,r in a['owners'].items() if b['owners'][j]!=r]
                row['event_owner_changed']=any(j.startswith('E1_') for j in row['changed_owners_between_methods'])
            pairs.append(row)
    sensitivity=[]
    for family in ('busy','ready','monitor_load','resource','load_count','hard','region'):
        for seed in protocol['seeds']:
            for policy in POLICIES:
                a=percase[f'{family}_l0_s{seed}'][policy];b=percase[f'{family}_l1_s{seed}'][policy]
                row=dict(family=family,seed=seed,policy=policy,comparison='level1 minus level0',level0_status=a['status'],level1_status=b['status'],both_feasible=a['feasible'] and b['feasible'])
                if row['both_feasible']:
                    for key in numeric:
                        if isinstance(a.get(key),(int,float)) and isinstance(b.get(key),(int,float)):row['delta_'+key]=b[key]-a[key]
                    row['changed_common_owners']=[j for j,r in a['owners'].items() if j in b['owners'] and b['owners'][j]!=r]
                sensitivity.append(row)
    grouped=defaultdict(list)
    for row in rows:grouped[(row['family'],row['policy'])].append(row)
    aggregates=[]
    for (family,policy),group in grouped.items():
        good=[r for r in group if r['feasible']];v=dict(family=family,policy=policy,n=len(group),feasible=len(good),statuses=dict(Counter(r['status'] for r in group)))
        for key in numeric:
            x=[r[key] for r in good if isinstance(r.get(key),(float,int))]
            if x:v['mean_'+key]=statistics.mean(x);v['median_'+key]=statistics.median(x)
        aggregates.append(v)
    summary=dict(passed=not errors,checks=checks,errors=errors,cases=len(percase),calls=len(rows),
        status_counts={m:dict(Counter(r['status'] for r in rows if r['policy']==m)) for m in POLICIES},
        feasible_calls=sum(r['feasible'] for r in rows),hard_violations=sum(r.get('hard_commitment_violations',0) for r in rows),
        interpretation='Independent constraint recheck, not independent robot trials or innovation proof; differences in B2 third-role restriction explicitly retained',
        artifacts={str(f.relative_to(run)):sha(f) for f in run.glob('cases/*/*/result.json')})
    write(out/'summary.json',summary);write(out/'native_constraint_audits.json',all_audits)
    csvwrite(out/'per_instance.csv',rows);csvwrite(out/'paired.csv',pairs);csvwrite(out/'sensitivity.csv',sensitivity);csvwrite(out/'policy_summary.csv',aggregates)
    write(out/'per_instance.json',rows);write(out/'paired.json',pairs);write(out/'sensitivity.json',sensitivity)
    print(json.dumps({k:v for k,v in summary.items() if k!='artifacts'},ensure_ascii=False))
    return summary

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('run',type=Path);a.add_argument('--output',type=Path,required=True);v=a.parse_args()
    sys.exit(0 if audit(v.run,v.output)['passed'] else 1)
