"""Read-only semantic explanations. Labels come from fields/uses, never ID abbreviations."""
from __future__ import annotations
import ast
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import re

ROLE_NAMES = {
    "patrol": ("巡逻服务", "Patrol service"), "routine_stock_check": ("例行库存检查", "Routine stock check"),
    "verify": ("事件核验", "Event verification"), "monitor": ("持续监护", "Continuous monitoring"),
    "pickup": ("物资取货", "Supply pickup"), "deliver": ("物资交付", "Supply delivery"),
    "exit": ("返场移动", "Return movement"),
}
STRATEGY_NAMES = {
    "local_impact": "承诺保护下的局部影响修复", "full_warm": "热启动全量重规划",
    "retained_milp": "保留计划 MILP", "fixed_structure": "固定结构重定时",
    "fixed_owner": "固定归属重定时", "local_current": "原部署局部修复",
    "local_no_seed_gate": "无种子门槛的离线诊断局部方法",
}
_METADATA_CACHE = {}
_RESEARCH_CATALOG_CACHE = None


def research_catalog():
    """Load the human-reviewed display catalog without changing raw run discovery."""
    global _RESEARCH_CATALOG_CACHE
    if _RESEARCH_CATALOG_CACHE is not None:
        return _RESEARCH_CATALOG_CACHE
    path = Path(__file__).resolve().parents[2] / "docs" / "clinic_research_catalog.json"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        value = {"schema": "clinic-research-catalog/v1", "primary": [], "supporting": [],
                 "name_rule": {}}
    if not isinstance(value, dict):
        value = {"schema": "clinic-research-catalog/v1", "primary": [], "supporting": [],
                 "name_rule": {}}
    value.setdefault("primary", [])
    value.setdefault("supporting", [])
    value.setdefault("name_rule", {})
    _RESEARCH_CATALOG_CACHE = value
    return value


def research_entry(run_id):
    for entry in research_catalog().get("primary", []):
        if entry.get("run_id") == run_id:
            return entry
    return None


def presentation_metadata(run_id, debug_confirmed=False):
    """Return explicit, human-reviewed fields for a runnable research record."""
    entry = research_entry(run_id)
    if not entry:
        return {"primary_research": False, "research_catalog_key": None,
                "presentation_status": "历史记录；未列入默认研究目录",
                "listing_group": "engineering_probe" if debug_confirmed else "historical_development",
                "listing_reason": ("运行记录显式标记为工程探针：默认隐藏但原始结果保留。" if debug_confirmed else
                                   "未列入当前研究主展示目录；保留为历史开发、资格、失败或诊断证据，可在全部历史记录中审计。")}
    return {
        "primary_research": True,
        "listing_group": "core_research",
        "listing_reason": "已人工审核并列入当前研究主展示目录。",
        "research_catalog_key": entry.get("key"),
        "research_content": entry.get("research_content", []),
        "presentation_name_zh": entry.get("display_name_zh"),
        "presentation_short_name_zh": entry.get("short_name_zh"),
        "research_roles": entry.get("roles"),
        "research_scene": entry.get("scene"),
        "research_task_plan": entry.get("task_plan"),
        "research_event_insertion": entry.get("event_insertion"),
        "research_validates": entry.get("validates"),
        "evidence_level": entry.get("evidence_level"),
        "presentation_status": entry.get("status_display"),
        "catalog_source": entry.get("source"),
    }


def number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def read(path, default=None):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return default


def ref(path, field, line=None):
    path = Path(path)
    result = {"path": str(path), "field": field}
    if path.is_file():
        result["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    if line is not None:
        result["line"] = line
    return result


def saved_problems(folder, result):
    rows = []
    for index, plan in enumerate(result.get("planning_records") or []):
        if not isinstance(plan, dict):
            continue
        candidate = Path(plan.get("problem_path") or "/NONEXISTENT")
        if candidate.is_file() and candidate.resolve().is_relative_to(folder.resolve()):
            problem = read(candidate, {}) or {}
            source = candidate
        else:
            problem = (plan.get("solver") or {}).get("selected_problem") or {}
            source = folder / ("result.json" if (folder / "result.json").is_file() else "summary.json")
        rows.append({"index": index, "record": plan, "problem": problem, "source": str(source)})
    return rows


def task_definitions(result, problems):
    definitions = {}
    sources = {}
    for entry in problems:
        for job, spec in (entry["problem"].get("tasks") or {}).items():
            if isinstance(spec, dict):
                definitions[job] = spec
                sources[job] = {"path": entry["source"], "field": "$.tasks." + job}
    for job, spec in (result.get("tasks") or {}).items() if isinstance(result.get("tasks"), dict) else []:
        if isinstance(spec, dict):
            definitions[job] = spec
            sources[job] = {"path": "result", "field": "$.tasks." + job}
    return definitions, sources


def task_dictionary(result, payload, problems):
    definitions, sources = task_definitions(result, problems)
    records = payload["records"]
    jobs = set(definitions) | {r.get("job_id") for r in records if r.get("job_id")}
    for version in payload.get("plan_versions", []):
        jobs.update((version.get("plan") or {}).get("owners", {}))
    output = {}
    for job in sorted(jobs):
        spec = definitions.get(job, {})
        observed = next((r for r in records if r.get("job_id") == job), {})
        role = spec.get("service_role") or spec.get("kind") or observed.get("role")
        zh, en = ROLE_NAMES.get(role, ("未分类任务", "Unclassified task"))
        cycle, waypoint, nominal = spec.get("cycle_id"), spec.get("waypoint"), spec.get("nominal_owner")
        prefixes = []
        prefixes_en = []
        if isinstance(cycle, int):
            prefixes.append("第" + str(cycle + 1) + "周期")
            prefixes_en.append("Cycle " + str(cycle + 1))
        if nominal is not None:
            prefixes.append("预设" + str(nominal).upper() + "任务通道")
            prefixes_en.append("Preassigned " + str(nominal).upper() + " task channel")
        if isinstance(waypoint, int):
            prefixes.append("第" + str(waypoint) + "站")
            prefixes_en.append("Stop " + str(waypoint))
        protocol_id = spec.get("protocol_task_id")
        event_id = protocol_id.split(":", 1)[0] if isinstance(protocol_id, str) and ":" in protocol_id else None
        first = next((v for v in payload["plan_versions"] if job in (v.get("plan") or {}).get("owners", {})), None)
        baseline_owner = first["plan"]["owners"].get(job) if first else None
        final = next((v for v in reversed(payload["plan_versions"]) if job in (v.get("plan") or {}).get("owners", {})), None)
        plan_owner = final["plan"]["owners"].get(job) if final else None
        output[job] = {
            "job_id": job, "task_id": observed.get("task_id"), "display_name_zh": " · ".join(prefixes + [zh]),
            "display_name_en": " · ".join(prefixes_en + [en]), "task_type": role,
            "batch": cycle, "waypoint": waypoint, "event_id": event_id, "protocol_task_id": protocol_id,
            "nominal_owner": nominal, "original_owner": nominal,
            "first_recorded_plan_owner": baseline_owner, "last_recorded_plan_owner": plan_owner,
            "actual_executor": observed.get("robot"), "target_node": spec.get("anchor") or observed.get("anchor"),
            "target": observed.get("target") or spec.get("location"), "capabilities": spec.get("capabilities"),
            "phase_recorded": observed.get("status"), "plan_revision": observed.get("plan_revision"),
            "actual_reassigned_from_nominal": nominal != observed["robot"] if nominal and observed.get("robot") else None,
            "source": sources.get(job, {"path": "result", "field": "$.records"}),
            "name_rule": "Structured cycle_id/waypoint/nominal_owner/service_role only; no owner inferred from ID.",
            "definition": spec,
        }
    return output


def node_registry(payload, scenario, scenario_path, tasks):
    nodes = {}
    for node_id, coords in (payload.get("anchors") or {}).items():
        if not isinstance(coords, list) or len(coords) < 2:
            continue
        nodes[node_id] = {
            "id": node_id, "display_name_zh": "注册位置 " + node_id, "display_name_en": "Registered location " + node_id,
            "categories": [], "coordinate": coords, "frame": "map", "static_registered": scenario_path is not None,
            "event_generated_coordinate": False if scenario_path else None, "service_point": False,
            "navigation_topology_point": None, "candidate_approach_point": False, "related_tasks": [],
            "capabilities": [], "sources": [{"path": str(scenario_path) if scenario_path else "result.records",
                                           "field": "$.anchors." + node_id if scenario_path else "target/anchor"}],
            "reachability": {"status": "NOT_RECORDED", "evidence": [], "scope": "finite saved observations only"},
            "coordinate_origin": "saved scenario registration; acquisition method not independently recorded",
        }
    def use(node, kind, source, job=None, capability=None):
        if node not in nodes:
            return
        row = nodes[node]
        if kind not in row["categories"]:
            row["categories"].append(kind)
        if source not in row["sources"]:
            row["sources"].append(source)
        if job and job not in row["related_tasks"]:
            row["related_tasks"].append(job)
        for value in capability or []:
            if value not in row["capabilities"]:
                row["capabilities"].append(value)
    for job, task in tasks.items():
        spec = task["definition"]
        source = task["source"]
        anchor = task["target_node"]
        if anchor in nodes:
            use(anchor, "service" if task["task_type"] != "exit" else "return_goal", source, job, task["capabilities"])
            nodes[anchor]["service_point"] = task["task_type"] != "exit"
        for key, kind in (("entry_anchor", "entry"), ("clear_anchor", "clear")):
            use(spec.get(key), kind, {**source, "subfield": key}, job)
    for service, phases in (scenario.get("resource_phases") or {}).items():
        for field, kind in (("entry", "entry"), ("clear", "clear")):
            node = phases.get(field)
            use(node, kind, {"path": str(scenario_path), "field": "$.resource_phases." + service + "." + field})
            if node in nodes and node != service:
                nodes[node]["display_name_zh"] = service + (" 服务入口 " if kind == "entry" else " 清空停靠位 ") + node
    for nominal, mapping in (scenario.get("normal_clear_overrides") or {}).items():
        for service, node in mapping.items():
            use(node, "clear_override", {"path": str(scenario_path), "field": "$.normal_clear_overrides." + nominal + "." + service})
            if node in nodes:
                nodes[node]["display_name_zh"] = service + " 清空停靠位 " + node + "（名义" + nominal.upper() + "通道）"
    for robot, node in (scenario.get("starts") or {}).items():
        use(node, "robot_start", {"path": str(scenario_path), "field": "$.starts." + robot})
    for role, node in ((scenario.get("event") or {}).get("services") or {}).items():
        use(node, "event_registered_service", {"path": str(scenario_path), "field": "$.event.services." + role})
        if node in nodes:
            nodes[node]["candidate_approach_point"] = True
    for row in nodes.values():
        if row["display_name_zh"].startswith("注册位置") and row["service_point"]:
            role_set = {tasks[job]["task_type"] for job in row["related_tasks"]}
            description = next((ROLE_NAMES[role][0] for role in ("verify", "monitor", "deliver", "pickup")
                                if role in role_set), "常态服务")
            row["display_name_zh"] = description + "位置 " + row["id"]
        for index, record in enumerate(payload["records"]):
            arrival = record.get("anchor") == row["id"] and number(record.get("stable_at"))
            gate = record.get("gate_anchor") == row["id"] and number(record.get("gate_arrival"))
            clear = record.get("clear_anchor") == row["id"] and number(record.get("clear_at"))
            if arrival or gate or clear:
                row["reachability"]["status"] = "OBSERVED_ARRIVAL_IN_THIS_RUN"
                row["reachability"]["evidence"].append({"source": "$.records[" + str(index) + "]",
                    "task_id": record.get("task_id"), "robot": record.get("robot"),
                    "kind": "service" if arrival else "entry" if gate else "clear"})
    return list(nodes.values())


def event_associations(payload, task_dict, problems):
    output = {}
    for episode in payload.get("semantic_events", []):
        event_id = episode["id"]
        jobs = {job for job, task in task_dict.items() if task["event_id"] == event_id}
        # Protocol tasks explicitly bind role to EventEpisode; only match definitions/observed job IDs when that binding exists.
        bindings = (episode.get("final") or {}).get("tasks") or {}
        for protocol in bindings.values():
            for record in payload["records"]:
                if record.get("role") == protocol.get("role") and record.get("job_id") in task_dict:
                    definition = task_dict[record["job_id"]]["definition"]
                    if definition.get("protocol_task_id") == protocol.get("task_id"):
                        jobs.add(record["job_id"])
        rows = []
        for entry in problems:
            index, record, problem = entry["index"], entry["record"], entry["problem"]
            solver_plan = (record.get("solver") or {}).get("plan") or {}
            version = next((v for v in payload["plan_versions"]
                            if number(record.get("returned_at")) and abs(v["at"] - record["returned_at"]) < .00001), None)
            planned = set(solver_plan.get("owners", {})) | set((version or {}).get("plan", {}).get("owners", {}))
            explicit = set(problem.get("tasks") or {})
            locked = set()
            for prefix in (problem.get("prefixes") or {}).values():
                locked.update(prefix.get("jobs") or [])
            matched = sorted(jobs & (planned | explicit | locked))
            if matched:
                rows.append({"plan_index": index, "stage": record.get("stage"), "requested_at": record.get("requested_at"),
                             "returned_at": record.get("returned_at"), "committed_at": version.get("at") if version else None,
                             "line": version.get("line") if version else None, "related_jobs": matched,
                             "relation": "explicit task/protocol IDs present in saved plan, input or protected prefix",
                             "problem_source": entry["source"]})
        verify_jobs = {job for job in jobs if task_dict.get(job, {}).get("task_type") == "verify"}
        first = next((row for row in rows if set(row["related_jobs"]) & verify_jobs), None)
        output[event_id] = {
            "event_id": event_id, "related_jobs": sorted(jobs), "planning": rows, "first_verification_plan": first,
            "excluded_initial_normal": [index for index, record in enumerate(payload["planning_records"])
                                       if record.get("stage") == "normal" and index not in {r["plan_index"] for r in rows}],
            "source": "saved task protocol IDs + plan/input membership; never global first plan",
        }
    return output


def code_evidence(folder):
    sources = {}
    for relative in ("tools/dense_tasks.py", "tools/aligned_contract.py", "tools/bed_contract.py",
                     "tools/bed_solver.py", "support/clinic_runtime/episode.py",
                     "tools/run_dense_episode.py", "tools/run_aligned_episode.py", "tools/tb4_io.py"):
        path = folder / "source" / relative
        if path.is_file():
            sources[relative] = {"path": str(path), "text": path.read_text(), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    return sources


def solver_log_info(folder, record):
    paths = []
    solver = record.get("solver") or {}
    for attempt in solver.get("attempts") or []:
        paths.extend(attempt.get("cbc_logs") or [])
    logs = []
    for filename in paths:
        path = Path(filename)
        if not path.is_file() or not path.resolve().is_relative_to(folder.resolve()):
            continue
        text = path.read_text(errors="replace")
        limit = re.search(r"-sec\s+([.\d]+)", text)
        wall = re.search(r"Time \(Wallclock seconds\):\s*([.\d]+)", text)
        termination = re.search(r"^Result - (.+)$", text, re.M)
        logs.append({"source": ref(path, "CBC original log"), "seconds_argument": float(limit[1]) if limit else None,
                     "cbc_wall_seconds": float(wall[1]) if wall else None,
                     "termination": termination[1].strip() if termination else None,
                     "stopped_on_time_limit": "Result - Stopped on time limit" in text})
    return logs


def repair_diagnostics(payload, result, folder, problems, code):
    output = []
    budget = None
    budget_source = None
    solver_code = code.get("tools/bed_solver.py")
    if solver_code:
        tree = ast.parse(solver_code["text"])
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "solve":
                defaults = dict(zip([arg.arg for arg in node.args.args][-len(node.args.defaults):], node.args.defaults))
                if isinstance(defaults.get("budget"), ast.Constant) and number(defaults["budget"].value):
                    budget = defaults["budget"].value
                    budget_source = {"path": solver_code["path"], "sha256": solver_code["sha256"],
                                     "line": node.lineno, "field": "solve(..., budget=...) frozen default"}
    for entry in problems:
        record, problem, index = entry["record"], entry["problem"], entry["index"]
        if record.get("stage") != "active_repair":
            continue
        solver = record.get("solver") or {}
        matching = next((d for d in payload.get("repair_decisions", [])
                         if isinstance(d, dict) and number(d.get("at"))
                         and abs(d["at"] - record["requested_at"]) < .00001), {})
        version = next((v for v in payload["plan_versions"]
                        if number(record.get("returned_at")) and abs(v["at"] - record["returned_at"]) < .00001), {})
        commits = version.get("at")
        after = [r for r in payload["records"] if number(commits) and number(r.get("begin")) and r["begin"] >= commits]
        dispatch = next((event for event in payload["events"] if number(commits) and number(event.get("at"))
                         and event["at"] >= commits and event.get("phase") == "navigation_requested"), None)
        first_dispatch = dispatch["at"] if dispatch else None
        changes = version.get("changes") or []
        scope = solver.get("scope") or {}
        free = scope.get("free")
        total = len(problem.get("tasks") or {})
        prefix_jobs = sorted({job for prefix in (problem.get("prefixes") or {}).values() for job in prefix.get("jobs") or []})
        logs = solver_log_info(folder, record)
        parts = (solver.get("validation") or {}).get("objective_parts") or {}
        output.append({
            "plan_index": index, "requested_at": record.get("requested_at"), "returned_at": record.get("returned_at"),
            "committed_at": commits, "first_recorded_dispatch_after_commit": first_dispatch,
            "dispatch_evidence": {"line": dispatch.get("_review_trace_line"), "phase": dispatch.get("phase")} if dispatch else None,
            "request_to_commit_sim": commits - record["requested_at"] if number(commits) and number(record.get("requested_at")) else None,
            "commit_to_dispatch_sim": first_dispatch - commits if number(first_dispatch) and number(commits) else None,
            "first_fully_validated_at": None, "first_fully_validated_note": "exact full-plan validation timestamp not recorded",
            "validated_seed_wall_upper_bound": solver.get("seed_seconds") if ((solver.get("seed_attempt") or {}).get("validation") or {}).get("passed") is True else None,
            "seed_time_note": "seed_seconds is an upper bound on seed preparation/validation completion, not the first valid timestamp",
            "end_to_end_wall_seconds": record.get("end_to_end_wall"), "solver_wrapper_wall_seconds": solver.get("planning_seconds"),
            "solver_status": solver.get("status"), "budget_seconds": budget, "budget_source": budget_source,
            "cbc_logs": logs, "budget_stop_recorded": any(log["stopped_on_time_limit"] for log in logs),
            "seed_objective": solver.get("seed_objective"), "objective": solver.get("objective"), "best_bound": solver.get("best_bound"),
            "seed_seconds": solver.get("seed_seconds"), "scope_expansions": solver.get("scope_expansions"),
            "released_tasks": free, "released_count": len(free) if isinstance(free, list) else None,
            "optimizable_suffix_tasks": sorted(problem.get("tasks") or {}), "suffix_count": total,
            "released_ratio": len(free) / total if isinstance(free, list) and total else None,
            "protected_prefix_tasks": prefix_jobs,
            "preserved_suffix": (solver.get("impact") or {}).get("preserved"),
            "impact": solver.get("impact"), "observation": matching.get("observation"),
            "trigger_reasons": matching.get("reasons"), "old_validation": matching.get("old_validation"),
            "coverage": matching.get("coverage"), "problem_source": entry["source"],
            "reassigned_tasks": [row["job"] for row in changes if row["reassigned"] is True],
            "reordered_tasks": [row["job"] for row in changes if row["order_changed"] is True],
            "retimed_tasks": [row["job"] for row in changes if row["time_changed"] is True],
            "weighted_change_parts": {key: parts.get(key) for key in ("owner", "shift", "adjacency")},
            "comparison_reference": "previous full saved committed version; new/disappearing tasks not counted as reassigned",
        })
    if output:
        for index, row in enumerate(output):
            row["request_interval_since_previous_sim"] = row["requested_at"] - output[index-1]["requested_at"] if index else None
            row["same_obstruction_origin_as_previous"] = (row.get("observation") or {}).get("blocked_since") == (output[index-1].get("observation") or {}).get("blocked_since") if index else None
    return output


def metadata(result, payload, run_id, source):
    event_count = len(payload.get("semantic_events") or [])
    phases = {event.get("phase") for event in payload.get("events", [])}
    model_frames = result.get("model_frames") or len(payload.get("model_samples") or [])
    probe = result.get("probe")
    strategy = payload.get("strategy", result.get("strategy", result.get("policy")))
    injected = "fall_event_injected" in phases
    visual = model_frames > 0 and (bool(payload.get("model_samples")) or any(e.get("review", {}).get("video") for e in payload.get("semantic_events", []) if e.get("review")))
    event_source = "真实视频回放模型候选" if visual else "执行器人工注入" if injected else "本轮无事件" if not event_count else "事件来源待核实"
    repair_count = sum(p.get("stage") == "active_repair" for p in payload.get("planning_records", []))
    if probe:
        category, en, prefix = "工程探针", "Engineering probe", "DEV"
    elif repair_count:
        category, en, prefix = "执行承诺与动态修复", "Commitment-aware dynamic repair", "PLN"
    elif visual and event_count:
        category, en, prefix = "视频驱动语义闭环", "Video-driven semantic loop", "SEM"
    elif event_count:
        category, en, prefix = "语义事件协同响应", "Semantic cooperative response", "PLN"
    elif payload.get("records"):
        category, en, prefix = "常态任务规划", "Routine task planning", "PLN"
    else:
        category, en, prefix = "未分类／待核实", "Unclassified / unverified", "DEV"
    status = "PASS" if result.get("passed") is True else "FAIL" if result.get("passed") is False else result.get("status") or "UNKNOWN"
    research = ([1] if visual else []) + ([2] if event_count else []) + ([3] if payload.get("records") or payload.get("planning_records") else [])
    code = prefix + "-" + hashlib.sha256(run_id.encode()).hexdigest()[:7].upper()
    info = {"run_id": run_id, "display_name_zh": category + " · " + STRATEGY_NAMES.get(strategy, "策略待核实") + " · " + str(len(payload.get("records") or [])) + "任务",
            "display_name_en": en + " · " + str(strategy or "unverified") + " · " + str(len(payload.get("records") or [])) + " tasks",
            "experiment_code": code, "code_rule": "display-only stable ID hash, not a renamed folder or chronological repeat index",
            "research_content": research, "scenario_type": category, "strategy_raw": strategy,
            "strategy_display": STRATEGY_NAMES.get(strategy, "策略待核实"),
            "execution_mode": "保存的导航／服务回放" if payload.get("records") else "未记录／待核实",
            "event_source": event_source, "disturbance_type": result.get("disturbances", result.get("disturbance")),
            "task_count": len(payload.get("records") or []),
            "robot_count": len({r.get("robot") for r in payload.get("records", []) if r.get("robot")}),
            "result_status": status, "repeat_index": result.get("repeat_index"),
            "comparison_group": None, "configuration_source": source, "evidence_completeness": payload.get("availability", {}),
            "debug_confirmed": bool(probe), "classification_source": "recorded fields and trace phases, not directory name"}
    info.update(presentation_metadata(run_id, bool(probe)))
    if info.get("primary_research"):
        # The catalog name is the default human-facing label; the raw parser name
        # remains available in audit mode and in the source record.
        info["display_name_zh"] = info["presentation_name_zh"]
        info["scenario_type"] = info["presentation_short_name_zh"] or info["scenario_type"]
    return info


def explain(root, name, folder, result, payload, scenario_path):
    problems = saved_problems(folder, result)
    tasks = task_dictionary(result, payload, problems)
    result_source = folder / ("result.json" if (folder / "result.json").is_file() else "summary.json")
    for task in tasks.values():
        if task["source"]["path"] == "result":
            task["source"]["path"] = str(result_source)
    nodes = node_registry(payload, payload.get("scenario") or {}, scenario_path, tasks)
    hashes = {}
    for source in [task["source"] for task in tasks.values()] + [source for node in nodes for source in node["sources"]]:
        path = Path(source.get("path", ""))
        if path.is_file() and (path.resolve().is_relative_to(folder.resolve()) or path.resolve().is_relative_to(root.resolve())):
            key = str(path)
            if key not in hashes:
                hashes[key] = hashlib.sha256(path.read_bytes()).hexdigest()
            source["sha256"] = hashes[key]
    associations = event_associations(payload, tasks, problems)
    code = code_evidence(folder)
    scenario = payload.get("scenario") or {}
    final_event = payload.get("semantic_final") or {}
    travel = next(({"matrix": entry["problem"]["travel_times"], "source": entry["source"],
                    "field": "$.travel_times", "unit": "model seconds, not future geometric paths",
                    "role": "saved model lookup matrix"} for entry in problems if isinstance(entry["problem"].get("travel_times"), dict)), None)
    event_targets = []
    for episode in payload.get("semantic_events", []):
        event = ((episode.get("final") or {}).get("event") or {})
        space = event.get("space") or {}
        event_id = event.get("event_id") or episode.get("id")
        if not isinstance(space, dict) or not space:
            continue
        compiled = [{"task_id": task["job_id"], "role": task["task_type"],
                     "target_node": task["target_node"], "target": task["target"],
                     "spatial_source": task["definition"].get("spatial_source"),
                     "region": task["definition"].get("region")}
                    for task in tasks.values() if task.get("event_id") == event_id]
        provenance = space.get("provenance")
        if provenance == "video_source_registered":
            method = "视频源登记的区域位置；服务任务目标由区域注册表映射，不是从随机人体像素在线估计的精确落地点。"
        elif provenance == "sensor_estimated":
            method = "来自传感器估计的位置；需结合该运行保存的深度、相机参数、TF、时间戳和误差证据审查。"
        else:
            method = "位置来源见原始空间证据；不能仅凭地图坐标判断其为传感器估计。"
        event_targets.append({"event_id": event_id, "lifecycle": event.get("lifecycle"),
                              "event_xy": space.get("event_xy"), "frame": space.get("frame"),
                              "provenance": provenance, "registration_id": space.get("registration_id"),
                              "service_points": space.get("service_points") or {},
                              "sensor_estimate": space.get("sensor_estimate"),
                              "compiled_task_targets": compiled, "interpretation": method})
    task_edges = []
    seen = set()
    for job, task in tasks.items():
        for dependency in task["definition"].get("dependencies") or []:
            key = (dependency, job, "strict_precedence")
            if key not in seen:
                task_edges.append({"from": dependency, "to": job, "kind": "strict_precedence", "source": task["source"]})
                seen.add(key)
        for resource in task["definition"].get("resources") or []:
            task_edges.append({"from": "resource:" + resource, "to": job, "kind": "resource_requirement", "source": task["source"]})
    for episode in payload.get("semantic_events", []):
        protocol = (episode.get("final") or {}).get("tasks") or {}
        by_protocol = {task.get("protocol_task_id"): job for job, task in tasks.items() if task.get("protocol_task_id")}
        for task_id, task in protocol.items():
            job = by_protocol.get(task_id, task_id)
            for dep in task.get("completion_dependencies") or []:
                source_job = by_protocol.get(dep, dep)
                key = (source_job, job, "strict_precedence")
                if key not in seen:
                    task_edges.append({"from": source_job, "to": job, "kind": "strict_precedence", "source": "result.protocol.tasks." + task_id})
                    seen.add(key)
            if "monitor_active" in (task.get("runtime_guards") or []):
                task_edges.append({"from": "guard:monitor_active", "to": job, "kind": "continuous_monitor_guard", "source": "result.protocol.tasks." + task_id + ".runtime_guards"})
    result_path = folder / ("result.json" if (folder / "result.json").is_file() else "summary.json")
    info = metadata(result, payload, name, str(scenario_path or result_path))
    injected = any(e.get("phase") == "fall_event_injected" for e in payload["events"])
    has_nav = any(isinstance(attempt, dict) and "FollowPath" in str(attempt.get("nav_kind"))
                  for record in payload["records"] for attempt in record.get("navigation_attempts") or [])
    path_report = {
        "travel_prior_description": scenario.get("travel_prior"), "phase_model": scenario.get("phase_model"),
        "travel_matrix": travel, "euclidean_scope": "bed_contract.project uses Euclidean remaining-distance/.22+12 for commitment forecasting; not the saved route travel matrix" if "tools/bed_contract.py" in code else "NOT_VERIFIED",
        "capability_constraints": "task.capabilities / robot.capabilities are separate assignment eligibility constraints; not evidence of per-robot geometric travel matrices",
        "resource_constraints": "saved resource occupancy and buffers are separate constraints; static travel matrix is not online obstacle prediction",
        "nav2_interface": "ComputePathToPose goal coordinate → approved FollowPath → Spin where recorded" if has_nav else "inspect saved navigation action/source; continuous-path interface not verified here",
        "future_geometry_saved": bool(payload["planned_paths"]),
        "grid_sandbox_connected": False, "grid_sandbox_note": "viewer-only A* draft, no MILP/Nav2/ROS dispatch integration",
        "candidate_generation": "registered scenario anchors / event service points" if scenario.get("event") or (final_event.get("space") or {}).get("service_points") else "NOT_RECORDED",
        "candidate_origin": "scripted event registration" if injected else (final_event.get("space") or {}).get("provenance"),
        "event_targets": event_targets,
        "event_target_policy": "Task destinations are resolved from registered event-region service points unless a run explicitly records sensor_estimated evidence; the event coordinate itself is not automatically a navigation goal.",
        "qualification_note": "space.valid, temporal position_valid, navigation observations and external qualification are different checks; do not collapse into one PASS",
        "unregistered_requested_ids": [node for node in ("CTL", "W1", "W2", "W3") if node not in {r["id"] for r in nodes}],
        "source_code": [{key: value for key, value in item.items() if key != "text"} for item in code.values()],
    }
    return {"schema": "clinic-review-explanation/v1", "metadata": info, "nodes": nodes, "tasks": tasks,
            "task_edges": task_edges, "event_planning": associations,
            "repair_diagnostics": repair_diagnostics(payload, result, folder, problems, code),
            "path_report": path_report,
            "qualification_fields": {
                "robot_localization_source": result.get("localization"),
                "human_space_valid": (final_event.get("space") or {}).get("valid"),
                "human_position_valid_at_final": final_event.get("position_valid"),
                "robot_localization_valid": result.get("localization", {}).get("valid") if isinstance(result.get("localization"), dict) else None,
                "meaning": "robot localization and human/event spatial registration are different sources; temporal validity is not identical to structural space.valid",
            }}



def catalog_metadata(root, descriptor_map):
    """Cheap field-backed catalog; never classify a strategy from a directory name."""
    rows = []
    for name, (folder, result_path) in descriptor_map.items():
        signature = tuple((str(path), path.stat().st_mtime_ns, path.stat().st_size) for path in
                          (result_path, folder / "trace.jsonl", folder / "review.json") if path.is_file())
        key = (str(folder), signature)
        if key in _METADATA_CACHE:
            rows.append(_METADATA_CACHE[key])
            continue
        result = read(result_path, {}) or {}
        if not isinstance(result, dict):
            result = {}
        protocol = result.get("protocol") or {}
        event = protocol.get("event") if isinstance(protocol, dict) else None
        review = read(folder / "review.json", {}) or {}
        records = result.get("records") or []
        records = records if isinstance(records, list) else []
        phases = []
        if event and not result.get("model_frames") and (folder / "trace.jsonl").is_file():
            with (folder / "trace.jsonl").open("rb") as stream:
                for line in stream:
                    if b'"phase": "fall_event_injected"' in line or b'"phase":"fall_event_injected"' in line:
                        phases.append({"phase": "fall_event_injected"})
                        break
        stub = {"records": records, "planning_records": result.get("planning_records") or [],
                "semantic_events": [{"review": review}] if event else [], "events": phases,
                "model_samples": [], "availability": {}}
        entry = metadata(result, stub, name, str(result_path))
        _METADATA_CACHE[key] = entry
        rows.append(entry)
    return rows
