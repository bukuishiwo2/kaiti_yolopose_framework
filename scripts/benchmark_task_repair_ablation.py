#!/usr/bin/env python3
"""Counterbalanced complete-workflow ablation; independent of production/ROS."""
from __future__ import annotations
import argparse
from collections import Counter
import csv
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import platform
from random import Random
import shutil
import statistics
import sys
from time import get_clock_info,perf_counter

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from kaiti_task_sim.scenarios import routine
from kaiti_task_sim.planner import Solver,policy_stages
from kaiti_task_sim.engine import Simulation
from kaiti_task_sim.artifacts import metrics
from run_task_level_simulation import protected_hashes

POLICIES=('full_replan','local_repair','retained_milp','candidate')
# Williams square: every policy occupies each slot once and every ordered
# within-block predecessor/successor pair occurs once in each four rounds.
WILLIAMS=((0,1,3,2),(1,2,0,3),(2,3,1,0),(3,0,2,1))


def make_schedule(cases,rounds,seed):
    rng=Random(seed);mapping=list(POLICIES);rng.shuffle(mapping);schedule=[]
    for round_id in range(rounds):
        order=list(range(len(cases)));rng.shuffle(order)
        for idx in order:
            variant,instance_seed=cases[idx]
            policies=[mapping[x] for x in WILLIAMS[(round_id+idx)%4]]
            schedule.append(dict(round=round_id+1,variant=variant,seed=instance_seed,policies=policies))
    return schedule


def describe(values):
    import numpy as np
    return dict(n=len(values),median=statistics.median(values),mean=statistics.mean(values),
                minimum=min(values),maximum=max(values),p95=float(np.percentile(values,95)))


def compare_pair(left,right):
    """Require all attempted scopes/statuses, not only final objective, to agree."""
    a,b=left['repair'],right['repair']
    statuses_a=[v['status'] for v in a['attempts']];statuses_b=[v['status'] for v in b['attempts']]
    scopes_a=[v['scope'] for v in a['attempts']];scopes_b=[v['scope'] for v in b['attempts']]
    optimal=a['status']==b['status']=='OPTIMAL'
    gap=abs(a['objective']-b['objective']) if optimal else None
    return dict(same_snapshot=left['snapshot_sha256']==right['snapshot_sha256'],
                same_attempt_scopes=scopes_a==scopes_b,same_attempt_statuses=statuses_a==statuses_b,
                same_expansions=a.get('scope_expansions')==b.get('scope_expansions'),
                objective_gap=gap,
                passed=optimal and gap<=1e-6 and scopes_a==scopes_b and statuses_a==statuses_b and
                       left['snapshot_sha256']==right['snapshot_sha256'] and
                       a.get('scope_expansions')==b.get('scope_expansions'))


def aggregate(rows,pairs):
    result={}
    for variant in sorted({r['variant'] for r in rows}):
        subset=[r for r in rows if r['variant']==variant]
        policies={}
        for policy in POLICIES:
            ps=[r for r in subset if r['policy']==policy]
            policies[policy]=dict(planning_seconds=describe([r['planning_seconds'] for r in ps]),
                simulation_wall_seconds=describe([r['simulation_wall_seconds'] for r in ps]),
                per_seed={str(seed):describe([r['planning_seconds'] for r in ps if r['seed']==seed]) for seed in sorted({r['seed'] for r in ps})},
                fallback_count=sum(r['fallback'] for r in ps),
                expansion_counts=dict(Counter(r['scope_expansions'] for r in ps)),
                statuses=dict(Counter(r['solver_status'] for r in ps)))
        paired=[p for p in pairs if p['variant']==variant]
        result[variant]=dict(policies=policies,
            full_over_retained=describe([p['full_over_retained'] for p in paired]),
            decomposition_over_retained=describe([p['decomposition_over_retained'] for p in paired]))
    return result


def plot(rows,out):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    variants=sorted({r['variant'] for r in rows})
    fig,axes=plt.subplots(1,len(variants),figsize=(12,4),squeeze=False)
    labels=['Full MILP','Local + fallback','Retained MILP','Retained + LP']
    for ax,variant in zip(axes[0],variants):
        for idx,policy in enumerate(POLICIES):
            vals=[r['planning_seconds'] for r in rows if r['variant']==variant and r['policy']==policy]
            ax.scatter([idx+(n%8-3.5)*.035 for n in range(len(vals))],vals,s=14,alpha=.6)
            ax.plot([idx-.25,idx+.25],[statistics.median(vals)]*2,color='black',linewidth=2)
        ax.set_xticks(range(4),labels,rotation=18,ha='right');ax.set_ylabel('Complete planning workflow (wall s)')
        ax.set_title(variant);ax.grid(axis='y',alpha=.2)
    fig.tight_layout();fig.savefig(out/'timing.png',dpi=160);fig.savefig(out/'timing.svg');plt.close(fig)


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--seeds',type=int,nargs='+',default=[7,19,43])
    ap.add_argument('--rounds',type=int,default=8)
    ap.add_argument('--schedule-seed',type=int,default=20261109)
    ap.add_argument('--budget',type=float,default=30)
    ap.add_argument('--out',type=Path)
    ap.add_argument('--no-plots',action='store_true')
    args=ap.parse_args()
    if args.rounds<4 or args.rounds%4:ap.error('rounds must be a positive multiple of 4 for slot balance')
    if args.budget<=0:ap.error('budget must be positive')
    if len(set(args.seeds))!=len(args.seeds):ap.error('seeds must be unique')
    out=args.out or ROOT/'outputs/task_repair_ablation'/datetime.now().strftime('%Y-%m-%d_%H%M%S_%f')
    out.mkdir(parents=True,exist_ok=False)
    before=protected_hashes();source=out/'source';source.mkdir()
    for path in [Path(__file__),ROOT/'scripts/run_task_level_simulation.py',*sorted((ROOT/'src/kaiti_task_sim').glob('*.py'))]:
        shutil.copy2(path,source/path.name)
    import pulp,scipy,numpy
    summary=dict(command=sys.argv,rounds=args.rounds,budget=args.budget,schedule_seed=args.schedule_seed,
                 environment=dict(python=platform.python_version(),platform=platform.platform(),pulp=pulp.__version__,
                   scipy=scipy.__version__,numpy=numpy.__version__,cpu_count=os.cpu_count(),load_start=os.getloadavg(),
                   timer_resolution=get_clock_info('perf_counter').resolution),
                 source_hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in source.iterdir()},
                 protected_before=before,warmups=[],runs=[],pairs=[],all_passed=True)
    cases=[(variant,seed) for variant in ('reassignment_required','retiming_allowed') for seed in args.seeds]
    fixtures={}
    # Identical initial plans generated once per input. No solution/cut/model
    # reuse across measured policies or rounds; warmups are explicitly excluded.
    for variant,seed in cases:
        case=out/f'{variant}_seed{seed}';case.mkdir();p=routine(seed,variant)
        initial=Solver(case/'initial_solver').solve(p,dict(free=list(p['tasks']),freeze_time=False),'monolithic',perf_counter()+args.budget)
        (case/'initial_solve.json').write_text(json.dumps(initial,indent=2))
        if initial['status']!='OPTIMAL':raise RuntimeError('Initial plan not proven optimal')
        fixtures[variant,seed]=(p,initial['plan'],case)
        for policy in POLICIES:
            run=Simulation(p,initial['plan'],case/'warmup'/policy,policy,budget=args.budget).execute()
            passed=run['status']=='COMPLETE' and run['execution_audit']['passed'] and run['repair'].get('validation',{}).get('passed',False)
            summary['warmups'].append(dict(variant=variant,seed=seed,policy=policy,metrics=metrics(run),passed=passed))
            summary['all_passed'] &= passed
        print('WARMUP',variant,seed,'complete',flush=True)
    schedule=make_schedule(cases,args.rounds,args.schedule_seed)
    (out/'schedule.json').write_text(json.dumps(schedule,indent=2))
    for block in schedule:
        variant,seed,round_id=block['variant'],block['seed'],block['round']
        p,initial,case=fixtures[variant,seed];runs={}
        for slot,policy in enumerate(block['policies'],1):
            begin=perf_counter();run=Simulation(p,initial,case/f'round_{round_id:02d}'/policy,policy,budget=args.budget).execute();wall=perf_counter()-begin
            runs[policy]=run
            passed=run['status']=='COMPLETE' and run['execution_audit']['passed'] and run['repair'].get('validation',{}).get('passed',False)
            row=dict(variant=variant,seed=seed,round=round_id,slot=slot,policy=policy,simulation_wall_seconds=wall,
                     snapshot_sha256=run['snapshot_sha256'],passed=passed,**metrics(run))
            summary['runs'].append(row);summary['all_passed'] &= passed
        comparison=compare_pair(runs['retained_milp'],runs['candidate'])
        full=runs['full_replan']['repair'];retained=runs['retained_milp']['repair'];decomp=runs['candidate']['repair']
        comparison.update(variant=variant,seed=seed,round=round_id,
            full_over_retained=full['planning_seconds']/retained['planning_seconds'],
            decomposition_over_retained=decomp['planning_seconds']/retained['planning_seconds'],
            full_objective_gap=abs(full.get('objective',float('inf'))-retained.get('objective',float('-inf'))),
            all_same_snapshot=len({r['snapshot_sha256'] for r in runs.values()})==1)
        # A scoped optimum must never improve on the all-free optimum; equality
        # is reported as an observation, not imposed as a general algorithm rule.
        if full['status']==retained['status']=='OPTIMAL':
            comparison['full_lower_bound_ok']=full['objective']<=retained['objective']+1e-6
        else:comparison['full_lower_bound_ok']=False
        summary['pairs'].append(comparison)
        summary['all_passed'] &= comparison['passed'] and comparison['all_same_snapshot'] and comparison['full_lower_bound_ok']
        (out/'summary.json').write_text(json.dumps(summary,indent=2))
        print('MEASURED',variant,seed,'round',round_id,'order',','.join(block['policies']),
              'retained/decomp matched',comparison['passed'],flush=True)
    after=protected_hashes();summary.update(protected_after=after,protected_unchanged=before==after,aggregate=aggregate(summary['runs'],summary['pairs']))
    summary['all_passed'] &= before==after
    summary['environment']['load_end']=os.getloadavg()
    with (out/'timings.csv').open('w') as f:
        writer=csv.DictWriter(f,fieldnames=list(summary['runs'][0]));writer.writeheader();writer.writerows(summary['runs'])
    (out/'summary.json').write_text(json.dumps(summary,indent=2))
    if not args.no_plots:plot(summary['runs'],out)
    print('OUTPUT',out,'ALL_PASSED',summary['all_passed'],flush=True)
    return 0 if summary['all_passed'] else 1


if __name__=='__main__':raise SystemExit(main())
