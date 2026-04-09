#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import random
import sys
from pathlib import Path

import cv2
import numpy as np
from ultralytics import YOLO

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / 'src'))

from yolopose.temporal.features import POSE_FEATURE_DIM, extract_primary_person_feature


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Build pose-sequence dataset for temporal fall classifier.')
    parser.add_argument('--labels', default='data/eval/video_labels_urfall_cam0.csv', help='CSV with video_path and fall_segments')
    parser.add_argument('--model', default='yolo11n-pose.pt', help='YOLO pose model path or alias')
    parser.add_argument('--device', default='0', help='Inference device')
    parser.add_argument('--imgsz', type=int, default=640, help='Inference image size')
    parser.add_argument('--conf', type=float, default=0.25, help='YOLO confidence threshold')
    parser.add_argument('--seq-len', type=int, default=32, help='Sequence length in frames')
    parser.add_argument('--stride', type=int, default=4, help='Sliding-window stride')
    parser.add_argument('--positive-ratio', type=float, default=0.3, help='Positive if at least this fraction of window is inside GT fall segment')
    parser.add_argument('--val-ratio', type=float, default=0.2, help='Video-level validation split ratio')
    parser.add_argument('--seed', type=int, default=42, help='Random seed for video split')
    parser.add_argument('--max-videos', type=int, default=None, help='Only use first N videos')
    parser.add_argument('--output', default='data/processed/urfall_pose_sequences.npz', help='Output dataset npz path')
    return parser.parse_args()


def parse_segments(raw: str) -> list[tuple[float, float]]:
    raw = (raw or '').strip()
    if not raw:
        return []
    segments: list[tuple[float, float]] = []
    for chunk in [part.strip() for part in raw.split(';') if part.strip()]:
        start_s, end_s = chunk.split('-', 1)
        start = float(start_s)
        end = float(end_s)
        if end < start:
            raise ValueError(f'invalid segment: {chunk}')
        segments.append((start, end))
    return segments


def load_labels(path: Path, max_videos: int | None = None) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    with path.open('r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            video_id = (row.get('video_id') or '').strip()
            video_path = Path((row.get('video_path') or '').strip()).expanduser()
            if not video_id or not video_path:
                continue
            rows.append(
                {
                    'video_id': video_id,
                    'video_path': video_path,
                    'fall_segments': parse_segments(row.get('fall_segments', '')),
                    'notes': (row.get('notes') or '').strip(),
                }
            )
    if max_videos is not None:
        rows = rows[: max(0, max_videos)]
    return rows


def get_fps(video_path: Path) -> float:
    cap = cv2.VideoCapture(str(video_path))
    fps = cap.get(cv2.CAP_PROP_FPS)
    cap.release()
    if fps is None or fps <= 1e-6:
        return 30.0
    return float(fps)


def frame_time(frame_idx: int, fps: float) -> float:
    return max(0.0, frame_idx / fps)


def is_positive_window(frame_start: int, seq_len: int, fps: float, segments: list[tuple[float, float]], positive_ratio: float) -> int:
    if not segments:
        return 0
    hits = 0
    for offset in range(seq_len):
        t = frame_time(frame_start + offset, fps)
        if any(start <= t <= end for start, end in segments):
            hits += 1
    return int((hits / max(1, seq_len)) >= positive_ratio)


def split_videos(video_ids: list[str], val_ratio: float, seed: int) -> set[str]:
    unique_ids = list(dict.fromkeys(video_ids))
    rng = random.Random(seed)
    rng.shuffle(unique_ids)
    val_count = max(1, int(round(len(unique_ids) * val_ratio))) if len(unique_ids) > 1 else 0
    return set(unique_ids[:val_count])


def main() -> None:
    args = parse_args()
    labels_path = (PROJECT_ROOT / args.labels).resolve() if not Path(args.labels).is_absolute() else Path(args.labels)
    output_path = (PROJECT_ROOT / args.output).resolve() if not Path(args.output).is_absolute() else Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    labels = load_labels(labels_path, max_videos=args.max_videos)
    if not labels:
        raise SystemExit('No videos found in labels CSV')

    model = YOLO(args.model)
    val_video_ids = split_videos([str(row['video_id']) for row in labels], val_ratio=float(args.val_ratio), seed=int(args.seed))

    xs: list[np.ndarray] = []
    ys: list[int] = []
    splits: list[str] = []
    video_ids: list[str] = []
    frame_starts: list[int] = []

    for item in labels:
        video_id = str(item['video_id'])
        video_path = Path(item['video_path'])
        fps = get_fps(video_path)
        features: list[np.ndarray] = []
        print(f'[build] {video_id}: {video_path}')
        results = model.predict(
            source=str(video_path),
            stream=True,
            conf=float(args.conf),
            imgsz=int(args.imgsz),
            device=args.device,
            classes=[0],
            save=False,
            verbose=False,
        )
        for result in results:
            feature, _meta = extract_primary_person_feature(result, keypoint_conf_threshold=0.3)
            features.append(feature)

        if len(features) < int(args.seq_len):
            print(f'[skip] {video_id}: too few frames ({len(features)}) for seq_len={args.seq_len}')
            continue

        feat_arr = np.stack(features, axis=0).astype(np.float32)
        for start in range(0, len(feat_arr) - int(args.seq_len) + 1, int(args.stride)):
            end = start + int(args.seq_len)
            xs.append(feat_arr[start:end])
            ys.append(
                is_positive_window(
                    frame_start=start,
                    seq_len=int(args.seq_len),
                    fps=fps,
                    segments=list(item['fall_segments']),
                    positive_ratio=float(args.positive_ratio),
                )
            )
            splits.append('val' if video_id in val_video_ids else 'train')
            video_ids.append(video_id)
            frame_starts.append(start)

    if not xs:
        raise SystemExit('No samples generated. Check labels, seq_len, and video paths.')

    x = np.stack(xs, axis=0).astype(np.float32)
    y = np.asarray(ys, dtype=np.int64)
    split = np.asarray(splits)
    vids = np.asarray(video_ids)
    starts = np.asarray(frame_starts, dtype=np.int64)

    np.savez_compressed(
        output_path,
        x=x,
        y=y,
        split=split,
        video_id=vids,
        frame_start=starts,
        feature_dim=np.asarray([POSE_FEATURE_DIM], dtype=np.int64),
        seq_len=np.asarray([int(args.seq_len)], dtype=np.int64),
        stride=np.asarray([int(args.stride)], dtype=np.int64),
        positive_ratio=np.asarray([float(args.positive_ratio)], dtype=np.float32),
    )

    train_count = int(np.sum(split == 'train'))
    val_count = int(np.sum(split == 'val'))
    pos_count = int(np.sum(y == 1))
    print(f'[done] dataset: {output_path}')
    print(f'[done] samples={len(y)} train={train_count} val={val_count} positive={pos_count} negative={len(y) - pos_count}')


if __name__ == '__main__':
    main()
