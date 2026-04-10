#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Merge multiple label CSV files into one.")
    parser.add_argument("--inputs", nargs="+", required=True, help="Input CSV files.")
    parser.add_argument("--output", required=True, help="Output merged CSV file.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    input_paths = [Path(p).expanduser().resolve() for p in args.inputs]
    output_path = Path(args.output).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    merged_rows: list[dict[str, str]] = []
    fieldnames: list[str] = []
    seen_ids: set[str] = set()

    for path in input_paths:
        with path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            current_fields = list(reader.fieldnames or [])
            for name in current_fields:
                if name not in fieldnames:
                    fieldnames.append(name)

            for row in reader:
                video_id = (row.get("video_id") or "").strip()
                if not video_id:
                    continue
                if video_id in seen_ids:
                    raise SystemExit(f"Duplicate video_id found while merging: {video_id}")
                seen_ids.add(video_id)
                merged_rows.append({k: (v or "") for k, v in row.items()})

    required = ["video_id", "video_path", "fall_segments", "notes"]
    for name in required:
        if name not in fieldnames:
            fieldnames.append(name)

    with output_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in merged_rows:
            normalized = {name: row.get(name, "") for name in fieldnames}
            writer.writerow(normalized)

    print(f"[done] merged {len(merged_rows)} rows -> {output_path}")


if __name__ == "__main__":
    main()
