#!/usr/bin/env python3
"""Offline causal gate consumes actual ROS/model logs; ACK fixtures are explicit."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import time

PROJECT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(PROJECT/'src'),'/home/yhc/clinic_planning_ws/tools']
from kaiti_task_sim.clinic_visual import VisualEventBridge, compile_tasks, registered_space
from kaiti_task_sim.event_protocol import canonical
import dense_tasks as dt
import bed_contract
import dense_solver as ds
import dense_validate as dv


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--replay',type=Path,required=True);ap.add_argument('--out',type=Path,required=True)
    a=ap.parse_args();a.out.mkdir(parents=True,exist_ok=False)
    cfg=bed_contract.config(); checks=[]; witnesses={}; real={}
    def check(name,value):checks.append(dict(name=name,passed=bool(value)))
    with (a.replay/'causal.jsonl').open() as f:
        for line in f:
            row=json.loads(line)
            if row['kind']=='image_model_event_tasks' and row['compiled']:
                real.setdefault(row['sample']['source_id'],row)
    for video in ['fall-01-cam0','adl-01-cam0']:
        check(video+'_has_real_model_candidate',video in real)
    assert all(c['passed'] for c in checks),checks
    for name,region,valid,enabled in [('no_semantic','A',True,False),('positive_A','A',True,True),('positive_B','B',True,True),('invalid_space','A',False,True),('false_alarm','A',True,True)]:
        video='adl-01-cam0' if name=='false_alarm' else 'fall-01-cam0'
        b=VisualEventBridge(cfg,region,source_id=video)
        actual=deepcopy(real[video]['sample']);now=actual['source_at']+.01
        if enabled:b.observe(actual,now,valid)
        else:b.tick(now)
        before=b.protocol.snapshot()
        compiled=compile_tasks(b.protocol.planning_view(),now,cfg,region,dt.phases)
        normals,_=dt.normal_tasks();normals={j:t for j,t in normals.items() if t['waypoint']==1}
        tasks={**normals,**compiled}
        states={r:dict(job=None,state='IDLE',anchor=cfg['starts'][r],cargo=None,record={},pose=dict(zip(('x','y','yaw'),cfg['anchors'][cfg['starts'][r]])),leg='service') for r in cfg['robots']}
        p=dt.problem(cfg,tasks,list(tasks),{},states,dict(starts={}),now,now,'visual_verify')
        scope=dict(free=list(p['tasks']),freeze_time=False)
        folder=a.out/name;folder.mkdir()
        result=ds.a.ScopedSolver(folder/'solver').solve(p,scope,'monolithic',time.perf_counter()+5)
        validation=dv.validate(p,result['plan'],scope,result['objective']) if result['status'] in {'OPTIMAL','FEASIBLE_BUDGET'} else dict(passed=False)
        check(name+'_original_milp_validated',validation['passed'])
        check(name+'_no_unauthorized_execution',all(not t['execution_authorized'] for t in compiled.values()))
        if name in {'no_semantic','invalid_space'}:check(name+'_no_emergency',not compiled)
        else:check(name+'_verify_only',set(compiled)=={'E1_verify'})
        lifecycle=None
        if name=='false_alarm':
            def msg(phase,at):return dict(schema='event-task/v1',kind='feedback',message_id='fixture:'+phase,event_id='E1',task_id='E1:verify',task_revision=1,attempt=1,robot_id=result['plan']['owners']['E1_verify'],phase=phase,at=at)
            b.feedback(msg('started',now+.1))
            b.feedback(msg('succeeded',now+.2),dict(result='no_fall',source='operator_review',event_id='E1',evidence_id='OFFLINE_TEST_FIXTURE_NOT_REAL_SERVICE_ACK'))
            lifecycle=b.protocol.snapshot()
            check('false_alarm_fixture_closes_without_response',lifecycle['event']['lifecycle']=='CLOSED' and set(lifecycle['tasks'])=={'E1:verify'})
        for file,obj in [('problem',p),('result',result),('validation',validation),('protocol',before)]:
            (folder/(file+'.json')).write_text(json.dumps(obj,indent=2))
        witnesses[name]=dict(compiled=compiled,plan=result.get('plan'),lifecycle_fixture=lifecycle,
            real_sample=actual if enabled else None,source_log=str(a.replay/'causal.jsonl'))
    A=witnesses['positive_A']['compiled']['E1_verify'];B=witnesses['positive_B']['compiled']['E1_verify']
    check('position_changes_actual_compiled_target',A['location']!=B['location'])
    check('position_changes_resource_and_entry',(A['resources'],A['entry_anchor'])!=(B['resources'],B['entry_anchor']))
    check('position_changes_travel',cfg['tables']['event']['G1'][A['entry_anchor']]!=cfg['tables']['event']['G1'][B['entry_anchor']])
    check('real_false_positive_not_hidden','E1_verify' in witnesses['false_alarm']['plan']['owners'])
    for region in ['A','B']:
        actual=deepcopy(real['fall-01-cam0']['sample']);now=actual['source_at']+.01
        b=VisualEventBridge(cfg,region,source_id=actual['source_id']);b.observe(actual,now)
        def ack(phase,at):return dict(schema='event-task/v1',kind='feedback',message_id='offline:'+phase,
            event_id='E1',task_id='E1:verify',task_revision=1,attempt=1,robot_id='r3',phase=phase,at=at)
        b.feedback(ack('started',now+.1));b.feedback(ack('succeeded',now+.2),dict(result='fall',source='operator_review',event_id='E1',evidence_id='OFFLINE_TEST_FIXTURE_NOT_ACTUAL_SERVICE'))
        compiled=compile_tasks(b.protocol.planning_view(),now+.2,cfg,region,dt.phases)
        tasks={**normals,**compiled}
        p=dt.problem(cfg,tasks,list(tasks),{'E1_verify':dict(end=now+.2)},states,dict(starts={}),now+.2,now,'response')
        folder=a.out/('response_'+region);folder.mkdir();scope=dict(free=list(p['tasks']),freeze_time=False)
        result=ds.a.ScopedSolver(folder/'solver').solve(p,scope,'monolithic',time.perf_counter()+5)
        validation=dv.validate(p,result['plan'],scope,result['objective']) if result['status'] in {'OPTIMAL','FEASIBLE_BUDGET'} else dict(passed=False)
        check('response_'+region+'_original_milp_validated',validation['passed'])
        check('response_'+region+'_monitor_and_courier_relations',len(p['cargo_pairs'])==1 and bool(p['events']))
        for file,obj in [('problem',p),('result',result),('validation',validation)]:
            (folder/(file+'.json')).write_text(json.dumps(obj,indent=2))
        witnesses['response_'+region]=dict(compiled=compiled,plan=result.get('plan'),
            verdict_source='OFFLINE_ACK_FIXTURE',actual_execution=False)
    summary=dict(passed=all(c['passed'] for c in checks),checks=checks,witnesses=witnesses,
        scope='offline real-model semantic/spatial counterfactual; lifecycle ACKs are unit fixtures',
        navigation_authorized=False,three_robot_execution=False,
        remaining_gate='actual dual-region navigation/service/resource qualification')
    (a.out/'summary.json').write_text(json.dumps(summary,indent=2));print(json.dumps(dict(passed=summary['passed'],checks=len(checks))))
    return 0 if summary['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
