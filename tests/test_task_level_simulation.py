"""Behavioral regressions for the independent DES, not ROS integration tests."""
from copy import deepcopy
from pathlib import Path
import sys
from time import perf_counter
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from kaiti_task_sim.scenarios import routine,TaskFactory
from kaiti_task_sim.planner import Solver,validate
from kaiti_task_sim.engine import Simulation


@pytest.fixture(scope='module')
def experiment(tmp_path_factory):
    out=tmp_path_factory.mktemp('task_des');p=routine(7)
    initial=Solver(out/'initial').solve(p,dict(free=list(p['tasks']),freeze_time=False),'monolithic',perf_counter()+20)
    assert initial['status']=='OPTIMAL'
    runs={policy:Simulation(p,initial['plan'],out/policy,policy,budget=20).execute()
          for policy in ('full_replan','local_repair','candidate')}
    return p,initial,runs,out


def test_seed_and_factory_extensions():
    assert routine(7)==routine(7)
    assert routine(7)!=routine(19)
    f=TaskFactory();tasks,events=f.fall('X',8,extensions=['guide','safety_zone'])
    assert len(tasks)==5 and tasks['X_guide']['dependencies']==['X_zone']
    assert tasks['X_pickup']['dependencies']==['X_zone']
    assert tasks['X_deliver']['dependencies']==['X_pickup']
    assert f.fall('X',9)==({},{})
    assert all(t['event_id']=='X' for t in tasks.values())
    assert events['X']['safety_region']==[1.4,.4,2.6,1.6]
    assert set(tasks['X_guide']['capabilities']).issubset(routine(7)['robots']['R2']['capabilities'])


def test_no_future_tasks_and_shared_snapshot(experiment):
    p,initial,runs,_=experiment
    assert not p['events'] and all(j.startswith('N') for j in initial['plan']['owners'])
    assert len({r['snapshot_sha256'] for r in runs.values()})==1
    assert all(r['snapshot']['reference']['owners']=={'N3':'R0','N4':'R1','N5':'R1'} for r in runs.values())
    for r in runs.values():
        assert all(e['time']>=8 for e in r['trace'] if e.get('task','') and str(e['task']).startswith('E1'))


def test_end_to_end_execution_and_immutable_prefix(experiment):
    _,initial,runs,_=experiment
    for r in runs.values():
        assert r['status']=='COMPLETE' and r['execution_audit']['passed']
        assert r['repair']['validation']['passed'] and len(r['records'])==9
        assert r['records']['N3']['owner']!='R0'
        for j in ('N0','N1','N2'):
            assert r['records'][j]==dict(owner=initial['plan']['owners'][j],start=0,finish=initial['plan']['finishes'][j])
        m,p,d=(r['records']['E1_'+j] for j in ('monitor','pickup','deliver'))
        assert m['start']<=p['start'] and m['finish']>=d['finish']
        assert p['owner']==d['owner']!=m['owner']


def test_scope_expansion_fallback_and_same_cost(experiment):
    _,_,runs,_=experiment
    local=runs['local_repair']['repair'];candidate=runs['candidate']['repair'];full=runs['full_replan']['repair']
    assert local['attempts'][0]['status']=='INFEASIBLE' and local['fallback_used']
    assert candidate['attempts'][0]['status']=='INFEASIBLE' and candidate['scope_expansions']==1
    assert abs(full['objective']-local['objective'])<1e-6
    assert abs(full['objective']-candidate['objective'])<1e-6
    assert candidate['attempts'][-1]['trace'][-1]['gap']<=1e-6


@pytest.mark.parametrize('fault,label',[('resource','resource_'),('energy','energy'),('dependency','dependency'),('roles','distinct_roles'),('cost','objective')])
def test_independent_validation_rejects_corruption(experiment,fault,label):
    _,_,runs,_=experiment;r=runs['full_replan'];p=deepcopy(r['snapshot']);plan=deepcopy(r['repair']['plan'])
    claimed=None
    if fault=='resource':plan['starts']['N4']=plan['starts']['E1_pickup'];plan['finishes']['N4']=plan['starts']['N4']+p['tasks']['N4']['duration']
    if fault=='energy':
        for robot in p['robots'].values():robot['energy']=robot['minimum']
    if fault=='dependency':plan['starts']['E1_deliver']=plan['starts']['E1_pickup']
    if fault=='roles':plan['owners']['E1_monitor']=plan['owners']['E1_pickup']
    if fault=='cost':claimed=r['repair']['objective']+1
    audit=validate(p,plan,dict(free=list(p['tasks']),freeze_time=False),claimed)
    assert not audit['passed'] and any(label in e['name'] for e in audit['errors'])


def test_unknown_budget_does_not_execute_old_plan_as_success(experiment):
    p,initial,_,out=experiment
    run=Simulation(p,initial['plan'],out/'unknown','candidate',budget=0).execute()
    assert run['status']=='FAILED' and run['repair']['status']=='UNKNOWN_BUDGET'
    assert not run['execution_audit']['passed']
    assert not any(j.startswith('E1') for j in run['records'])


def test_travel_and_wait_snapshot_projection(experiment):
    p,initial,_,out=experiment
    sim=Simulation(p,initial['plan'],out/'projection');sim.now=8
    sim.active['R0']=dict(kind='travel',end=10,position=[1,1],rate=.2,task=None)
    sim.state['R0']['energy']=50
    sim.active['R1']=dict(kind='wait',end=12,position=[8,0],rate=.02,task=None)
    snap=sim.make_snapshot()
    assert snap['robots']['R0']['ready']==10 and snap['robots']['R0']['energy']==49.6
    assert snap['robots']['R0']['position']==[1,1]
    assert snap['robots']['R1']['ready']==8 and sim.active['R1'] is None
