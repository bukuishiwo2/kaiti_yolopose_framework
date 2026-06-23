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

from kaiti_planning.models import load_problem_from_yaml
from kaiti_planning.replanner import build_resource_events_from_spatial_replay, run_dynamic_replanning
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
        '<style>text{font-family:monospace;font-size:12px;fill:#1f2937} .small{font-size:11px} .axis{stroke:#64748b;stroke-width:1} .grid{stroke:#cbd5e1;stroke-width:1;stroke-dasharray:4 4}</style>',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
    ]


def render_corridor_state_timeline(states: list[dict[str, float | str]], out_path: Path) -> None:
    width = 980
    height = 220
    left = 90
    right = 40
    top = 60
    bar_h = 46
    timeline_w = width - left - right
    max_time = max(float(item["end"]) for item in states)
    palette = {"free": "#9bd3ae", "temporary_occupied": "#f6c177", "blocked": "#e76f51"}
    svg = _svg_header(width, height, "corridor_H state timeline")
    svg.append('<text x="40" y="30" font-size="18">corridor_H state timeline</text>')
    svg.append(f'<line class="axis" x1="{left}" y1="{top + bar_h + 20}" x2="{left + timeline_w}" y2="{top + bar_h + 20}"/>')
    for item in states:
        start = float(item["start"])
        end = float(item["end"])
        state = str(item["state"])
        x = _scale(start, 0.0, max_time, left, timeline_w)
        x2 = _scale(end, 0.0, max_time, left, timeline_w)
        color = palette.get(state, "#94a3b8")
        svg.append(f'<rect x="{x:.1f}" y="{top}" width="{max(1.0, x2 - x):.1f}" height="{bar_h}" fill="{color}" stroke="#475569"/>')
        svg.append(f'<text x="{(x + x2) / 2:.1f}" y="{top + 28}" text-anchor="middle">{escape(state)}</text>')
    for tick in range(0, int(max_time) + 1, 10):
        x = _scale(float(tick), 0.0, max_time, left, timeline_w)
        svg.append(f'<line class="grid" x1="{x:.1f}" y1="{top - 10}" x2="{x:.1f}" y2="{top + bar_h + 20}"/>')
        svg.append(f'<text class="small" x="{x:.1f}" y="{top + bar_h + 40}" text-anchor="middle">{tick}</text>')
    svg.append(f'<text x="20" y="{top + 28}">state</text>')
    svg.append("</svg>")
    _write(out_path, "\n".join(svg))


def render_occupancy_curves(points: list[dict[str, float]], out_path: Path) -> None:
    width = 980
    height = 320
    left = 90
    right = 40
    top = 40
    bottom = 50
    plot_w = width - left - right
    plot_h = height - top - bottom
    max_time = max(point["time"] for point in points)
    max_value = 1.0

    def polyline(values: list[tuple[float, float]], color: str) -> str:
        coords = []
        for x_value, y_value in values:
            px = _scale(x_value, 0.0, max_time, left, plot_w)
            py = _scale(y_value, 0.0, max_value, top + plot_h, -plot_h)
            coords.append(f"{px:.1f},{py:.1f}")
        return f'<polyline fill="none" stroke="{color}" stroke-width="3" points="{" ".join(coords)}"/>'

    occ = [(point["time"], point["occupancy_ratio"]) for point in points]
    ema = [(point["time"], point["occupancy_ratio_ema"]) for point in points]
    svg = _svg_header(width, height, "corridor_H occupancy curves")
    svg.append('<text x="40" y="24" font-size="18">corridor_H occupancy ratio / EMA</text>')
    svg.append(f'<rect x="{left}" y="{top}" width="{plot_w}" height="{plot_h}" fill="#f8fafc" stroke="#cbd5e1"/>')
    for tick in range(0, 11, 2):
        y = _scale(tick / 10.0, 0.0, max_value, top + plot_h, -plot_h)
        svg.append(f'<line class="grid" x1="{left}" y1="{y:.1f}" x2="{left + plot_w}" y2="{y:.1f}"/>')
        svg.append(f'<text class="small" x="{left - 12}" y="{y + 4:.1f}" text-anchor="end">{tick / 10.0:.1f}</text>')
    for tick in range(0, int(max_time) + 1, 10):
        x = _scale(float(tick), 0.0, max_time, left, plot_w)
        svg.append(f'<line class="grid" x1="{x:.1f}" y1="{top}" x2="{x:.1f}" y2="{top + plot_h}"/>')
        svg.append(f'<text class="small" x="{x:.1f}" y="{top + plot_h + 20}" text-anchor="middle">{tick}</text>')
    svg.append(polyline(occ, "#2563eb"))
    svg.append(polyline(ema, "#dc2626"))
    svg.append('<text x="760" y="36" fill="#2563eb">occupancy_ratio</text>')
    svg.append('<text x="760" y="56" fill="#dc2626">occupancy_ratio_ema</text>')
    svg.append("</svg>")
    _write(out_path, "\n".join(svg))


def render_gantt(initial_assignments: list[dict[str, float | str]], replanned_assignments: list[dict[str, float | str]], out_path: Path) -> None:
    width = 1180
    height = 360
    left = 120
    right = 40
    top = 50
    lane_h = 36
    lane_gap = 16
    timeline_w = width - left - right
    robots = ["R1", "R2", "R3"]
    plan_rows = [("initial", initial_assignments), ("replan@45", replanned_assignments)]
    max_time = max(float(item["finish"]) for _, assignments in plan_rows for item in assignments)
    palette = {"T1": "#93c5fd", "T2": "#a7f3d0", "T3": "#fca5a5", "T4": "#fcd34d", "T5": "#c4b5fd"}

    svg = _svg_header(width, height, "dynamic replanning gantt")
    svg.append('<text x="40" y="24" font-size="18">dynamic replanning gantt: before vs after t=45</text>')
    for tick in range(0, int(max_time) + 1, 10):
        x = _scale(float(tick), 0.0, max_time, left, timeline_w)
        svg.append(f'<line class="grid" x1="{x:.1f}" y1="{top - 10}" x2="{x:.1f}" y2="{height - 30}"/>')
        svg.append(f'<text class="small" x="{x:.1f}" y="{height - 12}" text-anchor="middle">{tick}</text>')
    for plan_idx, (label, assignments) in enumerate(plan_rows):
        svg.append(f'<text x="30" y="{top + plan_idx * 3 * (lane_h + lane_gap) + 22}" font-size="15">{escape(label)}</text>')
        for robot_idx, robot in enumerate(robots):
            y = top + plan_idx * 3 * (lane_h + lane_gap) + robot_idx * (lane_h + lane_gap)
            svg.append(f'<text x="{left - 16}" y="{y + 22}" text-anchor="end">{robot}</text>')
            svg.append(f'<rect x="{left}" y="{y}" width="{timeline_w}" height="{lane_h}" fill="#f8fafc" stroke="#e2e8f0"/>')
            for item in assignments:
                if str(item["robot"]) != robot:
                    continue
                x = _scale(float(item["start"]), 0.0, max_time, left, timeline_w)
                x2 = _scale(float(item["finish"]), 0.0, max_time, left, timeline_w)
                task_id = str(item["task"])
                svg.append(f'<rect x="{x:.1f}" y="{y + 4}" width="{max(1.0, x2 - x):.1f}" height="{lane_h - 8}" fill="{palette.get(task_id, "#cbd5e1")}" stroke="#475569"/>')
                svg.append(f'<text x="{(x + x2) / 2:.1f}" y="{y + 22}" text-anchor="middle">{task_id}</text>')
    svg.append("</svg>")
    _write(out_path, "\n".join(svg))


def render_resource_timeline(states: list[dict[str, float | str]], initial_assignments: list[dict[str, float | str]], replanned_assignments: list[dict[str, float | str]], out_path: Path) -> None:
    width = 1180
    height = 300
    left = 130
    right = 40
    top = 50
    lane_h = 34
    gap = 18
    timeline_w = width - left - right
    max_time = max(
        max(float(item["end"]) for item in states),
        max(float(item["finish"]) for item in initial_assignments + replanned_assignments),
    )
    palette = {"free": "#9bd3ae", "temporary_occupied": "#f6c177", "blocked": "#e76f51"}
    rows = [
        ("corridor_H state", None),
        ("initial occupancy", initial_assignments),
        ("replan occupancy", replanned_assignments),
    ]
    svg = _svg_header(width, height, "corridor_H resource timeline")
    svg.append('<text x="40" y="24" font-size="18">corridor_H resource timeline</text>')
    for tick in range(0, int(max_time) + 1, 10):
        x = _scale(float(tick), 0.0, max_time, left, timeline_w)
        svg.append(f'<line class="grid" x1="{x:.1f}" y1="{top - 10}" x2="{x:.1f}" y2="{height - 30}"/>')
        svg.append(f'<text class="small" x="{x:.1f}" y="{height - 12}" text-anchor="middle">{tick}</text>')
    for idx, (label, assignments) in enumerate(rows):
        y = top + idx * (lane_h + gap)
        svg.append(f'<text x="{left - 16}" y="{y + 22}" text-anchor="end">{escape(label)}</text>')
        svg.append(f'<rect x="{left}" y="{y}" width="{timeline_w}" height="{lane_h}" fill="#f8fafc" stroke="#e2e8f0"/>')
        if assignments is None:
            for state in states:
                x = _scale(float(state["start"]), 0.0, max_time, left, timeline_w)
                x2 = _scale(float(state["end"]), 0.0, max_time, left, timeline_w)
                color = palette.get(str(state["state"]), "#cbd5e1")
                svg.append(f'<rect x="{x:.1f}" y="{y + 4}" width="{max(1.0, x2 - x):.1f}" height="{lane_h - 8}" fill="{color}" stroke="#475569"/>')
                svg.append(f'<text x="{(x + x2) / 2:.1f}" y="{y + 22}" text-anchor="middle">{escape(str(state["state"]))}</text>')
        else:
            for item in assignments:
                resources = set(item.get("resources", []))
                if "corridor_H" not in resources:
                    continue
                x = _scale(float(item["start"]), 0.0, max_time, left, timeline_w)
                x2 = _scale(float(item["finish"]), 0.0, max_time, left, timeline_w)
                task_id = str(item["task"])
                svg.append(f'<rect x="{x:.1f}" y="{y + 4}" width="{max(1.0, x2 - x):.1f}" height="{lane_h - 8}" fill="#93c5fd" stroke="#1d4ed8"/>')
                svg.append(f'<text x="{(x + x2) / 2:.1f}" y="{y + 22}" text-anchor="middle">{task_id}</text>')
    svg.append("</svg>")
    _write(out_path, "\n".join(svg))


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate SVG figures for the frozen planning case.")
    parser.add_argument("--config", required=True)
    parser.add_argument("--backend", default="pulp")
    parser.add_argument("--regions", required=True)
    parser.add_argument("--spatial-replay", required=True)
    parser.add_argument("--out-dir", default="reports/figures/planning_2026-06-22")
    args = parser.parse_args()

    problem = load_problem_from_yaml(Path(args.config))
    region_specs = load_region_specs(Path(args.regions))
    replay_cfg = load_spatial_replay_config(Path(args.spatial_replay))
    resource_events, spatial_snapshots = build_resource_events_from_spatial_replay(
        problem,
        replay_cfg=replay_cfg,
        region_specs=region_specs,
    )
    result = run_dynamic_replanning(
        problem,
        backend=args.backend,
        resource_events=resource_events,
        spatial_snapshots_by_time=spatial_snapshots,
    )

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    initial_plan = result["initial_plan"]["assignments"]
    replan_45 = next(item for item in result["timeline"] if float(item["time"]) == 45.0)
    replan_45_assignments = replan_45["plan"]["assignments"]
    end_time = max(
        float(result["initial_plan"]["metrics"]["makespan"]),
        float(replan_45["plan"]["metrics"]["makespan"]),
    )

    snapshot_points = []
    ordered_times = sorted(spatial_snapshots)
    state_segments = []
    for idx, time_value in enumerate(ordered_times):
        snapshot = spatial_snapshots[time_value]
        corridor = snapshot.region_states["corridor_H"]
        snapshot_points.append(
            {
                "time": float(time_value),
                "occupancy_ratio": float(corridor.get("occupancy_ratio", 0.0)),
                "occupancy_ratio_ema": float(corridor.get("occupancy_ratio_ema", 0.0)),
            }
        )
        end_value = ordered_times[idx + 1] if idx + 1 < len(ordered_times) else end_time
        state_segments.append(
            {
                "start": float(time_value),
                "end": float(end_value),
                "state": str(corridor["state"]),
            }
        )

    render_corridor_state_timeline(state_segments, out_dir / "corridor_H_state_timeline.svg")
    render_occupancy_curves(snapshot_points, out_dir / "corridor_H_occupancy_curves.svg")
    render_gantt(initial_plan, replan_45_assignments, out_dir / "dynamic_replan_gantt.svg")
    render_resource_timeline(state_segments, initial_plan, replan_45_assignments, out_dir / "corridor_H_resource_timeline.svg")

    summary = {
        "figure_dir": str(out_dir),
        "figures": [
            "corridor_H_state_timeline.svg",
            "corridor_H_occupancy_curves.svg",
            "dynamic_replan_gantt.svg",
            "corridor_H_resource_timeline.svg",
        ],
    }
    print(json.dumps(summary, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
