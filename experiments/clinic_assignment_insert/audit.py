#!/usr/bin/env python3
"""Independent plan, provenance and factorial audit. Never changes experiment data."""
from collections import Counter
from copy import deepcopy
import csv
import hashlib
import importlib.util
import itertools
import json
from pathlib import Path
import statistics
import sys

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
sys.path.insert(0,str(HERE));import adapter
spec=importlib.util.spec_from_file_location('allocation_independent_check',ROOT/'scripts/audit_clinic_assignment.py')
prior=importlib.util.module_from_spec(spec);spec.loader.exec_module(prior)
read=prior.read;write=prior.write;csvwrite=prior.csvwrite;digest=prior.digest;sha=prior.sha


def audit(run,out):
    out.mkdir(parents=True,exist_ok=False);protocol=read(run/'protocol.json');errors=[];checks=0;rows=[];bycase={};native_audits={};source_partitions=[];structures=[]
    def ck(name,ok):
        nonlocal checks
        checks+=1
        if not ok:errors.append(name)
    for path,s in protocol['source_manifest'].items():ck('frozen_code:'+path,sha(Path(path))==s)
    provenances={}
    for path in sorted((run/'sources').glob('*/provenance.json')):
        prov=read(path);provenances[prov['run']]=prov
        for f,s in prov['source_sha256'].items():ck('original_source:'+f,sha(Path(f))==s)
        root=Path(prov['related_snapshots']['01_verify']).parents[1]
        with (root/'trace.jsonl').open() as f:
            for i,line in enumerate(f,1):
                if i==prov['accepted_trace_line']:commit=json.loads(line);break
        ck(prov['run']+':actual_commit_phase',commit['phase']=='plan_committed' and commit['stage']=='normal')
        ck(prov['run']+':actual_accepted_exact',commit['plan']==prov['accepted_plan']==read(root/'00_normal/result.json')['plan'])
        ck(prov['run']+':accepted_before_event',commit['episode_time']<prov['historical_event_at'])
        p0=read(root/'00_normal/problem.json');ck(prov['run']+':original_accepted_native',prior.contract.validate(p0,commit['plan'],dict(free=list(p0['tasks']),freeze_time=False))['passed'])
    for name,expected in protocol['cases'].items():
        folder=run/'cases'/name;p=read(folder/'problem.json');src=read(Path(p['source_path']));episode=p['sample_unit']['source_episode'];prov=provenances[episode]
        p0=read(Path(p['source_path']).parents[1]/'00_normal/problem.json');ref=p['accepted_reference'];full=prov['accepted_plan'];part=p['task_partition'];bycase[name]={}
        ck(name+':frozen_input',digest(p)==expected);ck(name+':frozen_original_snapshot',sha(Path(p['source_path']))==p['source_sha256'])
        ck(name+':provenance_digest',digest(prov)==p['accepted_provenance_sha256'])
        ck(name+':prefix_exact',p['prefixes']==prior.finite(src['prefixes']))
        for k in ('snapshot_states','known_finishes','actual_known_finishes','fixed_resources'):
            ck(name+':original_'+k,p[k]==prior.finite(src[k]))
        for r,v in src['robots'].items():
            ck(name+':projected_source_'+r,p['robots'][r]['source_anchor']==v['source_anchor'])
            ck(name+':ready_'+r,p['robots'][r]['ready']>=v['ready'])
            ck(name+':capability_'+r,p['robots'][r]['capabilities']==v['capabilities'])
        issued={j for pre in src['prefixes'].values() for j in pre['jobs']};completed=set(src['actual_known_finishes']);remaining=set(p0['tasks'])-issued-completed
        ck(name+':only_unissued_normals',set(ref['owners'])==remaining)
        ck(name+':partition',set(part['unissued_suffix'])==remaining and set(part['issued_prefix'])==issued&set(p0['tasks']))
        ck(name+':removed_prefix_not_optimized',not set(p['tasks'])&issued)
        ck(name+':no_completed_released',not set(p['tasks'])&completed)
        ck(name+':reference_times_exact',ref['starts']=={j:full['starts'][j] for j in remaining})
        ck(name+':reference_owners_exact',ref['owners']=={j:full['owners'][j] for j in remaining})
        ck(name+':reference_order_exact',ref['routes']=={r:[j for j in route if j in remaining] for r,route in full['routes'].items()})
        excerpt=read(run/'sources'/episode/'trace_excerpt.json')
        nav_issued={q['record']['record']['job_id'] for q in excerpt if q['record']['phase']=='navigation_requested' and q['record']['episode_time']<=p['time']}
        ck(name+':unissued_confirmed_by_trace',not remaining&nav_issued)
        superseding=[q for q in excerpt if q['record']['phase']=='plan_committed' and q['record']['episode_time']>prov['accepted_at'] and q['record']['episode_time']<=p['time'] and q['record'].get('normal_selected')]
        ck(name+':no_superseding_ordinary_commit',not superseding)
        if p['reference_cost_enabled']:ck(name+':actual_objective_reference',p['reference']==ref)
        else:ck(name+':erasure_explicit',not p['reference']['owners'] and not p['reference']['starts'])
        for j in remaining:
            a=deepcopy(p['tasks'][j]);b=deepcopy(p0['tasks'][j]);a.pop('execution_authorized',None)
            if p['sample_unit']['variant']=='routine_window' and j=='C0_r3_W3':b['deadline']=max(p['time']+240.,ref['finishes'][j]+90.)
            ck(name+':normal_definition_'+j,a==b)
        for j,t in p['tasks'].items():
            ck(name+':no_dispatch_'+j,t['execution_authorized'] is False)
            if t['kind']!='normal':
                ck(name+':release_'+j,t['release']==p['time'])
                if t.get('start_deadline') is not None:ck(name+':fixed_start_deadline_'+j,t['start_deadline']==t['release']+360.)
        source_partitions.append(dict(case_id=name,accepted_at=prov['accepted_at'],candidate_at=p['clocks']['candidate_at'],snapshot_at=p['time'],reference_source='observed plan_committed line '+str(prov['accepted_trace_line']),completed=part['completed'],issued_prefix=part['issued_prefix'],unissued_suffix=part['unissued_suffix'],accepted_before=ref))
        if set(('F00','F01','F10','F11')).issubset(p['methods']):
            signatures={m:adapter.common_model_signature(p,m) for m in ('F00','F01','F10','F11')}
            ck(name+':strict_two_factor_common_model',len(set(signatures.values()))==1)
            structures.append(dict(case_id=name,common_signature=signatures['F00'],passed=len(set(signatures.values()))==1))
        for method in p['methods']:
            q=read(folder/method/'result.json');ck(name+method+':same_input',q['input_sha256']==expected)
            ck(name+method+':budget',q['budget_seconds']==5. and q['total_seconds']<=5.15)
            ck(name+method+':no_execution',q['physical_execution_authorized'] is False)
            third=method in ('B0','B1','F10','F11');opening='fixed' if method in ('B0','B1') else 'limited' if method[-1]=='0' else 'joint'
            ck(name+method+':factor_metadata',q['factor_profile']['third']==third and q['factor_profile']['opening']==opening)
            plan=q.get('plan');row=dict(case_id=name,episode=episode,stage=p['sample_unit']['stage'],variant=p['sample_unit']['variant'],reference_cost_enabled=p['reference_cost_enabled'],method=method,
                third_policy=third,opening=opening,status=q['status'],feasible=bool(plan),total_seconds=q['total_seconds'],solver_seconds=q['solver_seconds'],first_feasible_seconds=q['first_feasible_seconds'],cbc_first_integer_seconds=q.get('cbc_first_integer_seconds'),
                variables=q.get('model_size',{}).get('variables'),constraints=q.get('model_size',{}).get('constraints'),policy_class=q['business_policy_class'],task_count=len(p['tasks']),accepted_task_count=len(ref['owners']))
            if plan:
                n=prior.contract.validate(p,plan,dict(free=list(p['tasks']),freeze_time=False));native_audits[name+'/'+method]=n;ck(name+method+':full_native',n['passed'])
                for j,r in plan['owners'].items():
                    ck(name+method+':physical_domain_'+j,r in p['allowed_robots'][j] and set(p['tasks'][j]['capabilities']).issubset(p['robots'][r]['capabilities']))
                    if j in p['hard_owners']:ck(name+method+':hard_'+j,r==p['hard_owners'][j])
                    if method=='B0':ck(name+method+':fixed_'+j,r==p['static_owners'][j])
                    if j in ref['owners'] and (method=='B1' or opening=='limited' and j!=p.get('necessary_normal')):ck(name+method+':ordinary_lock_'+j,r==ref['owners'][j])
                business=True
                if p.get('necessary_normal'):
                    business=plan['owners'][p['necessary_normal']] not in (plan['owners']['E1_monitor'],plan['owners']['E1_pickup'])
                    ck(name+method+':handover',plan['finishes']['E1_monitor']+1e-5>=plan['finishes']['E1_deliver']+4.)
                    if third:ck(name+method+':required_business_third',business)
                cost=prior.independent_cost(p,plan);ck(name+method+':shared_J',abs(sum(cost.values())-q['objective'])<1e-4)
                ap=deepcopy(p);ap['reference']=ref;true_cost=prior.independent_cost(ap,plan)
                changes=sum(plan['owners'][j]!=r for j,r in ref['owners'].items());shift=sum(abs(plan['starts'][j]-s) for j,s in ref['starts'].items())
                ck(name+method+':true_accepted_changes',q['metrics']['accepted_owner_changes']==changes)
                ck(name+method+':true_accepted_shift',abs(q['metrics']['accepted_time_shift']-shift)<1e-5)
                row.update({k:v for k,v in q['metrics'].items() if k not in ('objective_parts','qualification','robot_normal_service_load')})
                row.update(objective=q['objective'],true_reference_evaluation=sum(true_cost.values()),objective_parts=cost,accepted_owner_changes=changes,accepted_time_shift=shift,
                    business_contract_satisfied=business,formally_admissible_business_policy=third and business,hard_violations=0,owners=plan['owners'],routes=plan['routes'],starts=plan['starts'],finishes=plan['finishes'])
            else:row['failure_reason']=q.get('construction',{}).get('reasons',{})
            rows.append(row);bycase[name][method]=row
    numeric=('objective','true_reference_evaluation','verify_response','monitor_response','delivery_from_confirmed','planned_remaining_completion','normal_wait','accepted_owner_changes','accepted_time_shift','accepted_adjacent_pair_breaks','total_seconds','first_feasible_seconds')
    def delta(a,b):
        d=dict(both_feasible=a['feasible'] and b['feasible'],base_status=a['status'],new_status=b['status'])
        if d['both_feasible']:
            for k in numeric:
                if isinstance(a.get(k),(float,int)) and isinstance(b.get(k),(float,int)):d['delta_'+k]=b[k]-a[k]
            d['changed_owners_between_methods']=[j for j,r in a['owners'].items() if b['owners'][j]!=r]
        return d
    effects=[];pairs=[];erasure=[]
    for name,methods in bycase.items():
        if all(m in methods for m in ('F00','F01','F10','F11')):
            for factor,a,b in [('third_with_limited','F00','F10'),('third_with_joint','F01','F11'),('opening_without_third','F00','F01'),('opening_with_third','F10','F11')]:
                effects.append(dict(case_id=name,factor=factor,base=a,new=b,interpretation='finite-budget incumbent difference; not global-optimum factor effect',**delta(methods[a],methods[b])))
            if all(methods[m]['feasible'] for m in ('F00','F01','F10','F11')):
                effects.append(dict(case_id=name,factor='objective_interaction',value=methods['F11']['objective']-methods['F10']['objective']-methods['F01']['objective']+methods['F00']['objective'],interpretation='incumbent interaction only'))
        if all(m in methods for m in ('B0','B1','F10','F11')):
            for a,b in [('B0','B1'),('B1','F10'),('B1','F11'),('F10','F11')]:pairs.append(dict(case_id=name,base=a,new=b,**delta(methods[a],methods[b])))
        if name.endswith('__reference_erased'):
            source_name=name.removesuffix('__reference_erased');p=read(run/'cases'/name/'problem.json');original=read(run/'cases'/source_name/'problem.json')
            ignore={'case_id','methods','reference','reference_cost_enabled'}
            ck(name+':only_reference_cost_changed',{k:v for k,v in p.items() if k not in ignore}=={k:v for k,v in original.items() if k not in ignore})
            for m in methods:erasure.append(dict(case_id=source_name,method=m,comparison='reference erased minus real accepted reference; compare true_reference_evaluation, not raw cross-objective J',**delta(bycase[source_name][m],methods[m])))
    summary=dict(passed=not errors,checks=checks,errors=errors,cases=len(bycase),calls=len(rows),feasible_calls=sum(r['feasible'] for r in rows),
        counts_by_method={m:dict(Counter(r['status'] for r in rows if r['method']==m)) for m in adapter.METHODS},
        relaxed_policy_violating_business=sum(r['feasible'] and not r.get('business_contract_satisfied',True) for r in rows if not r['third_policy']),
        legal_profile_violations=sum(r['feasible'] and not r.get('business_contract_satisfied',True) for r in rows if r['third_policy']),
        sources=len(provenances),factorial_cases=len(structures),physical_trials=0,new_mechanism='NOT_IMPLEMENTED_PENDING_EVIDENCE')
    write(out/'summary.json',summary);write(out/'per_instance.json',rows);csvwrite(out/'per_instance.csv',rows)
    write(out/'factor_effects.json',effects);csvwrite(out/'factor_effects.csv',effects);write(out/'paired.json',pairs);csvwrite(out/'paired.csv',pairs)
    write(out/'reference_erasure.json',erasure);csvwrite(out/'reference_erasure.csv',erasure);write(out/'accepted_before_and_partitions.json',source_partitions)
    write(out/'native_constraint_audits.json',native_audits);write(out/'strict_factorial_structures.json',structures)
    print(json.dumps(summary,ensure_ascii=False));return summary

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('run',type=Path);p.add_argument('--output',type=Path,required=True);v=p.parse_args();sys.exit(0 if audit(v.run,v.output)['passed'] else 1)
