#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]

import sys

sys.path.insert(0, str(PROJECT_ROOT / "src"))

from build_fallvision_sequence_dataset import POSE_FEATURE_DIM, load_csv_sequence


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build a small sequence-window dataset from FallVision videos with coarse "
            "segment annotations, without entering training."
        )
    )
    parser.add_argument(
        "--labels-csv",
        default="data/eval/fallvision_first_batch_segment_candidates_2026-04-15_labeled.csv",
        help="CSV file containing coarse segment labels per video.",
    )
    parser.add_argument(
        "--fallvision-root",
        default="data/external/fallvision/extracted",
        help="Canonical FallVision CSV root used to resolve keypoint files.",
    )
    parser.add_argument("--seq-len", type=int, default=32, help="Sequence length in frames.")
    parser.add_argument("--stride", type=int, default=4, help="Sliding-window stride.")
    parser.add_argument(
        "--keypoint-conf-threshold",
        type=float,
        default=0.3,
        help="Confidence threshold used when encoding frame features.",
    )
    parser.add_argument(
        "--positive-min-overlap-ratio",
        type=float,
        default=0.5,
        help="Minimum overlap ratio with the fall segment required to mark a window positive.",
    )
    parser.add_argument(
        "--post-min-overlap-ratio",
        type=float,
        default=0.5,
        help="Minimum overlap ratio with the post-fall segment required to mark a window post_fall_stable.",
    )
    parser.add_argument(
        "--output-npz",
        default="data/eval/fallvision_labeled_window_smoke_2026-04-15.npz",
        help="Output NPZ path for train-ready windows.",
    )
    parser.add_argument(
        "--output-window-csv",
        default="data/eval/fallvision_labeled_window_smoke_2026-04-15.csv",
        help="Output CSV path for all generated windows and their kinds.",
    )
    parser.add_argument(
        "--output-report-md",
        default="reports/benchmarks/fallvision_labeled_window_smoke_2026-04-15.md",
        help="Output Markdown report path.",
    )
    return parser.parse_args()


def resolve_repo_path(raw: str) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else (PROJECT_ROOT / path).resolve()


def load_labeled_rows(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise SystemExit(f"No labeled rows found in {path}")
    required = {
        "video_path",
        "scene",
        "fall_style",
        "fall_start_frame",
        "fall_end_frame",
        "post_fall_start_frame",
    }
    missing = required - set(rows[0].keys())
    if missing:
        raise SystemExit(f"Missing columns in {path}: {sorted(missing)}")
    return rows


def parse_required_int(row: dict[str, str], key: str) -> int:
    raw = str(row.get(key, "")).strip()
    if not raw:
        raise ValueError(f"missing_{key}")
    return int(float(raw))


def resolve_fallvision_csv(video_path: Path, fallvision_root: Path, scene: str) -> Path:
    stem = video_path.stem
    pattern = f"{stem}_keypoints.csv"
    matches = sorted(fallvision_root.rglob(pattern))
    scene_lower = scene.lower().strip()

    filtered = []
    for path in matches:
        lowered_parts = {part.lower() for part in path.parts}
        if "fall" not in lowered_parts or "no fall" in lowered_parts:
            continue
        if scene_lower and scene_lower not in lowered_parts:
            continue
        filtered.append(path)
    if not filtered:
        raise FileNotFoundError(f"no_fallvision_csv_match:{video_path}")
    if len(filtered) > 1:
        raise FileNotFoundError(f"ambiguous_fallvision_csv_match:{video_path}:{filtered}")
    return filtered[0]


def frame_overlap_count(start_frame: int, end_frame: int, seg_start: int, seg_end: int) -> int:
    lo = max(int(start_frame), int(seg_start))
    hi = min(int(end_frame), int(seg_end))
    return max(0, hi - lo + 1)


def classify_window(
    *,
    start_frame: int,
    end_frame: int,
    center_frame: int,
    seq_len: int,
    fall_start_frame: int,
    fall_end_frame: int,
    post_fall_start_frame: int,
    total_frames: int,
    positive_min_overlap_ratio: float,
    post_min_overlap_ratio: float,
) -> tuple[str, int, bool]:
    positive_overlap = frame_overlap_count(start_frame, end_frame, fall_start_frame, fall_end_frame)
    positive_ratio = positive_overlap / max(1, int(seq_len))

    post_overlap = frame_overlap_count(start_frame, end_frame, post_fall_start_frame, total_frames)
    post_ratio = post_overlap / max(1, int(seq_len))

    if center_frame < int(fall_start_frame) and end_frame < int(fall_start_frame):
        return "negative", 0, True
    if center_frame > int(fall_end_frame) and post_ratio >= float(post_min_overlap_ratio):
        return "post_fall_stable", 1, True
    if int(fall_start_frame) <= center_frame <= int(fall_end_frame) and positive_ratio >= float(positive_min_overlap_ratio):
        return "positive", 1, True
    return "transition_ignore", -1, False


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        raise SystemExit("No window rows to write.")
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def display_path(path: Path) -> str:
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def write_report(
    path: Path,
    *,
    video_stats: list[dict[str, Any]],
    scene_stats: dict[str, dict[str, int]],
    rules_text: list[str],
    npz_path: Path,
    window_csv_path: Path,
    skipped: list[str],
    flagged: list[str],
) -> None:
    lines = [
        "# FallVision Labeled Window Smoke 2026-04-15",
        "",
        "## 1. 目标",
        "",
        "基于已完成的粗粒度段级标注，验证这批 `FallVision` 视频是否已经足以支撑训练前的窗口构造与可用性检查。",
        "",
        "本次不进入训练，只做：",
        "",
        "1. 兼容当前 `LSTM` 主线输入格式的窗口构造",
        "2. 窗口级标签规则验证",
        "3. 每视频 / 每场景的窗口统计",
        "",
        "## 2. 窗口构造规则",
        "",
    ]
    lines.extend([f"- {item}" for item in rules_text])
    lines.extend(
        [
            "",
            "## 3. Smoke Test 输出",
            "",
            f"- window csv: `{display_path(window_csv_path)}`",
            f"- train-ready npz: `{display_path(npz_path)}`",
            "",
            "## 4. 每视频窗口统计",
            "",
            "| Video | Scene | Style | Total Windows | Positive | Transition Ignore | Post-Fall Stable | Negative |",
            "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in video_stats:
        lines.append(
            f"| `{row['video_name']}` | `{row['scene']}` | `{row['fall_style']}` | "
            f"{row['total_windows']} | {row['positive']} | {row['transition_ignore']} | "
            f"{row['post_fall_stable']} | {row['negative']} |"
        )

    lines.extend(["", "## 5. 每场景汇总", ""])
    lines.append("| Scene | Total Windows | Positive | Transition Ignore | Post-Fall Stable | Negative |")
    lines.append("| --- | ---: | ---: | ---: | ---: | ---: |")
    for scene in ("bed", "chair", "stand"):
        stats = scene_stats.get(scene, {})
        lines.append(
            f"| `{scene}` | {stats.get('total_windows', 0)} | {stats.get('positive', 0)} | "
            f"{stats.get('transition_ignore', 0)} | {stats.get('post_fall_stable', 0)} | {stats.get('negative', 0)} |"
        )

    if skipped:
        lines.extend(["", "## 6. 跳过项", ""])
        lines.extend([f"- {item}" for item in skipped])

    if flagged:
        lines.extend(["", "## 6.1 需要单独关注的视频", ""])
        lines.extend([f"- {item}" for item in flagged])

    lines.extend(
        [
            "",
            "## 7. 当前判断",
            "",
            "- 若一个视频能稳定生成 `positive + post_fall_stable + negative` 三类窗口，则其粗标已具备最小训练前可用性。",
            "- `transition_ignore` 的存在是正常的，它用于避免把粗标边界附近的混合窗口直接塞进正负样本。",
            "- 当前 15 个视频若都能稳定生成窗口，则足以支持后续受控补强训练的 pilot，但仍不足以直接替代主 benchmark 训练分布。",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    args = parse_args()
    labels_csv = resolve_repo_path(args.labels_csv)
    fallvision_root = resolve_repo_path(args.fallvision_root)
    output_npz = resolve_repo_path(args.output_npz)
    output_window_csv = resolve_repo_path(args.output_window_csv)
    output_report_md = resolve_repo_path(args.output_report_md)

    labeled_rows = load_labeled_rows(labels_csv)

    all_window_rows: list[dict[str, Any]] = []
    xs: list[np.ndarray] = []
    ys: list[int] = []
    window_kind_arr: list[str] = []
    scenes_arr: list[str] = []
    video_paths_arr: list[str] = []
    video_ids_arr: list[str] = []
    frame_starts_arr: list[int] = []
    frame_ends_arr: list[int] = []
    fall_styles_arr: list[str] = []

    video_stats: list[dict[str, Any]] = []
    scene_stats: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    skipped: list[str] = []
    flagged: list[str] = []

    for row in labeled_rows:
        video_path = resolve_repo_path(row["video_path"])
        scene = str(row["scene"]).strip().lower()
        fall_style = str(row["fall_style"]).strip()
        try:
            fall_start_frame = parse_required_int(row, "fall_start_frame")
            fall_end_frame = parse_required_int(row, "fall_end_frame")
            post_fall_start_frame = parse_required_int(row, "post_fall_start_frame")
        except ValueError as exc:
            skipped.append(f"{video_path.name}: invalid_label:{exc}")
            continue

        try:
            csv_path = resolve_fallvision_csv(video_path, fallvision_root=fallvision_root, scene=scene)
        except FileNotFoundError as exc:
            skipped.append(str(exc))
            continue

        frame_ids, feat_arr = load_csv_sequence(
            csv_path,
            keypoint_conf_threshold=float(args.keypoint_conf_threshold),
        )
        if len(feat_arr) < int(args.seq_len):
            skipped.append(f"{video_path.name}: too_few_frames:{len(feat_arr)}")
            continue

        stats = Counter()
        for start in range(0, len(feat_arr) - int(args.seq_len) + 1, int(args.stride)):
            end = start + int(args.seq_len)
            start_frame = int(frame_ids[start])
            end_frame = int(frame_ids[end - 1])
            center_frame = int(frame_ids[start + (int(args.seq_len) // 2)])
            rel_video_path = str(video_path.relative_to(PROJECT_ROOT))
            window_kind, y_binary, include_for_training = classify_window(
                start_frame=start_frame,
                end_frame=end_frame,
                center_frame=center_frame,
                seq_len=int(args.seq_len),
                fall_start_frame=fall_start_frame,
                fall_end_frame=fall_end_frame,
                post_fall_start_frame=post_fall_start_frame,
                total_frames=int(frame_ids[-1]),
                positive_min_overlap_ratio=float(args.positive_min_overlap_ratio),
                post_min_overlap_ratio=float(args.post_min_overlap_ratio),
            )

            stats["total_windows"] += 1
            stats[window_kind] += 1
            scene_stats[scene]["total_windows"] += 1
            scene_stats[scene][window_kind] += 1

            all_window_rows.append(
                {
                    "video_path": rel_video_path,
                    "csv_path": str(csv_path.relative_to(PROJECT_ROOT)),
                    "scene": scene,
                    "fall_style": fall_style,
                    "window_index": stats["total_windows"],
                    "seq_len": int(args.seq_len),
                    "stride": int(args.stride),
                    "feature_dim": POSE_FEATURE_DIM,
                    "start_frame": start_frame,
                    "end_frame": end_frame,
                    "center_frame": center_frame,
                    "fall_start_frame": fall_start_frame,
                    "fall_end_frame": fall_end_frame,
                    "post_fall_start_frame": post_fall_start_frame,
                    "window_kind": window_kind,
                    "y_binary": y_binary,
                    "include_for_training": int(include_for_training),
                }
            )

            if include_for_training:
                xs.append(feat_arr[start:end])
                ys.append(int(y_binary))
                window_kind_arr.append(window_kind)
                scenes_arr.append(scene)
                video_paths_arr.append(rel_video_path)
                video_ids_arr.append(video_path.stem)
                frame_starts_arr.append(start_frame)
                frame_ends_arr.append(end_frame)
                fall_styles_arr.append(fall_style)

        video_stats.append(
            {
                "video_name": video_path.name,
                "video_path": str(video_path.relative_to(PROJECT_ROOT)),
                "scene": scene,
                "fall_style": fall_style,
                "total_windows": int(stats["total_windows"]),
                "positive": int(stats["positive"]),
                "transition_ignore": int(stats["transition_ignore"]),
                "post_fall_stable": int(stats["post_fall_stable"]),
                "negative": int(stats["negative"]),
            }
        )

        issues: list[str] = []
        if int(stats["positive"]) == 0:
            issues.append("positive=0")
        if int(stats["negative"]) == 0:
            issues.append("negative=0")
        if int(stats["post_fall_stable"]) == 0:
            issues.append("post_fall_stable=0")
        if issues:
            flagged.append(f"{video_path.name}: " + ", ".join(issues))

    if not all_window_rows:
        raise SystemExit("No windows generated from labeled FallVision videos.")

    write_csv(output_window_csv, all_window_rows)

    if not xs:
        raise SystemExit("No train-ready windows generated.")
    output_npz.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        output_npz,
        x=np.stack(xs, axis=0).astype(np.float32),
        y=np.asarray(ys, dtype=np.int64),
        window_kind=np.asarray(window_kind_arr),
        scene=np.asarray(scenes_arr),
        video_path=np.asarray(video_paths_arr),
        video_id=np.asarray(video_ids_arr),
        frame_start=np.asarray(frame_starts_arr, dtype=np.int64),
        frame_end=np.asarray(frame_ends_arr, dtype=np.int64),
        fall_style=np.asarray(fall_styles_arr),
        feature_dim=np.asarray([POSE_FEATURE_DIM], dtype=np.int64),
        seq_len=np.asarray([int(args.seq_len)], dtype=np.int64),
        stride=np.asarray([int(args.stride)], dtype=np.int64),
        source=np.asarray(["fallvision_labeled_csv"]),
    )

    rules_text = [
        f"`seq_len={int(args.seq_len)}`, `stride={int(args.stride)}`，沿视频滑窗构造窗口。",
        "每个窗口先通过 `video_path -> *_keypoints.csv` 自动映射到 canonical FallVision keypoint CSV。",
        "若窗口结束帧仍早于 `fall_start_frame`，标为 `negative`。",
        (
            "若窗口中心帧落在 `[fall_start_frame, fall_end_frame]` 且与 fall 段的重叠比例 "
            f"`>= {float(args.positive_min_overlap_ratio):.2f}`，标为 `positive`。"
        ),
        (
            "若窗口中心帧晚于 `fall_end_frame` 且与 `[post_fall_start_frame, video_end]` 的重叠比例 "
            f"`>= {float(args.post_min_overlap_ratio):.2f}`，标为 `post_fall_stable`。"
        ),
        "其余跨边界混合窗口标为 `transition_ignore`，不直接进入 train-ready NPZ。",
        "`y_binary` 中：`negative=0`，`positive/post_fall_stable=1`，`transition_ignore=-1`。",
    ]
    write_report(
        output_report_md,
        video_stats=video_stats,
        scene_stats=scene_stats,
        rules_text=rules_text,
        npz_path=output_npz,
        window_csv_path=output_window_csv,
        skipped=skipped,
        flagged=flagged,
    )

    print(
        {
            "labels_csv": str(labels_csv.relative_to(PROJECT_ROOT)),
            "output_window_csv": str(output_window_csv.relative_to(PROJECT_ROOT)),
            "output_npz": str(output_npz.relative_to(PROJECT_ROOT)),
            "output_report_md": str(output_report_md.relative_to(PROJECT_ROOT)),
            "video_count": len(video_stats),
            "train_ready_windows": len(xs),
            "all_windows": len(all_window_rows),
            "skipped_count": len(skipped),
            "flagged_count": len(flagged),
        }
    )
    for row in video_stats:
        print(
            "[video]",
            row["video_name"],
            f"scene={row['scene']}",
            f"style={row['fall_style']}",
            f"total={row['total_windows']}",
            f"positive={row['positive']}",
            f"transition={row['transition_ignore']}",
            f"post={row['post_fall_stable']}",
            f"negative={row['negative']}",
        )


if __name__ == "__main__":
    main()
