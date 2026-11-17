#!/usr/bin/env python3
"""Run four independent event/task replays, with explicit per-step oracles."""
import argparse
from datetime import datetime
import csv
import hashlib
import json
import platform
from pathlib import Path
import shutil
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from kaiti_task_sim.event_protocol import EventTaskProtocol
from kaiti_task_sim.event_replay_cases import cases
from kaiti_task_sim.event_replay_validation import audit,check_expected
from run_task_level_simulation import protected_hashes


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out',type=Path)
    args=ap.parse_args()
    out=args.out or ROOT/'outputs/event_task_protocol'/datetime.now().strftime('%Y-%m-%d_%H%M%S_%f')
    out.mkdir(parents=True,exist_ok=False)
    before=protected_hashes()
    # Also protect all pre-existing independent simulator files.
    extra=['src/kaiti_task_sim/'+name for name in ['__init__.py','planner.py','engine.py','scenarios.py','artifacts.py']]
    before.update({name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in extra})
    source=out/'source';source.mkdir()
    for p in [Path(__file__),*sorted((ROOT/'src/kaiti_task_sim').glob('event_*.py'))]:shutil.copy2(p,source/p.name)
    summary=dict(schema='event-task/v1',python=platform.python_version(),command=sys.argv,
                 position_ttl=10.,supply=[6.,4.],all_passed=True,cases=[],protected_before=before,
                 source_hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in source.iterdir()})
    rows=[]
    for case in cases():
        protocol=EventTaskProtocol();previous=None;records=[];checks=0;errors=[]
        for idx,entry in enumerate(case['steps']):
            result=protocol.apply(entry['message']);view=protocol.planning_view()
            invariant=audit(result['snapshot'],view,previous,protocol.position_ttl)
            expected=check_expected(result,view,entry['expect'],previous)
            checks+=invariant['checks']+expected['checks'];errors+=invariant['errors']+expected['errors']
            records.append(dict(index=idx,input=entry['message'],expected=entry['expect'],result=result,
                                planning_view=view,invariants=invariant,expectation_check=expected))
            for op in result['operations']:
                task=result['snapshot']['tasks'][op['task_id']]
                rows.append(dict(case=case['name'],step=idx,time=entry['message']['at'],decision=result['decision'],
                    task_id=task['task_id'],role=task['role'],operation=op['operation'],state=task['state'],
                    revision=task['revision'],attempt=task['attempt'],target=json.dumps(task['target']),
                    blockers=','.join(task['blockers']),world_revision=result['snapshot']['world_revision']))
            previous=result['snapshot']
        (out/(case['name']+'.json')).write_text(json.dumps(records,indent=2,allow_nan=False))
        item=dict(name=case['name'],steps=len(records),checks=checks,passed=not errors,errors=errors,
                  final_event=protocol.event,final_tasks={t['role']:t['state'] for t in protocol.tasks.values()})
        summary['cases'].append(item);summary['all_passed'] &= not errors
        print(case['name'],len(records),'steps',checks,'checks','PASS' if not errors else errors,flush=True)
    after=protected_hashes();after.update({name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in extra})
    summary.update(protected_after=after,protected_unchanged=before==after,
                   total_steps=sum(c['steps'] for c in summary['cases']),total_checks=sum(c['checks'] for c in summary['cases']))
    summary['all_passed'] &= before==after
    (out/'summary.json').write_text(json.dumps(summary,indent=2,allow_nan=False))
    with (out/'task_timeline.csv').open('w') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    print('OUTPUT',out,'ALL_PASSED',summary['all_passed'])
    return 0 if summary['all_passed'] else 1


if __name__=='__main__':raise SystemExit(main())
