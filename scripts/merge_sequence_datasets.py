#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Merge multiple sequence dataset .npz files into one training-ready .npz. "
            "Datasets must share feature_dim and seq_len."
        )
    )
    parser.add_argument(
        "--inputs",
        nargs="+",
        required=True,
        help="Input .npz files in the desired merge order.",
    )
    parser.add_argument(
        "--names",
        nargs="*",
        default=None,
        help=(
            "Optional dataset names aligned with --inputs. "
            "Used to populate the per-sample source_dataset field."
        ),
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Output merged .npz path.",
    )
    return parser.parse_args()


def resolve_path(raw: str) -> Path:
    path = Path(raw)
    return (PROJECT_ROOT / path).resolve() if not path.is_absolute() else path


def scalar_int(blob: Any, key: str) -> int:
    arr = blob[key]
    return int(arr[0]) if getattr(arr, "shape", ()) else int(arr)


def scalar_float(blob: Any, key: str) -> float:
    arr = blob[key]
    return float(arr[0]) if getattr(arr, "shape", ()) else float(arr)


def main() -> None:
    args = parse_args()
    input_paths = [resolve_path(p) for p in args.inputs]
    if args.names is not None and len(args.names) not in (0, len(input_paths)):
        raise SystemExit("--names must have the same length as --inputs when provided.")

    output_path = resolve_path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    blobs = [np.load(path, allow_pickle=True) for path in input_paths]
    names = args.names if args.names else [path.stem for path in input_paths]

    feature_dims = {scalar_int(blob, "feature_dim") for blob in blobs}
    seq_lens = {scalar_int(blob, "seq_len") for blob in blobs}
    if len(feature_dims) != 1:
        raise SystemExit(f"feature_dim mismatch across inputs: {sorted(feature_dims)}")
    if len(seq_lens) != 1:
        raise SystemExit(f"seq_len mismatch across inputs: {sorted(seq_lens)}")

    x_parts: list[np.ndarray] = []
    y_parts: list[np.ndarray] = []
    split_parts: list[np.ndarray] = []
    video_id_parts: list[np.ndarray] = []
    frame_start_parts: list[np.ndarray] = []
    source_parts: list[np.ndarray] = []

    positive_ratio_values: list[float] = []
    stride_values: list[int] = []

    for blob, name, path in zip(blobs, names, input_paths):
        for required in ("x", "y", "split", "video_id", "frame_start"):
            if required not in blob.files:
                raise SystemExit(f"{path} is missing required key '{required}'")

        x = blob["x"].astype(np.float32)
        y = blob["y"].astype(np.int64)
        split = blob["split"].astype(str)
        video_id = blob["video_id"].astype(str)
        frame_start = blob["frame_start"].astype(np.int64)

        if not (len(x) == len(y) == len(split) == len(video_id) == len(frame_start)):
            raise SystemExit(f"Sample array length mismatch in {path}")

        x_parts.append(x)
        y_parts.append(y)
        split_parts.append(split)
        video_id_parts.append(video_id)
        frame_start_parts.append(frame_start)
        source_parts.append(np.asarray([name] * len(y)))

        if "positive_ratio" in blob.files:
            positive_ratio_values.append(scalar_float(blob, "positive_ratio"))
        if "stride" in blob.files:
            stride_values.append(scalar_int(blob, "stride"))

    merged = {
        "x": np.concatenate(x_parts, axis=0).astype(np.float32),
        "y": np.concatenate(y_parts, axis=0).astype(np.int64),
        "split": np.concatenate(split_parts, axis=0).astype(str),
        "video_id": np.concatenate(video_id_parts, axis=0).astype(str),
        "frame_start": np.concatenate(frame_start_parts, axis=0).astype(np.int64),
        "source_dataset": np.concatenate(source_parts, axis=0).astype(str),
        "feature_dim": np.asarray([next(iter(feature_dims))], dtype=np.int64),
        "seq_len": np.asarray([next(iter(seq_lens))], dtype=np.int64),
        "merged_from": np.asarray(names).astype(str),
    }

    if stride_values:
        merged["stride"] = np.asarray([min(stride_values)], dtype=np.int64)
    if positive_ratio_values:
        merged["positive_ratio"] = np.asarray([min(positive_ratio_values)], dtype=np.float32)

    np.savez_compressed(output_path, **merged)

    train_count = int(np.sum(merged["split"] == "train"))
    val_count = int(np.sum(merged["split"] == "val"))
    pos_count = int(np.sum(merged["y"] == 1))
    print(f"[done] merged dataset: {output_path}")
    print(
        f"[done] samples={len(merged['y'])} train={train_count} val={val_count} "
        f"positive={pos_count} negative={len(merged['y']) - pos_count}"
    )
    unique_sources, counts = np.unique(merged["source_dataset"], return_counts=True)
    for source, count in zip(unique_sources.tolist(), counts.tolist()):
        print(f"[source] {source}: {count}")


if __name__ == "__main__":
    main()
