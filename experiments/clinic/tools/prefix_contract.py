"""Revocable execution-prefix projection. No ROS, no pretending future facts are ACKs."""
from copy import deepcopy
import math
import aligned_tasks
from aligned_contract import validate as aligned_validate, impact_scope as aligned_impact

GUARD=35.0
START_WINDOW=2.0
ACK_MARGIN=1.0
CLEAR_MARGIN=5.0

def trim(plan,jobs):
    q=deepcopy(plan);keep=set(jobs)
    for k in ['owners','starts','finishes']:q[k]={j:v for j,v in q[k].items() if j in keep}
    q['routes']={r:[j for j in route if j in keep] for r,route in q['routes'].items()}
    return q

def projection(cfg,tasks,plan,completed,states,protocol_view,now,blocks,egress_updates):
    """Current goal through clear, and mandatory drop after a committed pickup.

    Times are forecasts that must be monitored and revoked, NOT actual completion.
    No prediction of nonzero battery consumption is implemented: reject it explicitly.
    """
    prefixes={};locked=set();sources={};forecasts={};reservations=[]
    for rid,state in states.items():
        route=[j for j in plan['routes'][rid] if j not in completed]
        job=state['job'];jobs=[];terminal=bool(job and str(job).startswith('EXIT_'))
        if job and not terminal:
            assert job in route and route[0]==job,(rid,job,route)
            jobs=[job]
        cargo=state.get('cargo')
        if jobs and tasks[jobs[0]].get('cargo_role')=='pickup':cargo=tasks[jobs[0]]['cargo_group']
        if cargo:
            drop=next(j for j in route if tasks[j].get('cargo_group')==cargo and tasks[j].get('cargo_role')=='drop')
            if drop not in jobs:jobs.append(drop)
            assert route[:len(jobs)]==jobs,'Committed custody must be a contiguous route prefix'
        anchor=state['anchor'];available=now+GUARD;schedule=[]
        for n,j in enumerate(jobs):
            task=tasks[j];assert task['kind']=='normal','This experiment repairs post-event normal backlog, not active monitoring'
            clear_remaining_bound=0.
            issued=(n==0 and state['job']==j)
            rec=state.get('record',{}) if issued else {}
            if issued:assert rec.get('job_id')==j,'Active record must match issued task'
            approach=task.get('approach',0.);egress=max(task.get('egress',0.),egress_updates.get(next(iter(task['resources']),''),0.))
            if issued:
                expected=plan['starts'][j]
                if state['state'] in ['NAV_ACK','NAVIGATING','HANDOFF_STOP','HEADING_ACK','HEADING_ACTIVE','STABILIZING']:
                    target=rec.get('target');pose=state.get('pose')
                    geometric=math.hypot(target['x']-pose['x'],target['y']-pose['y'])/.22 if target and pose else 0.
                    eta=max(state.get('navigation_eta',0.),geometric)+10.
                    if state.get('leg')=='entry':eta+=approach
                    if state.get('leg')=='clear':clear_remaining_bound=now+eta
                    expected=max(expected,now+eta)
                if rec.get('service_started') is not None:expected=rec['service_started']
            else:expected=max(plan['starts'][j],available+cfg['tables']['event'][anchor][task['entry_anchor']]+approach)
            actual_finish=rec.get('service_finished')
            end=(actual_finish if actual_finish is not None else max(expected+task['duration']+ACK_MARGIN,now+ACK_MARGIN))
            clear=max(end+egress+(CLEAR_MARGIN if task['resources'] else 0.),now+ACK_MARGIN,clear_remaining_bound)
            if task['resources'] and rec.get('lease_granted_at') is None:
                for block in sorted(blocks,key=lambda b:b['start']):
                    if block['resource'] in task['resources'] and expected-approach<block['finish']+cfg['resource_buffer'] and clear+cfg['resource_buffer']>block['start']:
                        expected=max(expected,block['finish']+cfg['resource_buffer']+approach);end=expected+task['duration']+ACK_MARGIN;clear=end+egress+CLEAR_MARGIN
            assert end<=task['deadline'],'Committed prefix forecast violates task deadline'
            start=(rec.get('service_started') if rec.get('service_started') is not None else expected)
            item=dict(job=j,owner=rid,start=start,service_finish_forecast=end,clear_forecast=clear,clear_anchor=task['clear_anchor'],actual_service_started=rec.get('service_started'),actual_service_finished=actual_finish,cargo_group=task.get('cargo_group'),cargo_role=task.get('cargo_role'),state=state['state'] if issued else 'COMMITTED_CUSTODY_DROP')
            schedule.append(item);forecasts[j]=end;locked.add(j)
            for resource in task['resources']:
                reservations.append(dict(resource=resource,start=rec.get('lease_granted_at',min(start-approach,plan['starts'][j]-approach) if n==0 else start-approach),finish=clear,change_id='commit:'+rid+':'+j,job=j,owner=rid,kind='committed_occupation'))
            anchor=task['clear_anchor'];available=clear
        if terminal:anchor=cfg['homes'][rid];available=max(now+GUARD,plan['ends'][rid]);schedule=[]
        sources[rid]=anchor;prefixes[rid]=dict(jobs=jobs,schedule=schedule,source_anchor=anchor,ready=max(available,now+GUARD),terminal=terminal,issued_job=job,cargo_at_snapshot=state.get('cargo'),snapshot_state=state['state'])
    ref=trim(plan,set(tasks)-set(completed)-locked)
    p=aligned_tasks.problem(sources,ref,completed,protocol_view,now,'response_plan')
    p['tasks']={j:deepcopy(tasks[j]) for j in p['tasks'] if j not in locked}
    assert all(t['kind']=='normal' for t in p['tasks'].values()),'No active event in this experiment'
    p['events']={};p['reference']=trim(ref,p['tasks']);p['planning_guard_seconds']=GUARD
    p['actual_known_finishes']=deepcopy(p['known_finishes']);p['committed_finishes']=forecasts
    p['known_finishes'].update(forecasts)
    p['cargo_pairs']=[pair for pair in p['cargo_pairs'] if all(j in p['tasks'] for j in pair)]
    p['blocked_resources']=deepcopy(blocks)+reservations
    p['execution_commitments']=prefixes;p['commitment_resources']=reservations;p['snapshot_states']=deepcopy(states);p['start_tolerance']=START_WINDOW
    for rid,robot in p['robots'].items():
        robot['ready']=prefixes[rid]['ready'];robot['source_anchor']=sources[rid];robot['position']=cfg['anchors'][sources[rid]][:2]
        if states[rid]['finished'] or prefixes[rid]['terminal']:robot['capabilities']=[]
        assert robot['move_rate']==robot['idle_rate']==0.,'Nonzero prefix energy requires an explicit battery projection'
    for t in p['tasks'].values():assert t['energy_rate']==0.
    p['projection_note']='Forecast dependency releases do not update actual completion/protocol. Prefix occupancy and sources are revocable; lease/dependency ACKs remain mandatory.'
    return p

def impact_scope(p):
    impact=aligned_impact(p);ref=p['reference'];tol=p.get('start_tolerance',0.)
    for j,reasons in list(impact['seeds'].items()):
        if reasons==['actual_ready_or_source_infeasible']:
            rid=ref['owners'][j]
            from aligned_contract import tau
            if p['robots'][rid]['ready']+tau(p,rid,'src',j)<=ref['starts'][j]+tol+1e-6:del impact['seeds'][j]
    free=set(impact['seeds']);queue=list(free)
    while queue:
        for j in impact['edges'].get(queue.pop(),[]):
            if j not in free:free.add(j);queue.append(j)
    impact.update(free=sorted(free),preserved=sorted(set(p['tasks'])-free),start_tolerance=tol)
    return impact

def validate(p,plan,scope,claimed=None):
    window=p.get('start_tolerance',0.) if scope['freeze_time'] else 0.
    check_scope=dict(scope,freeze_time=False) if window else scope
    audit=aligned_validate(p,plan,check_scope,claimed)
    if window:
        for j in set(p['reference']['owners'])-set(scope['free']):
            audit['checks']+=1
            if abs(plan['starts'][j]-p['reference']['starts'][j])>window+1e-6:audit['errors'].append(dict(name=j+'_start_window',residual=abs(plan['starts'][j]-p['reference']['starts'][j])-window))
    audit['passed']=not audit['errors'];return audit

def commitment_status(p,completed,states,now,check_dispatch=True):
    errors=[]
    for rid,prefix in p.get('execution_commitments',{}).items():
        state=states[rid]
        for item in prefix['schedule']:
            j=item['job']
            if j in completed:
                q=completed[j]
                if q['robot']!=rid or q['end']>item['clear_forecast']+1e-6:errors.append(dict(job=j,reason='completed_outside_commitment',actual=q['end'],bound=item['clear_forecast']))
            elif now>item['clear_forecast']+1e-6:errors.append(dict(job=j,reason='unresolved_after_forecast',at=now,bound=item['clear_forecast']))
        if check_dispatch and state['job'] and not str(state['job']).startswith('EXIT_') and state['job'] not in prefix['jobs']:errors.append(dict(robot=rid,job=state['job'],reason='uncontracted_dispatch_during_solve'))
    return dict(passed=not errors,errors=errors)
