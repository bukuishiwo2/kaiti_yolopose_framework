"""Read-only explanation contracts. Real-run checks skip outside the evidence workspace."""
from pathlib import Path
import os
import pytest
from kaiti_review.explanations import task_dictionary, metadata, explain, research_catalog
from kaiti_review.data import load_run

CLINIC_WORKSPACE=Path(os.environ.get('CLINIC_WORKSPACE','/home/yhc/clinic_planning_ws')).expanduser()


def test_no_semantics_inferred_from_identifier():
    p={"records":[{"job_id":"C9_r3_W2","robot":"r1","role":"patrol"}],"plan_versions":[]}
    t=task_dictionary({},p,[])["C9_r3_W2"]
    assert t["nominal_owner"] is None
    assert t["batch"] is None and t["waypoint"] is None
    assert t["actual_executor"] == "r1"
    assert "第" not in t["display_name_zh"]


def test_metadata_never_guesses_policy_from_folder():
    p={"records":[],"events":[],"planning_records":[],"semantic_events":[]}
    t=metadata({},p,"fall_local_full_unified_bed", "fixture")
    assert t["strategy_raw"] is None
    assert t["scenario_type"] == "未分类／待核实"
    assert not t["debug_confirmed"]
    assert t["repeat_index"] is None


def test_explicit_catalog_separates_primary_runs_from_supporting_studies():
    c=research_catalog()
    assert len(c["primary"]) == 5
    assert len(c["supporting"]) == 3
    assert all(item.get("display_name_zh") and item.get("roles") and item.get("scene")
               and item.get("task_plan") and item.get("event_insertion")
               and item.get("validates") and item.get("evidence_level") for item in c["primary"]+c["supporting"])
    assert next(item for item in c["primary"] if item["key"]=="semantic_positive")["run_id"].endswith("positive_02")
    assert not any(item.get("run_id") for item in c["supporting"])


def test_explicit_null_event_space_is_unknown(tmp_path):
    p={"records":[],"events":[],"plan_versions":[],"planning_records":[],"semantic_events":[],"semantic_final":{"space":None},"anchors":{},"planned_paths":[]}
    e=explain(tmp_path,"fixture",tmp_path,{},p,None)
    assert e["qualification_fields"]["human_space_valid"] is None
    assert e["path_report"]["grid_sandbox_connected"] is False


@pytest.fixture(scope="module")
def actual():
    root=CLINIC_WORKSPACE
    if not (root/'runs/unified_bed_local_r1/result.json').is_file():
        pytest.skip('historical evidence not installed')
    return load_run(root,'unified_bed_local_r1')


def test_nominal_and_actual_owner_are_independent(actual):
    t=actual['explanation']['tasks']['C0_r3_W2']
    assert (t['batch'],t['waypoint'],t['nominal_owner']) == (0,2,'r3')
    assert t['actual_executor']=='r1'
    assert t['definition']['clear_anchor']=='CPW2C'
    assert t['actual_reassigned_from_nominal'] is True


def test_nodes_are_verified_registration_not_acronym_guesses(actual):
    e=actual['explanation'];nodes={n['id']:n for n in e['nodes']}
    assert len(nodes)==22
    assert 'CTL' not in nodes and 'CTLR3' in nodes
    assert not {'W1','W2','W3'} & nodes.keys()
    assert nodes['EPW2']['display_name_zh']=='PW2 服务入口 EPW2'
    assert all(n['navigation_topology_point'] is None for n in nodes.values())
    assert all(n['coordinate'] == actual['anchors'][n['id']] for n in nodes.values())


def test_event_plan_excludes_initial_normal(actual):
    a=actual['explanation']['event_planning']['E1']
    assert a['first_verification_plan']['committed_at']==pytest.approx(187.65)
    assert a['first_verification_plan']['requested_at']==pytest.approx(187.20)
    assert a['excluded_initial_normal']==[0]
    assert all(r['plan_index']!=0 for r in a['planning'])


def test_three_repairs_release_is_not_reassignment(actual):
    rows=actual['explanation']['repair_diagnostics']
    assert len(rows)==3
    for r in rows:
        assert (r['released_count'],r['suffix_count'])==(10,11)
        assert r['released_ratio']==pytest.approx(10/11)
        assert r['reassigned_tasks']==[]
        assert r['budget_seconds']==25
        assert r['budget_stop_recorded'] is True
        assert r['first_fully_validated_at'] is None
        assert r['scope_expansions']==0
        assert set(r['protected_prefix_tasks'])=={'C0_r1_W3','E1_deliver','E1_monitor'}
    assert all(r['same_obstruction_origin_as_previous'] for r in rows[1:])
    assert all(r['request_interval_since_previous_sim']==pytest.approx(30.01) for r in rows[1:])


def test_dependency_kinds_are_explicit(actual):
    edges=actual['explanation']['task_edges']
    assert any(e['from']=='E1_verify' and e['to']=='E1_pickup' and e['kind']=='strict_precedence' for e in edges)
    assert any(e['from']=='guard:monitor_active' and e['to']=='E1_deliver' and e['kind']=='continuous_monitor_guard' for e in edges)
    assert all(e['source'] for e in edges)
    p=actual['explanation']['path_report']
    assert p['travel_matrix']['matrix']
    assert p['future_geometry_saved'] is False
    assert p['grid_sandbox_connected'] is False


@pytest.mark.skipif(not (CLINIC_WORKSPACE/'verification/visual_positive_2026-11-18_c1/positive_02/summary.json').is_file(),
                    reason='historical visual evidence is not part of a clean repository checkout')
def test_video_source_registration_is_not_sensor_estimated():
    positive=load_run(CLINIC_WORKSPACE,'verification/visual_positive_2026-11-18_c1/positive_02')
    targets=positive['explanation']['path_report']['event_targets']
    e=next(row for row in targets if row['event_id']=='E1')
    assert e['provenance']=='video_source_registered'
    assert e['registration_id']=='A'
    assert e['event_xy']==[15.4,-10.8]
    assert {row['target_node'] for row in e['compiled_task_targets']} >= {'V1','M1','G1','H1'}
    assert '不是从随机人体像素在线估计' in e['interpretation']
