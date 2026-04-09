#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path

import cv2


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build eval labels CSV from UR Fall extracted feature labels.")
    parser.add_argument(
        "--falls-csv",
        default="data/urfall/labels_raw/urfall-cam0-falls.csv",
        help="Path to urfall-cam0-falls.csv",
    )
    parser.add_argument(
        "--video-dir",
        default="data/urfall/cam0_mp4",
        help="Directory containing fall-XX-cam0.mp4 and adl-XX-cam0.mp4",
    )
    parser.add_argument(
        "--out",
        default="data/eval/video_labels_urfall_cam0.csv",
        help="Output labels CSV for eval_fall_batch.py",
    )
    parser.add_argument(
        "--fallback-fps",
        type=float,
        default=30.0,
        help="Fallback fps when video cannot be opened",
    )
    parser.add_argument(
        "--include-adl",
        action="store_true",
        help="Include adl-01..adl-40 with empty fall segments",
    )
    return parser.parse_args()


def read_fall_labels(path: Path) -> dict[str, list[tuple[int, int]]]:
    seq_to_rows: dict[str, list[tuple[int, int]]] = defaultdict(list)
    with path.open("r", encoding="utf-8") as f:
        reader = csv.reader(f)
        for row in reader:
            if len(row) < 3:
                continue
            seq = row[0].strip()
            try:
                frame_id = int(float(row[1]))
                label = int(float(row[2]))
            except ValueError:
                continue
            # label semantics from dataset page:
            # -1 not lying, 0 falling-transition, 1 lying
            seq_to_rows[seq].append((frame_id, label))
    return seq_to_rows


def get_fps(video_path: Path, fallback: float) -> float:
    cap = cv2.VideoCapture(str(video_path))
    fps = cap.get(cv2.CAP_PROP_FPS)
    cap.release()
    if fps is None or fps <= 1e-6:
        return fallback
    return float(fps)


def frames_to_segments(frames: list[int]) -> list[tuple[int, int]]:
    if not frames:
        return []
    frames = sorted(set(frames))
    segs: list[tuple[int, int]] = []
    start = prev = frames[0]
    for f in frames[1:]:
        if f == prev + 1:
            prev = f
            continue
        segs.append((start, prev))
        start = prev = f
    segs.append((start, prev))
    return segs


def segs_to_str(segs: list[tuple[int, int]], fps: float) -> str:
    out = []
    for s, e in segs:
        ss = (s - 1) / fps
        ee = (e - 1) / fps
        out.append(f"{ss:.3f}-{ee:.3f}")
    return ";".join(out)


def main() -> None:
    args = parse_args()
    falls_csv = Path(args.falls_csv).expanduser().resolve()
    video_dir = Path(args.video_dir).expanduser().resolve()
    out_csv = Path(args.out).expanduser().resolve()

    if not falls_csv.exists():
        raise SystemExit(f"falls csv not found: {falls_csv}")

    seq_rows = read_fall_labels(falls_csv)

    rows: list[dict[str, str]] = []

    for idx in range(1, 31):
        seq = f"fall-{idx:02d}"
        video_path = video_dir / f"{seq}-cam0.mp4"
        fps = get_fps(video_path, args.fallback_fps)

        rows_for_seq = seq_rows.get(seq, [])
        positive_frames = [f for f, label in rows_for_seq if label >= 0]
        segs = frames_to_segments(positive_frames)
        seg_str = segs_to_str(segs, fps)

        rows.append(
            {
                "video_id": seq,
                "video_path": str(video_path),
                "fall_segments": seg_str,
                "notes": "urfall auto-generated from urfall-cam0-falls.csv",
            }
        )

    if args.include_adl:
        for idx in range(1, 41):
            seq = f"adl-{idx:02d}"
            video_path = video_dir / f"{seq}-cam0.mp4"
            rows.append(
                {
                    "video_id": seq,
                    "video_path": str(video_path),
                    "fall_segments": "",
                    "notes": "urfall adl sequence",
                }
            )

    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with out_csv.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f, fieldnames=["video_id", "video_path", "fall_segments", "notes"]
        )
        writer.writeheader()
        writer.writerows(rows)

    print(f"wrote: {out_csv}")
    print(f"rows: {len(rows)}")


if __name__ == "__main__":
    main()
