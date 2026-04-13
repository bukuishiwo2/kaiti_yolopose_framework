#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Sample a sequence dataset .npz into a smaller .npz while preserving train/val split. "
            "Sampling can operate at the sequence level or video_id level."
        )
    )
    parser.add_argument("--input", required=True, help="Input .npz dataset path.")
    parser.add_argument("--output", required=True, help="Output sampled .npz path.")
    parser.add_argument(
        "--fraction",
        type=float,
        default=None,
        help="Fraction to keep per split. Mutually exclusive with --max-units-per-split.",
    )
    parser.add_argument(
        "--max-units-per-split",
        type=int,
        default=None,
        help="Maximum number of sampling units per split. Mutually exclusive with --fraction.",
    )
    parser.add_argument(
        "--unit",
        choices=("video", "sequence"),
        default="video",
        help="Sampling unit. 'video' keeps all sequences from sampled video_ids.",
    )
    parser.add_argument("--seed", type=int, default=42, help="Random seed.")
    return parser.parse_args()


def resolve_path(raw: str) -> Path:
    path = Path(raw)
    return (PROJECT_ROOT / path).resolve() if not path.is_absolute() else path


def choose_count(total: int, fraction: float | None, max_units: int | None) -> int:
    if total <= 0:
        return 0
    if fraction is not None:
        if not (0.0 < fraction <= 1.0):
            raise SystemExit("--fraction must be in (0, 1].")
        return max(1, int(round(total * fraction)))
    if max_units is not None:
        if max_units <= 0:
            raise SystemExit("--max-units-per-split must be > 0.")
        return min(total, max_units)
    raise SystemExit("One of --fraction or --max-units-per-split is required.")


def sample_indices_for_split(
    indices: np.ndarray,
    video_id: np.ndarray,
    rng: np.random.Generator,
    unit: str,
    fraction: float | None,
    max_units: int | None,
) -> np.ndarray:
    if unit == "sequence":
        take = choose_count(len(indices), fraction=fraction, max_units=max_units)
        chosen = rng.choice(indices, size=take, replace=False)
        return np.sort(chosen.astype(np.int64))

    video_ids = np.unique(video_id[indices].astype(str))
    take = choose_count(len(video_ids), fraction=fraction, max_units=max_units)
    chosen_video_ids = rng.choice(video_ids, size=take, replace=False)
    chosen_set = set(chosen_video_ids.tolist())
    chosen = indices[np.isin(video_id[indices].astype(str), list(chosen_set))]
    return np.sort(chosen.astype(np.int64))


def main() -> None:
    args = parse_args()
    if (args.fraction is None) == (args.max_units_per_split is None):
        raise SystemExit("Specify exactly one of --fraction or --max-units-per-split.")

    input_path = resolve_path(args.input)
    output_path = resolve_path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    blob = np.load(input_path, allow_pickle=True)
    required = ("x", "y", "split", "video_id", "frame_start")
    for key in required:
        if key not in blob.files:
            raise SystemExit(f"{input_path} is missing required key '{key}'")

    y = blob["y"]
    split = blob["split"].astype(str)
    video_id = blob["video_id"].astype(str)
    sample_count = len(y)
    for key in required:
        if len(blob[key]) != sample_count:
            raise SystemExit(f"Per-sample array length mismatch for key '{key}'")

    rng = np.random.default_rng(args.seed)
    chosen_parts: list[np.ndarray] = []
    for split_name in sorted(np.unique(split).tolist()):
        split_indices = np.flatnonzero(split == split_name)
        chosen_parts.append(
            sample_indices_for_split(
                split_indices,
                video_id=video_id,
                rng=rng,
                unit=args.unit,
                fraction=args.fraction,
                max_units=args.max_units_per_split,
            )
        )
    chosen_indices = np.concatenate(chosen_parts, axis=0).astype(np.int64)

    sampled: dict[str, np.ndarray] = {}
    for key in blob.files:
        value = blob[key]
        if getattr(value, "shape", ()) and len(value) == sample_count:
            sampled[key] = value[chosen_indices]
        else:
            sampled[key] = value

    sampled["sampled_from"] = np.asarray([str(input_path)], dtype=str)
    sampled["sampled_unit"] = np.asarray([args.unit], dtype=str)
    sampled["sampled_seed"] = np.asarray([args.seed], dtype=np.int64)
    if args.fraction is not None:
        sampled["sampled_fraction"] = np.asarray([args.fraction], dtype=np.float32)
    if args.max_units_per_split is not None:
        sampled["sampled_max_units_per_split"] = np.asarray([args.max_units_per_split], dtype=np.int64)

    np.savez_compressed(output_path, **sampled)

    sampled_split = sampled["split"].astype(str)
    sampled_video = sampled["video_id"].astype(str)
    sampled_y = sampled["y"].astype(np.int64)
    print(f"[done] sampled dataset: {output_path}")
    print(
        f"[done] samples={len(sampled_y)} train={int(np.sum(sampled_split == 'train'))} "
        f"val={int(np.sum(sampled_split == 'val'))} positive={int(np.sum(sampled_y == 1))} "
        f"negative={int(np.sum(sampled_y == 0))}"
    )
    for split_name in sorted(np.unique(sampled_split).tolist()):
        mask = sampled_split == split_name
        print(
            f"[split] {split_name}: samples={int(np.sum(mask))} "
            f"videos={len(np.unique(sampled_video[mask]))}"
        )


if __name__ == "__main__":
    main()
