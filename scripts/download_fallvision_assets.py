#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import urllib.request
from collections import defaultdict
from pathlib import Path
from typing import Any


DATASET_PID = "doi:10.7910/DVN/75QPKK"
DATASET_API_URL = (
    "https://dataverse.harvard.edu/api/datasets/:persistentId/"
    f"?persistentId={DATASET_PID}"
)
DATAFILE_URL_TEMPLATE = "https://dataverse.harvard.edu/api/access/datafile/{file_id}"

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Download selected FallVision assets from Harvard Dataverse. "
            "Defaults to keypoint archives only, without video archives."
        )
    )
    parser.add_argument(
        "--out-root",
        default="data/Fall Detection Video Dataset",
        help="Local directory used to store downloaded archives.",
    )
    parser.add_argument(
        "--asset-type",
        choices=["keypoints", "videos", "both"],
        default="keypoints",
        help="Which asset family to download.",
    )
    parser.add_argument(
        "--label",
        choices=["fall", "no_fall", "both"],
        default="both",
        help="Which label partition to download.",
    )
    parser.add_argument(
        "--scene",
        choices=["bed", "chair", "stand", "all"],
        default="all",
        help="Which scene subgroup to download.",
    )
    parser.add_argument(
        "--variant",
        choices=["mask", "raw", "both"],
        default="mask",
        help=(
            "Which variant to download. Keypoint archives only exist for mask videos. "
            "When asset-type=keypoints, raw is ignored."
        ),
    )
    parser.add_argument(
        "--max-files",
        type=int,
        default=None,
        help="Download at most N matched files after filtering and sorting.",
    )
    parser.add_argument(
        "--max-files-per-group",
        type=int,
        default=None,
        help=(
            "Cap downloads per (label, scene) group after sorting. "
            "Useful for smoke-test subsets."
        ),
    )
    parser.add_argument(
        "--match",
        default=None,
        help="Optional substring filter applied to the remote filename.",
    )
    parser.add_argument(
        "--manifest",
        default=None,
        help="Optional path for a JSON manifest of the selected files.",
    )
    parser.add_argument(
        "--extract",
        action="store_true",
        help="Extract downloaded .rar archives when an extractor is available.",
    )
    parser.add_argument(
        "--remove-archives-after-extract",
        action="store_true",
        help="Delete the downloaded .rar files after successful extraction.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only print the matched files without downloading.",
    )
    return parser.parse_args()


def load_dataset_metadata() -> dict[str, Any]:
    request = urllib.request.Request(
        DATASET_API_URL,
        headers={
            "User-Agent": "kaiti-yolopose-framework/0.1",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(request) as response:
        payload = json.load(response)
    if payload.get("status") != "OK":
        raise RuntimeError(f"Unexpected Dataverse response: {payload!r}")
    return payload["data"]


def infer_label(directory_label: str) -> str:
    parts = [part.strip().lower() for part in directory_label.split("/") if part.strip()]
    if "no fall" in parts:
        return "no_fall"
    if "fall" in parts:
        return "fall"
    return "unknown"


def infer_scene(directory_label: str) -> str:
    parts = {part.strip().lower() for part in directory_label.split("/") if part.strip()}
    for scene in ("bed", "chair", "stand"):
        if scene in parts:
            return scene
    return "unknown"


def infer_variant(directory_label: str) -> str:
    lowered = directory_label.lower()
    if "mask video" in lowered:
        return "mask"
    if "raw video" in lowered:
        return "raw"
    return "unknown"


def infer_asset_type(filename: str) -> str:
    lowered = filename.lower()
    if "keypoints_csv" in lowered or "ketpoints_csv" in lowered:
        return "keypoints"
    return "videos"


def rel_archive_dir(directory_label: str) -> Path:
    parts = [part.strip() for part in directory_label.split("/") if part.strip()]
    if parts and parts[0].lower() == "fall detection video dataset":
        parts = parts[1:]
    return Path(*parts)


def select_files(
    files: list[dict[str, Any]],
    *,
    asset_type: str,
    label: str,
    scene: str,
    variant: str,
    match: str | None,
    max_files_per_group: int | None,
    max_files: int | None,
) -> list[dict[str, Any]]:
    match_lower = match.lower() if match else None
    selected: list[dict[str, Any]] = []

    for item in files:
        data_file = item.get("dataFile", {})
        filename = str(data_file.get("filename", ""))
        directory_label = str(item.get("directoryLabel", ""))
        item_asset_type = infer_asset_type(filename)
        item_label = infer_label(directory_label)
        item_scene = infer_scene(directory_label)
        item_variant = infer_variant(directory_label)

        if asset_type != "both" and item_asset_type != asset_type:
            continue
        if label != "both" and item_label != label:
            continue
        if scene != "all" and item_scene != scene:
            continue
        if item_asset_type == "videos" and variant != "both" and item_variant != variant:
            continue
        if item_asset_type == "keypoints" and item_variant != "mask":
            continue
        if match_lower and match_lower not in filename.lower():
            continue

        enriched = {
            "file_id": int(data_file["id"]),
            "filename": filename,
            "filesize": int(data_file.get("filesize", 0)),
            "md5": str(data_file.get("md5", "")),
            "directory_label": directory_label,
            "rel_dir": str(rel_archive_dir(directory_label)),
            "asset_type": item_asset_type,
            "label": item_label,
            "scene": item_scene,
            "variant": item_variant,
        }
        selected.append(enriched)

    selected.sort(key=lambda item: (item["label"], item["scene"], item["filename"]))

    if max_files_per_group is not None:
        grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
        for item in selected:
            grouped[(item["label"], item["scene"])].append(item)

        capped: list[dict[str, Any]] = []
        for group_key in sorted(grouped.keys()):
            capped.extend(grouped[group_key][: max(0, max_files_per_group)])
        selected = capped

    if max_files is not None:
        selected = selected[: max(0, max_files)]

    return selected


def sizeof_fmt(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024.0 or unit == "TB":
            return f"{value:.1f}{unit}"
        value /= 1024.0
    return f"{size}B"


def write_manifest(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def find_extractor() -> list[str] | None:
    for candidate in (["unrar", "x"], ["7z", "x", "-y"], ["unar"]):
        if shutil.which(candidate[0]):
            return candidate
    return None


def extract_archive(archive_path: Path, out_dir: Path, extractor: list[str]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = list(extractor)
    if extractor[0] == "unrar":
        cmd.extend([str(archive_path), str(out_dir)])
    elif extractor[0] == "7z":
        cmd.extend([f"-o{out_dir}", str(archive_path)])
    else:
        cmd.extend(["-o", str(out_dir), str(archive_path)])
    subprocess.run(cmd, check=True)


def download_file(file_id: int, target_path: Path) -> None:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    url = DATAFILE_URL_TEMPLATE.format(file_id=file_id)
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "kaiti-yolopose-framework/0.1",
            "Accept": "*/*",
        },
    )
    with urllib.request.urlopen(request) as response, target_path.open("wb") as out_file:
        shutil.copyfileobj(response, out_file)


def main() -> None:
    args = parse_args()
    out_root = (PROJECT_ROOT / args.out_root).resolve() if not Path(args.out_root).is_absolute() else Path(args.out_root)

    dataset = load_dataset_metadata()
    files = list(dataset["latestVersion"]["files"])
    selected = select_files(
        files,
        asset_type=args.asset_type,
        label=args.label,
        scene=args.scene,
        variant=args.variant,
        match=args.match,
        max_files_per_group=args.max_files_per_group,
        max_files=args.max_files,
    )

    if not selected:
        raise SystemExit("No FallVision files matched the requested filters.")

    total_size = sum(item["filesize"] for item in selected)
    print(f"[fallvision] persistent_id={DATASET_PID}")
    print(f"[fallvision] matched_files={len(selected)} total_size={sizeof_fmt(total_size)}")
    for item in selected:
        print(
            f" - {item['filename']} [{item['label']}/{item['scene']}/{item['asset_type']}] "
            f"{sizeof_fmt(item['filesize'])}"
        )

    manifest_payload = {
        "persistent_id": DATASET_PID,
        "source_api": DATASET_API_URL,
        "matched_files": selected,
        "total_size_bytes": total_size,
    }
    manifest_path = None
    if args.manifest:
        manifest_path = (
            (PROJECT_ROOT / args.manifest).resolve()
            if not Path(args.manifest).is_absolute()
            else Path(args.manifest)
        )
    else:
        manifest_path = out_root / "_download_manifest.json"
    write_manifest(manifest_path, manifest_payload)
    print(f"[fallvision] manifest={manifest_path}")

    if args.dry_run:
        print("[fallvision] dry-run only, no files downloaded")
        return

    extractor = find_extractor() if args.extract else None
    if args.extract and extractor is None:
        raise SystemExit(
            "No archive extractor found. Install one of: unrar, 7z, unar. "
            "Or rerun without --extract."
        )

    for idx, item in enumerate(selected, start=1):
        archive_dir = out_root / item["rel_dir"]
        archive_path = archive_dir / item["filename"]
        if archive_path.exists() and archive_path.stat().st_size == item["filesize"]:
            print(f"[skip {idx}/{len(selected)}] already exists: {archive_path}")
        else:
            print(
                f"[download {idx}/{len(selected)}] {item['filename']} "
                f"-> {archive_path}"
            )
            download_file(item["file_id"], archive_path)

        if extractor is not None:
            extract_dir = archive_path.with_suffix("")
            marker = extract_dir / ".extracted.ok"
            if marker.exists():
                print(f"[skip extract] already extracted: {extract_dir}")
            else:
                print(f"[extract {idx}/{len(selected)}] {archive_path} -> {extract_dir}")
                extract_archive(archive_path, extract_dir, extractor)
                marker.write_text("ok\n", encoding="utf-8")
            if args.remove_archives_after_extract:
                archive_path.unlink(missing_ok=True)

    print("[fallvision] done")


if __name__ == "__main__":
    main()
