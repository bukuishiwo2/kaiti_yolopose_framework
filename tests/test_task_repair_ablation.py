"""Same complete expansion workflow, backend isolation, and timing schedule."""
from collections import Counter
from copy import deepcopy
from pathlib import Path
import sys
from time import perf_counter
import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'scripts')]
from kaiti_task_sim import planner
from kaiti_task_sim.scenarios import routine
from kaiti_task_sim.engine import Simulation
from benchmark_task_repair_ablation import POLICIES,compare_pair,make_schedule


def test_counterbalanced_reproducible_schedule():
    cases=[(v,s) for v in ['reassignment_required','retiming_allowed'] for s in [7,19,43]]
    blocks=make_schedule(cases,8,20261109)
    assert blocks==make_schedule(cases,8,20261109) and len(blocks)==48
    for variant,seed in cases:
        subset=[b for b in blocks if (b['variant'],b['seed'])==(variant,seed)]
        assert len(subset)==8
        for policy in POLICIES:
            assert Counter(b['policies'].index(policy) for b in subset)=={0:2,1:2,2:2,3:2}
        transitions=Counter((a,b) for block in subset for a,b in zip(block['policies'],block['policies'][1:]))
        assert len(transitions)==12 and set(transitions.values())=={2}


@pytest.fixture(scope='module',params=['reassignment_required','retiming_allowed'])
def paired_run(request,tmp_path_factory):
    out=tmp_path_factory.mktemp(request.param);p=routine(7,request.param)
    initial=planner.Solver(out/'initial').solve(p,dict(free=list(p['tasks']),freeze_time=False),'monolithic',perf_counter()+20)
    runs={policy:Simulation(p,initial['plan'],out/policy,policy,budget=20).execute() for policy in ['retained_milp','candidate']}
    return request.param,runs


def test_complete_workflow_equivalence(paired_run):
    variant,runs=paired_run;mono,decomp=(runs[p] for p in ['retained_milp','candidate'])
    assert compare_pair(mono,decomp)['passed']
    assert mono['execution_audit']['passed'] and decomp['execution_audit']['passed']
    assert [a['kind'] for a in mono['repair']['attempts']]==['monolithic']*len(mono['repair']['attempts'])
    assert all(a['kind']=='decomposition' for a in decomp['repair']['attempts'])
    stages_a=planner.policy_stages(mono['snapshot'],'retained_milp')
    stages_b=planner.policy_stages(mono['snapshot'],'candidate')
    assert stages_a==stages_b
    expected=1 if variant=='reassignment_required' else 0
    assert mono['repair']['scope_expansions']==expected
    assert len(mono['repair']['attempts'])==expected+1
    assert not mono['repair']['fallback_used']
    for r in runs.values():
        assert r['repair']['planning_seconds']>=sum(a['timing']['total'] for a in r['repair']['attempts'])


def test_pair_audit_rejects_changed_workflow(paired_run):
    _,runs=paired_run;left=deepcopy(runs['retained_milp']);right=deepcopy(runs['candidate'])
    right['repair']['attempts'][0]['scope']['freeze_time']=True
    audit=compare_pair(left,right)
    assert not audit['passed'] and not audit['same_attempt_scopes']


@pytest.mark.parametrize('policy',['candidate','retained_milp'])
def test_single_deadline_across_expansion_and_unknown_stops(monkeypatch,tmp_path,policy):
    p=routine(7);p['reference']=dict(owners={'N3':'R0'},starts={'N3':20},routes={'R0':['N3'],'R1':[],'R2':[]})
    calls=[]
    class FakeSolver:
        def __init__(self,out):pass
        def solve(self,p,scope,kind,deadline):
            calls.append((deepcopy(scope),kind,deadline))
            return dict(status='INFEASIBLE' if len(calls)==1 else 'UNKNOWN_BUDGET')
    monkeypatch.setattr(planner,'Solver',FakeSolver)
    result=planner.replan(p,policy,tmp_path,30)
    assert result['status']=='UNKNOWN_BUDGET' and len(calls)==2
    assert calls[0][2]==calls[1][2]
    assert all(c[1]==('decomposition' if policy=='candidate' else 'monolithic') for c in calls)
