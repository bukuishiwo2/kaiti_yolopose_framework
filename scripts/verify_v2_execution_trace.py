#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


def verify_trace(
    rows: list[dict[str, Any]],
    *,
    required_task_prefixes: tuple[str, ...] = (),
    require_terminal_completed: bool = False,
) -> dict[str, Any]:
    statuses = [
        row.get("payload", {})
        for row in rows
        if row.get("topic") == "/planning/executor_status"
        and isinstance(row.get("payload"), dict)
    ]
    plans = [
        row.get("payload", {})
        for row in rows
        if row.get("topic") == "/planning/plan" and isinstance(row.get("payload"), dict)
    ]
    errors: list[str] = []
    if not statuses:
        errors.append("missing_executor_status")
    if not plans:
        errors.append("missing_plan")

    latest_history: list[dict[str, Any]] = []
    completed_keys: set[tuple[str, str, int]] = set()
    for status in statuses:
        history = status.get("dispatched_goal_history", [])
        if isinstance(history, list) and len(history) >= len(latest_history):
            latest_history = [item for item in history if isinstance(item, dict)]
        for item in status.get("completed_step_keys", []):
            if isinstance(item, dict):
                completed_keys.add(
                    (
                        str(item.get("task_id", "")),
                        str(item.get("step_name", "")),
                        int(item.get("attempt", 1)),
                    )
                )

    dispatch_keys = [
        (
            str(item.get("task_id", "")),
            str(item.get("step_name", "")),
            int(item.get("attempt", 1)),
        )
        for item in latest_history
    ]
    duplicate_keys = []
    for key, count in Counter(dispatch_keys).items():
        if count <= 1:
            continue
        retry_indexes = [
            int(item.get("nav_retry_index", 0))
            for item, item_key in zip(latest_history, dispatch_keys)
            if item_key == key
        ]
        if len(set(retry_indexes)) != count or min(retry_indexes) != 0:
            duplicate_keys.append(key)
    duplicate_keys.sort()
    if duplicate_keys:
        errors.append("duplicate_task_step_dispatch")
    missing_dispatch = sorted(completed_keys.difference(dispatch_keys))
    if missing_dispatch:
        errors.append("completed_step_without_dispatch")

    plan_revisions = [int(plan.get("revision", -1)) for plan in plans]
    if any(current < previous for previous, current in zip(plan_revisions, plan_revisions[1:])):
        errors.append("non_monotonic_plan_revision")
    dispatched_task_ids = [key[0] for key in dispatch_keys]
    missing_task_prefixes = [
        prefix
        for prefix in required_task_prefixes
        if not any(task_id.startswith(prefix + ":") for task_id in dispatched_task_ids)
    ]
    if missing_task_prefixes:
        errors.append("missing_required_task_dispatch")
    terminal_state = str(statuses[-1].get("planner_state", "")) if statuses else ""
    if require_terminal_completed and terminal_state != "completed":
        errors.append("execution_not_terminal_completed")

    return {
        "ok": not errors,
        "errors": errors,
        "plan_revisions": plan_revisions,
        "dispatch_sequence": [
            {
                "task_id": item.get("task_id"),
                "step_name": item.get("step_name"),
                "attempt": item.get("attempt", 1),
                "location_id": item.get("location_id"),
                "plan_revision": item.get("plan_revision"),
                "nav_retry_index": item.get("nav_retry_index", 0),
            }
            for item in latest_history
        ],
        "duplicate_keys": [list(key) for key in duplicate_keys],
        "completed_step_count": len(completed_keys),
        "nav_path_samples": sum(1 for row in rows if row.get("topic") == "/plan"),
        "amcl_pose_samples": sum(1 for row in rows if row.get("topic") == "/amcl_pose"),
        "missing_task_prefixes": missing_task_prefixes,
        "terminal_state": terminal_state,
    }


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"line {line_number} is not a JSON object")
        rows.append(value)
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description="Reject duplicate task-step Nav2 dispatches in a v2 trace.")
    parser.add_argument("trace", type=Path)
    parser.add_argument("--require-task-prefix", action="append", default=[])
    parser.add_argument("--require-terminal-completed", action="store_true")
    args = parser.parse_args()
    result = verify_trace(
        load_jsonl(args.trace),
        required_task_prefixes=tuple(args.require_task_prefix),
        require_terminal_completed=args.require_terminal_completed,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
