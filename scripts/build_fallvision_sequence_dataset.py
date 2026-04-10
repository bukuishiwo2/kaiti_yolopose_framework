#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import random
import re
from collections import defaultdict
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]

import sys

sys.path.insert(0, str(PROJECT_ROOT / "src"))

from yolopose.temporal.features import POSE_FEATURE_DIM, empty_person_feature, encode_person_feature


KEYPOINT_ORDER = [
    "Nose",
    "Left Eye",
    "Right Eye",
    "Left Ear",
    "Right Ear",
    "Left Shoulder",
    "Right Shoulder",
    "Left Elbow",
    "Right Elbow",
    "Left Wrist",
    "Right Wrist",
    "Left Hip",
    "Right Hip",
    "Left Knee",
    "Right Knee",
    "Left Ankle",
    "Right Ankle",
]
KEYPOINT_TO_INDEX = {name: idx for idx, name in enumerate(KEYPOINT_ORDER)}
FRAME_PREFIX_RE = re.compile(r"^\s*(\d+)\s+(.*)$")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a sequence dataset from FallVision keypoint CSV files.")
    parser.add_argument(
        "--root",
        default="data/Fall Detection Video Dataset",
        help="Root directory containing extracted FallVision CSV files.",
    )
    parser.add_argument(
        "--glob",
        default="**/*.csv",
        help="Glob pattern under --root used to find extracted CSV files.",
    )
    parser.add_argument("--seq-len", type=int, default=32, help="Sequence length in frames.")
    parser.add_argument("--stride", type=int, default=4, help="Sliding-window stride.")
    parser.add_argument("--val-ratio", type=float, default=0.2, help="Video-level validation split ratio.")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for split.")
    parser.add_argument(
        "--keypoint-conf-threshold",
        type=float,
        default=0.3,
        help="Confidence threshold used when encoding frame features.",
    )
    parser.add_argument(
        "--positive-mode",
        choices=["all", "tail"],
        default="tail",
        help="How to label windows from fall videos. 'tail' only labels windows whose center is late enough in the clip.",
    )
    parser.add_argument(
        "--fall-positive-start-ratio",
        type=float,
        default=0.4,
        help="When --positive-mode=tail, windows with normalized center >= this ratio are labeled positive.",
    )
    parser.add_argument("--max-files", type=int, default=None, help="Only use first N CSV files after sorting.")
    parser.add_argument(
        "--max-files-per-label",
        type=int,
        default=None,
        help="Cap the number of CSV files per label class (Fall / No Fall) after sorting.",
    )
    parser.add_argument(
        "--max-files-per-scene-label",
        type=int,
        default=None,
        help="Cap the number of CSV files for each (label, scene) group after sorting.",
    )
    parser.add_argument(
        "--output",
        default="data/processed/fallvision_pose_sequences.npz",
        help="Output dataset npz path.",
    )
    return parser.parse_args()


def discover_csv_files(root: Path, pattern: str, max_files: int | None) -> list[Path]:
    files = sorted([p for p in root.glob(pattern) if p.is_file()])
    if max_files is not None:
        files = files[: max(0, max_files)]
    return files


def infer_video_label(csv_path: Path) -> int:
    parts = {part.lower() for part in csv_path.parts}
    if "no fall" in parts:
        return 0
    if "fall" in parts:
        return 1
    raise ValueError(f"Cannot infer fall/no-fall label from path: {csv_path}")


def infer_scene(csv_path: Path) -> str:
    parts = {part.lower() for part in csv_path.parts}
    for scene in ("bed", "chair", "stand"):
        if scene in parts:
            return scene
    return "unknown"


def maybe_limit_per_label(csv_files: list[Path], max_files_per_label: int | None) -> list[Path]:
    if max_files_per_label is None:
        return csv_files

    grouped: dict[int, list[Path]] = {0: [], 1: []}
    for path in csv_files:
        grouped[infer_video_label(path)].append(path)

    selected: list[Path] = []
    for label in (1, 0):
        selected.extend(grouped[label][: max(0, max_files_per_label)])
    return sorted(selected)


def maybe_limit_per_scene_label(csv_files: list[Path], max_files_per_scene_label: int | None) -> list[Path]:
    if max_files_per_scene_label is None:
        return csv_files

    grouped: dict[tuple[int, str], list[Path]] = defaultdict(list)
    for path in csv_files:
        key = (infer_video_label(path), infer_scene(path))
        grouped[key].append(path)

    selected: list[Path] = []
    for label in (1, 0):
        for scene in ("bed", "chair", "stand", "unknown"):
            key = (label, scene)
            selected.extend(grouped.get(key, [])[: max(0, max_files_per_scene_label)])
    return sorted(selected)


def parse_frame_id(row: dict[str, str]) -> int | None:
    raw = (row.get("Frame") or "").strip()
    if raw:
        try:
            return int(float(raw))
        except ValueError:
            pass

    raw_kp = (row.get("Keypoint") or "").strip()
    m = FRAME_PREFIX_RE.match(raw_kp)
    if m:
        return int(m.group(1))
    return None


def parse_keypoint_name(row: dict[str, str]) -> str | None:
    raw_kp = (row.get("Keypoint") or "").strip()
    if not raw_kp:
        return None
    m = FRAME_PREFIX_RE.match(raw_kp)
    name = m.group(2).strip() if m else raw_kp
    return name if name in KEYPOINT_TO_INDEX else None


def build_feature_from_frame_points(
    kpt_xy: np.ndarray,
    kpt_conf: np.ndarray,
    keypoint_conf_threshold: float,
) -> np.ndarray:
    valid = kpt_conf >= float(keypoint_conf_threshold)
    if int(np.sum(valid)) < 2:
        return empty_person_feature()

    valid_xy = kpt_xy[valid]
    x1 = float(np.min(valid_xy[:, 0]))
    y1 = float(np.min(valid_xy[:, 1]))
    x2 = float(np.max(valid_xy[:, 0]))
    y2 = float(np.max(valid_xy[:, 1]))
    if x2 <= x1:
        x2 = x1 + 1.0
    if y2 <= y1:
        y2 = y1 + 1.0

    return encode_person_feature(
        box_xyxy=[x1, y1, x2, y2],
        kpt_xy=kpt_xy,
        kpt_conf=kpt_conf,
        keypoint_conf_threshold=float(keypoint_conf_threshold),
    )


def load_csv_features(csv_path: Path, keypoint_conf_threshold: float) -> np.ndarray:
    frames: dict[int, dict[str, object]] = defaultdict(
        lambda: {
            "xy": np.zeros((len(KEYPOINT_ORDER), 2), dtype=np.float32),
            "conf": np.zeros((len(KEYPOINT_ORDER),), dtype=np.float32),
        }
    )

    with csv_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        required = {"Frame", "Keypoint", "X", "Y", "Confidence"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"Missing columns in {csv_path}: {sorted(missing)}")

        for row in reader:
            frame_id = parse_frame_id(row)
            keypoint_name = parse_keypoint_name(row)
            if frame_id is None or keypoint_name is None:
                continue

            kp_idx = KEYPOINT_TO_INDEX[keypoint_name]
            try:
                x = float((row.get("X") or "").strip())
                y = float((row.get("Y") or "").strip())
                conf = float((row.get("Confidence") or "").strip())
            except ValueError:
                continue

            frames[frame_id]["xy"][kp_idx, 0] = x
            frames[frame_id]["xy"][kp_idx, 1] = y
            frames[frame_id]["conf"][kp_idx] = conf

    if not frames:
        return np.zeros((0, POSE_FEATURE_DIM), dtype=np.float32)

    ordered_features: list[np.ndarray] = []
    for frame_id in sorted(frames.keys()):
        state = frames[frame_id]
        feature = build_feature_from_frame_points(
            kpt_xy=state["xy"],
            kpt_conf=state["conf"],
            keypoint_conf_threshold=keypoint_conf_threshold,
        )
        ordered_features.append(feature.astype(np.float32))

    return np.stack(ordered_features, axis=0).astype(np.float32)


def split_videos(video_ids: list[str], val_ratio: float, seed: int) -> set[str]:
    unique_ids = list(dict.fromkeys(video_ids))
    rng = random.Random(seed)
    rng.shuffle(unique_ids)
    val_count = max(1, int(round(len(unique_ids) * val_ratio))) if len(unique_ids) > 1 else 0
    return set(unique_ids[:val_count])


def label_window(
    *,
    video_label: int,
    start: int,
    seq_len: int,
    total_frames: int,
    positive_mode: str,
    fall_positive_start_ratio: float,
) -> int:
    if video_label == 0:
        return 0

    if positive_mode == "all":
        return 1

    center = start + (seq_len / 2.0)
    center_ratio = center / max(1.0, float(total_frames))
    return int(center_ratio >= float(fall_positive_start_ratio))


def main() -> None:
    args = parse_args()
    root = (PROJECT_ROOT / args.root).resolve() if not Path(args.root).is_absolute() else Path(args.root)
    output_path = (PROJECT_ROOT / args.output).resolve() if not Path(args.output).is_absolute() else Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    csv_files = discover_csv_files(root, args.glob, args.max_files)
    csv_files = maybe_limit_per_label(csv_files, args.max_files_per_label)
    csv_files = maybe_limit_per_scene_label(csv_files, args.max_files_per_scene_label)
    if not csv_files:
        raise SystemExit(f"No CSV files found under {root} with pattern {args.glob}")

    video_ids = [csv_path.stem.replace("_keypoints", "") for csv_path in csv_files]
    val_video_ids = split_videos(video_ids, val_ratio=float(args.val_ratio), seed=int(args.seed))

    xs: list[np.ndarray] = []
    ys: list[int] = []
    splits: list[str] = []
    out_video_ids: list[str] = []
    frame_starts: list[int] = []
    scenes: list[str] = []

    for csv_path in csv_files:
        video_id = csv_path.stem.replace("_keypoints", "")
        video_label = infer_video_label(csv_path)
        scene = infer_scene(csv_path)
        print(f"[build] {video_id}: label={video_label} scene={scene} csv={csv_path}")

        feat_arr = load_csv_features(csv_path, keypoint_conf_threshold=float(args.keypoint_conf_threshold))
        if len(feat_arr) < int(args.seq_len):
            print(f"[skip] {video_id}: too few frames ({len(feat_arr)}) for seq_len={args.seq_len}")
            continue

        for start in range(0, len(feat_arr) - int(args.seq_len) + 1, int(args.stride)):
            end = start + int(args.seq_len)
            xs.append(feat_arr[start:end])
            ys.append(
                label_window(
                    video_label=video_label,
                    start=start,
                    seq_len=int(args.seq_len),
                    total_frames=len(feat_arr),
                    positive_mode=str(args.positive_mode),
                    fall_positive_start_ratio=float(args.fall_positive_start_ratio),
                )
            )
            splits.append("val" if video_id in val_video_ids else "train")
            out_video_ids.append(video_id)
            frame_starts.append(start)
            scenes.append(scene)

    if not xs:
        raise SystemExit("No samples generated from FallVision CSV files.")

    x = np.stack(xs, axis=0).astype(np.float32)
    y = np.asarray(ys, dtype=np.int64)
    split = np.asarray(splits)
    vids = np.asarray(out_video_ids)
    starts = np.asarray(frame_starts, dtype=np.int64)
    scene_arr = np.asarray(scenes)

    np.savez_compressed(
        output_path,
        x=x,
        y=y,
        split=split,
        video_id=vids,
        frame_start=starts,
        scene=scene_arr,
        feature_dim=np.asarray([POSE_FEATURE_DIM], dtype=np.int64),
        seq_len=np.asarray([int(args.seq_len)], dtype=np.int64),
        stride=np.asarray([int(args.stride)], dtype=np.int64),
        source=np.asarray(["fallvision_csv"]),
        positive_mode=np.asarray([str(args.positive_mode)]),
        fall_positive_start_ratio=np.asarray([float(args.fall_positive_start_ratio)], dtype=np.float32),
    )

    train_count = int(np.sum(split == "train"))
    val_count = int(np.sum(split == "val"))
    pos_count = int(np.sum(y == 1))
    print(f"[done] dataset: {output_path}")
    print(
        f"[done] samples={len(y)} train={train_count} val={val_count} "
        f"positive={pos_count} negative={len(y) - pos_count}"
    )


if __name__ == "__main__":
    main()
