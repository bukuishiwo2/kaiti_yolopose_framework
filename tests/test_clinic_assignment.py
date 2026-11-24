"""Focused offline allocation contract tests; no ROS, Gazebo or old S1."""
from copy import deepcopy
import importlib.util
from pathlib import Path
import sys
import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
spec=importlib.util.spec_from_file_location('allocation_bench',ROOT/'scripts/benchmark_clinic_assignment.py')
bench=importlib.util.module_from_spec(spec);spec.loader.exec_module(bench)
ca=bench.ca
pytestmark=pytest.mark.skipif(not (ca.WORKSPACE/'verification/visual_bed_2026-11-18_d1/bed_before_pickup_04/02_response/problem.json').is_file(),
                             reason='historical Clinic execution snapshots are not part of a clean repository checkout')


def test_hard_owner_conflict_cannot_be_overwritten_by_policy():
    p=bench.make_case('monitor_load',0,7);p['hard_owners']['C0_r1_W2']='r3'
    assert ca.domains(p,'B0')['C0_r1_W2']==[]
    assert ca.domains(p,'B3')['C0_r1_W2']==['r3']


def test_capability_and_qualification_intersect():
    p=bench.make_case('control_response',0,0)
    assert ca.domains(p,'B3')['E1_monitor']==['r1']
    p['allowed_robots']['E1_monitor']=['r2']
    assert ca.domains(p,'B3')['E1_monitor']==[]


def test_nominal_reference_is_not_an_accepted_plan():
    p=bench.make_case('ready',0,7);q=ca.greedy(p)
    assert q.get('plan'),q
    assert p['reference']['owners']=={}
    assert ca.parts(p,q['plan'])['owner']==0.
    assert ca.parts(p,q['plan'])['shift']==0.


def test_accepted_shift_and_owner_are_charged_only_to_accepted_set():
    p=bench.make_case('ready',0,7);q=ca.greedy(p);plan=q['plan'];j='C0_r1_W2'
    p['reference']['owners']={j:next(r for r in p['robots'] if r!=plan['owners'][j])}
    p['reference']['starts']={j:plan['starts'][j]-10.}
    assert ca.parts(p,plan)['owner']==2.
    assert abs(ca.parts(p,plan)['shift']-.5)<1e-8


def test_monitor_covers_delivery_and_courier_is_same_robot():
    p=bench.make_case('ready',0,7);plan=ca.greedy(p)['plan']
    assert plan['owners']['E1_pickup']==plan['owners']['E1_deliver']!=plan['owners']['E1_monitor']
    assert plan['finishes']['E1_monitor']>=plan['finishes']['E1_deliver']+4.
    bad=deepcopy(plan);bad['finishes']['E1_monitor']=bad['finishes']['E1_deliver']-1.
    assert not ca.validate(p,bad,'B3')['passed']


def test_greedy_failure_never_falls_back_to_milp():
    p=bench.make_case('hard',1,7);q=ca.greedy(p)
    assert q['status']=='GREEDY_NO_FEASIBLE_INSERTION' and 'plan' not in q


def test_mipstart_satisfies_complete_native_model_and_shared_objective():
    p=bench.make_case('ready',0,7);q=ca.greedy(p,'B3');tpl,m,v=ca.model(p,'B3')
    values,residual=ca.warm_values(p,tpl,m,q['plan'])
    assert residual<1e-6
    for x in m.variables():x.setInitialValue(values[x.name])
    a,_=ca.native()
    assert abs(float(a.b.pulp.value(m.objective))-q['objective'])<1e-6


def test_busy_extension_keeps_original_source_and_never_releases_prefix():
    p=bench.make_case('busy',1,7);q=ca.greedy(p)
    assert q.get('plan'),q
    assert p['robots']['r1']['ready']==p['immutable_projection']['r1']['ready']+160.
    pre={j for x in p['prefixes'].values() for j in x['jobs']}
    assert not pre.intersection(p['tasks'])
    bad=deepcopy(p);bad['robots']['r1']['ready']=0.
    assert not ca.validate(bad,q['plan'],'B3')['passed']


def test_frozen_compiler_does_not_slide_release_or_deadline():
    ca.native();import bed_contract;import dense_tasks
    config=bed_contract.config()
    task=dict(task_id='E1:verify',role='verify',generated_at=43.87,
        capabilities=['move','camera'],target=dict(frame='map',xy=config['anchors']['V1'][:2]),
        completion_dependencies=[],revision=1,attempt=1)
    clocks=dict(candidate_at=43.87,confirmed_at=None,task_planning_release={'E1:verify':43.87})
    first=ca.compile_frozen(dict(tasks=[task]),44.,config,'A',dense_tasks.phases,clocks)
    late=ca.compile_frozen(dict(tasks=[task]),144.,config,'A',dense_tasks.phases,clocks)
    assert first==late
    assert late['E1_verify']['release']==43.87
    assert late['E1_verify']['start_deadline']==403.87


def test_generator_is_paired_deterministic_and_never_authorizes_execution():
    p=bench.make_case('region',1,113)
    assert p==bench.make_case('region',1,113)
    assert p['tasks']['E1_monitor']['anchor']=='CDL'
    assert p['tasks']['E1_pickup']['anchor']=='G1'
    assert not p['physical_execution_authorized']
    assert all(not t['execution_authorized'] for t in p['tasks'].values())
