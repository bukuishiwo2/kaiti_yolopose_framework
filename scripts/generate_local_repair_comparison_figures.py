#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from xml.sax.saxutils import escape

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from kaiti_planning.local_repair import run_local_repair
from kaiti_planning.milp_solver import solve_milp
from kaiti_planning.models import load_problem_from_yaml
from kaiti_planning.replanner import build_resource_events_from_spatial_replay
from kaiti_planning.spatial_state import load_region_specs, load_spatial_replay_config


def _scale(value: float, min_value: float, max_value: float, start: float, length: float) -> float:
    if max_value <= min_value:
        return start
    ratio = (float(value) - float(min_value)) / (float(max_value) - float(min_value))
    return start + ratio * length


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _svg_header(width: int, height: int, title: str) -> list[str]:
    return [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        f'<title>{escape(title)}</title>',
        '<style>text{font-family:monospace;font-size:12px;fill:#1f2937} .small{font-size:11px;fill:#475569} .axis{stroke:#64748b;stroke-width:1} .grid{stroke:#cbd5e1;stroke-width:1;stroke-dasharray:4 4}</style>',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
    ]


def render_local_repair_comparison_gantt(
    *,
    baseline_assignments: list[dict[str, object]],
    full_assignments: list[dict[str, object]],
    local_assignments: list[dict[str, object]],
    full_modified_tasks: list[str],
    local_modified_tasks: list[str],
    trigger_time: float,
    affected_tasks: list[str],
    frozen_tasks: list[str],
    out_path: Path,
) -> None:
    width = 1320
    height = 520
    left = 130
    right = 40
    top = 78
    lane_h = 34
    lane_gap = 14
    group_gap = 24
    footer_h = 88
    timeline_w = width - left - right
    robots = ["R1", "R2", "R3"]
    plans = [
        ("baseline", baseline_assignments),
        ("full_replan@45", full_assignments),
        ("local_repair@45", local_assignments),
    ]
    task_palette = {
        "T1": "#93c5fd",
        "T2": "#a7f3d0",
        "T3": "#fca5a5",
        "T4": "#fcd34d",
        "T5": "#c4b5fd",
        "T6": "#fdba74",
        "T7": "#86efac",
    }
    max_time = max(float(item["finish"]) for assignments in (baseline_assignments, full_assignments, local_assignments) for item in assignments)
    affected_set = set(affected_tasks)
    frozen_set = set(frozen_tasks)
    full_modified_set = set(full_modified_tasks)
    local_modified_set = set(local_modified_tasks)

    svg = _svg_header(width, height, "Full-Replan vs LocalRepair gantt")
    svg.append('<text x="40" y="28" font-size="18">local repair comparison gantt: baseline vs full replanning vs local repair</text>')
    svg.append(f'<text class="small" x="40" y="48">trigger=t={trigger_time:.0f} corridor_H temporary_occupied | affected={escape(",".join(affected_tasks))} | frozen={escape(",".join(frozen_tasks))}</text>')

    for tick in range(0, int(max_time) + 1, 10):
        x = _scale(float(tick), 0.0, max_time, left, timeline_w)
        svg.append(f'<line class="grid" x1="{x:.1f}" y1="{top - 10}" x2="{x:.1f}" y2="{height - footer_h}"/>')
        svg.append(f'<text class="small" x="{x:.1f}" y="{height - footer_h + 22}" text-anchor="middle">{tick}</text>')
    trigger_x = _scale(float(trigger_time), 0.0, max_time, left, timeline_w)
    svg.append(f'<line x1="{trigger_x:.1f}" y1="{top - 16}" x2="{trigger_x:.1f}" y2="{height - footer_h}" stroke="#dc2626" stroke-width="2"/>')
    svg.append(f'<text class="small" x="{trigger_x + 6:.1f}" y="{top - 22}">trigger @ {trigger_time:.0f}</text>')

    for plan_idx, (label, assignments) in enumerate(plans):
        group_y = top + plan_idx * (len(robots) * (lane_h + lane_gap) + group_gap)
        svg.append(f'<text x="32" y="{group_y + 22}" font-size="15">{escape(label)}</text>')
        for robot_idx, robot in enumerate(robots):
            y = group_y + robot_idx * (lane_h + lane_gap)
            svg.append(f'<text x="{left - 16}" y="{y + 22}" text-anchor="end">{robot}</text>')
            svg.append(f'<rect x="{left}" y="{y}" width="{timeline_w}" height="{lane_h}" fill="#f8fafc" stroke="#e2e8f0"/>')
            for item in assignments:
                if str(item["robot"]) != robot:
                    continue
                task_id = str(item["task"])
                x1 = _scale(float(item["start"]), 0.0, max_time, left, timeline_w)
                x2 = _scale(float(item["finish"]), 0.0, max_time, left, timeline_w)
                color = task_palette.get(task_id, "#cbd5e1")
                stroke = "#475569"
                stroke_width = 1.2
                if task_id in affected_set:
                    stroke = "#b91c1c"
                    stroke_width = 2.4
                elif task_id in frozen_set:
                    stroke = "#0f766e"
                    stroke_width = 2.0
                dash = ""
                if (label == "full_replan@45" and task_id in full_modified_set) or (label == "local_repair@45" and task_id in local_modified_set):
                    dash = ' stroke-dasharray="5 3"'
                svg.append(
                    f'<rect x="{x1:.1f}" y="{y + 4}" width="{max(1.0, x2 - x1):.1f}" height="{lane_h - 8}" fill="{color}" stroke="{stroke}" stroke-width="{stroke_width}"{dash}/>'
                )
                svg.append(f'<text x="{(x1 + x2) / 2:.1f}" y="{y + 22}" text-anchor="middle">{task_id}</text>')

    legend_y = height - 56
    svg.append(f'<rect x="40" y="{legend_y - 16}" width="16" height="12" fill="#f8fafc" stroke="#0f766e" stroke-width="2"/>')
    svg.append(f'<text class="small" x="66" y="{legend_y - 6}">frozen task</text>')
    svg.append(f'<rect x="180" y="{legend_y - 16}" width="16" height="12" fill="#f8fafc" stroke="#b91c1c" stroke-width="2.4"/>')
    svg.append(f'<text class="small" x="206" y="{legend_y - 6}">affected task</text>')
    svg.append(f'<line x1="330" y1="{legend_y - 10}" x2="346" y2="{legend_y - 10}" stroke="#dc2626" stroke-width="2"/>')
    svg.append(f'<text class="small" x="356" y="{legend_y - 6}">resource trigger</text>')
    svg.append(f'<line x1="470" y1="{legend_y - 10}" x2="490" y2="{legend_y - 10}" stroke="#334155" stroke-width="2" stroke-dasharray="5 3"/>')
    svg.append(f'<text class="small" x="500" y="{legend_y - 6}">modified vs baseline</text>')
    svg.append("</svg>")
    _write(out_path, "\n".join(svg))


def render_local_repair_resource_timeline(
    *,
    state_segments: list[dict[str, object]],
    baseline_assignments: list[dict[str, object]],
    full_assignments: list[dict[str, object]],
    local_assignments: list[dict[str, object]],
    trigger_time: float,
    out_path: Path,
) -> None:
    width = 1280
    height = 360
    left = 160
    right = 40
    top = 70
    lane_h = 34
    lane_gap = 18
    footer_h = 66
    timeline_w = width - left - right
    max_time = max(
        max(float(item["end"]) for item in state_segments),
        max(float(item["finish"]) for assignments in (baseline_assignments, full_assignments, local_assignments) for item in assignments),
    )
    rows = [
        ("corridor_H state", None),
        ("baseline supply_point_S", baseline_assignments),
        ("full_replan supply_point_S", full_assignments),
        ("local_repair supply_point_S", local_assignments),
    ]
    state_palette = {"free": "#9bd3ae", "temporary_occupied": "#f6c177", "blocked": "#e76f51"}
    task_palette = {"T4": "#fcd34d", "T6": "#fdba74", "T7": "#86efac"}

    svg = _svg_header(width, height, "Local repair resource timeline")
    svg.append('<text x="40" y="28" font-size="18">local repair resource timeline: corridor_H and supply_point_S</text>')
    svg.append('<text class="small" x="40" y="48">resource trigger changes corridor_H at t=45; supply_point_S occupancy order reveals the difference between full replanning and local repair</text>')
    for tick in range(0, int(max_time) + 1, 10):
        x = _scale(float(tick), 0.0, max_time, left, timeline_w)
        svg.append(f'<line class="grid" x1="{x:.1f}" y1="{top - 10}" x2="{x:.1f}" y2="{height - footer_h}"/>')
        svg.append(f'<text class="small" x="{x:.1f}" y="{height - footer_h + 22}" text-anchor="middle">{tick}</text>')
    trigger_x = _scale(float(trigger_time), 0.0, max_time, left, timeline_w)
    svg.append(f'<line x1="{trigger_x:.1f}" y1="{top - 14}" x2="{trigger_x:.1f}" y2="{height - footer_h}" stroke="#dc2626" stroke-width="2"/>')
    svg.append(f'<text class="small" x="{trigger_x + 6:.1f}" y="{top - 18}">trigger @ {trigger_time:.0f}</text>')

    for idx, (label, assignments) in enumerate(rows):
        y = top + idx * (lane_h + lane_gap)
        svg.append(f'<text x="{left - 16}" y="{y + 22}" text-anchor="end">{escape(label)}</text>')
        svg.append(f'<rect x="{left}" y="{y}" width="{timeline_w}" height="{lane_h}" fill="#f8fafc" stroke="#e2e8f0"/>')
        if assignments is None:
            for item in state_segments:
                x1 = _scale(float(item["start"]), 0.0, max_time, left, timeline_w)
                x2 = _scale(float(item["end"]), 0.0, max_time, left, timeline_w)
                state = str(item["state"])
                color = state_palette.get(state, "#cbd5e1")
                svg.append(f'<rect x="{x1:.1f}" y="{y + 4}" width="{max(1.0, x2 - x1):.1f}" height="{lane_h - 8}" fill="{color}" stroke="#475569"/>')
                svg.append(f'<text x="{(x1 + x2) / 2:.1f}" y="{y + 22}" text-anchor="middle">{escape(state)}</text>')
        else:
            for item in assignments:
                if "supply_point_S" not in set(item.get("resources", [])):
                    continue
                task_id = str(item["task"])
                x1 = _scale(float(item["start"]), 0.0, max_time, left, timeline_w)
                x2 = _scale(float(item["finish"]), 0.0, max_time, left, timeline_w)
                color = task_palette.get(task_id, "#cbd5e1")
                svg.append(f'<rect x="{x1:.1f}" y="{y + 4}" width="{max(1.0, x2 - x1):.1f}" height="{lane_h - 8}" fill="{color}" stroke="#475569"/>')
                svg.append(f'<text x="{(x1 + x2) / 2:.1f}" y="{y + 22}" text-anchor="middle">{task_id}</text>')
    svg.append("</svg>")
    _write(out_path, "\n".join(svg))


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate SVG comparison figures for local repair.")
    parser.add_argument("--config", required=True)
    parser.add_argument("--backend", default="pulp")
    parser.add_argument("--regions", required=True)
    parser.add_argument("--spatial-replay", required=True)
    parser.add_argument("--out-dir", default="reports/figures/local_repair_comparison_2026-06-23")
    args = parser.parse_args()

    problem = load_problem_from_yaml(Path(args.config))
    region_specs = load_region_specs(Path(args.regions))
    replay_cfg = load_spatial_replay_config(Path(args.spatial_replay))
    resource_events, spatial_snapshots = build_resource_events_from_spatial_replay(
        problem,
        replay_cfg=replay_cfg,
        region_specs=region_specs,
    )
    result = run_local_repair(
        problem,
        backend=args.backend,
        resource_events=resource_events,
        spatial_snapshots_by_time=spatial_snapshots,
    )
    baseline = solve_milp(problem, backend=args.backend, plan_kind="static")
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    full_modified_tasks = []
    local_modified_tasks = []
    baseline_map = {item.task: item for item in baseline.assignments}
    for assignment in result["full_replan"]["assignments"]:
        base = baseline_map.get(assignment["task"])
        if base is None:
            full_modified_tasks.append(str(assignment["task"]))
            continue
        if base.robot != assignment["robot"] or round(base.start, 3) != round(float(assignment["start"]), 3):
            full_modified_tasks.append(str(assignment["task"]))
    for assignment in result["local_repair"]["assignments"]:
        base = baseline_map.get(assignment["task"])
        if base is None:
            local_modified_tasks.append(str(assignment["task"]))
            continue
        if base.robot != assignment["robot"] or round(base.start, 3) != round(float(assignment["start"]), 3):
            local_modified_tasks.append(str(assignment["task"]))
    baseline_assignments = [{
        "robot": item.robot,
        "task": item.task,
        "start": item.start,
        "finish": item.finish,
        "location": item.location,
        "resources": item.resources,
        "energy_after": item.energy_after,
    } for item in baseline.assignments]
    ordered_times = sorted(spatial_snapshots)
    state_segments = []
    for idx, time_value in enumerate(ordered_times):
        snapshot = spatial_snapshots[time_value]
        corridor = snapshot.region_states["corridor_H"]
        end_value = ordered_times[idx + 1] if idx + 1 < len(ordered_times) else max(float(item["finish"]) for item in baseline_assignments)
        state_segments.append(
            {
                "start": float(time_value),
                "end": float(end_value),
                "state": str(corridor["state"]),
            }
        )

    render_local_repair_comparison_gantt(
        baseline_assignments=baseline_assignments,
        full_assignments=result["full_replan"]["assignments"],
        local_assignments=result["local_repair"]["assignments"],
        full_modified_tasks=full_modified_tasks,
        local_modified_tasks=local_modified_tasks,
        trigger_time=float(result["trigger_time"]),
        affected_tasks=list(result["affected_tasks"]),
        frozen_tasks=list(result["frozen_tasks"]),
        out_path=out_dir / "local_repair_vs_full_replan_gantt.svg",
    )
    render_local_repair_resource_timeline(
        state_segments=state_segments,
        baseline_assignments=baseline_assignments,
        full_assignments=result["full_replan"]["assignments"],
        local_assignments=result["local_repair"]["assignments"],
        trigger_time=float(result["trigger_time"]),
        out_path=out_dir / "local_repair_resource_timeline.svg",
    )

    summary = {
        "figure_dir": str(out_dir),
        "figures": [
            "local_repair_vs_full_replan_gantt.svg",
            "local_repair_resource_timeline.svg",
        ],
    }
    print(json.dumps(summary, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
