#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import itertools
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Grid-search fall detector parameters using eval_fall_batch.py")
    parser.add_argument("--labels", default="data/eval/video_labels_urfall_cam0.csv", help="Labels CSV")
    parser.add_argument("--base-config", default="configs/infer_pose_stream.yaml", help="Base infer config")
    parser.add_argument("--grid", default="data/eval/fall_grid_track.yaml", help="Grid YAML")
    parser.add_argument("--device", default="0", help="Inference device")
    parser.add_argument("--mode", choices=["predict", "track"], default="track", help="Inference mode")
    parser.add_argument("--tracker", default="bytetrack.yaml", help="Tracker yaml used when mode=track")
    parser.add_argument("--model", default=None, help="Optional model override")
    parser.add_argument("--out-dir", default="outputs/tune_fall_grid", help="Output directory")
    parser.add_argument("--max-combinations", type=int, default=None, help="Only run first N combos")
    parser.add_argument("--max-videos", type=int, default=None, help="Only run first N videos from labels")
    parser.add_argument(
        "--target-detector",
        choices=["fall_detector", "sequence_fall_detector"],
        default=None,
        help="Config section to tune. When omitted, infer from grid YAML root key.",
    )
    parser.add_argument("--raw-key", default="raw_fall_detected", help="JSONL raw fall field to evaluate.")
    parser.add_argument("--stable-key", default="stable_fall_detected", help="JSONL stable fall field to evaluate.")
    return parser.parse_args()


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def resolve_target_detector(grid_cfg: dict[str, Any], explicit: str | None) -> str:
    if explicit:
        return explicit

    candidates = ["sequence_fall_detector", "fall_detector"]
    hits = [name for name in candidates if isinstance(grid_cfg.get(name), dict)]
    if len(hits) != 1:
        raise ValueError(
            "Grid YAML must contain exactly one supported detector root "
            "('fall_detector' or 'sequence_fall_detector') unless --target-detector is set"
        )
    return hits[0]


def expand_grid(grid_cfg: dict[str, Any], target_detector: str) -> list[dict[str, Any]]:
    if target_detector not in grid_cfg or not isinstance(grid_cfg[target_detector], dict):
        raise ValueError(f"Grid YAML must contain '{target_detector}' mapping")

    items: list[tuple[str, list[Any]]] = []
    for k, v in grid_cfg[target_detector].items():
        if isinstance(v, list):
            values = v
        else:
            values = [v]
        if not values:
            raise ValueError(f"Grid key '{k}' has empty candidate list")
        items.append((k, values))

    keys = [k for k, _ in items]
    value_lists = [vals for _, vals in items]

    combos: list[dict[str, Any]] = []
    for values in itertools.product(*value_lists):
        combos.append(dict(zip(keys, values)))
    return combos


def maybe_subset_labels(labels_path: Path, out_dir: Path, max_videos: int | None) -> Path:
    if max_videos is None:
        return labels_path

    with labels_path.open("r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
        fieldnames = rows[0].keys() if rows else ["video_id", "video_path", "fall_segments", "notes"]

    subset = rows[: max(0, max_videos)]
    target = out_dir / "labels_subset.csv"
    with target.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(subset)
    return target


def write_cfg(base_cfg: dict[str, Any], combo: dict[str, Any], path: Path, target_detector: str) -> None:
    cfg = json.loads(json.dumps(base_cfg))
    detector_cfg = dict(cfg.get(target_detector, {}))
    for k, v in combo.items():
        detector_cfg[k] = v
    cfg[target_detector] = detector_cfg
    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(cfg, f, sort_keys=False, allow_unicode=False)


def read_metrics(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def to_int(x: Any) -> int:
    try:
        return int(float(x))
    except Exception:
        return 0


def to_float(x: Any) -> float:
    try:
        return float(x)
    except Exception:
        return 0.0


def aggregate(rows: list[dict[str, Any]], prefix: str, predicate) -> dict[str, float]:
    subset = [r for r in rows if predicate(r)]
    tp = sum(to_int(r[f"{prefix}_tp_frames"]) for r in subset)
    fp = sum(to_int(r[f"{prefix}_fp_frames"]) for r in subset)
    fn = sum(to_int(r[f"{prefix}_fn_frames"]) for r in subset)

    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0

    fp_seg = sum(to_int(r[f"{prefix}_fp_segments"]) for r in subset)
    fn_seg = sum(to_int(r[f"{prefix}_fn_segments"]) for r in subset)
    fa_per_min = [to_float(r["stable_false_alarm_per_min"]) for r in subset]

    return {
        "count": len(subset),
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "fp_segments": fp_seg,
        "fn_segments": fn_seg,
        "mean_false_alarm_per_min": (sum(fa_per_min) / len(fa_per_min)) if fa_per_min else 0.0,
    }


def evaluate_combo(metrics_rows: list[dict[str, Any]]) -> dict[str, float]:
    all_s = aggregate(metrics_rows, "stable", lambda _r: True)
    fall_s = aggregate(metrics_rows, "stable", lambda r: str(r["video_id"]).startswith("fall-"))
    adl_s = aggregate(metrics_rows, "stable", lambda r: str(r["video_id"]).startswith("adl-"))

    return {
        "all_precision": all_s["precision"],
        "all_recall": all_s["recall"],
        "all_f1": all_s["f1"],
        "fall_recall": fall_s["recall"],
        "fall_fn_segments": fall_s["fn_segments"],
        "adl_fp_segments": adl_s["fp_segments"],
        "adl_false_alarm_per_min": adl_s["mean_false_alarm_per_min"],
        "all_fp_frames": all_s["fp"],
        "all_fn_frames": all_s["fn"],
    }


def run_combo(
    combo_id: int,
    combo: dict[str, Any],
    labels_path: Path,
    cfg_path: Path,
    out_root: Path,
    mode: str,
    tracker: str,
    device: str,
    model: str | None,
    raw_key: str,
    stable_key: str,
) -> tuple[bool, str, Path]:
    run_dir = out_root / f"run_{combo_id:03d}"
    run_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable,
        str(PROJECT_ROOT / "scripts" / "eval_fall_batch.py"),
        "--labels",
        str(labels_path),
        "--config",
        str(cfg_path),
        "--mode",
        mode,
        "--tracker",
        tracker,
        "--device",
        str(device),
        "--out-dir",
        str(run_dir),
        "--raw-key",
        raw_key,
        "--stable-key",
        stable_key,
    ]
    if model:
        cmd.extend(["--model", model])

    proc = subprocess.run(cmd, capture_output=True, text=True)
    (run_dir / "stdout.log").write_text(proc.stdout, encoding="utf-8")
    (run_dir / "stderr.log").write_text(proc.stderr, encoding="utf-8")

    ok = proc.returncode == 0
    msg = "ok" if ok else f"failed(returncode={proc.returncode})"
    return ok, msg, run_dir


def main() -> None:
    args = parse_args()

    labels_path = (PROJECT_ROOT / args.labels).resolve() if not Path(args.labels).is_absolute() else Path(args.labels)
    base_cfg_path = (
        (PROJECT_ROOT / args.base_config).resolve()
        if not Path(args.base_config).is_absolute()
        else Path(args.base_config)
    )
    grid_path = (PROJECT_ROOT / args.grid).resolve() if not Path(args.grid).is_absolute() else Path(args.grid)
    out_dir = (PROJECT_ROOT / args.out_dir).resolve() if not Path(args.out_dir).is_absolute() else Path(args.out_dir)

    out_dir.mkdir(parents=True, exist_ok=True)
    cfg_out = out_dir / "configs"
    cfg_out.mkdir(parents=True, exist_ok=True)

    base_cfg = load_yaml(base_cfg_path)
    grid_cfg = load_yaml(grid_path)
    target_detector = resolve_target_detector(grid_cfg, args.target_detector)
    combos = expand_grid(grid_cfg, target_detector)
    if args.max_combinations is not None:
        combos = combos[: max(0, args.max_combinations)]

    labels_used = maybe_subset_labels(labels_path, out_dir, args.max_videos)

    print(f"[tune] labels={labels_used}")
    print(f"[tune] detector={target_detector}")
    print(f"[tune] keys raw={args.raw_key} stable={args.stable_key}")
    print(f"[tune] combos={len(combos)}")

    leaderboard: list[dict[str, Any]] = []

    for idx, combo in enumerate(combos, start=1):
        combo_tag = f"c{idx:03d}"
        combo_cfg_path = cfg_out / f"{combo_tag}.yaml"
        write_cfg(base_cfg, combo, combo_cfg_path, target_detector)

        print(f"[run] {combo_tag} {combo}")
        ok, status, run_dir = run_combo(
            combo_id=idx,
            combo=combo,
            labels_path=labels_used,
            cfg_path=combo_cfg_path,
            out_root=out_dir,
            mode=args.mode,
            tracker=args.tracker,
            device=args.device,
            model=args.model,
            raw_key=args.raw_key,
            stable_key=args.stable_key,
        )

        row: dict[str, Any] = {
            "combo_id": combo_tag,
            "status": status,
            "run_dir": str(run_dir),
        }
        row.update({f"param.{k}": v for k, v in combo.items()})

        if ok:
            metrics_path = run_dir / "metrics_per_video.csv"
            if metrics_path.exists():
                metrics_rows = read_metrics(metrics_path)
                row.update(evaluate_combo(metrics_rows))
            else:
                row["status"] = "failed(missing metrics_per_video.csv)"

        leaderboard.append(row)

    # sort successful rows by objective priority
    def sort_key(r: dict[str, Any]):
        if not str(r.get("status", "")).startswith("ok"):
            return (1, float("inf"), float("inf"), float("inf"), float("-inf"))
        return (
            0,
            to_int(r.get("fall_fn_segments", 0)),
            to_int(r.get("adl_fp_segments", 0)),
            to_float(r.get("adl_false_alarm_per_min", 0.0)),
            -to_float(r.get("all_f1", 0.0)),
        )

    leaderboard.sort(key=sort_key)

    # assign rank to successful runs
    rank = 0
    for r in leaderboard:
        if str(r.get("status", "")).startswith("ok"):
            rank += 1
            r["rank"] = rank
        else:
            r["rank"] = ""

    # write leaderboard
    all_keys = []
    for r in leaderboard:
        for k in r.keys():
            if k not in all_keys:
                all_keys.append(k)

    leaderboard_path = out_dir / "leaderboard.csv"
    with leaderboard_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=all_keys)
        writer.writeheader()
        writer.writerows(leaderboard)

    # export best config
    best = next((r for r in leaderboard if str(r.get("status", "")).startswith("ok")), None)
    if best is not None:
        best_cfg = json.loads(json.dumps(base_cfg))
        best_detector_cfg = dict(best_cfg.get(target_detector, {}))
        for k, v in best.items():
            if k.startswith("param."):
                best_detector_cfg[k.split(".", 1)[1]] = v
        best_cfg[target_detector] = best_detector_cfg
        with (out_dir / "best_config.yaml").open("w", encoding="utf-8") as f:
            yaml.safe_dump(best_cfg, f, sort_keys=False, allow_unicode=False)

        best_summary = {
            "combo_id": best.get("combo_id"),
            "status": best.get("status"),
            "rank": best.get("rank"),
            "run_dir": best.get("run_dir"),
            "target_detector": target_detector,
            "raw_key": args.raw_key,
            "stable_key": args.stable_key,
            "metrics": {
                "all_f1": best.get("all_f1"),
                "fall_recall": best.get("fall_recall"),
                "fall_fn_segments": best.get("fall_fn_segments"),
                "adl_fp_segments": best.get("adl_fp_segments"),
                "adl_false_alarm_per_min": best.get("adl_false_alarm_per_min"),
            },
            "params": {k.split(".", 1)[1]: v for k, v in best.items() if k.startswith("param.")},
        }
        (out_dir / "best_summary.json").write_text(json.dumps(best_summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[done] leaderboard: {leaderboard_path}")
    if best is not None:
        print(f"[done] best config: {out_dir / 'best_config.yaml'}")
        print(f"[done] best summary: {out_dir / 'best_summary.json'}")


if __name__ == "__main__":
    main()
