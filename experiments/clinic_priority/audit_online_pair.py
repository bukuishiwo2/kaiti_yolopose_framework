"""Audit the actual Clinic outcome and publish an explainable pair for the workbench."""
import argparse
import json
from pathlib import Path
from statistics import mean

from online_pair import CROSS_JOB, PREFIX_JOB, G1_HOLD, Comparison, READ, WRITE, benchmark, allocation, solve_worker
from feedback_repair import FeedbackComparison, path_checks, revised_problem
from audit_clinic_visual_positive import native_arrival

LABEL = {'E1_verify':'现场核验','E1_monitor':'现场监护',
         'E1_pickup':'领取物资','E1_deliver':'送达物资'}


def audit(folder, policy):
    run = READ(folder/'result.json')
    initial = READ(folder/'initial.json')
    out = dict(policy=policy, run=folder.name, passed=False, reason=run.get('failure'),
               actual=[], predicted=[], checks={})
    ck = out['checks']
    recheck = folder/'runtime_recheck/runtime_preflight.json'
    ck['runtime'] = READ(recheck if recheck.is_file() else folder/'runtime_preflight.json')['passed']
    ck['cleanup'] = READ(folder/'cleanup.json')['passed']
    ck['all_tasks_completed'] = run['passed'] and set(run['completed']) == set(run['tasks'])
    for j, rec in sorted(run['completed'].items(), key=lambda x:x[1]['service_started']):
        out['actual'].append(dict(job=j, robot=rec['robot'], anchor=rec['anchor'],
                                  label=LABEL.get(j,'常态巡检'), start=rec['service_started'],
                                  finish=rec['service_finished'], end=rec['end'],
                                  xy=[rec['target']['x'],rec['target']['y']]))
    out['confirmed'] = confirm = run['confirmed']
    out['initialHash'] = allocation.digest(initial)
    out['scenarioHash'] = benchmark.sha(folder/'runtime_scenario.json')
    if confirm is not None:
        out['reservation'] = [confirm,confirm+G1_HOLD]
    out['pathWitness'] = run['path_witness']
    out['files'] = {name:benchmark.sha(folder/name) for name in ('result.json','trace.jsonl','initial.json')}
    if not (folder/'response/solve/result.json').is_file():
        return out
    p = READ(folder/'response/problem.json')
    q = READ(folder/'response/solve/result.json')
    commit = run['commit']
    attempt = 'response'
    if commit and commit.get('rejected_transition'):
        attempt = 'response_repair'
        rejection = commit['rejected_transition']
        revised = READ(folder/attempt/'problem.json')
        repair = READ(folder/attempt/'solve/result.json')
        old = FeedbackComparison.validate(revised, q['plan'], policy, q['objective'])
        ck['feedback_revision'] = (
            q['input_sha256'] == allocation.digest(p)
            and revised == revised_problem(p, rejection['arc'], rejection['witness'])
            and rejection['witness'] in run['path_witness']
            and [e['name'] for e in old['errors']] == ['rejected_transition'])
        p, q = revised, repair
    ck['plan_hash'] = q['input_sha256'] == allocation.digest(p)
    if not q.get('plan'):
        return out
    plan = q['plan']
    ck['same_saved_plan'] = bool(commit and commit['plan'] == plan and commit['prefixes'] == p['prefixes'])
    ck['validated_plan'] = FeedbackComparison.validate(p,q['plan'],policy,q['objective'])['passed']
    ck['registered_domain'] = all(r in p['allowed_robots'][j] for j,r in q['plan']['owners'].items())
    ck['archived_qualification'] = all(benchmark.sha(Path(f)) == h for f,h in initial['sources'].items())
    witnessed = [x for x in run['path_witness'] if x.get('attempt', 'response') == attempt]
    expected = list(path_checks(p, plan, CROSS_JOB))
    ck['cross_route_preflight'] = len(witnessed) == len(expected) and all(
        x['passed'] and tuple(x['edge']) == edge and tuple(x.get('arc', arc)) == arc
        and (commit is None or x['at'] <= commit['at'])
        for x, (arc, edge) in zip(witnessed, expected))
    out.update(eligible=p['allowed_robots'], changes={j:[r,plan['owners'][j]]
               for j,r in p['reference']['owners'].items() if r != plan['owners'][j]},
               terms=q['validation']['objective_parts'],
               checkpoint={r:v['jobs'] for r,v in p['prefixes'].items()},
               commit=commit['at'] if commit else None,
               newTasks={j:dict(label=LABEL[j], anchor=t['anchor'], prerequisites=t['dependencies'],
                                resource=t['resources'], release=t['release'])
                         for j,t in p['tasks'].items() if j.startswith('E1_')},
               firstSolution=q['first_feasible_seconds'])
    other = 'full' if policy=='fixed' else 'fixed'
    shadow = folder.parent/'shadow'/policy/'solve/result.json'
    if shadow.is_file():
        alt = READ(shadow)
        if (alt.get('plan') and alt['input_sha256']==q['input_sha256'] and
                Comparison.validate(p,alt['plan'],other,alt['objective'])['passed']):
            m = alt['metrics']
            out['sameSnapshotComparison'] = dict(otherPolicy=other,
                objectiveDelta=alt['objective']-q['objective'],
                positiveDelayDelta=m['positive_delay']-q['metrics']['positive_delay'],
                deliveryDelta=m['delivery_from_confirmed']-q['metrics']['delivery_from_confirmed'])
    out['predicted'] = [dict(job=j,robot=r,anchor=p['tasks'][j]['anchor'],
                             label=LABEL.get(j,'常态巡检'),
                             start=plan['starts'][j],finish=plan['finishes'][j],
                             xy=p['tasks'][j]['location']) for j,r in plan['owners'].items()]
    out['predictionDelivery'] = plan['finishes']['E1_deliver']-confirm
    ck['prefix'] = (p['prefixes']['r2']['jobs'] == [PREFIX_JOB] and
                    PREFIX_JOB not in p['tasks'] and
                    run['completed'].get(PREFIX_JOB,{}).get('task_id') == p['prefixes']['r2']['record_task_id'])
    reservation = run['reservation']
    ck['G1_ack_and_duration'] = (
        abs(reservation['finish']-reservation['start']-G1_HOLD) < 1e-6 and
        any(e['phase']=='availability_changed' and e['request']==reservation for e in run['resource_events']))
    ck['G1_no_lease_during_reservation'] = not any(
        e['phase']=='granted' and e.get('request',{}).get('resource')=='G1' and
        reservation['start'] <= e['at'] < reservation['finish'] for e in run['resource_events'])
    records = run['completed']
    with (folder/'trace.jsonl').open() as stream:
        rows = [json.loads(line) for line in stream]
    confirmations = [row for row in rows if row['phase']=='paired_event_confirmed']
    feedback = {(row['robot'], row['feedback']['task_id'], row['feedback']['phase'])
                for row in rows if row['phase']=='service_feedback'}
    ck['actual_service_tokens'] = all(
        all((rec['robot'],rec['task_id'],phase) in feedback for phase in ('started','succeeded'))
        for rec in records.values())
    ck['confirmed_by_actual_verify_ack'] = (len(confirmations)==1 and
        ('r1',records['E1_verify']['task_id'],'succeeded') in feedback and
        abs(confirm - confirmations[0]['episode_time']) < .2)
    if confirmations:
        out['confirmationStage'] = {r:dict(job=v['job'],leg=v['leg'],state=v['state'])
                                    for r,v in confirmations[0]['checkpoint'].items()}
    if PREFIX_JOB in records:
        r = records[PREFIX_JOB]
        ck['prefix_dispatch_and_finish'] = r['begin'] <= confirm < r['end']
    ck['qualified_arrival_and_resource_release'] = all(
        native_arrival(r) and
        (not run['tasks'][j]['resources'] or
         r['lease_released_at'] >= r['clear_at'] > r['service_finished'] >= r['lease_granted_at'])
        for j,r in records.items())
    ck['executed_plan_owners'] = all(j in records and records[j]['robot']==r for j,r in plan['owners'].items())
    ck['monitor_custody_feedback'] = False
    if {'E1_monitor','E1_pickup','E1_deliver'} <= records.keys():
        mon,pick,drop = (records[j] for j in ('E1_monitor','E1_pickup','E1_deliver'))
        ck['monitor_custody_feedback'] = (mon['service_started'] <= pick['service_started'] and
            pick['robot']==drop['robot'] != mon['robot'] and pick['end'] <= drop['service_started'] and
            drop['service_finished'] <= mon['service_finished'] and run['protocol']['event']['lifecycle']=='COMPLETED')
        out['delivery'] = drop['service_finished']-confirm
    offsets = {j:records[j]['service_finished']-t for j,t in p['reference']['finishes'].items() if j in records}
    if offsets:
        out['routineOffsets'] = offsets
    if offsets and offsets.keys() == p['reference']['finishes'].keys():
        routine = [records[j]['end']-confirm for j in offsets]
        out.update(routineEnd=max(routine), routineMeanEnd=mean(routine),
                   routineDelay=sum(max(0.,x) for x in offsets.values()))
    out['passed'] = all(ck.values())
    return out


def publish(pair):
    arms, repeats = {}, []
    for policy in ('fixed','full'):
        candidates = sorted(pair.glob(f'{policy}*/result.json'))
        if candidates:
            arms[policy] = audit(candidates[0].parent,policy)
        for path in candidates[1:]:
            run = READ(path)
            failed_jobs = [r['job_id'] for r in run['records'] if r['status'] == run['failure']]
            repeats.append(dict(policy=policy, run=path.parent.name, passed=run['passed'],
                                reason=run['failure'], failedJobs=failed_jobs,
                                completed=len(run['completed']), sha256=benchmark.sha(path)))
    matched = conditions_matched = False
    if set(arms) == {'fixed','full'}:
        fixed,full = (arms[k] for k in ('fixed','full'))
        fields = ('initialHash','scenarioHash','eligible','checkpoint','confirmationStage')
        conditions_matched = all(k in fixed and k in full and fixed[k]==full[k] for k in fields)
        matched = conditions_matched and fixed['passed'] and full['passed']
    data = dict(schema='clinic-online-pair/v1', matched=matched,
                conditionsMatched=conditions_matched, arms=arms, repeats=repeats,
                candidate='三机巡检中确认应急事件 · 物资站 G1 预约 240 秒')
    WRITE(pair/'viewer.json',data)
    return data


def shadow_solve(pair):
    for policy, other in (('fixed','full'),('full','fixed')):
        candidates = sorted(pair.glob(f'{policy}*/result.json'))
        if candidates:
            source = candidates[0].parent/'response/problem.json'
            target = pair/'shadow'/policy
            if source.is_file() and not (target/'solve').exists():
                WRITE(target/'problem.json', READ(source))
                solve_worker(target,other)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('pair',type=Path)
    parser.add_argument('--shadow',action='store_true',help='solve the other policy offline on each saved online input')
    args=parser.parse_args()
    output=args.pair.resolve()
    if args.shadow:
        shadow_solve(output)
    result=publish(output)
    print({policy:(value['passed'],value.get('reason')) for policy,value in result['arms'].items()},
          'matched',result['matched'])
