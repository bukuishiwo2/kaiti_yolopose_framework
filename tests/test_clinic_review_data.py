"""Evidence adapter regressions; fixtures are not physical experiment evidence."""
import hashlib
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from kaiti_review import data


def fixture_run(tmp_path, result=None, trace=None):
    folder = tmp_path / "runs" / "fixture"
    folder.mkdir(parents=True)
    result = result if result is not None else {"passed": True, "epoch": 10, "records": []}
    trace = trace if trace is not None else [{"at": 10, "episode_time": 0, "phase": "episode_ready"}]
    (folder / "result.json").write_text(json.dumps(result))
    (folder / "trace.jsonl").write_text("".join(json.dumps(row) + "\n" for row in trace))
    return folder


def test_epoch_uses_saved_value_and_preserves_negative_preepisode(tmp_path):
    fixture_run(tmp_path, trace=[
        {"at": 8, "episode_time": -1, "phase": "resource_feedback", "resource": {"owners": {}}},
        {"at": 12, "episode_time": 2, "phase": "pose_sample", "poses": {"r1": {"x": 1, "y": 2}}},
    ])
    result = data.load_run(tmp_path, "fixture")
    assert result["events"][0]["at"] == -2
    assert result["samples"][0]["at"] == 2
    assert result["samples"][0]["source_at"] == 12
    assert result["clock"]["source"] == "result.epoch"


def test_epoch_can_only_be_derived_from_consistent_nonnegative_pairs():
    rows = [{"at": 11 + i, "episode_time": i} for i in range(4)]
    assert data.epoch_from({}, rows) == (11, "trace.at - trace.episode_time (>=3 consistent records)")
    rows[-1]["at"] += 1
    assert data.epoch_from({}, rows)[0] is None
    assert data.epoch_from({}, rows[:2])[0] is None


def test_original_raw_line_is_not_normalized_or_reserialized(tmp_path):
    folder = fixture_run(tmp_path, trace=[{"at": 13, "episode_time": 3, "phase": "custom", "source_at": 1.5}])
    before = (folder / "trace.jsonl").read_bytes()
    result = data.load_run(tmp_path, "fixture")
    assert result["events"][0]["at"] == 3
    raw = data.raw_line(tmp_path, "fixture", 1)
    assert raw["raw_text"].encode() == before
    assert json.loads(raw["raw_text"])["source_at"] == 1.5
    assert (folder / "trace.jsonl").read_bytes() == before


def test_missing_fields_and_nonfinite_values_are_unknown(tmp_path):
    fixture_run(tmp_path, {"passed": False, "records": [
        {"task_id": "T", "robot": "r1", "status": "SUCCEEDED", "arrival": {"position_error": float("nan")}}
    ]})
    result = data.load_run(tmp_path, "fixture")
    assert result["task_analysis"][0]["total"] is None
    assert result["task_analysis"][0]["arrival_error"] is None
    assert result["clock"]["mode"] == "unverified"
    assert result["nonfinite_fields"]
    json.dumps(result, allow_nan=False)


def test_pose_handoff_cancel_is_not_a_failed_task():
    records = [{
        "status": "SUCCEEDED", "service_finished": 4,
        "navigation_attempts": [
            {"leg": "entry", "status": 5, "handoff": {"reason": "pose transfer"}, "arrival_guard_passed": True},
            {"leg": "service", "status": 5, "handoff": {"reason": "pose transfer"}, "arrival_guard_passed": True},
        ]
    }]
    analysis, findings = data.task_analysis(records)
    assert analysis[0]["expected_handoffs"] == 2
    assert analysis[0]["extra_attempts"] == 0
    assert not any(f["level"] == "error" for f in findings)


def test_released_reassigned_order_and_time_changes_are_independent():
    old = {"plan": {"owners": {"A": "r1", "B": "r1", "C": "r2"},
                    "routes": {"r1": ["A", "B"], "r2": ["C"]}, "starts": {"A": 1, "B": 3, "C": 5}}}
    new = {"plan": {"owners": {"A": "r1", "B": "r1", "C": "r3"},
                    "routes": {"r1": ["B", "A"], "r3": ["C"]}, "starts": {"A": 2, "B": 3, "C": 5}},
           "scope": {"free": ["A", "C"]}, "prefixes": {"r1": {"jobs": ["B"]}}}
    changes = {row["job"]: row for row in data.plan_changes(old, new)}
    assert changes["A"]["released"] and not changes["A"]["reassigned"]
    assert changes["A"]["order_changed"] and changes["A"]["time_changed"]
    assert changes["B"]["protected"] and not changes["B"]["released"]
    assert changes["C"]["reassigned"] and changes["C"]["order_changed"] is None


def test_paging_and_raw_row_bounds(tmp_path):
    fixture_run(tmp_path, trace=[{"at": 10 + i, "phase": "custom", "robot": "r1"} for i in range(205)])
    result = data.paged_events(tmp_path, "fixture", "custom", page=2, size=80)
    assert result["total"] == 205 and len(result["rows"]) == 45
    with pytest.raises(ValueError):
        data.raw_line(tmp_path, "fixture", 0)
    with pytest.raises(ValueError):
        data.load_run(tmp_path, "../fixture")


def test_stat_signature_invalidates_cached_result(tmp_path):
    folder = fixture_run(tmp_path)
    first = data.load_run(tmp_path, "fixture")
    assert first["passed"] is True
    (folder / "result.json").write_text(json.dumps({"passed": False, "epoch": 10, "failure": "SAVED_FAILURE", "records": []}))
    second = data.load_run(tmp_path, "fixture")
    assert second["passed"] is False and second["failure"] == "SAVED_FAILURE"


def test_unknown_current_configuration_is_not_presented_as_frozen(tmp_path):
    folder = fixture_run(tmp_path)
    current = tmp_path / "config" / "fixture" / "scenario.json"
    current.parent.mkdir(parents=True)
    current.write_text('{"anchors": {"made_up": [1,2]}}')
    scenario, path, state = data.load_scenario(tmp_path, folder)
    assert scenario == {} and path is None and state == "NOT_RECORDED"
    manifest = {"config/fixture/scenario.json": hashlib.sha256(current.read_bytes()).hexdigest()}
    (folder / "source_manifest.json").write_text(json.dumps(manifest))
    scenario, path, state = data.load_scenario(tmp_path, folder)
    assert "made_up" in scenario["anchors"] and path == current


def test_no_fall_closure_and_explicit_final_snapshot_are_preserved(tmp_path):
    event = {"event_id": "E1", "lifecycle": "CLOSED", "closed_reason": "no_fall", "verified": False}
    folder = fixture_run(tmp_path, {"passed": True, "epoch": 10, "records": [],
                                   "protocol": {"time": 5, "event": event, "tasks": {}}})
    result = data.load_run(tmp_path, "fixture")
    assert result["semantic_events"][0]["final"]["event"]["closed_reason"] == "no_fall"
    assert result["semantic_events"][0]["final"]["source"] == "result.protocol"


def test_saved_problem_projection_preserves_prefix_and_forecast_provenance(tmp_path):
    plan = {"owners": {"A": "r1"}, "starts": {"A": 3}, "finishes": {"A": 5}, "routes": {"r1": ["A"]}}
    folder = fixture_run(tmp_path, trace=[
        {"at": 10, "episode_time": 0, "phase": "plan_committed", "plan": plan},
        {"at": 11, "episode_time": 1, "phase": "active_repair_committed", "plan": plan,
         "scope": {"free": []}},
    ])
    problem_path = folder / "repair" / "problem.json"
    problem_path.parent.mkdir()
    problem_path.write_text(json.dumps({
        "prefixes": {"r1": {"jobs": ["A"], "schedule": [{"service_finish_forecast": 5}]}},
        "active_commitments": {"r1": {"jobs": ["A"]}},
        "projection_note": "forecast only", "tasks": {},
    }))
    original_sha = hashlib.sha256(problem_path.read_bytes()).hexdigest()
    result = {"passed": True, "epoch": 10, "records": [], "planning_records": [
        {"requested_at": .2, "returned_at": 1, "problem_path": str(problem_path), "solver": {}}
    ]}
    (folder / "result.json").write_text(json.dumps(result))
    payload = data.load_run(tmp_path, "fixture")
    assert payload["plan_versions"][1]["prefixes"]["r1"]["jobs"] == ["A"]
    assert payload["plan_versions"][1]["changes"][0]["protected"] is True
    assert payload["plan_versions"][1]["prefixes_source"]["snapshot_at"] == .2
    assert payload["problem_evidence"][0]["source"] == str(problem_path)
    assert hashlib.sha256(problem_path.read_bytes()).hexdigest() == original_sha
