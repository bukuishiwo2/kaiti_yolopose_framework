#!/usr/bin/env python3
"""Run isolated task-level DES; never imports or mutates the production planner."""
from __future__ import annotations
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import platform
import shutil
import sys
from time import perf_counter

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from kaiti_task_sim.scenarios import routine
from kaiti_task_sim.planner import Solver
from kaiti_task_sim.engine import Simulation
from kaiti_task_sim.artifacts import comparisons,metrics


def protected_hashes():
    paths=list((ROOT/'src/kaiti_planning').rglob('*.py'))+list((ROOT/'ros2_ws/src').rglob('*.py'))
    paths+=list((ROOT/'configs').glob('planner*.yaml'))+list((ROOT/'configs').glob('public_space_v3*.yaml'))
    paths+=list((ROOT/'scripts').glob('verify*repair_equivalence.py'))
    return {str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths)}


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--seeds',type=int,nargs='+',default=[7,19,43])
    ap.add_argument('--variants',nargs='+',choices=['reassignment_required','retiming_allowed'],default=['reassignment_required','retiming_allowed'])
    ap.add_argument('--budget',type=float,default=30,help='Shared wall-second budget per policy, including all attempts')
    ap.add_argument('--out',type=Path)
    ap.add_argument('--no-plots',action='store_true')
    args=ap.parse_args()
    if args.budget<=0:ap.error('budget must be positive')
    out=args.out or ROOT/'outputs/task_level_simulation'/datetime.now().strftime('%Y-%m-%d_%H%M%S_%f')
    out.mkdir(parents=True,exist_ok=False)
    before=protected_hashes()
    import pulp,scipy,numpy
    summary=dict(command=sys.argv,python=platform.python_version(),pulp=pulp.__version__,scipy=scipy.__version__,numpy=numpy.__version__,
                 budget=args.budget,protected_before=before,experiments=[],all_passed=True,
                 semantics='synchronous planning pauses virtual time; deterministic travel; standby after return uses zero energy')
    source_dir=out/'source';source_dir.mkdir()
    for source in [Path(__file__),*sorted((ROOT/'src/kaiti_task_sim').glob('*.py'))]:
        shutil.copy2(source,source_dir/source.name)
    for variant in args.variants:
        for seed in args.seeds:
            case=out/f'{variant}_seed{seed}';case.mkdir()
            p=routine(seed,variant)
            (case/'routine_input.json').write_text(json.dumps(p,indent=2))
            initial=Solver(case/'initial_solver').solve(p,{'free':list(p['tasks']),'freeze_time':False},'monolithic',perf_counter()+args.budget)
            (case/'initial_solve.json').write_text(json.dumps(initial,indent=2))
            if initial['status']!='OPTIMAL':raise RuntimeError(f'Initial solve: {initial["status"]}')
            baseline=Simulation(p,initial['plan'],case/'no_fall').execute()
            runs={}
            for policy in ('full_replan','local_repair','candidate'):
                run=Simulation(p,initial['plan'],case/policy,policy,budget=args.budget).execute();runs[policy]=run
                print(variant,seed,policy,json.dumps(metrics(run)),flush=True)
            # Offline same-scope cross-check: excluded from policy runtime.
            candidate=runs['candidate'];scope=candidate['repair']['attempts'][-1]['scope']
            cross=Solver(case/'offline_same_scope').solve(candidate['snapshot'],scope,'monolithic',perf_counter()+args.budget)
            (case/'offline_same_scope.json').write_text(json.dumps(cross,indent=2))
            eq=cross['status']==candidate['repair']['status'] and (cross['status']=='INFEASIBLE' or
                  (cross['status']=='OPTIMAL' and abs(cross['objective']-candidate['repair']['objective'])<=1e-6))
            hashes={r['snapshot_sha256'] for r in runs.values()}
            entry=dict(variant=variant,seed=seed,metrics={k:metrics(v) for k,v in runs.items()},
                       same_snapshot=len(hashes)==1,baseline_audit=baseline['execution_audit'],
                       offline_same_scope=dict(status=cross['status'],passed=eq,objective=cross.get('objective')))
            passed=eq and len(hashes)==1 and baseline['execution_audit']['passed'] and all(v['execution_audit']['passed'] and v['status']=='COMPLETE' for v in runs.values())
            entry['passed']=passed;summary['all_passed'] &= passed;summary['experiments'].append(entry)
            if not args.no_plots:comparisons(p,baseline,runs,case)
            (out/'summary.json').write_text(json.dumps(summary,indent=2))
    after=protected_hashes();summary.update(protected_after=after,protected_unchanged=before==after)
    summary['all_passed'] &= before==after
    (out/'summary.json').write_text(json.dumps(summary,indent=2))
    print('OUTPUT',out,flush=True)
    return 0 if summary['all_passed'] else 1


if __name__=='__main__':raise SystemExit(main())
