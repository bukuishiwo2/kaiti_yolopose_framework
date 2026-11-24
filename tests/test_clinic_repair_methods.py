"""Offline mechanism checks; no ROS/world/current execution artifacts changed."""
import importlib.util
import json
from pathlib import Path
from copy import deepcopy
import pytest

path=Path(__file__).resolve().parents[1]/'scripts/benchmark_clinic_repair_methods.py'
spec=importlib.util.spec_from_file_location('clinic_methods',path)
study=importlib.util.module_from_spec(spec);spec.loader.exec_module(study)


@pytest.mark.parametrize('family',study.FAMILIES)
@pytest.mark.parametrize('count',[6,12,24])
def test_old_plan_valid_before_and_invalid_after(family,count):
    before,after,design=study.make_case(family,101,count)
    assert design['baseline_validation']['passed']
    assert not design['old_invalid']['passed']
    assert after['external_commitments']==before['external_commitments']
    assert after['hard_owners']==before['hard_owners']
    assert not design['physical_navigation_qualified']


@pytest.mark.parametrize('family',study.FAMILIES)
def test_independent_seed_changes_optimization_input_not_just_metadata(family):
    inputs=[]
    for seed in [101,211,307]:
        _,p,_=study.make_case(family,seed,12)
        p.pop('external_commitments');p.pop('commitment_basis')
        inputs.append(json.dumps(p,sort_keys=True))
    assert len(set(inputs))==3


def test_loss_of_lift_proves_fixed_ownership_impossible():
    for family in ['L','G']:
        _,p,_=study.make_case(family,7,6)
        impossible=[j for j,t in p['tasks'].items() if not set(t['capabilities']).issubset(p['robots'][p['reference']['owners'][j]]['capabilities'])]
        assert len(impossible)==(1 if family=='L' else 2)
        assert all('lift' in p['tasks'][j]['capabilities'] for j in impossible)


def test_temporal_closure_can_be_global_without_assignment_need():
    _,p,d=study.make_case('P',7,12)
    assert len(d['impact']['free'])==12
    assert all(set(t['capabilities']).issubset(p['robots'][p['reference']['owners'][j]]['capabilities']) for j,t in p['tasks'].items())


def test_hard_owner_independently_checked():
    p,_,_=study.make_case('T',7,6);plan=deepcopy(p['reference']);plan['owners']['N2_0']='r1'
    result=study.validate(p,plan,dict(free=list(p['tasks']),freeze_time=False))
    assert not result['passed']
    assert any(e['name']=='hard_owner_N2_0' for e in result['errors'])


@pytest.mark.parametrize('family',study.FAMILIES)
def test_hard_owners_also_use_native_constraints_for_unchanged_legacy(family):
    _,p,_=study.make_case(family,113,12)
    for j,owner in p['hard_owners'].items():
        eligible=[r for r,v in p['robots'].items() if set(p['tasks'][j]['capabilities']).issubset(v['capabilities'])]
        assert eligible==[owner]


@pytest.mark.parametrize('family',study.FAMILIES)
@pytest.mark.parametrize('count',[6,12,18])
def test_constructive_certificate_demonstrates_post_disturbance_feasibility(family,count):
    audit_spec=importlib.util.spec_from_file_location('clinic_methods_audit',path.with_name('audit_clinic_repair_methods.py'))
    audit=importlib.util.module_from_spec(audit_spec);audit_spec.loader.exec_module(audit)
    _,problem,_=study.make_case(family,53,count)
    original=deepcopy(problem)
    certificate=audit.constructive_feasibility_witness(problem,family)
    assert certificate['passed'],certificate['validation']
    assert certificate['owner_changes']==({'T':0,'L':1,'P':0,'G':count//3}[family])
    assert problem==original
