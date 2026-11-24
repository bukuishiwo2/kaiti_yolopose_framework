#!/usr/bin/env python3
"""Static scientific summary of all attempted cases, with censored failures."""
import argparse
import json
from pathlib import Path
import statistics


def plot(audit,out,budget):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    import numpy as np
    out.mkdir(parents=True,exist_ok=False)
    s=json.loads((audit/'summary.json').read_text());rows=json.loads((audit/'rows_extended.json').read_text())
    policies=['fixed_structure','fixed_owner','full_warm','local_current','local_no_seed_gate']
    labels=['Fixed structure','Fixed owner','Full warm','Deployed local','Diagnostic local']
    colors=dict(T='#2878b5',L='#2a9d60',P='#e39b31',G='#9955aa')
    fig,axes=plt.subplots(1,3,figsize=(16,4.9),gridspec_kw={'width_ratios':[1.2,1,1]})
    x=np.arange(4);width=.15
    palette=['#9ba5b0','#697a8a','#2878b5','#dc8655','#269d81']
    for idx,(policy,label,color) in enumerate(zip(policies,labels,palette)):
        rates=[s['stats'][f][policy]['successes']/s['stats'][f][policy]['cases'] for f in 'TLPG']
        axes[0].bar(x+(idx-2)*width,rates,width,label=label,color=color)
    axes[0].set(xticks=x,xticklabels=list('TLPG'),ylim=(0,1.5),yticks=np.arange(0,1.01,.2),ylabel='Validated recovery fraction',title='All instances retained (5 s per call)')
    axes[0].legend(fontsize=8,loc='upper right')
    grouped={}
    for q in rows:grouped.setdefault(q['id'],{})[q['policy']]=q
    for group in grouped.values():
        full=group['full_warm'];local=group['local_no_seed_gate'];color=colors[full['family']]
        tx=full['first_validated']['seconds'] if full['valid'] else budget
        ty=local['first_validated']['seconds'] if local['valid'] else budget
        axes[1].scatter(tx,ty,color=color,s=34,marker='o' if full['valid'] and local['valid'] else 'x',alpha=.8)
    axes[1].plot([.01,budget*1.2],[.01,budget*1.2],ls='--',color='#777',lw=1)
    axes[1].axvline(budget,color='#aaa',lw=.7);axes[1].axhline(budget,color='#aaa',lw=.7)
    axes[1].set(xscale='log',yscale='log',xlim=(.01,budget*1.3),ylim=(.01,budget*1.3),xlabel='Full: first validated availability / s',ylabel='Diagnostic: first validated availability / s',title='x = failure/timeout censored at budget')
    axes[1].legend(handles=[Line2D([],[],marker='o',linestyle='',color=c,label=f) for f,c in colors.items()],fontsize=8,loc='upper left')
    ratios=[];changed=[]
    for family in 'TLPG':
        rr=[q for q in rows if q['family']==family and q['policy']=='local_no_seed_gate']
        ratios.append(statistics.median(q['max_attempted_ratio'] for q in rr))
        valid=[q for q in rr if q['valid']]
        changed.append(statistics.median(q['owner_changes']/q['tasks'] for q in valid) if valid else 0.)
    axes[2].bar(x-.18,ratios,.36,color='#269d81',label='Maximum attempted free scope')
    axes[2].bar(x+.18,changed,.36,color='#6a74a3',label='Actual reassignment (successes)')
    axes[2].set(xticks=x,xticklabels=list('TLPG'),ylim=(0,1.1),ylabel='Fraction of tasks (median)',title='Temporal closure != structural change')
    axes[2].legend(fontsize=8,loc='upper left')
    for ax in axes:ax.grid(axis='y',alpha=.15);ax.set_axisbelow(True)
    fig.suptitle('Independent synthetic task-level mechanism suite — not physical navigation trials',fontsize=13)
    fig.text(.01,.01,'T: retiming sufficient   L: reassignment necessary   P: temporal propagation   G: backup coupling / expansion. Diagnostic local is NOT deployed local.',fontsize=9)
    fig.tight_layout(rect=(0,.035,1,.94));fig.savefig(out/'methods.png',dpi=160);fig.savefig(out/'methods.svg');plt.close(fig)
    (out/'metadata.json').write_text(json.dumps(dict(source=str(audit),budget=budget,censoring='Failed/no-incumbent calls plotted at budget with x; not imputed successful solve times',physical_execution=False),indent=2))


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--audit',type=Path,required=True);ap.add_argument('--out',type=Path,required=True);ap.add_argument('--budget',type=float,default=5.)
    a=ap.parse_args();plot(a.audit,a.out,a.budget)
