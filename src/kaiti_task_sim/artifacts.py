"""Static, exportable plan comparisons; no dependencies on production tooling."""
import csv
from pathlib import Path


def comparisons(problem,baseline,runs,out):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch
    out=Path(out)
    colors={'normal':'#497eb4','monitor':'#c34045','pickup':'#8059ac','deliver':'#e79a35',
            'guide':'#32946a','safety_zone':'#3dabb2'}
    panels=[('Before fall: routine plan',baseline['records'])]
    panels += [(name,run['records']) for name,run in runs.items()]
    fig,axes=plt.subplots(len(panels),1,figsize=(13,10),sharex=True)
    for ax,(name,records) in zip(axes,panels):
        for j,v in records.items():
            if 'finish' not in v:continue
            kind='normal' if j.startswith('N') else j.split('_',1)[1]
            row=list(problem['robots']).index(v['owner'])
            changed=j in baseline['records'] and v['owner']!=baseline['records'][j]['owner']
            label=j.replace('E1_','')+('*' if changed else '')
            ax.barh(row,v['finish']-v['start'],left=v['start'],height=.6,color=colors[kind],edgecolor='black',linewidth=.6)
            ax.text((v['start']+v['finish'])/2,row,label,ha='center',va='center',fontsize=8,color='white')
        ax.axvline(8,color='#b42525',linestyle='--',linewidth=1)
        ax.set_yticks(range(3),list(problem['robots']));ax.invert_yaxis()
        ax.set_title(name,loc='left',fontsize=11);ax.grid(axis='x',alpha=.2)
    axes[-1].set_xlabel('Virtual time (s); dashed line: fall at t=8; *: routine task changes robot')
    fig.legend(handles=[Patch(color=colors[k],label=k) for k in ('normal','monitor','pickup','deliver')],loc='upper right',ncol=4)
    fig.tight_layout(rect=(0,0,1,.97));fig.savefig(out/'plans.png',dpi=160);fig.savefig(out/'plans.svg');plt.close(fig)
    rows=[]
    for policy,run in runs.items():
        for j,v in run['records'].items():
            old=baseline['records'].get(j)
            status='new' if old is None else ('immutable_prefix' if old['start']<8 else
                    ('reassigned' if old['owner']!=v['owner'] else ('shifted' if abs(old['start']-v['start'])>1e-6 else 'unchanged')))
            rows.append(dict(policy=policy,task=j,status=status,old_robot=old['owner'] if old else '',
                             old_start=old['start'] if old else '',old_finish=old['finish'] if old else '',
                             new_robot=v['owner'],new_start=v['start'],new_finish=v.get('finish','')))
    if rows:
        with (out/'before_after.csv').open('w') as f:
            writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)


def metrics(run):
    repair=run['repair'];rec=run['records'];old=run['initial_plan']
    attempts=repair['attempts'] if repair else []
    result=dict(status=run['status'],execution_passed=run['execution_audit']['passed'],
                completed=sum('finish' in x for x in rec.values()),makespan=run['makespan'],
                min_energy=min(r['minimum_energy'] for r in run['state'].values()))
    if repair:
        result.update(solver_status=repair['status'],objective=repair.get('objective'),
                      planning_seconds=repair['planning_seconds'],fallback=repair.get('fallback_used',False),
                      scope_expansions=repair.get('scope_expansions',0),attempts=len(attempts),
                      cbc_seconds=sum(a['timing']['cbc'] for a in attempts),
                      external_lp_seconds=sum(a['timing']['external_lp'] for a in attempts),
                      decomposition_iterations=sum(len(a['trace']) for a in attempts),
                      response_seconds=rec['E1_monitor']['start']-8 if 'E1_monitor' in rec else None,
                      delivery_seconds=rec['E1_deliver']['finish']-8 if 'finish' in rec.get('E1_deliver',{}) else None,
                      reassigned=sum(rec[j]['owner']!=old['owners'][j] for j in old['owners'] if old['starts'][j]>=8 and j in rec),
                      total_start_shift=sum(abs(rec[j]['start']-old['starts'][j]) for j in old['owners'] if old['starts'][j]>=8 and j in rec))
    return result
