"""Publish measured EPW2 qualification and a separately audited prior recovery."""
import argparse
import json
from pathlib import Path

from factorial import WORKSPACE, benchmark, READ, WRITE
from qualify_epw2 import SOURCE

BED = WORKSPACE/'verification/visual_bed_2026-11-18_d1/bed_before_pickup_04'


def case(run):
    result = READ(run/'result.json')
    setup = READ(run/'protocol.json')
    record = result['record']
    track = []
    with (run/'trace.jsonl').open() as log:
        for row in map(json.loads,log):
            if row['phase'] == 'pose_sample' and row['episode_time'] >= record.get('begin',0.):
                t, p = row['episode_time'], row['truth']['r3']
                track.append([round(t,2),round(p['x'],3),round(p['y'],3)])
    stages = {key:record.get(field) for key,field in dict(
        dispatch='begin', entry='gate_arrival', lease='lease_granted_at',
        service='service_started', serviceEnd='service_finished', clear='clear_at',
        released='lease_released_at', terminal='end').items()}
    names = ('result.json','trace.jsonl','protocol.json','cleanup.json','startup.log')
    with (run/'startup.log').open() as log:
        collision_warnings = sum('r3.controller_server' in line and 'detected collision ahead' in line for line in log)
    return dict(run=run.name, occupied=result['occupied'], passed=result['passed'],
                failure=result['failure'], reservationAck=result['reservation_ack'],
                poses=result['poses'], dispatchPose=result['dispatch_pose'], track=track,
                paths=record.get('path_checks',[]), attempts=record.get('navigation_attempts',[]),
                stages=stages, collisionWarnings=collision_warnings, cleanup=READ(run/'cleanup.json')['passed'],
                sourceHashes=setup['source_hashes'], fileHashes={name:benchmark.sha(run/name) for name in names})


def bed_witness(audit_path):
    summary = READ(BED/'summary.json')
    audit = READ(audit_path)
    if not (audit['passed'] and summary['passed'] and
            audit['summary_sha256'] == benchmark.sha(BED/'summary.json')):
        raise ValueError('Historical feedback recovery audit must match the source summary')
    completed = summary['completed']
    repairs = []
    with (BED/'trace.jsonl').open() as log:
        for row in map(json.loads,log):
            if row['phase'] == 'visual_repair_committed':
                repairs.append(row['episode_time'])
    # The publishing timeline preserves actual service ACKs and exit times.
    actual = [dict(job=j,robot=r['robot'],anchor=r['anchor'],label=j,
                      xy=[r['target']['x'],r['target']['y']],
                      start=r['service_started'],finish=r['service_finished'])
                 for j,r in completed.items()]
    return dict(run=BED.name, passed=True, services=len(completed),
                delivery=completed['E1_deliver']['service_finished'],
                routineEnd=max(r['end'] for r in completed.values()),
                repairTimes=repairs, actual=actual, summarySha=benchmark.sha(BED/'summary.json'),
                auditSha=benchmark.sha(audit_path))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('batch',type=Path)
    parser.add_argument('--audit',type=Path,required=True)
    args = parser.parse_args()
    cases = [case(f.parent) for f in sorted(args.batch.glob('epw2_*/result.json'))]
    if {c['occupied'] for c in cases} != {True,False} or len(cases) != 2:
        raise ValueError('Expected one measured run for each occupancy condition')
    if any(not c['reservationAck'] or not c['cleanup'] or not c['paths'] or not c['track'] for c in cases):
        raise ValueError('Missing dispatch, path, trajectory, or cleanup evidence')
    if any(cases[0]['poses'][r]!=cases[1]['poses'][r] for r in ('r2','r3')):
        raise ValueError('R2/R3 initial poses must match')
    cfg = READ(SOURCE/'runtime_scenario.json')
    WRITE(args.batch/'viewer.json',dict(schema='clinic-epw2-qualification/v1',
        cases=cases, anchors={k:cfg['anchors'][k][:2] for k in ('CTLR3','M1','V1','EPW2','PW2','CPW2C')},
        reservationSeconds=240, bedWitness=bed_witness(args.audit)))


if __name__ == '__main__':
    main()
