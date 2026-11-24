#!/usr/bin/env python3
"""Read-only independent audit and paired analysis of the offline method suite."""
import argparse
from collections import Counter
import csv
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import re
import statistics
from copy import deepcopy

spec=importlib.util.spec_from_file_location('study',Path(__file__).with_name('benchmark_clinic_repair_methods.py'))
study=importlib.util.module_from_spec(spec);spec.loader.exec_module(study)


def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def describe(v):
    if not v:return None
    v=sorted(v);return dict(n=len(v),median=statistics.median(v),mean=statistics.mean(v),p95=v[max(0,math.ceil(.95*len(v))-1)],min=v[0],max=v[-1])


def constructive_feasibility_witness(p,family):
    """Certificate, not a timed method, warm start, or an optimality proof."""
    from aligned_contract import tau
    plan=deepcopy(p['reference']);routes=plan['routes']
    if family=='L':
        j=routes['r0'].pop();routes['r1'].append(j);plan['owners'][j]='r1'
    if family=='G':
        urgent=routes['r0'];routes['r0']=[];routes['r1']=urgent+routes['r1']
        for j in urgent:plan['owners'][j]='r1'
    predecessor={j:(rid,route[k-1] if k else 'src') for rid,route in routes.items() for k,j in enumerate(route)}
    plan['starts']={};plan['finishes']={};todo=set(p['tasks'])
    while todo:
        progress=False
        for j in sorted(todo):
            t=p['tasks'][j];rid,prev=predecessor[j]
            if prev!='src' and prev not in plan['finishes']:continue
            if any(d in p['tasks'] and d not in plan['finishes'] for d in t['dependencies']):continue
            available=p['robots'][rid]['ready'] if prev=='src' else plan['finishes'][prev]
            start=max([p['time'],t['release'],p['reference']['starts'][j],available+tau(p,rid,prev,j)]+
                [plan['finishes'].get(d,p['known_finishes'].get(d,0.)) for d in t['dependencies']])
            for block in sorted(p['blocked_resources'],key=lambda b:b['start']):
                if block['resource'] in t['resources'] and start-t['approach']<block['finish']+p['buffer'] and start+t['duration']+t['egress']+p['buffer']>block['start']:
                    start=block['finish']+p['buffer']+t['approach']
            plan['starts'][j]=start;plan['finishes'][j]=start+t['duration'];todo.remove(j);progress=True
        if not progress:raise ValueError('certificate graph cycle')
    plan['ends']={r:(plan['finishes'][route[-1]]+tau(p,r,route[-1],'end') if route else p['robots'][r]['ready']+tau(p,r,'src','end')) for r,route in routes.items()}
    check=study.validate(p,plan,dict(free=list(p['tasks']),freeze_time=False))
    return dict(passed=check['passed'],validation=check,plan=plan,
        owner_changes=sum(plan['owners'][j]!=r for j,r in p['reference']['owners'].items()),
        scope='constructive feasibility certificate only; not timed, not supplied to measured methods, not an optimality proof')


def audit(run,out):
    out.mkdir(parents=True,exist_ok=False)
    manifest=json.loads((run/'manifest.json').read_text());rows=json.loads((run/'rows.json').read_text())
    checks={};extended=[];case_rows={};normalized=[]
    checks['all_expected_runs_retained']=len(rows)==len(manifest['cases'])*len(study.POLICIES)
    for c in manifest['cases']:
        folder=Path(c['path']);p=json.loads((folder/'problem.json').read_text());before=json.loads((folder/'baseline.json').read_text())
        design=json.loads((folder/'design.json').read_text());scope=dict(free=list(p['tasks']),freeze_time=False)
        group=[r for r in rows if r['id']==c['id']];case_rows[c['id']]=group
        checks[c['id']+'_paired_input_budget']=len(group)==5 and {q['policy'] for q in group}==set(study.POLICIES) and {q['input_sha256'] for q in group}=={digest(folder/'problem.json')} and {q['budget'] for q in group}=={manifest['budget']}
        checks[c['id']+'_reference_valid_then_invalid']=study.validate(before,before['reference'],scope)['passed'] and not study.validate(p,p['reference'],scope)['passed']
        checks[c['id']+'_projected_commitments_unchanged']=p['external_commitments']==before['external_commitments']
        certificate=constructive_feasibility_witness(p,c['family'])
        study.write(out/'feasibility_witnesses'/f'{c["id"]}.json',certificate)
        checks[c['id']+'_constructive_feasible_certificate']=certificate['passed']
        checks[c['id']+'_native_owner_lock_same_every_policy']=all([r for r,v in p['robots'].items() if set(p['tasks'][j]['capabilities']).issubset(v['capabilities'])]==[owner] for j,owner in p['hard_owners'].items())
        stripped={k:v for k,v in p.items() if k not in {'external_commitments','commitment_basis'}}
        normalized.append(hashlib.sha256(json.dumps(stripped,sort_keys=True).encode()).hexdigest())
        for row in group:
            raw=json.loads(Path(row['result']).read_text());key=c['id']+'_'+row['policy'];q=dict(row)
            q['first_validated_seconds']=(raw.get('first_validated') or {}).get('seconds')
            q['first_validated_objective']=(raw.get('first_validated') or {}).get('objective')
            checks[key+'_no_process_error']=row['exit']==0 and not raw['status'].startswith('ERROR')
            if raw.get('plan'):
                valid=study.validate(p,raw['plan'],raw['scope'],raw['objective'],row['policy'])
                checks[key+'_independent_constraints']=valid['passed']
                checks[key+'_incumbent_available_inside_budget']=raw.get('first_validated') is not None and raw['first_validated']['seconds']<=row['budget']+1e-6
                q['hard_violations']=sum(e['name'].startswith('hard_owner') for e in valid['errors'])
            else:q['hard_violations']=None
            if raw['status']=='SEED_INFEASIBLE_SEARCH_NOT_RUN':
                checks[key+'_no_false_domain_infeasibility_claim']=raw.get('native_status')=='INFEASIBLE' and raw.get('seed_gate') is True
            # Count attempted, not merely the scope of a seed returned on timeout.
            impact=study.contract.impact_scope(p);scopes=[initial for initial in [dict(free=impact['free'],freeze_time=True)]]
            free=set(impact['free'])
            for j in sorted(set(p['tasks'])-free,key=lambda j:p['reference']['starts'][j]):
                free.add(j);scopes.append(dict(free=sorted(free),freeze_time=True))
            scopes.append(dict(free=list(p['tasks']),freeze_time=False))
            attempted=[len(a.get('scope',{}).get('free',[])) for a in raw.get('attempts',[])]
            if row['policy']=='local_no_seed_gate':
                for folder2 in Path(row['result']).parent.glob('search_*'):
                    idx=int(folder2.name.split('_')[-1]);attempted.append(len(scopes[idx]['free']))
            if row['policy']=='full_warm' and any(Path(row['result']).parent.glob('search_*')):
                attempted.append(len(p['tasks']))
            if row['policy']=='local_current' and raw['status']!='SEED_INFEASIBLE_SEARCH_NOT_RUN':attempted.append(len(impact['free']))
            q['max_attempted_free']=max(attempted,default=0)
            q['max_attempted_ratio']=q['max_attempted_free']/len(p['tasks'])
            model_sizes=[]
            for log in Path(row['result']).parent.rglob('cbc.log'):
                if 'seed' in log.parts:continue
                found=re.findall(r'processed model has (\d+) rows, (\d+) columns \((\d+) integer.*?(\d+) of which binary',log.read_text(errors='replace'))
                if found:model_sizes.append(dict(log=str(log),rows=int(found[-1][0]),columns=int(found[-1][1]),integer=int(found[-1][2]),binary=int(found[-1][3])))
            q['processed_binary_peak']=max((x['binary'] for x in model_sizes),default=None)
            q['processed_models']=model_sizes
            extended.append(q)
        full=next(q for q in group if q['policy']=='full_warm')
        if full['status']=='OPTIMAL':
            for q in group:
                if q['valid']:checks[c['id']+'_full_optimum_lower_bound_'+q['policy']]=q['objective']>=full['objective']-1e-5
    checks['no_optimization_duplicate_hidden_by_tokens']=len(set(normalized))==len(normalized)
    sources=json.loads((run/'source_manifest.json').read_text())
    checks['source_hashes_unchanged']=all(Path(p).exists() and digest(Path(p))==h for p,h in sources.items())
    stats={};pairs=[]
    for family in study.FAMILIES:
        stats[family]={}
        for policy in study.POLICIES:
            rr=[r for r in extended if r['family']==family and r['policy']==policy];vv=[r for r in rr if r['valid']]
            stats[family][policy]=dict(cases=len(rr),successes=len(vv),statuses=dict(Counter(q['status'] for q in rr)),
                worker_seconds_all=describe([q['worker_seconds'] for q in rr]),first_validated_success=describe([q['first_validated']['seconds'] for q in vv]),
                owner_changes_success=describe([q['owner_changes'] for q in vv]),max_attempted_ratio=describe([q['max_attempted_ratio'] for q in rr]),
                processed_binary_peak=describe([q['processed_binary_peak'] for q in rr if q['processed_binary_peak'] is not None]))
    for case,group in case_rows.items():
        best=min((q['objective'] for q in group if q['valid']),default=None)
        full=next(q for q in group if q['policy']=='full_warm')
        for method in ['fixed_structure','fixed_owner','local_current','local_no_seed_gate']:
            q=next(q for q in group if q['policy']==method)
            both=q['valid'] and full['valid']
            pairs.append(dict(case=case,family=q['family'],tasks=q['tasks'],method=method,both_recovered=both,
                method_status=q['status'],full_status=full['status'],best_observed=best,
                within_5pct_best=q['valid'] and q['objective']<=best+.05*max(1.,abs(best)),
                objective_gap_vs_full=q['objective']-full['objective'] if both else None,
                worker_speedup_full_over_method=full['worker_seconds']/q['worker_seconds'] if both else None,
                first_validated_speedup_full_over_method=full['first_validated']['seconds']/q['first_validated']['seconds'] if both else None,
                assignment_difference=q['owner_changes']-full['owner_changes'] if both else None))
    result=dict(passed=all(checks.values()),checks=checks,instances=len(manifest['cases']),runs=len(rows),stats=stats,pairs=pairs,
        scope='independent synthetic mechanism instances; original solver/model; not navigation trials or population generalization',
        no_legacy_fix_deployed=True,physical_comparison='NOT_RUN',academic_novelty='NOT_ESTABLISHED')
    study.write(out/'summary.json',result);study.write(out/'rows_extended.json',extended)
    flat=[{k:v for k,v in q.items() if not isinstance(v,(dict,list))} for q in extended]
    keys=sorted(set().union(*(q.keys() for q in flat)))
    with (out/'metrics.csv').open('w') as f:
        writer=csv.DictWriter(f,fieldnames=keys);writer.writeheader();writer.writerows(flat)
    print(json.dumps(dict(passed=result['passed'],checks=len(checks),failed=[k for k,v in checks.items() if not v],instances=result['instances'],runs=result['runs'])))
    return result


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--run',type=Path,required=True);ap.add_argument('--out',type=Path,required=True)
    a=ap.parse_args();raise SystemExit(0 if audit(a.run,a.out)['passed'] else 1)
