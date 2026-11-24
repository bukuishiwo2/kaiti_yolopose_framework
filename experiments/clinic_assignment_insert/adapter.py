"""Offline accepted-plan bundle insertion; leaves all deployed/old code untouched."""
from copy import deepcopy
import itertools
import json
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'src'))
from kaiti_task_sim import clinic_assignment as base
native=base.native
digest=base.digest
warm_values=base.warm_values
WEIGHTS=base.WEIGHTS

METHODS=('B0','B1','F00','F01','F10','F11')

def profile(method):
    # Fxy: x=third-role policy; y=all-normal suffix open (0=legacy limited).
    if method in ('B0','B1'):return dict(third=True,opening='fixed',label=method)
    if method not in METHODS:raise ValueError(method)
    return dict(third=method[1]=='1',opening='joint' if method[2]=='1' else 'limited',label=method)


def domains(p,method):
    d=base.domains(p,'B3');pr=profile(method);ref=p['accepted_reference']
    for j,t in p['tasks'].items():
        lock=None
        if method=='B0':lock=p['static_owners'][j]
        elif t['kind']=='normal' and (pr['opening']=='fixed' or pr['opening']=='limited' and j!=p.get('necessary_normal')):lock=ref['owners'][j]
        if lock is not None:d[j]=[r for r in d[j] if r==lock]
    return d


def business_check(p,plan):
    j=p.get('necessary_normal')
    return j is None or plan['owners'][j] not in (plan['owners']['E1_monitor'],plan['owners']['E1_pickup'])


def validate(p,plan,method,claimed=None):
    q=base.validate(p,plan,'B3',claimed);d=domains(p,method);pr=profile(method)
    for j,r in plan['owners'].items():
        q['checks']+=1
        if r not in d[j]:q['errors'].append(dict(name='profile_domain_'+j,residual=1.))
    business=business_check(p,plan)
    if pr['third']:
        q['checks']+=1
        if not business:q['errors'].append(dict(name='required_third_role_policy',residual=1.))
    q.update(passed=not q['errors'],business_contract_satisfied=business,
        analysis_only_policy_relaxation=not pr['third'],execution_authorized=False)
    return q


def model(p,method):
    tpl,m,v=base.model(p,'B3');a,_=native();d=domains(p,method)
    for j in p['tasks']:
        for r in p['robots']:
            if r not in d[j]:m+=v[a.b.xk(r,j)]==0.,'policy_owner_'+r+'_'+j
    if profile(method)['third'] and p.get('necessary_normal'):
        for r in p['robots']:
            m+=sum(v[a.b.xk(r,j)] for j in (p['necessary_normal'],'E1_monitor','E1_pickup'))<=1.,'policy_third_'+r
    return tpl,m,v


def common_model_signature(p,method):
    """Removing only tested policy rows leaves exactly the same mathematical model."""
    _,m,_=model(p,method)
    return digest(dict(rows={n:dict(sense=q.sense,constant=q.constant,coefficients=sorted((v.name,c) for v,c in q.items())) for n,q in m.constraints.items() if not n.startswith('policy_')},
        objective=dict(constant=m.objective.constant,coefficients=sorted((v.name,c) for v,c in m.objective.items())),
        variables={v.name:[v.lowBound,v.upBound,v.cat] for v in m.variables()}))


def greedy(p,method='B1',deadline=float('inf')):
    """Earliest service bundle insertion in the *actual accepted* ordinary order."""
    ref=p['accepted_reference'];routes=deepcopy(ref['routes']);eligible=domains(p,method)
    candidates=[];reasons={};evaluations=0
    def consider(trial):
        nonlocal evaluations
        if time.perf_counter()>=deadline:return
        evaluations+=1;plan,reason=base.schedule_routes(p,trial)
        if plan:
            q=validate(p,plan,method)
            if not q['passed']:reason=','.join(e['name'] for e in q['errors'][:3]);plan=None
        if plan:
            first=plan['starts'].get('E1_verify',plan['starts'].get('E1_monitor',p['time']))
            delivery=plan['finishes'].get('E1_deliver',max(plan['ends'].values()))
            candidates.append(((first,delivery,sum(base.parts(p,plan).values()),json.dumps(trial,sort_keys=True)),plan))
        else:reasons[reason]=reasons.get(reason,0)+1
    if 'E1_verify' in p['tasks']:
        for r in eligible['E1_verify']:
            for i in range(len(routes[r])+1):
                q=deepcopy(routes);q[r].insert(i,'E1_verify');consider(q)
    else:
        for monitor,courier in itertools.product(eligible['E1_monitor'],eligible['E1_pickup']):
            if monitor==courier or courier not in eligible['E1_deliver']:continue
            for i,j in itertools.product(range(len(routes[monitor])+1),range(len(routes[courier])+1)):
                q=deepcopy(routes);q[monitor].insert(i,'E1_monitor');q[courier][j:j]=['E1_pickup','E1_deliver'];consider(q)
    if not candidates:return dict(status='GREEDY_NO_FEASIBLE_INSERTION',reasons=reasons,evaluations=evaluations)
    _,plan=min(candidates,key=lambda q:q[0]);cost=sum(base.parts(p,plan).values())
    return dict(status='FEASIBLE_CONSTRUCTIVE',plan=plan,objective=cost,validation=validate(p,plan,method,cost),evaluations=evaluations,reasons=reasons)


def metrics(p,plan):
    q=base.metrics(p,plan);ref=p['accepted_reference']
    q['accepted_owner_changes']=sum(plan['owners'][j]!=r for j,r in ref['owners'].items())
    q['accepted_time_shift']=sum(abs(plan['starts'][j]-s) for j,s in ref['starts'].items())
    q['accepted_adjacent_pair_breaks']=sum((u,v) not in set(zip(plan['routes'][r],plan['routes'][r][1:])) for r,route in ref['routes'].items() for u,v in zip(route,route[1:]))
    q['accepted_retained_same_robot_order_inversions']=sum(plan['routes'][r].index(u)>plan['routes'][r].index(v) for r,route in ref['routes'].items() for u,v in itertools.combinations(route,2) if plan['owners'][u]==r and plan['owners'][v]==r)
    q['original_nominal_owner_deviations']=sum(plan['owners'][j]!=r for j,r in p['original_nominal_owners'].items())
    q['reference_cost_enabled']=p['reference_cost_enabled'];q['business_contract_satisfied']=business_check(p,plan)
    q['physical_status']='MODEL_ONLY_NEW_TIMING_AND_CONCURRENCY_NOT_QUALIFIED'
    q['historical_accepted_plan']=True;q['new_physical_trial']=False
    return q
