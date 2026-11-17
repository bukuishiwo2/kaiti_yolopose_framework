"""Independent snapshot/trace checks; never calls protocol transition helpers."""
import math


def audit(snapshot,view,previous=None,position_ttl=10.):
    errors=[];checks=0
    def check(value,label):
        nonlocal checks
        checks+=1
        if not value:errors.append(label)
    e=snapshot['event'];tasks=snapshot['tasks']
    check(snapshot['schema']=='event-task/v1','schema')
    check(len(tasks)==len({t['task_id'] for t in tasks.values()}),'unique task IDs')
    check(view['world_revision']==snapshot['world_revision'],'planning view revision')
    check({t['task_id'] for t in view['completed_facts']}=={t['task_id'] for t in tasks.values() if t['state']=='SUCCEEDED'},'actual completed dependency facts')
    if e is None:
        check(not tasks,'no tasks without event')
        return dict(passed=not errors,checks=checks,errors=errors)
    stamp=e['position_source_at']
    valid=bool(e['space'] and e['space']['valid'] and stamp is not None and 0<=snapshot['time']-stamp<=position_ttl)
    check(e['position_valid']==valid,'position freshness')
    byrole={t['role']:t for t in tasks.values()}
    def succeeded(role):return byrole.get(role,{}).get('state')=='SUCCEEDED'
    mon=byrole.get('monitor',{})
    for key,t in tasks.items():
        role=t['role'];state=t['state']
        check(key==t['task_id']==e['event_id']+':'+role,'identity:'+role)
        check(t['event_id']==e['event_id'],'event binding:'+role)
        check(t['revision']>=1 and t['attempt']>=1,'positive versions:'+role)
        if role!='verify':check(e['verified'],'no response tasks before verification:'+role)
        target=t['target']
        check(t['target_valid']==(target is not None),'target flag:'+role)
        if target:
            check(target['frame']=='map' and len(target['xy'])==2 and all(isinstance(v,(int,float)) and math.isfinite(v) for v in target['xy']),'finite map target:'+role)
        if state not in {'SUCCEEDED','CANCELLED'}:
            if not valid or e['lifecycle']=='CLOSED':check(target is None,'invalid target suppressed:'+role)
        if state in {'READY','RUNNING'}:
            check(valid and t['target_valid'] and e['lifecycle']=='OPEN','execution spatial guard:'+role)
            check(not t['blockers'],'execution blockers:'+role)
            check(all(tasks.get(d,{}).get('state')=='SUCCEEDED' for d in t['completion_dependencies']),'execution dependencies:'+role)
            if role in {'pickup','deliver'}:
                check(mon.get('state')=='RUNNING' and mon.get('target_valid'),'continuous monitor guard:'+role)
                if state=='RUNNING':check(t['owner']!=mon.get('owner'),'distinct monitor:'+role)
        if state=='RUNNING':
            check(t['execution_target']==t['target'] and t['execution_revision']==t['revision'],'current execution target:'+role)
        if role=='deliver' and state in {'READY','RUNNING'}:
            check(succeeded('pickup'),'delivery requires actual pickup')
            check(t['required_owner']==e['cargo_owner'] and t['required_owner'] is not None,'cargo owner binding')
            if state=='RUNNING':check(t['owner']==e['cargo_owner'],'same courier')
        if role=='monitor' and state=='SUCCEEDED':check(succeeded('deliver'),'monitor end after delivery')
        if e['lifecycle']=='CLOSED':check(state in {'SUCCEEDED','CANCELLED','CANCEL_REQUESTED'},'closed event cancellation:'+role)
    active=[t for t in tasks.values() if t['state'] in {'RUNNING','CANCEL_REQUESTED'}]
    check(len(active)==len({t['owner'] for t in active}),'no simultaneous robot executions')
    check({t['task_id'] for t in view['active_commitments']}=={t['task_id'] for t in active},'cancel request retains commitment')
    check({t['task_id'] for t in view['tasks']}=={t['task_id'] for t in tasks.values() if t['state'] in {'PENDING','READY'} and t['target_valid']},'planning target filter')
    if e['lifecycle']=='COMPLETED':check(all(succeeded(r) for r in ['verify','monitor','pickup','deliver']),'all service acknowledgements before completion')
    if previous:
        check(set(previous['tasks']).issubset(tasks),'IDs never erased')
        for key,old in previous['tasks'].items():
            t=tasks[key]
            check(t['revision']>=old['revision'] and t['attempt']>=old['attempt'],'monotonic versions:'+key)
            if old['state'] in {'SUCCEEDED','CANCELLED'}:check(t==old,'terminal task immutable:'+key)
            if old['state']=='CANCEL_REQUESTED' and t['state'] not in {'CANCEL_REQUESTED','CANCELLED'}:
                check(t['attempt']==old['attempt']+1,'resume only on cancellation acknowledgement:'+key)
    return dict(passed=not errors,checks=checks,errors=errors)


def check_expected(result,view,expect,previous=None):
    s=result['snapshot'];tasks=s['tasks'];e=s['event'];errors=[];checks=0
    def check(value,label):
        nonlocal checks
        checks+=1
        if not value:errors.append(label)
    actual={t['role']:t['state'] for t in tasks.values()}
    check(actual==expect['states'],'hand-authored exact role states')
    generated=sorted(o['task_id'].split(':',1)[1] for o in result['operations'] if o['operation']=='GENERATE')
    check(generated==sorted(expect['generated']),'hand-authored generation delta')
    for k in ('lifecycle','verified','position_valid','cargo_disposition'):
        if k in expect:check(e[k]==expect[k],'expected '+k)
    for k in ('changed','decision'):
        if k in expect:check(result[k]==expect[k],'expected '+k)
    for key,field in [('revisions','revision'),('attempts','attempt'),('required_owner','required_owner')]:
        for role,value in expect.get(key,{}).items():check(tasks[e['event_id']+':'+role][field]==value,'expected '+field+':'+role)
    for role,xy in expect.get('targets',{}).items():
        target=tasks[e['event_id']+':'+role]['target']
        check((target['xy'] if target else None)==xy,'expected target:'+role)
    if expect.get('same_ids'):check(previous is not None and set(tasks)==set(previous['tasks']),'same IDs')
    if 'active_commitments' in expect:check(len(view['active_commitments'])==expect['active_commitments'],'expected retained commitments')
    if 'planning_tasks' in expect:check(len(view['tasks'])==expect['planning_tasks'],'expected planning task count')
    return dict(passed=not errors,checks=checks,errors=errors)
