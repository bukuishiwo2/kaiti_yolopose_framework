#!/usr/bin/env python3
"""Read-only Clinic audit plus synthetic semantic counterfactuals; never starts ROS.

This diagnoses integration gaps. Passing diagnostic assertions is NOT passing
the image-to-execution acceptance gate. No images or real ACKs are manufactured.
Use a new --out directory; solver artefacts stay outside the source snapshot.
"""
from __future__ import annotations

import argparse
import ast
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from time import perf_counter
import xml.etree.ElementTree as ET


PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "src"))
from kaiti_task_sim.event_protocol import EventTaskProtocol, canonical


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n")


def without_protocol_revision(tasks):
    """Only metadata differs in the moved-target witness; keep full input too."""
    value = deepcopy(tasks)
    for task in value.values():
        task.pop("protocol_revision", None)
    return value


def method(path, cls, name):
    text = path.read_text()
    tree = ast.parse(text)
    klass = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == cls)
    node = next(n for n in klass.body if isinstance(n, ast.FunctionDef) and n.name == name)
    return dict(file=str(path), line=node.lineno,
                source="\n".join(text.splitlines()[node.lineno - 1:node.end_lineno]))


def observation(mid, at, space, source_at=None, status="confirmed"):
    result = dict(schema="event-task/v1", kind="observation", message_id=mid,
                  event_id="E1", at=at, source_at=at if source_at is None else source_at,
                  status=status)
    if status == "confirmed":
        result["space"] = deepcopy(space)
    return result


def feedback(mid, at, phase, result=None):
    value = dict(schema="event-task/v1", kind="feedback", message_id=mid,
                 event_id="E1", task_id="E1:verify", at=at, phase=phase,
                 robot_id="r3", task_revision=1, attempt=1)
    if result:
        value["result"] = result
    return value


def audit(workspace, out, run_solver):
    # Exact deployed source is authoritative, never experiments/clinic.
    tools = workspace / "tools"
    sys.path.insert(0, str(tools))
    import dense_tasks as dt
    import bed_contract as bc
    dt.config = bc.config  # Isolated interpreter only, matching runtime setup.
    cfg = bc.config()
    paths = [PROJECT / "src/kaiti_task_sim/event_protocol.py", Path(__file__),
             workspace / "worlds/clinic_l1_three.sdf",
             workspace / "launch/clinic_experiment.launch.py",
             workspace / "support/clinic_runtime/episode.py",
             workspace / "support/clinic_runtime/bootstrap.py",
             workspace / "config/hospital_bed/scenario.json"]
    paths += sorted(tools.glob("*.py"))
    paths += sorted((workspace / "config/three_tb4").glob("*.urdf"))
    before = {str(p): sha(p) for p in paths}
    write(out / "source_hashes.json", before)

    world = ET.parse(workspace / "worlds/clinic_l1_three.sdf")
    cameras = {}
    for rid in cfg["robots"]:
        tree = ET.parse(workspace / "config/three_tb4" / f"{rid}.urdf")
        cameras[rid] = [dict(name=s.get("name"), type=s.get("type"),
                            hz=float(s.findtext("update_rate", "0")),
                            width=s.findtext("camera/image/width"),
                            height=s.findtext("camera/image/height"),
                            optical_frame=s.findtext("camera/optical_frame_id"))
                        for s in tree.findall(".//sensor")
                        if s.get("type") in {"camera", "depth_camera", "rgbd_camera"}]
    hooks = dict(
        trigger=method(tools / "run_dense_episode.py", "Episode", "tick"),
        observe=method(tools / "run_aligned_episode.py", "Episode", "observe"),
        verdict=method(tools / "run_aligned_episode.py", "Bot", "feedback"),
    )
    launch = (workspace / "launch/clinic_experiment.launch.py").read_text()
    inventory = dict(
        workspace=str(workspace), world_actor_count=len(world.findall(".//actor")),
        human_includes=[i.findtext("uri") for i in world.findall(".//include")
                        if any(k in (i.findtext("uri") or "").lower()
                               for k in ("human", "person", "actor", "visitor", "patient"))],
        cameras=cameras,
        image_bridge_declared_in_unified_launch="sensor_msgs/msg/Image" in launch,
        camera_info_bridge_declared_in_unified_launch="sensor_msgs/msg/CameraInfo" in launch,
        sequence_length_from_config=32,
        source_hooks=hooks,
        model_files={str(p): dict(exists=p.is_file(), bytes=p.stat().st_size if p.is_file() else None)
                     for p in [PROJECT / "yolo11n-pose.pt", PROJECT / "models/fall_sequence_lstm_urfall_finetune_from_fallvision_sampled.pt"]},
        dependency_import_specs={name: importlib.util.find_spec(name) is not None
                                 for name in ("torch", "ultralytics", "pulp", "numpy", "yaml")},
        runtime_graph_probed=False, image_inference_run=False,
    )
    write(out / "inventory.json", inventory)

    event = cfg["event"]
    space = dict(valid=True, frame="map", event_xy=event["center"],
                 service_points={r: cfg["anchors"][event["services"][r]][:2]
                                 for r in ("verify", "monitor")})
    space["service_points"]["deliver"] = cfg["anchors"][event["services"]["event_handoff"]][:2]
    moved = deepcopy(space)
    moved["event_xy"][0] += 1.0
    for point in moved["service_points"].values():
        point[0] += 1.0
    inputs = {
        "no_detection": [],
        "confirmed_invalid_position": [observation("invalid", 10., {"valid": False})],
        "confirmed_valid": [observation("positive", 10., space)],
        "duplicate": [observation("positive", 10., space), observation("positive", 11., space, source_at=10.)],
        "short_occlusion": [observation("positive", 10., space), observation("hidden", 11., None, status="occluded")],
        "expired_position": [observation("old", 0., space)],
        "moved_position": [observation("positive", 10., space), observation("moved", 11., moved)],
        "verify_no_fall": [observation("positive", 10., space), feedback("start", 10.5, "started"), feedback("negative", 11., "succeeded", "no_fall")],
        "verify_fall": [observation("positive", 10., space), feedback("start", 10.5, "started"), feedback("positive_ack", 11., "succeeded", "fall")],
    }
    checks = []

    def check(name, value):
        checks.append(dict(name=name, passed=bool(value)))

    cases = {}
    for name, messages in inputs.items():
        protocol = EventTaskProtocol(supply=cfg["anchors"]["G1"][:2])
        transitions = [protocol.apply(m) for m in messages]
        protocol.apply(dict(schema="event-task/v1", kind="tick", message_id="clock", at=12.))
        view = protocol.planning_view()
        compiled = dt.event_tasks(view, 12.)
        cases[name] = dict(input_kind="hand_authored_protocol_fixture_not_image_inference",
                           messages=messages, transitions=transitions,
                           snapshot=protocol.snapshot(), view=view, compiled=compiled)
    for name in ("no_detection", "confirmed_invalid_position", "expired_position", "verify_no_fall"):
        check(name + "_no_event_navigation_tasks", not cases[name]["compiled"])
    check("confirmed_only_verify_before_ack", set(cases["confirmed_valid"]["compiled"]) == {"E1_verify"})
    check("duplicate_no_planning_change", not cases["duplicate"]["transitions"][-1]["planning_changed"])
    check("occlusion_keeps_task", canonical(cases["short_occlusion"]["compiled"]) == canonical(cases["confirmed_valid"]["compiled"]))
    check("positive_ack_generates_response_graph", set(cases["verify_fall"]["compiled"]) == {"E1_monitor", "E1_pickup", "E1_deliver"})
    check("response_graph_has_monitor_and_courier_relations", len(cases["verify_fall"]["view"]["relations"]) == 2)
    check("protocol_preserves_moved_target", cases["moved_position"]["view"]["tasks"][0]["target"]["xy"] == moved["service_points"]["verify"])
    location_lost = canonical(without_protocol_revision(cases["moved_position"]["compiled"])) == canonical(without_protocol_revision(cases["confirmed_valid"]["compiled"]))
    check("compiler_location_loss_reproduced", location_lost)
    # Existing semantics request cancellation on loss of position even during
    # monitoring/carrying. This must be reconciled with Clinic commitments.
    active = EventTaskProtocol(supply=cfg["anchors"]["G1"][:2])
    for msg in inputs["verify_fall"]:
        active.apply(msg)
    active.apply(dict(schema="event-task/v1", kind="feedback", message_id="monitor_start",
                      event_id="E1", task_id="E1:monitor", at=11.2, phase="started",
                      robot_id="r3", task_revision=1, attempt=1))
    active.apply(dict(schema="event-task/v1", kind="tick", message_id="expired", at=21.))
    active_expiry = active.snapshot()
    check("active_monitor_expiry_requests_cancel", active_expiry["tasks"]["E1:monitor"]["state"] == "CANCEL_REQUESTED")
    write(out / "protocol_cases.json", dict(cases=cases, active_monitor_expiry=active_expiry))

    solver_results = {}
    if run_solver:
        # Existing deployed compiler/model/validator, not a replacement planner.
        import dense_solver as ds
        import dense_validate as dv
        normal, _ = dt.normal_tasks()
        normal = {j: t for j, t in normal.items() if t["waypoint"] == 1}
        states = {rid: dict(job=None, state="IDLE", anchor=cfg["starts"][rid], cargo=None,
                            record={}, pose=dict(zip(("x", "y", "yaw"), cfg["anchors"][cfg["starts"][rid]])),
                            leg="service") for rid in cfg["robots"]}
        cache = {}
        for name in ("no_detection", "confirmed_invalid_position", "confirmed_valid", "duplicate", "short_occlusion", "expired_position", "moved_position", "verify_no_fall"):
            tasks = {**deepcopy(normal), **deepcopy(cases[name]["compiled"])}
            problem = dt.problem(cfg, tasks, list(tasks), {}, deepcopy(states),
                                 dict(starts={}), 12., None, "semantic_counterfactual")
            digest = hashlib.sha256(canonical(problem).encode()).hexdigest()
            optimization = deepcopy(problem)
            optimization["tasks"] = without_protocol_revision(optimization["tasks"])
            optimization_digest = hashlib.sha256(canonical(optimization).encode()).hexdigest()
            write(out / (name + "_problem.json"), problem)
            if digest in cache:
                solver_results[name] = dict(reused_identical_input=cache[digest], input_sha256=digest,
                                            optimization_projection_sha256=optimization_digest)
                continue
            cache[digest] = name
            scope = dict(free=list(problem["tasks"]), freeze_time=False)
            result = ds.a.ScopedSolver(out / "solver" / name).solve(problem, scope, "monolithic", perf_counter() + 5.)
            write(out / (name + "_solver.json"), result)
            accepted = result["status"] in {"OPTIMAL", "FEASIBLE_BUDGET"}
            valid = accepted and dv.validate(problem, result["plan"], scope, result["objective"])["passed"]
            check(name + "_existing_milp_valid", valid)
            solver_results[name] = dict(input_sha256=digest, status=result["status"], independently_validated=valid,
                                         optimization_projection_sha256=optimization_digest,
                                         plan=result.get("plan"), objective=result.get("objective"))
        negative = solver_results["no_detection"]
        positive = solver_results["confirmed_valid"]
        check("semantic_task_changes_solver_input", negative["input_sha256"] != positive["input_sha256"])
        if negative.get("plan") and positive.get("plan"):
            check("semantic_task_changes_actual_assignment_output", "E1_verify" not in negative["plan"]["owners"] and
                  positive["plan"]["owners"].get("E1_verify") in {"r1", "r3"})
        check("moved_position_changes_protocol_revision_metadata", solver_results["moved_position"]["input_sha256"] != positive["input_sha256"])
        check("moved_position_lost_in_optimization_projection", solver_results["moved_position"]["optimization_projection_sha256"] == positive["optimization_projection_sha256"])
        check("moved_position_produces_same_plan", solver_results["moved_position"].get("plan") == positive.get("plan"))

    after = {str(p): sha(p) for p in paths}
    check("existing_sources_unchanged", before == after)
    write(out / "integrity.json", dict(passed=before == after, checked=len(before),
                                       changed=[p for p in before if before[p] != after[p]]))
    summary = dict(
        schema="clinic-semantic-readiness-audit/v1", workspace=str(workspace),
        audit_passed=all(c["passed"] for c in checks), checks=checks,
        synthetic_protocol_cases=len(cases), unique_milp_solves=sum("status" in r for r in solver_results.values()),
        solver_results=solver_results, integration_ready=False,
        observed_end_to_end_semantic_simulation=False,
        evidence_boundary="Synthetic protocol counterfactuals and static deployed-source audit; no image inference, ROS, Gazebo, physical ACK or execution experiment.",
        blockers=[
            "Unified episode self-injects fall and refreshes confirmed evidence without camera observations.",
            "Unified launch has no RGB/depth/CameraInfo bridge or perception-to-protocol consumer.",
            "TB4 RGB-D configured at 1 Hz; trained temporal sampling and measured throughput need validation.",
            "Active world has no explicit person/actor include; inspected local actors have no declared fall animation.",
            "Compiler discards protocol targets in favour of V1/M1/H1; moved-position witness changes revision metadata but not geometry/optimization input or plan.",
            "Verification success is unconditionally labelled fall in Bot.feedback.",
            "Position expiry requests monitor cancellation; reconciliation with hard active commitments is unvalidated.",
        ],
    )
    write(out / "summary.json", summary)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path("/home/yhc/clinic_planning_ws"))
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--solve", action="store_true", help="Run small offline MILPs using deployed modules")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    try:
        result = audit(args.workspace.resolve(), args.out.resolve(), args.solve)
    except Exception as exc:
        write(args.out / "failure.json", dict(type=type(exc).__name__, error=str(exc), integration_ready=False))
        raise
    print(json.dumps({k: result[k] for k in ("audit_passed", "integration_ready", "synthetic_protocol_cases", "unique_milp_solves")}))
    return 0 if result["audit_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
