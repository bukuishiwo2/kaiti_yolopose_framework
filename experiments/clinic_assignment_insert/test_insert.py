"""Narrow tests for the new offline experiment, without old S1/Gazebo."""
from copy import deepcopy
import importlib.util
from pathlib import Path
import sys
import pytest
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE))
import adapter as a
pytestmark=pytest.mark.skipif(not (a.base.WORKSPACE/'runs/dense_loop_a13/result.json').is_file(),
                             reason='historical accepted Clinic plans are not part of a clean repository checkout')
spec=importlib.util.spec_from_file_location('insert_run',HERE/'run.py');run=importlib.util.module_from_spec(spec);spec.loader.exec_module(run)

@pytest.fixture(scope='module')
def p(tmp_path_factory):
    folder=tmp_path_factory.mktemp('accepted-insert')
    prov=run.extract('dense_loop_a13',folder)
    return run.make_case('dense_loop_a13',prov,'02_response'),prov


def test_reference_has_actual_trace_commit_before_candidate(p):
    case,prov=p
    assert prov['reference_kind']=='HISTORICALLY_OBSERVED_PLAN_COMMIT'
    assert prov['accepted_at']<case['clocks']['candidate_at']
    assert prov['initial_full_validation']['passed']
    assert prov['accepted_trace_line']==8
    assert len(prov['accepted_plan']['owners'])==9
    assert 'NOT visual' in prov['historical_event_origin']


def test_issued_prefix_and_completed_not_released_into_suffix(p):
    case,prov=p;part=case['task_partition']
    assert set(part['issued_prefix']).isdisjoint(case['tasks'])
    assert set(part['completed']).isdisjoint(case['tasks'])
    assert set(case['accepted_reference']['owners'])==set(part['unissued_suffix'])
    for j,s in case['accepted_reference']['starts'].items():assert s==prov['accepted_plan']['starts'][j]
    assert all(s>0 for s in case['reference']['starts'].values())
    assert part['issued_prefix']==['C0_r2_W2']


def test_common_model_exactly_identical_across_two_by_two(p):
    case,_=p
    assert len({a.common_model_signature(case,m) for m in ('F00','F01','F10','F11')})==1


def test_third_factor_adds_only_three_business_rows(p):
    case,_=p;_,low,_=a.model(case,'F00');_,high,_=a.model(case,'F10')
    assert set(high.constraints)-set(low.constraints)=={'policy_third_'+r for r in case['robots']}
    assert set(low.constraints)-set(high.constraints)==set()
    assert str(low.objective)==str(high.objective)


def test_opening_factor_removes_only_owner_lock_rows(p):
    case,_=p;_,limited,_=a.model(case,'F10');_,joint,_=a.model(case,'F11')
    removed=set(limited.constraints)-set(joint.constraints)
    assert removed and all(n.startswith('policy_owner_') for n in removed)
    assert set(joint.constraints)-set(limited.constraints)==set()
    assert str(limited.objective)==str(joint.objective)


def test_policy_uses_accepted_owner_not_nominal_fallback(p):
    case,_=p;case=deepcopy(case);j='C0_r1_W3';owner=case['accepted_reference']['owners'][j]
    case['nominal_owners'][j]='r3'
    assert a.domains(case,'F10')[j]==[owner]


def test_real_accepted_shift_charged_once_and_reference_erasure_is_explicit(p):
    case,prov=p;q=a.greedy(case,'B1');assert q.get('plan'),q
    erased=run.make_case('dense_loop_a13',prov,'02_response',reference_cost=False)
    plan=q['plan'];c=a.base.parts(case,plan);e=a.base.parts(erased,plan)
    assert c['shift']>0 and e['shift']==0 and e['owner']==0
    assert abs(sum(c.values())-sum(e.values())-c['shift']-c['owner'])<1e-6
    assert a.metrics(case,plan)['accepted_time_shift']==a.metrics(erased,plan)['accepted_time_shift']>0
    assert erased['accepted_reference']==case['accepted_reference']


def test_relaxed_solution_cannot_be_presented_as_business_legal(p):
    case,_=p;routes=deepcopy(case['accepted_reference']['routes'])
    routes['r3'].insert(0,'E1_monitor');routes['r2'][0:0]=['E1_pickup','E1_deliver']
    plan,error=a.base.schedule_routes(case,routes);assert plan,error
    assert a.validate(case,plan,'F01')['passed']
    strict=a.validate(case,plan,'F11')
    assert not strict['passed'] and not strict['business_contract_satisfied']
    assert not a.validate(case,plan,'F01')['execution_authorized']


def test_greedy_empty_role_domain_fails_without_solver_fallback(p):
    case,_=p;case=deepcopy(case);case['allowed_robots']['E1_monitor']=[]
    q=a.greedy(case,'B1');assert q['status']=='GREEDY_NO_FEASIBLE_INSERTION' and 'plan' not in q


def test_warm_start_remains_complete_and_valid_with_real_accepted_reference(p):
    case,_=p;q=a.greedy(case,'F11');assert q.get('plan'),q
    tpl,m,_=a.model(case,'F11');values,residual=a.warm_values(case,tpl,m,q['plan'])
    assert residual<1e-6
    for v in m.variables():v.setInitialValue(values[v.name])
    native,_=a.native();assert abs(native.b.pulp.value(m.objective)-q['objective'])<1e-6


def test_all_scenarios_explicit_and_do_not_release_saved_sources(p):
    _,prov=p
    for variant in run.PROFILES:
        c=run.make_case('dense_loop_a13',prov,'02_response',variant)
        assert c['sample_unit']['scenario_kind']=='SAVED_STATE_PLUS_COUNTERFACTUAL_EVENT_INSERTION'
        assert c['accepted_reference']==p[0]['accepted_reference']
        for r,v in c['immutable_projection'].items():
            assert c['robots'][r]['source_anchor']==v['source_anchor'] and c['robots'][r]['ready']>=v['ready']
        assert not c['physical_execution_authorized']
