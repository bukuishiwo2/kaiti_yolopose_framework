"""Continue a retargeted verification through the existing A-area response."""
from copy import deepcopy
import hashlib
import math
from pathlib import Path
import subprocess
import sys

from factorial import READ, WRITE, WORKSPACE, benchmark
from feedback_repair import check_prefix
from kaiti_task_sim.clinic_visual import compile_tasks, execution_fence, execution_tokens
from kaiti_task_sim.event_protocol import canonical
from audit_clinic_visual_positive import native_arrival


ROUTINE = 'C0_r3_W1'
APPROACH = 'E1_monitor_approach'
RESPONSE = {'E1_monitor':'r1','E1_pickup':'r2','E1_deliver':'r2'}
QA = WORKSPACE/'verification/visual_positive_2026-11-18_c1'
REFERENCE = QA/'positive_02/summary.json'


def fixture(cfg):
    certificate = QA/'a_qualification_audit/A.json'
    cert = READ(certificate)
    evidence = Path(cert['evidence'])
    reference = READ(REFERENCE)
    expected = dict(verify=['r1'],monitor=['r1'],pickup=['r2'],deliver=['r2'])
    if not (cert['passed'] and cert['concurrent_resource_qualification']
            and cert['config_sha256']==hashlib.sha256(canonical(cfg).encode()).hexdigest()
            and cert['qualified_robots']==expected and READ(evidence)['passed']
            and benchmark.sha(evidence)==cert['evidence_sha256']
            and reference['passed'] and reference['completed']['E1_deliver']['status']=='SUCCEEDED'):
        raise ValueError('Missing matching A-area qualification and positive execution')
    courier = reference['completed']['C0_r2_W1']
    if not (courier['final_anchor']=='CDL' and native_arrival(courier)
            and courier['lease_released_at']>=courier['clear_at']):
        raise ValueError('Missing qualified courier source pose')
    return dict(poses={'r2':[courier['ground_truth'][k] for k in ('x','y','yaw')],
                       'r3':cfg['robots']['r3']['start']},
                anchors={'r2':'CDL','r3':cfg['starts']['r3']},
                routine=reference['tasks'][ROUTINE],
                sources={f.name:benchmark.sha(f) for f in (certificate,evidence,REFERENCE)})


def issue_routine(c, prior, wait):
    task = deepcopy(prior['routine'])
    robot = c.peers['r3']
    c.tasks[ROUTINE]=task
    start=c.elapsed()+1.+c.cfg['tables']['event'][robot.anchor][task['entry_anchor']]+task['approach']
    c.plan['starts'][ROUTINE]=start
    c.plan['finishes'][ROUTINE]=start+task['duration']
    c.plan['owners'][ROUTINE]='r3'
    c.queues['r3']=[ROUTINE]
    wait(lambda:(c.dispatch_dense(robot) or robot.job==ROUTINE),15.,move=True)
    c.log('routine_issued_before_verify',task_id=robot.record['task_id'],start=start)


def continue_response(c,out,query,wait,result,*,via_v3=False,after_patrol=False):
    import dense_tasks as dt
    from dense_validate import validate

    verify=c.completed['E1_verify']
    confirmed=c.protocol.tasks['E1:verify']['finished_at']
    view=c.protocol.planning_view()
    if c.peers['r3'].job!=ROUTINE or not c.protocol.event['verified']:
        raise ValueError('Expected positive verify ACK and still-active routine commitment')
    result.update(confirmed=confirmed, released_tasks=view['tasks'], passed=False,
                  monitorApproach='V3' if via_v3 else 'direct', monitorAfterPatrol=after_patrol)
    tasks=compile_tasks(view,c.elapsed(),c.cfg,'A',dt.phases)
    if set(tasks)!=RESPONSE.keys():
        raise ValueError('Unexpected event task release')
    for job,rid in RESPONSE.items():
        task=tasks[job]
        qualifier='qualified_role_'+task['kind']
        task['capabilities'].append(qualifier)
        c.cfg['capabilities'][rid]=[*c.cfg['capabilities'][rid],qualifier]
        task['spatial_source']='controlled_gazebo_body_mask'
    tokens=execution_tokens(c.protocol,[t['protocol_task_id'] for t in tasks.values()])
    anchors=c.cfg['anchors']
    owners=dict(RESPONSE)
    monitor_routes=[('r1',verify['final_anchor'],'M1',None)]
    if via_v3:
        monitor_routes=[('r1',verify['final_anchor'],'V3',None),('r1','V3','M1',anchors['V3'])]
        owners[APPROACH]='r1'
        tasks[APPROACH]=dt.phases(dict(kind='transit',anchor='V3',duration=1.,
            release=c.elapsed(),deadline=1800.,resources=[],dependencies=['E1_verify'],
            capabilities=['move','qualified_role_monitor'],service_role='monitor_approach_stop',energy_rate=0.),c.cfg)
        tasks['E1_monitor']['dependencies'].append(APPROACH)
    if after_patrol:
        # Gate navigation itself on the observed clearance, not just service.
        first_monitor_job=APPROACH if via_v3 else 'E1_monitor'
        tasks[first_monitor_job]['dependencies'].append(ROUTINE)
    routes=[*monitor_routes,('r2','CDL','AG1',None),('r2','CG1','H1',anchors['CG1'])]
    checks=[]
    for rid,source,target,start in routes:
        q=query(dict(id=target,pose=anchors[target]),False,c.peers[rid],start)
        q.update(robot=rid,source=source)
        checks.append(q)
        c.log('response_route_screen',witness=q)
    result['path_queries']=checks
    if not all(q['passed'] for q in checks):
        raise ValueError('Response failed fresh Nav2 route screening')
    # The south stand is a source for monitor only. Set the measured arc and
    # keep unused model arcs defined because the native solver enumerates them.
    table=c.cfg['tables']['event']
    table[verify['final_anchor']]=dict(table['V1'])
    for q in checks:
        # Use the same centisecond grid as the execution snapshot projection.
        # Round up so the path-derived travel bound stays conservative.
        table[q['source']][q['id']]=math.ceil((12.+q['length']/.22)*100)/100
    c.tasks.update(tasks)
    now=c.elapsed()
    p=dt.problem(c.cfg,c.tasks,list(tasks),c.completed,c.states(),c.plan,now,confirmed,'response')
    prefix=p['prefixes']['r3']
    if prefix['jobs']!=[ROUTINE] or ROUTINE in p['tasks']:
        raise ValueError('Response snapshot lost the issued patrol prefix')
    result['prefix']=deepcopy(prefix)
    folder=out/'response'
    WRITE(folder/'request.json',dict(variants=[p]))
    with (folder/'worker.log').open('w') as log:
        subprocess.run([sys.executable,str(WORKSPACE/'tools/dense_solver.py'),
            str(folder/'request.json'),str(folder/'result.json')],check=True,timeout=20.,
            stdout=log,stderr=subprocess.STDOUT)
    q=READ(folder/'result.json')
    plan=q.get('plan')
    if (not plan or plan['owners']!=owners or q['selected_problem']!=p
            or not validate(p,plan,q['scope'],q['objective'])['passed']
            or not execution_fence(c.protocol,tokens)['passed']
            or c.elapsed()>min(r['ready'] for r in p['robots'].values())):
        raise ValueError('Response plan failed validation or live execution fence')
    check_prefix(p,plan,c.states(),c.completed)
    for key in ('owners','starts','finishes'):
        c.plan[key].update(plan[key])
    c.queues=deepcopy(plan['routes'])
    c.plan_revision+=1
    c.planned_owners.update({j.replace('_',':',1):plan['owners'][j] for j in RESPONSE})
    result.update(plan=plan, planStatus=q['status'], committed=c.elapsed())
    c.log('south_stand_response_committed',plan=plan,prefix=prefix)

    def finished():
        drop=c.completed.get('E1_deliver')
        if drop and not c.handover_ack and c.elapsed()>=drop['end']+3.:
            c.handover_ack=True
            c.log('scripted_handover_ack',event_id='E1',source='controlled receiver after actual delivery')
        if c.failed is None:
            for peer in c.peers.values():
                c.dispatch_dense(peer)
        return (all(j in c.completed for j in (*owners,ROUTINE))
                and c.protocol.event['lifecycle']=='COMPLETED'
                and not c.resource.get('owners'))

    wait(finished,620.,move=True)
    records={j:c.completed[j] for j in (*owners,ROUTINE)}
    patrol=records[ROUTINE]
    monitor,pickup,delivery=(records[j] for j in RESPONSE)
    actual_checks={
        'same_patrol_dispatch': (patrol['task_id']==prefix['record_task_id']
            and patrol['begin']<confirmed<=result['committed']<patrol['end']
            and patrol['robot']=='r3' and patrol['plan_revision']==1),
        'native_arrivals':all(native_arrival(r) for r in records.values()),
        'verify_before_response':all(confirmed<=r['begin'] for j,r in records.items() if j!=ROUTINE),
        'monitor_coverage':monitor['service_started']<=pickup['service_started']
            <delivery['service_finished']<=monitor['service_finished'],
        'courier_custody':pickup['robot']==delivery['robot']!='r1'
            and pickup['end']<=delivery['begin'] and c.peers['r2'].cargo is None,
        'resource_ack':all(
            r['lease_granted_at']<=r['service_started']<r['service_finished']<r['clear_at']<=r['lease_released_at']
            and {'granted','released'} <= {e['phase'] for e in c.resource_events
                 if (e.get('request') or {}).get('lease_id')==r['task_id']} for r in (pickup,patrol)),
        'protocol_ack':all(c.protocol.tasks['E1:'+j[3:]]['state']=='SUCCEEDED' for j in RESPONSE),
        'resources_clear':not c.resource.get('owners'),
    }
    if via_v3:
        actual_checks['intermediate_stop_ack']=records[APPROACH]['end']<=monitor['begin']
    if after_patrol:
        actual_checks['patrol_clear_before_approach']=patrol['end']<=records[first_monitor_job]['begin']
    result.update(checks=actual_checks,passed=all(actual_checks.values()), actual=list(records.values()))
