#!/usr/bin/env python3
from __future__ import annotations

import argparse
import contextlib
import json
import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
LEGACY_ROOT = PROJECT_ROOT / "data" / "Fall Detection Video Dataset"
FALL_KEYPOINTS_ROOT = PROJECT_ROOT / "data" / "external" / "fallvision_fall_keypoints"
FALL_VIDEOS_ROOT = PROJECT_ROOT / "data" / "external" / "fallvision_fall_videos_debug"
CANONICAL_ROOT = PROJECT_ROOT / "data" / "external" / "fallvision"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Create a canonical FallVision view under data/external/fallvision "
            "without moving or deleting existing local dataset assets."
        )
    )
    parser.add_argument("--apply", action="store_true", help="Create or update symlinks instead of dry-run only.")
    parser.add_argument(
        "--canonical-root",
        default=str(CANONICAL_ROOT.relative_to(PROJECT_ROOT)),
        help="Canonical grouped FallVision root.",
    )
    return parser.parse_args()


def resolve_repo_path(raw: str) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else (PROJECT_ROOT / path).resolve()


def rel_to_project(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path.resolve())


def leaf_dataset_dirs(root: Path) -> list[Path]:
    if not root.exists():
        return []
    leaves: list[Path] = []
    for path in sorted(root.rglob("*")):
        if not path.is_dir():
            continue
        if any(child.is_file() and child.suffix.lower() == ".csv" for child in path.iterdir()):
            leaves.append(path)
    return leaves


def extracted_payload_files(root: Path) -> list[Path]:
    if not root.exists():
        return []
    matched: list[Path] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if path.name == ".extracted.ok":
            continue
        if path.suffix.lower() in {".rar", ".zip", ".7z", ".tar", ".gz", ".bz2", ".xz"}:
            continue
        matched.append(path)
    return matched


def archive_files(root: Path) -> list[Path]:
    if not root.exists():
        return []
    matched: list[Path] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() in {".rar", ".zip", ".7z", ".tar", ".gz", ".bz2", ".xz"}:
            matched.append(path)
    return matched


def clear_symlink_tree(root: Path) -> None:
    if not root.exists():
        return
    for path in sorted(root.rglob("*"), reverse=True):
        if path.is_symlink():
            path.unlink()
            continue
        if path.is_dir():
            with contextlib.suppress(OSError):
                path.rmdir()


def ensure_parent(path: Path, apply: bool) -> None:
    if apply:
        path.parent.mkdir(parents=True, exist_ok=True)


def safe_symlink(src: Path, dst: Path, apply: bool, records: list[dict[str, str]]) -> None:
    record = {"src": str(src), "dst": str(dst)}
    if not src.exists():
        record["status"] = "missing_source"
        records.append(record)
        return
    if dst.exists() or dst.is_symlink():
        if dst.is_symlink() and os.path.realpath(dst) == str(src.resolve()):
            record["status"] = "already_linked"
            records.append(record)
            return
        record["status"] = "conflict_existing_path"
        records.append(record)
        return
    record["status"] = "planned" if not apply else "linked"
    records.append(record)
    if not apply:
        return
    ensure_parent(dst, apply=True)
    dst.symlink_to(src)


def add_mapping_group(
    *,
    source_root: Path,
    target_root: Path,
    entries: list[Path],
    records: list[dict[str, str]],
    apply: bool,
) -> None:
    for src in entries:
        rel = src.relative_to(source_root)
        dst = target_root / rel
        safe_symlink(src, dst, apply=apply, records=records)


def write_report(path: Path, payload: dict[str, object], apply: bool) -> None:
    if not apply:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def main() -> None:
    args = parse_args()
    apply = bool(args.apply)
    canonical_root = resolve_repo_path(args.canonical_root)
    raw_root = canonical_root / "raw"
    extracted_root = canonical_root / "extracted"
    manifests_root = canonical_root / "manifests"
    reports_root = canonical_root / "reports"
    splits_root = canonical_root / "splits"
    if apply:
        for directory in (raw_root, extracted_root, manifests_root, reports_root, splits_root):
            directory.mkdir(parents=True, exist_ok=True)
        clear_symlink_tree(raw_root)
        clear_symlink_tree(extracted_root)

    records: list[dict[str, str]] = []

    legacy_no_fall = LEGACY_ROOT / "No Fall"
    add_mapping_group(
        source_root=legacy_no_fall,
        target_root=raw_root / "No Fall",
        entries=archive_files(legacy_no_fall),
        records=records,
        apply=apply,
    )
    add_mapping_group(
        source_root=legacy_no_fall,
        target_root=extracted_root / "No Fall",
        entries=extracted_payload_files(legacy_no_fall),
        records=records,
        apply=apply,
    )

    fall_raw_root = FALL_KEYPOINTS_ROOT / "raw" / "Fall"
    fall_extracted_root = FALL_KEYPOINTS_ROOT / "extracted" / "Fall"
    add_mapping_group(
        source_root=fall_raw_root,
        target_root=raw_root / "Fall",
        entries=archive_files(fall_raw_root),
        records=records,
        apply=apply,
    )
    add_mapping_group(
        source_root=fall_extracted_root,
        target_root=extracted_root / "Fall",
        entries=extracted_payload_files(fall_extracted_root),
        records=records,
        apply=apply,
    )

    fall_videos_raw_root = FALL_VIDEOS_ROOT / "raw" / "Fall"
    fall_videos_extracted_root = FALL_VIDEOS_ROOT / "extracted" / "Fall"
    add_mapping_group(
        source_root=fall_videos_raw_root,
        target_root=raw_root / "Fall",
        entries=archive_files(fall_videos_raw_root),
        records=records,
        apply=apply,
    )
    add_mapping_group(
        source_root=fall_videos_extracted_root,
        target_root=extracted_root / "Fall",
        entries=extracted_payload_files(fall_videos_extracted_root),
        records=records,
        apply=apply,
    )

    payload = {
        "canonical_root": rel_to_project(canonical_root),
        "legacy_no_fall_root": rel_to_project(legacy_no_fall),
        "fall_keypoints_root": rel_to_project(FALL_KEYPOINTS_ROOT),
        "fall_videos_root": rel_to_project(FALL_VIDEOS_ROOT),
        "apply": apply,
        "record_count": len(records),
        "records": records,
    }
    write_report(manifests_root / "layout_sync_report.json", payload, apply=apply)


if __name__ == "__main__":
    main()
