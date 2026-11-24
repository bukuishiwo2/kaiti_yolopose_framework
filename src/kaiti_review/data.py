"""Evidence-only adapters for the local Clinic workbench. Never import ROS/solver code."""
from __future__ import annotations

import ast
import base64
from collections import OrderedDict, Counter
import hashlib
import json
import math
from pathlib import Path
import re
import statistics
import threading

REPO = Path(__file__).resolve().parents[2]
_CACHE = OrderedDict()
_LOCK = threading.RLock()
CACHE_LIMIT = 5
SEMANTIC_ROOTS = (
    "visual_integration_2026-11-18_b1",
    "visual_positive_2026-11-18_c1",
    "visual_bed_2026-11-18_d1",
)
ASSETS = {}


def finite(value):
    return isinstance(value, (float, int)) and not isinstance(value, bool) and math.isfinite(value)


def read_json(path, fallback=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return fallback


def digest(path):
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def provenance(path, **extra):
    return {"path": str(path), "sha256": digest(path), "bytes": path.stat().st_size, **extra}


def clean(value, unknown=None, location="$"):
    if isinstance(value, float) and not math.isfinite(value):
        if unknown is not None:
            unknown.append(location)
        return None
    if isinstance(value, dict):
        return {str(key): clean(item, unknown, location + "." + str(key)) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean(item, unknown, location + "[" + str(index) + "]") for index, item in enumerate(value)]
    return value


def descriptors(root):
    root = Path(root).resolve()
    found = {}
    runs = root / "runs"
    if runs.is_dir():
        for folder in sorted(runs.iterdir()):
            if folder.is_dir() and not folder.is_symlink() and (folder / "result.json").is_file() and (folder / "trace.jsonl").is_file():
                found[folder.name] = (folder, folder / "result.json")
    for name in SEMANTIC_ROOTS:
        parent = root / "verification" / name
        if not parent.is_dir():
            continue
        for folder in sorted(parent.iterdir()):
            if folder.is_symlink() or not folder.is_dir():
                continue
            if (folder / "summary.json").is_file() and (folder / "trace.jsonl").is_file():
                found[str(folder.relative_to(root))] = (folder, folder / "summary.json")
    return found


def catalog(root):
    return list(descriptors(root))


def resolve_run(root, name):
    descriptor = descriptors(root).get(name)
    if not descriptor:
        raise ValueError("未注册的运行；只允许 runs/ 或已知视觉验证目录中的保存记录。")
    return descriptor


def frozen_file(root, folder, relative):
    """Return a frozen or hash-matching file; current unbound config is not evidence."""
    manifest = read_json(folder / "source_manifest.json", {}) or {}
    if not isinstance(manifest, dict):
        manifest = {}
    wanted = None
    for key, value in manifest.items():
        if str(key).endswith(relative) and isinstance(value, str):
            wanted = value
            break
    candidate = folder / "source" / relative
    if candidate.is_file() and (wanted is None or digest(candidate) == wanted):
        return candidate
    candidate = Path(root) / relative
    if wanted and candidate.is_file() and digest(candidate) == wanted:
        return candidate
    return None


def load_scenario(root, folder):
    path = folder / "runtime_scenario.json"
    if path.is_file():
        return read_json(path, {}) or {}, path, "run_runtime_snapshot"
    manifest = read_json(folder / "source_manifest.json", {}) or {}
    if isinstance(manifest, dict):
        relatives = [str(key)[len(str(root)) + 1:] if str(key).startswith(str(root) + "/") else str(key)
                     for key in manifest if str(key).endswith("/scenario.json")]
        for relative in relatives:
            candidate = frozen_file(root, folder, relative)
            if candidate:
                return read_json(candidate, {}) or {}, candidate, "frozen_or_hash_verified"
    return {}, None, "NOT_RECORDED"


def map_identity(root, folder):
    manifest = read_json(folder / "source_manifest.json", {}) or {}
    output = {"recorded_maps": {}, "recorded_configuration": {}}
    if isinstance(manifest, dict):
        for name, value in manifest.items():
            if isinstance(value, str) and str(name).endswith((".pgm", ".yaml", ".json", ".py")):
                if str(name).endswith(".pgm"):
                    output["recorded_maps"][str(name)] = value
                if any(term in str(name) for term in ("nav2", "profile.json", "scenario.json", "bed_solver", "prefix", "guard", "worker")):
                    output["recorded_configuration"][str(name)] = value
    return output


def load_map(root):
    path = Path(root) / "maps/clinic_l1.pgm"
    raw = path.read_bytes()
    header = re.match(rb"P5\s+(\d+)\s+(\d+)\s+255[\r]?\n", raw)
    if not header:
        raise ValueError("只支持原始 8 位 P5 占用地图；没有生成替代地图。")
    width, height = map(int, header.groups())
    pixels = raw[header.end():]
    if len(pixels) != width * height:
        raise ValueError("地图像素长度与头信息不一致。")
    yaml_path = path.with_suffix(".yaml")
    config = yaml_path.read_text()
    resolution = float(re.search(r"resolution: *([0-9.]+)", config)[1])
    origin_text = config.split("origin:", 1)[1].split("negate:", 1)[0]
    origin = [float(value) for value in re.findall(r"-?[0-9]+(?:[.][0-9]+)?", origin_text)]
    if len(origin) != 3 or origin[2] != 0 or resolution <= 0:
        raise ValueError("当前适配器不支持该地图坐标或旋转。")
    return {"width": width, "height": height, "resolution": resolution, "origin": origin,
            "pixels": base64.b64encode(pixels).decode(), "source": str(path),
            "sha256": hashlib.sha256(raw).hexdigest(), "yaml_source": str(yaml_path),
            "yaml_sha256": digest(yaml_path), "display_scope": "workspace_reference_map"}


def epoch_from(result, rows):
    if finite(result.get("epoch")):
        return result["epoch"], "result.epoch"
    offsets = [row["at"] - row["episode_time"] for row in rows
               if finite(row.get("at")) and finite(row.get("episode_time")) and row["episode_time"] >= 0]
    if len(offsets) >= 3 and max(offsets) - min(offsets) <= .00001:
        return statistics.median(offsets), "trace.at - trace.episode_time (>=3 consistent records)"
    return None, "NOT_RECORDED_OR_INCONSISTENT"


def compact_event(row, number, epoch):
    at = row.get("at")
    normalized = at - epoch if finite(at) and epoch is not None else at
    record = row.get("record") or row.get("request") or row.get("feedback") or {}
    return {
        "at": normalized, "phase": row.get("phase", row.get("kind", "unknown")),
        "robot": row.get("robot", record.get("robot", record.get("robot_id"))) if isinstance(record, dict) else row.get("robot"),
        "task_id": row.get("task_id", record.get("task_id")) if isinstance(record, dict) else row.get("task_id"),
        "job": row.get("job", record.get("job_id")) if isinstance(record, dict) else row.get("job"),
        "stage": row.get("stage"), "reason": row.get("reason"),
        "leg": row.get("leg"), "accepted": row.get("accepted"), "length": row.get("length"),
        "_review_source_at": at, "_review_trace_line": number,
    }


def normalize_snapshot(snapshot):
    if not isinstance(snapshot, dict):
        return None
    event = snapshot.get("event")
    if not isinstance(event, dict):
        return None
    tasks = snapshot.get("tasks") or {}
    return {
        "time": snapshot.get("time"), "event": event,
        "tasks": {key: {field: task.get(field) for field in (
            "task_id", "event_id", "role", "state", "owner", "required_owner", "revision",
            "execution_revision", "attempt", "generated_at", "started_at", "finished_at",
            "completion_dependencies", "runtime_guards", "target", "blockers",
            "execution_target", "cancel_reason")} for key, task in tasks.items() if isinstance(task, dict)}
    }


def register_asset(path):
    path = Path(path)
    if not path.is_file() or path.is_symlink() or path.suffix.lower() not in (".jpg", ".jpeg", ".png", ".mp4", ".webm"):
        return None
    key = hashlib.sha256(str(path.resolve()).encode()).hexdigest()[:24]
    ASSETS[key] = path.resolve()
    return {"id": key, **provenance(path), "url": "/api/asset?id=" + key,
            "kind": "video" if path.suffix.lower() in (".mp4", ".webm") else "image",
            "time_mapping": "NOT_RECORDED; independent preview, not synchronized"}


def semantic_events(rows, result, epoch, folder):
    histories, models, registrations, media = {}, [], [], []
    signatures = {}
    def take(snapshot, at, source, line=None):
        normalized = normalize_snapshot(snapshot)
        if not normalized:
            return
        event = normalized["event"]
        event_id = event.get("event_id")
        if not event_id:
            return
        entry = histories.setdefault(event_id, {"id": event_id, "history": [], "milestones": []})
        signature = json.dumps({"lifecycle": event.get("lifecycle"), "verified": event.get("verified"),
                                "closed_reason": event.get("closed_reason"), "space": event.get("space"),
                                "cargo_owner": event.get("cargo_owner"), "cargo_disposition": event.get("cargo_disposition"),
                                "tasks": normalized["tasks"]}, sort_keys=True, default=str)
        if signatures.get(event_id) != signature:
            entry["history"].append({"at": at, **normalized, "source": source, "line": line})
            signatures[event_id] = signature
    for number, row in rows:
        at = row.get("at")
        at = at - epoch if finite(at) and epoch is not None else at
        phase = str(row.get("phase", ""))
        transition = row.get("transition") or row.get("output") or {}
        if isinstance(transition, dict):
            take(transition.get("snapshot"), at, "trace.jsonl", number)
        if phase == "explicit_spatial_registration":
            registrations.append({"at": at, "registration": row.get("registration"), "line": number})
        sample = row.get("sample")
        if phase == "visual_model_transition" and isinstance(sample, dict):
            models.append({"at": at, "line": number, **{key: sample.get(key) for key in
                          ("sample_id", "source_id", "source_at", "video_time", "score", "stable", "window_ready", "registration_mode")},
                           "model_latency": row.get("model_latency"),
                           "clock_mapping": "same trace row records simulation at and source video_time; no continuous mapping inferred"})
        event_id = row.get("event_id") or (row.get("message") or {}).get("event_id")
        if event_id:
            entry = histories.setdefault(event_id, {"id": event_id, "history": [], "milestones": []})
            if any(word in phase for word in ("candidate", "fall_event", "closed", "handover")):
                entry["milestones"].append({"at": at, "phase": phase, "line": number})
    for index, record in enumerate(result.get("protocol_records", []) or []):
        if not isinstance(record, dict):
            continue
        output = record.get("output") or {}
        message = record.get("message") or {}
        take(output.get("snapshot"), message.get("at"), "result.protocol_records[" + str(index) + "]")
    final = result.get("protocol")
    if isinstance(final, dict):
        take(final, final.get("time"), "result.protocol")
    review = read_json(folder / "review.json", {})
    if isinstance(review, dict):
        evidence_path = review.get("evidence_id")
        if evidence_path:
            path = Path(evidence_path)
            if path.is_file() and path.resolve().is_relative_to(folder.parents[1].resolve()):
                asset = register_asset(path)
                if asset:
                    asset["review"] = review
                    media.append(asset)
    for entry in histories.values():
        entry["history"].sort(key=lambda row: row["at"] if finite(row.get("at")) else math.inf)
        entry["final"] = entry["history"][-1] if entry["history"] else None
        if isinstance(final, dict) and isinstance(final.get("event"), dict) and final["event"].get("event_id") == entry["id"]:
            final_snapshot = normalize_snapshot(final)
            entry["final"] = {"at": final.get("time"), **final_snapshot, "source": "result.protocol", "line": None}
        entry["review"] = review if review.get("event_id") == entry["id"] else None
        entry["models"] = models
        entry["registrations"] = registrations
    return list(histories.values()), models, media


def task_analysis(records):
    analysis, findings = [], []
    for index, record in enumerate(records):
        def duration(a, b):
            first, second = record.get(a), record.get(b)
            return second - first if finite(first) and finite(second) and second >= first else None
        legs, expected = Counter(), 0
        for attempt in record.get("navigation_attempts", []) or []:
            if isinstance(attempt, dict):
                legs[str(attempt.get("leg", "unknown"))] += 1
                expected += bool(attempt.get("status") == 5 and attempt.get("handoff")
                                 and attempt.get("arrival_guard_passed") is True)
        rejected = sum(check.get("accepted") is False for check in record.get("path_checks", []) or [] if isinstance(check, dict))
        extra = sum(max(0, count - 1) for count in legs.values())
        analysis.append({"index": index, **{key: duration(a, b) for key, a, b in (
            ("total", "begin", "end"), ("prepare", "begin", "stable_at"),
            ("wait", "stable_at", "service_started"), ("service", "service_started", "service_finished"),
            ("clear", "service_finished", "end"), ("resource_wait", "gate_arrival", "lease_granted_at"),
            ("ack_wait", "start_requested", "service_started"))},
            "extra_attempts": extra, "path_rejections": rejected, "expected_handoffs": expected,
            "arrival_error": (record.get("arrival") or {}).get("position_error")})
        cues = []
        status = record.get("status")
        if status and status not in ("SUCCEEDED", "RUNNING", "PENDING", "ACCEPTED"):
            cues.append(("error", "任务终态未成功", str(status)))
        if extra:
            cues.append(("cue", "同一导航段额外尝试", str(extra) + " 次；entry/service/clear 分开计数。"))
        if rejected:
            cues.append(("cue", "路径准入拒绝", str(rejected) + " 条；结合后续恢复检查。"))
        if status == "SUCCEEDED" and not record.get("exit") and not finite(record.get("service_finished")):
            cues.append(("gap", "缺少服务结束时间字段", "旧格式或角色可能未记录；不能据此断定缺失实际 ACK。"))
        for level, title, detail in cues:
            findings.append({"level": level, "title": title, "detail": detail, "task_index": index,
                             "at": record.get("end", record.get("begin")), "source": "$.records[" + str(index) + "]"})
    return analysis, findings


def plan_changes(before, after):
    old, new = before.get("plan", {}), after.get("plan", {})
    old_owners, new_owners = old.get("owners", {}), new.get("owners", {})
    def order(plan, job, robot):
        route = plan.get("routes", {}).get(robot, [])
        return route.index(job) if job in route else None
    scope = after.get("scope") or {}
    released = scope.get("free")
    protected = set()
    for prefix in (after.get("prefixes") or {}).values():
        if isinstance(prefix, dict):
            protected.update(prefix.get("jobs") or [])
    rows = []
    for job in sorted(set(old_owners) | set(new_owners)):
        a, b = old_owners.get(job), new_owners.get(job)
        x, y = old.get("starts", {}).get(job), new.get("starts", {}).get(job)
        old_order, new_order = order(old, job, a), order(new, job, b)
        rows.append({"job": job, "old_robot": a, "new_robot": b,
                     "old_order": old_order, "new_order": new_order,
                     "old_start": x, "new_start": y,
                     "reassigned": a != b if a is not None and b is not None else None,
                     "order_changed": old_order != new_order if a == b and old_order is not None and new_order is not None else None,
                     "time_changed": abs(y - x) > .000001 if finite(x) and finite(y) else None,
                     "released": job in released if isinstance(released, list) else None,
                     "protected": job in protected if after.get("prefixes") is not None else None})
    return rows


def failure_info(root, folder, result, records, events, guards):
    failed = [event for event in events if any(token in str(event.get("phase")) for token in ("execution_failed", "episode_failed"))]
    row = next((record for record in records if record.get("status") == result.get("failure")), None)
    if not row:
        row = next((record for record in records if record.get("status") not in ("SUCCEEDED", "RUNNING", None)), None)
    if result.get("passed") is not False and not row and not failed:
        return None
    code = result.get("failure", result.get("error")) or (row or {}).get("status")
    task_id = (row or {}).get("task_id")
    samples = [guard for guard in guards if task_id and guard.get("task_id") == task_id]
    last = samples[-1] if samples else None
    explanations = {"ARRIVAL_NOT_STABLE": "导航动作结束后，未在本轮记录要求的窗口内达到稳定到达条件。",
                    "NAV_FAILED": "导航动作未报告成功；请查看原始 action 状态。",
                    "SERVICE_FAILED": "服务 worker 保存了失败反馈。",
                    "START_ACK_TIMEOUT": "服务启动 ACK 等待超时。"}
    # Only display literal thresholds from hash-bound/frozen source, never today's defaults.
    thresholds, sources = {}, []
    for relative in ("tools/run_hospital_episode.py", "tools/verify_three_tb4.py"):
        path = frozen_file(root, folder, relative)
        if not path:
            continue
        text = path.read_text()
        sources.append(provenance(path))
        patterns = {
            "stable_hold_seconds": r"t-self\.stable\s*>=\s*([.\d]+)",
            "stabilizing_timeout_seconds": r"t-self\.phase_at\s*>\s*([.\d]+):self\.fail\(['\"]ARRIVAL_NOT_STABLE",
            "position_error": r"\[['\"]position_error['\"]\]\s*<\s*([.\d]+)",
            "yaw_error": r"\[['\"]yaw_error['\"]\]\s*<\s*([.\d]+)",
            "tf_age": r"\[['\"]tf_age['\"]\]\s*<\s*([.\d]+)",
            "odom_age": r"\[['\"]odom_age['\"]\]\s*<\s*([.\d]+)",
            "scan_age": r"\[['\"]scan_age['\"]\]\s*<\s*([.\d]+)",
        }
        for key, pattern in patterns.items():
            match = re.search(pattern, text)
            if match:
                thresholds[key] = float(match[1])
    return {"code": code, "explanation": explanations.get(str(code), "本轮记录的失败；详细原因以原始记录为准。"),
            "robot": (row or {}).get("robot"), "task_id": task_id, "target": (row or {}).get("target"),
            "at": (row or {}).get("end") or (failed[-1].get("at") if failed else None),
            "position": (last or {}).get("detail"), "guard_last": last,
            "guard_samples": samples, "thresholds": thresholds,
            "threshold_sources": sources,
            "threshold_note": "仅列出本轮冻结或哈希绑定源码中的可提取字面阈值；缺失字段不可判定。", "record": row}


def load_uncached(root, name, descriptor):
    folder, result_path = descriptor
    result = read_json(result_path, {})
    if not isinstance(result, dict):
        raise ValueError("结果文件不是 JSON 对象")
    trace = folder / "trace.jsonl"
    rows, offsets, skipped = [], [], 0
    with trace.open("rb") as stream:
        line_number = 0
        while True:
            offset = stream.tell()
            line = stream.readline()
            if not line:
                break
            line_number += 1
            offsets.append(offset)
            try:
                row = json.loads(line)
            except (ValueError, UnicodeDecodeError):
                skipped += 1
                continue
            if isinstance(row, dict) and finite(row.get("at")):
                rows.append((line_number, row))
            else:
                skipped += 1
    epoch, clock_source = epoch_from(result, [row for _, row in rows])
    events, samples, guards, resources, commitments, plans, paths = [], [], [], [], [], [], []
    actual_pose_phases = {"pose_sample", "measured_pose_sample"}
    for line_number, row in rows:
        event = compact_event(row, line_number, epoch)
        at = event["at"]
        phase = str(event["phase"])
        if phase in actual_pose_phases:
            poses = row.get("poses") or row.get("measured") or {}
            if isinstance(poses, dict):
                samples.append({"at": at, "source_at": row["at"], "poses": poses,
                                "line": line_number, "source_kind": phase})
        else:
            events.append(event)
        if phase == "guard_sample":
            guards.append({"at": at, "task_id": row.get("task_id"), "robot": row.get("robot"),
                           "detail": row.get("detail"), "effective_ready": row.get("effective_ready"),
                           "line": line_number})
        if phase == "resource_feedback" and isinstance(row.get("resource"), dict):
            resources.append({"at": at, "resource": row["resource"], "line": line_number})
        if phase in ("plan_committed", "active_repair_committed", "visual_repair_committed", "initial_clearance_committed") and isinstance(row.get("plan"), dict):
            plans.append({"at": at, "phase": phase, "stage": row.get("stage"),
                          "plan": row["plan"], "prefixes": row.get("prefixes"),
                          "scope": row.get("scope"), "commitments": row.get("commitments"),
                          "line": line_number})
        if phase in ("online_commitment_check", "visual_plan_fence"):
            commitments.append({"at": at, "check": row.get("check"), "tokens": row.get("tokens"), "line": line_number})
        # Only accept explicitly stored point geometry, never use target-to-target straight lines.
        for field in ("path_xy", "polyline", "points"):
            points = row.get(field)
            if isinstance(points, list) and len(points) >= 2 and all(isinstance(p, (list, tuple)) and len(p) >= 2 and finite(p[0]) and finite(p[1]) for p in points):
                paths.append({"at": at, "robot": row.get("robot"), "points": points, "line": line_number, "field": field})
    pose_note = "Measured pose samples; no interpolation. Gaps >2 seconds are not joined."
    if not samples and guards:
        # Guard poses really are measured, but do not imply a continuously recorded trajectory.
        grouped = {}
        for guard in guards:
            detail = guard.get("detail") or {}
            if finite(detail.get("x")) and finite(detail.get("y")) and guard.get("robot"):
                grouped.setdefault(guard["at"], {})[guard["robot"]] = detail
        samples = [{"at": at, "poses": poses, "source_kind": "guard_sample_sparse"}
                   for at, poses in sorted(grouped.items())]
        pose_note = "Sparse measured guard positions only; no continuous navigation trace was recorded."
    samples.sort(key=lambda row: row["at"])
    events.sort(key=lambda row: row["at"])
    records = [record for record in (result.get("records") or []) if isinstance(record, dict)]
    scenario, scenario_path, scenario_status = load_scenario(root, folder)
    analysis, findings = task_analysis(records)
    semantic, models, media = semantic_events(rows, result, epoch, folder)
    semantic_final = (result.get("protocol") or {}).get("event") if isinstance(result.get("protocol"), dict) else None
    if not scenario.get("anchors"):
        targets = {}
        for record in records:
            target = record.get("target") or {}
            if record.get("anchor") and finite(target.get("x")) and finite(target.get("y")):
                targets[record["anchor"]] = [target["x"], target["y"], target.get("yaw", 0)]
        scenario["anchors"] = targets
    times = [row["at"] for row in events + samples if finite(row.get("at"))]
    times.extend(record[field] for record in records for field in ("begin", "end") if finite(record.get(field)))
    planning_records = result.get("planning_records") or []
    if not isinstance(planning_records, list):
        planning_records = []
    problem_evidence = []
    for index, record in enumerate(planning_records):
        problem = (record.get("solver") or {}).get("selected_problem") or {}
        problem_path = record.get("problem_path")
        evidence_source = "result.planning_records[" + str(index) + "].solver.selected_problem"
        if isinstance(problem_path, str):
            candidate = Path(problem_path)
            if candidate.is_file() and candidate.resolve().is_relative_to(folder.resolve()):
                saved = read_json(candidate)
                if isinstance(saved, dict):
                    problem = saved
                    evidence_source = str(candidate)
        problem_evidence.append({
            "plan_index": index, "at": record.get("requested_at"), "returned_at": record.get("returned_at"),
            "source": evidence_source, "prefixes": problem.get("prefixes"),
            "active_commitments": problem.get("active_commitments"),
            "coverage_projection": problem.get("coverage_projection"),
            "projection_note": problem.get("projection_note"),
            "dependencies": {job: {field: task.get(field) for field in
                                   ("dependencies", "completion_dependencies", "predecessors")
                                   if task.get(field) is not None}
                             for job, task in (problem.get("tasks") or {}).items()
                             if isinstance(task, dict) and any(task.get(field) is not None for field in
                                                                ("dependencies", "completion_dependencies", "predecessors"))},
        })
    plans.sort(key=lambda row: row["at"])
    for index, plan in enumerate(plans):
        projection = next((problem for problem in problem_evidence
                           if finite(problem.get("returned_at")) and abs(problem["returned_at"] - plan["at"]) < .00001), None)
        if projection:
            plan["projection_evidence"] = projection
            if plan.get("prefixes") is None and projection.get("prefixes") is not None:
                plan["prefixes"] = projection["prefixes"]
                plan["prefixes_source"] = {"path": projection["source"], "snapshot_at": projection["at"],
                                           "note": "planning-input commitment projection, not new actual completion evidence"}
        plan["changes"] = plan_changes(plans[index - 1], plan) if index else []
    strategy = result.get("strategy", result.get("policy"))
    strategy_source = "result.strategy" if result.get("strategy") is not None else "result.policy" if result.get("policy") is not None else "NOT_RECORDED"
    identities = map_identity(root, folder)
    robots = scenario.get("robots") or {}
    if not robots and planning_records:
        robots = ((planning_records[0].get("solver") or {}).get("selected_problem") or {}).get("robots") or {}
    capabilities = scenario.get("capabilities") or {robot: entry.get("capabilities") for robot, entry in robots.items() if isinstance(entry, dict)}
    task_ids = sorted({record.get("job_id") or record.get("task_id") for record in records if record.get("job_id") or record.get("task_id")})
    problems = [(plan.get("solver") or {}).get("selected_problem") or {} for plan in planning_records]
    weights = next((problem.get("weights") for problem in problems if problem.get("weights")), None)
    ready_times = [plan.get("returned_at") for plan in planning_records if finite(plan.get("returned_at"))]
    source_list = [provenance(result_path), provenance(trace)]
    for problem in problem_evidence:
        candidate = Path(problem["source"])
        if candidate.is_file():
            source_list.append(provenance(candidate, role="saved_planning_input"))
    for candidate in (scenario_path, folder / "source_manifest.json", folder / "review.json"):
        if candidate and candidate.is_file():
            source_list.append(provenance(candidate))
    failure = failure_info(root, folder, result, records, events, guards)
    event_markers = [event for event in events if any(token in str(event.get("phase")) for token in
                    ("candidate_created", "fall_event_injected", "invalidated", "bed_scenario_requested",
                     "planning_requested", "plan_committed", "repair_committed", "navigation_requested", "incident_closed"))]
    event_origin = next((event["at"] for event in events if "candidate_created" in str(event.get("phase")) or event.get("phase") == "fall_event_injected"), None)
    disturbance_origin = next((event["at"] for event in events if "bed_scenario_requested" == event.get("phase")), None)
    first_commit_after_disturbance = next((version["at"] for version in plans
                                          if disturbance_origin is not None and version["at"] >= disturbance_origin), None)
    first_dispatch_after_commit = next((event["at"] for event in events
                                       if first_commit_after_disturbance is not None
                                       and event["phase"] == "navigation_requested"
                                       and event["at"] >= first_commit_after_disturbance), None)
    numerator = sum(record.get("status") == "SUCCEEDED" for record in records if not record.get("exit"))
    denominator = len([record for record in records if not record.get("exit")])
    payload = {
        "name": name, "passed": result.get("passed"), "failure": result.get("failure", result.get("error")),
        "status": result.get("status"), "strategy": strategy, "strategy_source": strategy_source,
        "records": records, "task_analysis": analysis, "findings": findings,
        "samples": samples, "sample_note": pose_note, "events": events,
        "event_count": len(events), "raw_trace_lines": len(offsets), "skipped_rows": skipped,
        "start": min(times, default=0), "end": max(times, default=1),
        "clock": {"mode": "episode_relative" if epoch is not None else "unverified", "epoch": epoch,
                  "source": clock_source, "note": "Trace simulation at minus verified epoch; task and plan episode-relative fields unchanged. Negative pre-episode records retained."},
        "anchors": scenario.get("anchors", {}), "scenario": scenario,
        "scenario_evidence": {"status": scenario_status, "path": str(scenario_path) if scenario_path else None},
        "sources": source_list, "planning_records": planning_records,
        "problem_evidence": problem_evidence,
        "plan_versions": plans, "planned_paths": paths,
        "repair_decisions": result.get("repair_decisions", result.get("repair_cases", [])) or [],
        "resource_history": resources, "resource_events": result.get("resource_events", []),
        "commitment_history": commitments, "guard_samples": guards,
        "navigation_commitments": [event for event in events if event["phase"] in
                                   ("motion_path_admitted", "motion_path_released",
                                    "visual_navigation_cancel_ack", "bed_navigation_cancel_ACK")],
        "semantic_events": semantic, "model_samples": models, "media": media,
        "semantic_final": semantic_final, "failure_info": failure, "markers": event_markers,
        "summary": {key: result.get(key) for key in
                    ("event_at", "incident_closed_at", "handover_ack", "wall_seconds", "disturbances", "scope")},
        "metrics": {"task_completion_numerator": numerator, "task_completion_denominator": denominator,
                    "task_completion_rate": numerator / denominator if denominator else None,
                    "last_task_end_sim": max((r["end"] for r in records if finite(r.get("end")) and not r.get("exit")), default=None),
                    "return_end_sim": max((r["end"] for r in records if r.get("exit") and finite(r.get("end"))), default=None),
                    "event_sim": event_origin, "disturbance_sim": disturbance_origin,
                    "planning_wall_sum": sum(p["end_to_end_wall"] for p in planning_records if finite(p.get("end_to_end_wall"))),
                    "first_commit_after_disturbance_sim": first_commit_after_disturbance,
                    "first_dispatch_after_commit_sim": first_dispatch_after_commit,
                    "disturbance_to_commit_sim": first_commit_after_disturbance - disturbance_origin
                    if first_commit_after_disturbance is not None and disturbance_origin is not None else None,
                    "disturbance_to_dispatch_sim": first_dispatch_after_commit - disturbance_origin
                    if first_dispatch_after_commit is not None and disturbance_origin is not None else None,
                    "first_validated_sim": None,
                    "first_validated_note": "NOT_RECORDED unless solver explicitly saves a complete validation timestamp; return time is not substituted",
                    "resource_conflicts": None, "commitment_violations": None},
        "comparison_signature": {
            **identities, "scenario_sha256": digest(scenario_path) if scenario_path else None,
            "task_set": task_ids, "robot_capabilities": capabilities if capabilities else None,
            "disturbance": {"description": result.get("disturbances", result.get("disturbance")),
                            "bed": scenario.get("bed_experiment")},
            "weights": weights, "clock_verified": epoch is not None,
        },
        "availability": {"measured_positions": bool(samples), "future_path_geometry": bool(paths),
                         "plan_task_schedule": bool(plans or planning_records), "resource_history": bool(resources),
                         "event_lifecycle": bool(semantic), "commitment_evidence": bool(commitments or any(p.get("prefixes") is not None for p in plans)),
                         "semantic_room_polygons": False, "rgb_evidence": bool(media),
                         "synchronized_video": False, "execution_thresholds": bool(failure and failure["thresholds"])},
    }
    unknown = []
    payload = clean(payload, unknown)
    payload["nonfinite_fields"] = unknown
    from .explanations import explain
    payload["explanation"] = clean(explain(root, name, folder, result, payload, scenario_path))
    payload["comparison_signature"]["event_input"] = {
        "source": payload["explanation"]["metadata"]["event_source"],
        "source_media": [{key: (episode.get("review") or {}).get(key) for key in ("video", "source", "source_sha256")} for episode in semantic],
        "event": (scenario.get("event") or {}),
        "review_result": next((episode.get("review", {}).get("result") for episode in semantic
                               if isinstance(episode.get("review"), dict)), None),
    }
    payload["comparison_signature"]["task_constraints"] = {
        job: {field: task["definition"].get(field) for field in
              ("anchor", "duration", "capabilities", "dependencies", "resources", "release", "deadline")}
        for job, task in payload["explanation"]["tasks"].items()
    }
    return payload, {"offsets": offsets, "trace": trace}


def load_run(root, name):
    folder, result_path = resolve_run(root, name)
    signature_paths = [result_path, folder / "trace.jsonl", folder / "runtime_scenario.json",
                       folder / "source_manifest.json", folder / "review.json"]
    signature = tuple((str(path), path.stat().st_mtime_ns, path.stat().st_size)
                      for path in signature_paths if path.is_file())
    key = (str(Path(root).resolve()), name)
    with _LOCK:
        old = _CACHE.get(key)
        if old and old["signature"] == signature:
            _CACHE.move_to_end(key)
            return old["payload"]
        payload, internal = load_uncached(Path(root), name, (folder, result_path))
        _CACHE[key] = {"signature": signature, "payload": payload, **internal}
        _CACHE.move_to_end(key)
        while len(_CACHE) > CACHE_LIMIT:
            _CACHE.popitem(last=False)
        return payload


def raw_line(root, name, line):
    load_run(root, name)
    key = (str(Path(root).resolve()), name)
    with _LOCK:
        entry = _CACHE[key]
        number = int(line)
        if number < 1 or number > len(entry["offsets"]):
            raise ValueError("原始日志行超出范围")
        with entry["trace"].open("rb") as stream:
            stream.seek(entry["offsets"][number - 1])
            text = stream.readline().decode("utf-8", errors="replace")
        return {"run": name, "path": str(entry["trace"]), "line": number,
                "raw_text": text, "timestamps_modified": False}


def paged_events(root, name, query="", page=0, size=80):
    payload = load_run(root, name)
    size = max(1, min(200, int(size)))
    page = max(0, int(page))
    query = query.casefold()
    rows = payload["events"]
    if query:
        rows = [row for row in rows if query in json.dumps(row, ensure_ascii=False).casefold()]
    return {"rows": rows[page * size:(page + 1) * size], "total": len(rows), "page": page, "page_size": size}


def offline_rows(root):
    path = Path(root) / "verification/repair_methods_2026-11-18_e1/paired_02/rows.json"
    rows = read_json(path, [])
    if not isinstance(rows, list):
        raise ValueError("离线实验索引格式不受支持")
    return clean({"kind": "offline_synthetic_task_level", "source": provenance(path),
                  "rows": rows, "limits": "36 constructed inputs, 5 methods; not physical Nav2 execution or iid sampling."})
