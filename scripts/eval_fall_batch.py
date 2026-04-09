#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2

PROJECT_ROOT = Path(__file__).resolve().parents[1]

import sys

sys.path.insert(0, str(PROJECT_ROOT / "src"))

from yolopose.core.config import abs_path, load_yaml
from yolopose.pipeline.runner import PoseRunner


@dataclass
class VideoLabel:
    video_id: str
    video_path: Path
    fall_segments: list[tuple[float, float]]
    notes: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Batch run and evaluate fall detection on labeled videos.")
    parser.add_argument(
        "--labels",
        default="data/eval/video_labels_template.csv",
        help="CSV path with columns: video_id,video_path,fall_segments,notes",
    )
    parser.add_argument("--config", default="configs/infer_pose_stream.yaml", help="Base infer config.")
    parser.add_argument("--model", default=None, help="Override model path or model alias.")
    parser.add_argument("--device", default=None, help="Override device, e.g. 0/cpu.")
    parser.add_argument("--mode", choices=["predict", "track"], default=None, help="Override infer mode.")
    parser.add_argument("--tracker", default=None, help="Override tracker yaml when mode=track.")
    parser.add_argument("--skip-inference", action="store_true", help="Only evaluate existing JSONL outputs.")
    parser.add_argument(
        "--out-dir",
        default="outputs/eval",
        help="Directory for per-video jsonl and metrics tables.",
    )
    parser.add_argument("--raw-key", default="raw_fall_detected", help="JSONL raw fall field to evaluate.")
    parser.add_argument("--stable-key", default="stable_fall_detected", help="JSONL stable fall field to evaluate.")
    return parser.parse_args()


def parse_segments(raw: str) -> list[tuple[float, float]]:
    raw = (raw or "").strip()
    if not raw:
        return []
    segments: list[tuple[float, float]] = []
    parts = [p.strip() for p in raw.split(";") if p.strip()]
    for part in parts:
        if "-" not in part:
            raise ValueError(f"Invalid segment format: {part}, expected start-end")
        s, e = part.split("-", 1)
        start = float(s.strip())
        end = float(e.strip())
        if end < start:
            raise ValueError(f"Invalid segment range: {part}")
        segments.append((start, end))
    return segments


def load_labels(path: Path) -> list[VideoLabel]:
    labels: list[VideoLabel] = []
    with path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        required = {"video_id", "video_path", "fall_segments", "notes"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"Missing columns in labels CSV: {sorted(missing)}")
        for row in reader:
            vid = row["video_id"].strip()
            if not vid:
                continue
            labels.append(
                VideoLabel(
                    video_id=vid,
                    video_path=Path(row["video_path"].strip()).expanduser(),
                    fall_segments=parse_segments(row.get("fall_segments", "")),
                    notes=(row.get("notes", "") or "").strip(),
                )
            )
    return labels


def frame_time(frame_id: int, fps: float) -> float:
    return max(0.0, (frame_id - 1) / fps)


def overlap(a: tuple[float, float], b: tuple[float, float]) -> bool:
    return not (a[1] < b[0] or b[1] < a[0])


def segments_to_text(segs: list[tuple[float, float]], ndigits: int = 3) -> str:
    if not segs:
        return ""
    out = []
    for s, e in segs:
        out.append(f"{round(s, ndigits)}-{round(e, ndigits)}")
    return ";".join(out)


def to_segments(events: list[dict[str, Any]], key: str, fps: float) -> list[tuple[float, float]]:
    segs: list[tuple[float, float]] = []
    in_seg = False
    start_f = 1

    for r in events:
        fid = int(r["frame_id"])
        v = bool(r.get(key, False))
        if v and not in_seg:
            in_seg = True
            start_f = fid
        if not v and in_seg:
            segs.append((frame_time(start_f, fps), frame_time(fid - 1, fps)))
            in_seg = False

    if in_seg and events:
        fid = int(events[-1]["frame_id"])
        segs.append((frame_time(start_f, fps), frame_time(fid, fps)))

    return segs


def safe_div(a: float, b: float) -> float:
    if b == 0:
        return 0.0
    return a / b


def frame_metrics(events: list[dict[str, Any]], gt_segments: list[tuple[float, float]], key: str, fps: float) -> dict[str, float]:
    tp = fp = fn = tn = 0
    for r in events:
        t = frame_time(int(r["frame_id"]), fps)
        gt = any(s <= t <= e for s, e in gt_segments)
        pred = bool(r.get(key, False))
        if pred and gt:
            tp += 1
        elif pred and not gt:
            fp += 1
        elif (not pred) and gt:
            fn += 1
        else:
            tn += 1

    precision = safe_div(tp, tp + fp)
    recall = safe_div(tp, tp + fn)
    f1 = safe_div(2 * precision * recall, precision + recall)

    return {
        "tp_frames": tp,
        "fp_frames": fp,
        "fn_frames": fn,
        "tn_frames": tn,
        "precision": precision,
        "recall": recall,
        "f1": f1,
    }


def segment_metrics(pred_segments: list[tuple[float, float]], gt_segments: list[tuple[float, float]]) -> dict[str, float]:
    matched_gt = set()
    matched_pred = set()

    for i, p in enumerate(pred_segments):
        for j, g in enumerate(gt_segments):
            if overlap(p, g):
                matched_pred.add(i)
                matched_gt.add(j)

    tp_seg = len(matched_gt)
    fp_seg = len(pred_segments) - len(matched_pred)
    fn_seg = len(gt_segments) - len(matched_gt)

    precision_seg = safe_div(tp_seg, tp_seg + fp_seg)
    recall_seg = safe_div(tp_seg, tp_seg + fn_seg)
    f1_seg = safe_div(2 * precision_seg * recall_seg, precision_seg + recall_seg)

    return {
        "tp_segments": tp_seg,
        "fp_segments": fp_seg,
        "fn_segments": fn_seg,
        "precision_segments": precision_seg,
        "recall_segments": recall_seg,
        "f1_segments": f1_seg,
    }


def mean_detection_delay(pred_segments: list[tuple[float, float]], gt_segments: list[tuple[float, float]]) -> float | None:
    delays: list[float] = []
    for gs, ge in gt_segments:
        starts = [ps for ps, pe in pred_segments if overlap((ps, pe), (gs, ge))]
        if starts:
            delays.append(max(0.0, min(starts) - gs))
    if not delays:
        return None
    return sum(delays) / len(delays)


def read_events(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for ln in f:
            ln = ln.strip()
            if ln:
                rows.append(json.loads(ln))
    return rows


def get_fps(video_path: Path) -> float:
    cap = cv2.VideoCapture(str(video_path))
    fps = cap.get(cv2.CAP_PROP_FPS)
    cap.release()
    if fps is None or fps <= 1e-6:
        return 30.0
    return float(fps)


def run_inference_for_video(
    base_cfg: dict[str, Any],
    label: VideoLabel,
    out_jsonl: Path,
    out_vis_dir: Path,
    model_override: str | None,
    device_override: str | None,
    mode_override: str | None,
    tracker_override: str | None,
) -> None:
    cfg = dict(base_cfg)
    cfg["source"] = str(label.video_path)
    cfg["save_jsonl"] = str(out_jsonl)
    cfg["save_visualization"] = False
    cfg["output_dir"] = str(out_vis_dir)
    cfg["verbose"] = False

    if model_override:
        cfg["model"] = model_override
    if device_override is not None:
        cfg["device"] = device_override
    if mode_override is not None:
        cfg["mode"] = mode_override
    if tracker_override is not None:
        cfg["tracker"] = tracker_override

    cfg["source"] = abs_path(PROJECT_ROOT, cfg.get("source"))
    cfg["model"] = abs_path(PROJECT_ROOT, cfg.get("model"))

    out_jsonl.parent.mkdir(parents=True, exist_ok=True)
    runner = PoseRunner(cfg=cfg, project_root=PROJECT_ROOT)
    runner.run()


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    args = parse_args()

    labels_path = Path(args.labels)
    if not labels_path.is_absolute():
        labels_path = (PROJECT_ROOT / labels_path).resolve()

    labels = load_labels(labels_path)
    if not labels:
        raise SystemExit(f"No labels found in {labels_path}")

    cfg_path = Path(args.config)
    if not cfg_path.is_absolute():
        cfg_path = (PROJECT_ROOT / cfg_path).resolve()
    base_cfg = load_yaml(cfg_path)

    out_dir = Path(args.out_dir)
    if not out_dir.is_absolute():
        out_dir = (PROJECT_ROOT / out_dir).resolve()

    jsonl_dir = out_dir / "jsonl"
    vis_dir = out_dir / "vis"
    jsonl_dir.mkdir(parents=True, exist_ok=True)
    vis_dir.mkdir(parents=True, exist_ok=True)

    per_video_rows: list[dict[str, Any]] = []
    segments_rows: list[dict[str, Any]] = []

    raw_tot = {"tp": 0, "fp": 0, "fn": 0, "tn": 0}
    stable_tot = {"tp": 0, "fp": 0, "fn": 0, "tn": 0}

    for lb in labels:
        if not lb.video_path.exists():
            print(f"[skip] {lb.video_id}: video not found -> {lb.video_path}")
            continue

        out_jsonl = jsonl_dir / f"{lb.video_id}.jsonl"

        if not args.skip_inference:
            print(f"[run] {lb.video_id}: {lb.video_path}")
            run_inference_for_video(
                base_cfg=base_cfg,
                label=lb,
                out_jsonl=out_jsonl,
                out_vis_dir=vis_dir / lb.video_id,
                model_override=args.model,
                device_override=args.device,
                mode_override=args.mode,
                tracker_override=args.tracker,
            )
        elif not out_jsonl.exists():
            print(f"[skip] {lb.video_id}: missing jsonl for --skip-inference -> {out_jsonl}")
            continue

        events = read_events(out_jsonl)
        if not events:
            print(f"[skip] {lb.video_id}: empty events -> {out_jsonl}")
            continue

        fps = get_fps(lb.video_path)
        duration_sec = len(events) / fps

        raw_frame = frame_metrics(events, lb.fall_segments, args.raw_key, fps)
        stable_frame = frame_metrics(events, lb.fall_segments, args.stable_key, fps)

        raw_pred_segments = to_segments(events, args.raw_key, fps)
        stable_pred_segments = to_segments(events, args.stable_key, fps)

        raw_seg = segment_metrics(raw_pred_segments, lb.fall_segments)
        stable_seg = segment_metrics(stable_pred_segments, lb.fall_segments)

        delay = mean_detection_delay(stable_pred_segments, lb.fall_segments)

        raw_tot["tp"] += int(raw_frame["tp_frames"])
        raw_tot["fp"] += int(raw_frame["fp_frames"])
        raw_tot["fn"] += int(raw_frame["fn_frames"])
        raw_tot["tn"] += int(raw_frame["tn_frames"])

        stable_tot["tp"] += int(stable_frame["tp_frames"])
        stable_tot["fp"] += int(stable_frame["fp_frames"])
        stable_tot["fn"] += int(stable_frame["fn_frames"])
        stable_tot["tn"] += int(stable_frame["tn_frames"])

        per_video_rows.append(
            {
                "video_id": lb.video_id,
                "video_path": str(lb.video_path),
                "notes": lb.notes,
                "fps": round(fps, 3),
                "frames": len(events),
                "duration_sec": round(duration_sec, 3),
                "gt_segments": len(lb.fall_segments),
                "pred_segments_raw": len(raw_pred_segments),
                "pred_segments_stable": len(stable_pred_segments),
                "raw_tp_frames": raw_frame["tp_frames"],
                "raw_fp_frames": raw_frame["fp_frames"],
                "raw_fn_frames": raw_frame["fn_frames"],
                "raw_precision": round(raw_frame["precision"], 6),
                "raw_recall": round(raw_frame["recall"], 6),
                "raw_f1": round(raw_frame["f1"], 6),
                "stable_tp_frames": stable_frame["tp_frames"],
                "stable_fp_frames": stable_frame["fp_frames"],
                "stable_fn_frames": stable_frame["fn_frames"],
                "stable_precision": round(stable_frame["precision"], 6),
                "stable_recall": round(stable_frame["recall"], 6),
                "stable_f1": round(stable_frame["f1"], 6),
                "raw_fp_segments": raw_seg["fp_segments"],
                "raw_fn_segments": raw_seg["fn_segments"],
                "stable_fp_segments": stable_seg["fp_segments"],
                "stable_fn_segments": stable_seg["fn_segments"],
                "stable_precision_segments": round(stable_seg["precision_segments"], 6),
                "stable_recall_segments": round(stable_seg["recall_segments"], 6),
                "stable_f1_segments": round(stable_seg["f1_segments"], 6),
                "stable_false_alarm_per_min": round(safe_div(stable_seg["fp_segments"], max(duration_sec / 60.0, 1e-9)), 6),
                "stable_mean_detection_delay_sec": "" if delay is None else round(delay, 6),
            }
        )
        segments_rows.append(
            {
                "video_id": lb.video_id,
                "video_path": str(lb.video_path),
                "gt_fall_segments_sec": segments_to_text(lb.fall_segments),
                "pred_raw_fall_segments_sec": segments_to_text(raw_pred_segments),
                "pred_stable_fall_segments_sec": segments_to_text(stable_pred_segments),
            }
        )

    if not per_video_rows:
        raise SystemExit("No valid videos were evaluated.")

    per_video_path = out_dir / "metrics_per_video.csv"
    per_video_fields = list(per_video_rows[0].keys())
    write_csv(per_video_path, per_video_rows, per_video_fields)

    compare_rows = []
    for r in per_video_rows:
        compare_rows.append(
            {
                "video_id": r["video_id"],
                "raw_fp_frames": r["raw_fp_frames"],
                "stable_fp_frames": r["stable_fp_frames"],
                "raw_fn_frames": r["raw_fn_frames"],
                "stable_fn_frames": r["stable_fn_frames"],
                "raw_fp_segments": r["raw_fp_segments"],
                "stable_fp_segments": r["stable_fp_segments"],
                "raw_f1": r["raw_f1"],
                "stable_f1": r["stable_f1"],
            }
        )
    write_csv(out_dir / "metrics_compare.csv", compare_rows, list(compare_rows[0].keys()))
    write_csv(out_dir / "segments_per_video.csv", segments_rows, list(segments_rows[0].keys()))

    def total_to_metrics(tot: dict[str, int]) -> dict[str, float]:
        tp = tot["tp"]
        fp = tot["fp"]
        fn = tot["fn"]
        tn = tot["tn"]
        p = safe_div(tp, tp + fp)
        r = safe_div(tp, tp + fn)
        f1 = safe_div(2 * p * r, p + r)
        return {
            "tp_frames": tp,
            "fp_frames": fp,
            "fn_frames": fn,
            "tn_frames": tn,
            "precision": p,
            "recall": r,
            "f1": f1,
        }

    summary = {
        "videos_evaluated": len(per_video_rows),
        "raw_frame_micro": total_to_metrics(raw_tot),
        "stable_frame_micro": total_to_metrics(stable_tot),
    }

    with (out_dir / "summary.json").open("w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print(f"[done] per-video metrics: {per_video_path}")
    print(f"[done] compare table: {out_dir / 'metrics_compare.csv'}")
    print(f"[done] segment table: {out_dir / 'segments_per_video.csv'}")
    print(f"[done] summary: {out_dir / 'summary.json'}")


if __name__ == "__main__":
    main()
