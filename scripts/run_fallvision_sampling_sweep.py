#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run FallVision no-fall sampling experiments end-to-end: sample, merge, mixed-train, "
            "UR Fall fine-tune, and formal UR Fall evaluation."
        )
    )
    parser.add_argument(
        "--ratios",
        nargs="+",
        type=float,
        required=True,
        help="Sampling ratios, e.g. 0.03 0.10 0.15",
    )
    parser.add_argument(
        "--device",
        default="0",
        help="Torch / eval device passed through to training configs and eval script.",
    )
    parser.add_argument(
        "--reuse-existing",
        action="store_true",
        help="Reuse existing artifacts when present instead of rerunning the step.",
    )
    parser.add_argument(
        "--summary-json",
        default="outputs/fallvision_sampling_sweep_2026-04-13.json",
        help="Where to write the consolidated sweep summary JSON.",
    )
    return parser.parse_args()


def resolve_path(raw: str) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else (PROJECT_ROOT / path).resolve()


def ratio_label(ratio: float) -> str:
    value = int(round(ratio * 100))
    return f"{value:02d}pct"


def run_cmd(args: list[str], *, cwd: Path | None = None) -> None:
    print(f"[run] {' '.join(args)}")
    subprocess.run(args, check=True, cwd=str(cwd or PROJECT_ROOT))


def write_yaml_temp(payload: dict[str, Any]) -> Path:
    try:
        import yaml
    except Exception as exc:  # pragma: no cover - dependency is already in project env
        raise SystemExit(f"PyYAML is required to write temp configs: {exc}") from exc

    tmp = tempfile.NamedTemporaryFile("w", suffix=".yaml", prefix="fallvision_sweep_", delete=False)
    with tmp:
        yaml.safe_dump(payload, tmp, sort_keys=False)
    return Path(tmp.name)


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def parse_adl_fp(metrics_csv: Path) -> dict[str, Any]:
    total_fp_frames = 0
    total_fp_segments = 0
    worst: list[dict[str, Any]] = []
    with metrics_csv.open("r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            video_id = row["video_id"]
            if not video_id.startswith("adl-"):
                continue
            fp_frames = int(float(row["stable_fp_frames"]))
            fp_segments = int(float(row["stable_fp_segments"]))
            total_fp_frames += fp_frames
            total_fp_segments += fp_segments
            worst.append(
                {
                    "video_id": video_id,
                    "stable_fp_frames": fp_frames,
                    "stable_fp_segments": fp_segments,
                }
            )
    worst.sort(key=lambda row: row["stable_fp_frames"], reverse=True)
    return {
        "adl_total_stable_fp_frames": total_fp_frames,
        "adl_total_stable_fp_segments": total_fp_segments,
        "worst_adl_videos": worst[:8],
    }


def maybe_run_sample(
    *,
    ratio: float,
    out_path: Path,
    reuse_existing: bool,
) -> None:
    if reuse_existing and out_path.exists():
        print(f"[reuse] sampled dataset: {out_path}")
        return
    run_cmd(
        [
            sys.executable,
            str(PROJECT_ROOT / "scripts" / "sample_sequence_dataset.py"),
            "--input",
            str(PROJECT_ROOT / "data/processed/fallvision_nofall_pose_sequences.npz"),
            "--output",
            str(out_path),
            "--fraction",
            str(ratio),
            "--unit",
            "video",
            "--seed",
            "42",
        ]
    )


def maybe_run_merge(
    *,
    sampled_path: Path,
    merged_path: Path,
    ratio_name: str,
    reuse_existing: bool,
) -> None:
    if reuse_existing and merged_path.exists():
        print(f"[reuse] merged dataset: {merged_path}")
        return
    run_cmd(
        [
            sys.executable,
            str(PROJECT_ROOT / "scripts" / "merge_sequence_datasets.py"),
            "--inputs",
            str(PROJECT_ROOT / "data/processed/urfall_pose_sequences.npz"),
            str(sampled_path),
            "--names",
            "urfall",
            f"fallvision_nofall_{ratio_name}",
            "--output",
            str(merged_path),
        ]
    )


def maybe_run_train(
    *,
    config_payload: dict[str, Any],
    checkpoint_path: Path,
    reuse_existing: bool,
) -> None:
    if reuse_existing and checkpoint_path.exists():
        print(f"[reuse] checkpoint: {checkpoint_path}")
        return
    config_path = write_yaml_temp(config_payload)
    try:
        run_cmd(
            [
                sys.executable,
                str(PROJECT_ROOT / "scripts" / "run_fall_sequence_train.py"),
                "--config",
                str(config_path),
            ]
        )
    finally:
        config_path.unlink(missing_ok=True)


def maybe_run_eval(
    *,
    checkpoint_path: Path,
    out_dir: Path,
    device: str,
    reuse_existing: bool,
) -> None:
    summary_path = out_dir / "summary.json"
    if reuse_existing and summary_path.exists():
        print(f"[reuse] eval summary: {summary_path}")
        return

    infer_cfg = {
        "model": "yolo11n-pose.pt",
        "mode": "predict",
        "source": 0,
        "imgsz": 640,
        "conf": 0.25,
        "iou": 0.7,
        "device": None,
        "half": False,
        "classes": [0],
        "vid_stride": 1,
        "stream_buffer": False,
        "show": False,
        "save_visualization": True,
        "output_dir": "outputs/vis",
        "save_jsonl": "outputs/pose_events.jsonl",
        "tracker": "bytetrack.yaml",
        "stabilizer": {
            "min_true_frames": 3,
            "min_false_frames": 5,
            "min_persons": 1,
        },
        "fall_detector": {
            "enabled": True,
            "keypoint_conf_threshold": 0.3,
            "bbox_aspect_ratio_threshold": 1.2,
            "torso_vertical_ratio_threshold": 0.22,
            "hip_to_ankle_vertical_ratio_threshold": 0.38,
            "min_signals_to_fall": 2,
            "min_true_frames": 5,
            "min_false_frames": 8,
            "use_track_stabilization": True,
            "track_ttl_frames": 45,
        },
        "sequence_fall_detector": {
            "enabled": True,
            "model_path": str(checkpoint_path.relative_to(PROJECT_ROOT)),
            "device": None,
            "seq_len": 32,
            "score_threshold": 0.6,
            "keypoint_conf_threshold": 0.3,
            "min_true_frames": 3,
            "min_false_frames": 5,
            "use_track_sequences": True,
            "track_ttl_frames": 45,
        },
    }
    cfg_path = write_yaml_temp(infer_cfg)
    try:
        run_cmd(
            [
                sys.executable,
                str(PROJECT_ROOT / "scripts" / "eval_fall_batch.py"),
                "--labels",
                str(PROJECT_ROOT / "data/eval/video_labels_urfall_cam0.csv"),
                "--config",
                str(cfg_path),
                "--mode",
                "predict",
                "--device",
                str(device),
                "--raw-key",
                "seq_raw_fall_detected",
                "--stable-key",
                "seq_stable_fall_detected",
                "--out-dir",
                str(out_dir),
            ]
        )
    finally:
        cfg_path.unlink(missing_ok=True)


def main() -> None:
    args = parse_args()
    summary_path = resolve_path(args.summary_json)
    summary_path.parent.mkdir(parents=True, exist_ok=True)

    results: dict[str, Any] = {"ratios": {}}

    for ratio in args.ratios:
        label = ratio_label(ratio)
        sampled_path = resolve_path(f"data/processed/fallvision_nofall_pose_sequences_sampled_{label}.npz")
        merged_path = resolve_path(f"data/processed/urfall_plus_fallvision_nofall_sampled_{label}_sequences.npz")
        mixed_ckpt = resolve_path(f"models/fall_sequence_lstm_urfall_plus_fallvision_nofall_sampled_{label}.pt")
        finetune_ckpt = resolve_path(f"models/fall_sequence_lstm_urfall_finetune_from_fallvision_sampled_{label}.pt")
        eval_dir = resolve_path(f"outputs/eval_urfall_sequence_fallvision_nofall_sampled_{label}_finetuned")

        maybe_run_sample(ratio=ratio, out_path=sampled_path, reuse_existing=args.reuse_existing)
        maybe_run_merge(sampled_path=sampled_path, merged_path=merged_path, ratio_name=label, reuse_existing=args.reuse_existing)

        mixed_cfg = {
            "data": {"dataset": str(merged_path.relative_to(PROJECT_ROOT))},
            "model": {"hidden_dim": 128, "num_layers": 2, "dropout": 0.2, "bidirectional": False},
            "train": {
                "device": args.device,
                "batch_size": 64,
                "epochs": 20,
                "learning_rate": 0.001,
                "weight_decay": 0.0001,
                "threshold": 0.5,
            },
            "output": {"checkpoint": str(mixed_ckpt.relative_to(PROJECT_ROOT))},
        }
        maybe_run_train(config_payload=mixed_cfg, checkpoint_path=mixed_ckpt, reuse_existing=args.reuse_existing)

        finetune_cfg = {
            "data": {"dataset": "data/processed/urfall_pose_sequences.npz"},
            "model": {"hidden_dim": 128, "num_layers": 2, "dropout": 0.2, "bidirectional": False},
            "train": {
                "device": args.device,
                "batch_size": 64,
                "epochs": 12,
                "learning_rate": 0.0003,
                "weight_decay": 0.0001,
                "threshold": 0.5,
                "init_checkpoint": str(mixed_ckpt.relative_to(PROJECT_ROOT)),
            },
            "output": {"checkpoint": str(finetune_ckpt.relative_to(PROJECT_ROOT))},
        }
        maybe_run_train(config_payload=finetune_cfg, checkpoint_path=finetune_ckpt, reuse_existing=args.reuse_existing)

        maybe_run_eval(
            checkpoint_path=finetune_ckpt,
            out_dir=eval_dir,
            device=args.device,
            reuse_existing=args.reuse_existing,
        )

        eval_summary = load_json(eval_dir / "summary.json")
        stable = eval_summary["stable_frame_micro"]
        adl_fp = parse_adl_fp(eval_dir / "metrics_per_video.csv")
        results["ratios"][label] = {
            "ratio": ratio,
            "sampled_dataset": str(sampled_path.relative_to(PROJECT_ROOT)),
            "merged_dataset": str(merged_path.relative_to(PROJECT_ROOT)),
            "mixed_checkpoint": str(mixed_ckpt.relative_to(PROJECT_ROOT)),
            "finetuned_checkpoint": str(finetune_ckpt.relative_to(PROJECT_ROOT)),
            "eval_dir": str(eval_dir.relative_to(PROJECT_ROOT)),
            "stable_precision": stable["precision"],
            "stable_recall": stable["recall"],
            "stable_f1": stable["f1"],
            **adl_fp,
        }

    with summary_path.open("w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"[done] sweep summary: {summary_path}")


if __name__ == "__main__":
    main()
