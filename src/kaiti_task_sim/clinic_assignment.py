"""Independent offline allocation adapter; never dispatches a robot.

Native phase-aware MILP/validator are reused from the actual Clinic workspace.
Nominal assignment, accepted soft plans and irrevocable prefixes stay distinct.
"""
from copy import deepcopy
import os
import hashlib
import itertools
import json
from pathlib import Path
import sys
import time

REPO_ROOT=Path(__file__).resolve().parents[2]
WORKSPACE=Path(os.environ.get('CLINIC_WORKSPACE','/home/yhc/clinic_planning_ws')).expanduser()
POLICIES=('B0','B1','B2','B3')
WEIGHTS=dict(response=4.,completion=.1,normal_wait=.1,owner=2.,shift=.05,travel=.1)


def native():
    tools=WORKSPACE/'tools'
    if not tools.is_dir():tools=REPO_ROOT/'experiments/clinic/tools'
    if not tools.is_dir():raise FileNotFoundError('Clinic tools are not available; set CLINIC_WORKSPACE or use the uploaded experiments/clinic snapshot')
    if str(tools) not in sys.path:sys.path.insert(0,str(tools))
    import aligned_solver
    import aligned_contract
    return aligned_solver,aligned_contract


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,allow_nan=False).encode()).hexdigest()


def compile_frozen(view,now,config,region,phases,clocks,certificate=None):
    """Replanning now never rebases first semantic generation/release/deadline."""
    from .clinic_visual import compile_tasks
    result={}
    for task in view['tasks']:
        role=task['role'];release=clocks['task_planning_release'][task['task_id']]
        if release>now or release!=task['generated_at']:
            raise ValueError('first generation clock must be explicit, immutable and not future')
        if role=='verify' and release<clocks['candidate_at']:
            raise ValueError('verify cannot predate candidate')
        if role!='verify' and (clocks.get('confirmed_at') is None or release<clocks['confirmed_at']):
            raise ValueError('response cannot predate explicit confirmation')
        result.update(compile_tasks(dict(tasks=[task]),release,config,region,phases,certificate))
    return result


def nominal_routes(p):
    routes={r:[] for r in p['robots']}
    for j in p['nominal_owners']:
        routes[p['nominal_owners'][j]].append(j)
    return routes


def policy_locks(p,policy):
    if policy=='B0':return dict(p['static_owners'])
    if policy=='B2':
        return {j:r for j,r in p['nominal_owners'].items() if j!=p.get('necessary_normal')}
    return {}


def domains(p,policy=None):
    fixed=dict(p.get('hard_owners',{}));locks=policy_locks(p,policy)
    conflicts={j for j in fixed if j in locks and fixed[j]!=locks[j]}
    fixed.update({j:r for j,r in locks.items() if j not in fixed})
    return {j:[r for r,v in p['robots'].items()
        if r in p['allowed_robots'][j] and set(t['capabilities']).issubset(v['capabilities'])
        and j not in conflicts and (j not in fixed or fixed[j]==r)] for j,t in p['tasks'].items()}


def parts(p,plan):
    _,contract=native();w=p['assignment_weights'];normal=[j for j,t in p['tasks'].items() if t['kind']=='normal']
    accepted=p['reference'];clock=p['clocks']
    if 'E1_verify' in p['tasks']:response=plan['starts']['E1_verify']-clock['candidate_at']
    elif 'E1_monitor' in p['tasks']:response=plan['starts']['E1_monitor']-clock['confirmed_at']
    else:response=0.
    travel=0.
    for r,route in plan['routes'].items():
        for u,v in zip(['src']+route,route+['end']):travel+=contract.tau(p,r,u,v)
    return dict(response=w['response']*response,
        completion=w['completion']*(max(plan['ends'].values())-p['time']),
        normal_wait=w['normal_wait']*sum(plan['starts'][j]-p['tasks'][j]['release'] for j in normal),
        owner=w['owner']*sum(plan['owners'][j]!=r for j,r in accepted['owners'].items()),
        shift=w['shift']*sum(abs(plan['starts'][j]-s) for j,s in accepted['starts'].items()),
        travel=w['travel']*travel)


def validate(p,plan,policy=None,claimed=None):
    """Original full phase/energy/cargo/resource checker + new contract checks."""
    _,contract=native()
    audit=contract.validate(p,plan,dict(free=list(p['tasks']),freeze_time=False),None)
    errors=audit['errors']
    def ck(name,ok):
        audit['checks']+=1
        if not ok:errors.append(dict(name=name,residual=1.))
    eligible=domains(p,policy)
    for j,r in plan['owners'].items():ck('legal_owner_'+j,r in eligible[j])
    if 'E1_monitor' in p['tasks']:
        ck('explicit_handover_margin',plan['finishes']['E1_monitor']+1e-5>=plan['finishes']['E1_deliver']+4.)
    if policy=='B2' and p.get('necessary_normal') and 'E1_monitor' in p['tasks']:
        ck('legacy_third_role',plan['owners'][p['necessary_normal']] not in
            [plan['owners']['E1_monitor'],plan['owners']['E1_pickup']])
    locked={j for v in p.get('prefixes',{}).values() for j in v.get('jobs',[])}
    ck('active_prefix_not_released_into_suffix',not locked.intersection(p['tasks']))
    for r,v in p['immutable_projection'].items():
        ck('projected_source_ready_'+r,p['robots'][r]['source_anchor']==v['source_anchor'] and p['robots'][r]['ready']>=v['ready']-1e-6)
    objective_parts=parts(p,plan)
    if claimed is not None:ck('new_shared_objective',abs(sum(objective_parts.values())-claimed)<1e-4)
    audit.update(passed=not errors,objective_parts=objective_parts)
    return audit


def model(p,policy):
    a,_=native();b=a.b
    class AllocationModel(a.Model):
        def _build(self):
            super()._build();w=p['assignment_weights'];eligible=domains(p,policy)
            for j in p['tasks']:
                for r in p['robots']:
                    if r not in eligible[j]:self.eq('qualified_'+r+j,{b.xk(r,j):1})
            self.var('allocation_cmax',p['time'],p['horizon'])
            for r in p['robots']:self.row('allocation_completion_'+r,{'allocation_cmax':1,'end_'+r:-1})
            self.add_cost('allocation_cmax',w['completion']);self.constant-=w['completion']*p['time']
            if 'E1_verify' in p['tasks']:
                self.add_cost('s_E1_verify',w['response']);self.constant-=w['response']*p['clocks']['candidate_at']
            if 'E1_monitor' in p['tasks']:
                self.add_cost('s_E1_monitor',w['response']);self.constant-=w['response']*p['clocks']['confirmed_at']
                self.row('allocation_handover',{'f_E1_monitor':1,'s_E1_deliver':-1},p['tasks']['E1_deliver']['duration']+4.)
            if policy=='B2' and p.get('necessary_normal') and 'E1_monitor' in p['tasks']:
                for r in p['robots']:
                    self.row('legacy_third_'+r,{b.xk(r,p['necessary_normal']):-1,b.xk(r,'E1_monitor'):-1,b.xk(r,'E1_pickup'):-1},-1.)
    template=AllocationModel(p);m,v=template.pulp_model(dict(free=list(p['tasks']),freeze_time=False))
    z={k:b.pulp.LpVariable(k,*template.bounds[k]) for k in template.outer}
    for row in template.rows:
        if any(k in template.outer for k in row.coefficients):
            m+=sum(c*(z[k] if k in z else v[k]) for k,c in row.coefficients.items())>=row.rhs,row.name
    m+=template.constant+sum(c*(z[k] if k in z else v[k]) for k,c in template.cost.items())
    return template,m,{**v,**z}


def schedule_routes(p,routes):
    """Deterministic earliest schedule, full graph propagation and resource shifts.

    No optimizer or global assignment fallback. Resource order is deterministic
    from initial arrival estimates; a resulting cycle is an explicit failure.
    """
    _,contract=native();jobs=list(p['tasks']);owners={j:r for r,route in routes.items() for j in route}
    if set(owners)!=set(jobs) or sum(map(len,routes.values()))!=len(jobs):return None,'ROUTE_COVERAGE'
    bounds={('s',j):max(p['time'],p['tasks'][j]['release']) for j in jobs}
    bounds.update({('f',j):0. for j in jobs});edges=[]
    for lock in p['fixed_resources']:
        for j,t in p['tasks'].items():
            if lock['resource'] in t['resources']:bounds['s',j]=max(bounds['s',j],lock['finish']+p['buffer'])
    for j,t in p['tasks'].items():
        edges.append((('s',j),('f',j),t['minimum_duration'] if t['kind']=='monitor' else t['duration']))
        for dep in t['dependencies']:
            if dep in p['tasks']:edges.append((('f',dep),('s',j),0.))
            else:bounds['s',j]=max(bounds['s',j],p['known_finishes'][dep])
    for r,route in routes.items():
        if route:bounds['s',route[0]]=max(bounds['s',route[0]],p['robots'][r]['ready']+contract.tau(p,r,'src',route[0]))
        for u,v in zip(route,route[1:]):edges.append((('f',u),('s',v),contract.tau(p,r,u,v)))
    if 'E1_monitor' in p['tasks']:
        edges += [(('s','E1_monitor'),('s','E1_pickup'),0.),(('f','E1_deliver'),('f','E1_monitor'),4.)]
    def propagate():
        for iteration in range(len(bounds)+1):
            changed=False
            for u,v,lag in edges:
                t=bounds[u]+lag
                if bounds[v]+1e-7<t:bounds[v]=t;changed=True
            if not changed:return True
        return False
    if not propagate():return None,'DEPENDENCY_ROUTE_CYCLE'
    for resource in sorted({k for t in p['tasks'].values() for k in t['resources']}):
        order=sorted((j for j,t in p['tasks'].items() if resource in t['resources']),key=lambda j:(bounds['s',j],j))
        for u,v in zip(order,order[1:]):edges.append((('f',u),('s',v),p['tasks'][u]['egress']+p['tasks'][v]['approach']+p['buffer']))
    for iteration in range(4*len(bounds)+1):
        if not propagate():return None,'RESOURCE_ROUTE_CYCLE'
        shifted=False
        for lock in sorted(p['blocked_resources'],key=lambda q:q['start']):
            for j,t in p['tasks'].items():
                if lock['resource'] in t['resources']:
                    start=bounds['s',j]-t['approach'];end=bounds['f',j]+t['egress']
                    if end+p['buffer']>lock['start']+1e-7 and start<lock['finish']+p['buffer']-1e-7:
                        bounds['s',j]=lock['finish']+p['buffer']+t['approach'];shifted=True
        if not shifted:break
    else:return None,'RESOURCE_PROPAGATION_LIMIT'
    plan=dict(routes=deepcopy(routes),owners=owners,starts={j:bounds['s',j] for j in jobs},finishes={j:bounds['f',j] for j in jobs},ends={},energy_end={r:1. for r in routes})
    for r,route in routes.items():plan['ends'][r]=plan['finishes'][route[-1]]+contract.tau(p,r,route[-1],'end') if route else p['robots'][r]['ready']+contract.tau(p,r,'src','end')
    check=validate(p,plan)
    return (plan,None) if check['passed'] else (None,','.join(q['name'] for q in check['errors'][:5]))


def greedy(p,policy='B1',deadline=float('inf')):
    """Bundle earliest-service insertion. Never reassigns the ordinary backlog.

    Tests all eligible event role pairs and insertion slots against the complete
    graph/resource checker; chooses earliest service, delivery, then shared J.
    """
    eligible=domains(p,policy);routes=nominal_routes(p);candidates=[];reasons={};evaluations=0
    def consider(trial):
        nonlocal evaluations
        if time.perf_counter()>=deadline:return
        evaluations+=1;plan,reason=schedule_routes(p,trial)
        if plan:
            audit=validate(p,plan,policy)
            if not audit['passed']:reason=','.join(e['name'] for e in audit['errors'][:3]);plan=None
        if plan:
            first=plan['starts'].get('E1_verify',plan['starts'].get('E1_monitor',p['time']))
            delivery=plan['finishes'].get('E1_deliver',max(plan['ends'].values()))
            candidates.append(((first,delivery,sum(parts(p,plan).values()),json.dumps(trial,sort_keys=True)),plan))
        else:reasons[reason]=reasons.get(reason,0)+1
    if 'E1_verify' in p['tasks']:
        for r in eligible['E1_verify']:
            for slot in range(len(routes[r])+1):
                trial=deepcopy(routes);trial[r].insert(slot,'E1_verify');consider(trial)
    elif 'E1_monitor' in p['tasks']:
        for monitor,courier in itertools.product(eligible['E1_monitor'],eligible['E1_pickup']):
            if monitor==courier or courier not in eligible['E1_deliver']:continue
            for i,j in itertools.product(range(len(routes[monitor])+1),range(len(routes[courier])+1)):
                trial=deepcopy(routes);trial[monitor].insert(i,'E1_monitor');trial[courier][j:j]=['E1_pickup','E1_deliver'];consider(trial)
    else:consider(routes)
    if not candidates:return dict(status='GREEDY_NO_FEASIBLE_INSERTION',reasons=reasons,evaluations=evaluations)
    _,plan=min(candidates,key=lambda q:q[0]);objective=sum(parts(p,plan).values())
    return dict(status='FEASIBLE_CONSTRUCTIVE',plan=plan,objective=objective,validation=validate(p,plan,policy,objective),evaluations=evaluations,reasons=reasons)


def warm_values(p,template,m,plan):
    """Encode a validated zero-energy route as a complete native MIPStart."""
    a,_=native();b=a.b;values={v.name:0. for v in m.variables()};values['allocation_cmax']=max(plan['ends'].values())
    for j,t in p['tasks'].items():
        values['s_'+j]=plan['starts'][j]
        if t['kind']=='monitor':values['f_'+j]=plan['finishes'][j]
        if j in p['reference']['starts']:values['shift_'+j]=abs(plan['starts'][j]-p['reference']['starts'][j])
    for r,route in plan['routes'].items():
        values['end_'+r]=plan['ends'][r];values['Eend_'+r]=1.
        for rank,j in enumerate(route,1):
            values[b.xk(r,j)]=1.;values['rank_'+r+'_'+j]=float(rank)
            values['pre_'+r+'_'+j]=values['post_'+r+'_'+j]=1.
        previous='src';finish=p['robots'][r]['ready']
        for j in route+['end']:
            values[b.ak(r,previous,j)]=1.
            start=plan['ends'][r] if j=='end' else plan['starts'][j]
            values['wait_'+r+'_'+previous+'_'+j]=max(0.,start-finish-b.tau(p,r,previous,j))
            finish=start if j=='end' else plan['finishes'][j];previous=j
    for key,u,v,_ in template.pairs:
        values[key]=float(plan['finishes'][u]+p['tasks'][u]['egress']+p['buffer']<=plan['starts'][v]-p['tasks'][v]['approach']+1e-6)
    for i,lock in enumerate(p['blocked_resources']):
        for j,t in p['tasks'].items():
            key='block_'+str(i)+j
            if key in values:values[key]=float(plan['starts'][j]-t['approach']>=lock['finish']+p['buffer']-1e-6)
    maximum=0.
    for row in m.constraints.values():
        expression=float(row.constant)+sum(float(c)*values[v.name] for v,c in row.items())
        maximum=max(maximum,abs(expression) if row.sense==0 else max(0.,-row.sense*expression))
    for v in m.variables():
        maximum=max(maximum,max(0.,(v.lowBound or 0.)-values[v.name]),max(0.,values[v.name]-(v.upBound if v.upBound is not None else float('inf'))))
    return values,maximum


def qualification(p,plan):
    cert=p['physical_certificate'];missing=[]
    for j,r in plan['owners'].items():
        t=p['tasks'][j]
        if t['kind']=='normal':
            if r!=p['nominal_owners'][j] or j.startswith('LOAD_'):missing.append(j+':routine_reassignment_or_new_sequence')
        elif p['region']!=cert['region'] or r not in cert.get('qualified_robots',{}).get(t['kind'],[]):missing.append(j+':'+r)
    return dict(status='MODEL_FEASIBLE_NOT_PHYSICALLY_QUALIFIED' if missing else 'ROLE_ASSIGNMENT_QUALIFIED_EXECUTION_NOT_RUN',
        gaps=missing,execution_authorized=False,scope='role assignment screen only; counterfactual timing/concurrency is never a dispatch credential')


def metrics(p,plan):
    normal=[j for j,t in p['tasks'].items() if t['kind']=='normal'];cl=p['clocks']
    monitor=plan['starts'].get('E1_monitor');delivery=plan['finishes'].get('E1_deliver')
    verify=plan['starts'].get('E1_verify',cl.get('actual_verify_started_at'))
    return dict(objective=sum(parts(p,plan).values()),objective_parts=parts(p,plan),
        verify_response=None if verify is None else verify-cl['candidate_at'],
        verify_metric_source='planned' if 'E1_verify' in plan['starts'] else 'shared_actual_history',
        monitor_response=None if monitor is None else monitor-cl['confirmed_at'],
        monitor_from_candidate=None if monitor is None else monitor-cl['candidate_at'],
        delivery_from_confirmed=None if delivery is None else delivery-cl['confirmed_at'],
        delivery_from_candidate=None if delivery is None else delivery-cl['candidate_at'],
        planned_makespan=max(plan['ends'].values()),planned_remaining_completion=max(plan['ends'].values())-p['time'],
        normal_wait=sum(plan['starts'][j]-p['tasks'][j]['release'] for j in normal),
        accepted_owner_changes=sum(plan['owners'][j]!=r for j,r in p['reference']['owners'].items()),
        accepted_time_shift=sum(abs(plan['starts'][j]-v) for j,v in p['reference']['starts'].items()),
        nominal_owner_deviations=sum(plan['owners'][j]!=r for j,r in p['nominal_owners'].items()),
        robot_normal_service_load={r:sum(p['tasks'][j]['duration'] for j in route if p['tasks'][j]['kind']=='normal') for r,route in plan['routes'].items()},
        qualification=qualification(p,plan),actual_nav2_completion=None)
