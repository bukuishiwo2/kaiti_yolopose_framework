#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import subprocess
import sys
import tarfile
import urllib.parse
import urllib.request
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any

import cv2


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from yolopose.core.config import load_yaml


MEDIA_EXTENSIONS = {
    ".mp4",
    ".avi",
    ".mov",
    ".mkv",
    ".webm",
    ".m4v",
}
ARCHIVE_EXTENSIONS = {
    ".zip",
    ".rar",
    ".7z",
    ".tar",
    ".tgz",
    ".gz",
    ".bz2",
    ".xz",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Prepare external dataset resources under data/external/ without changing "
            "the default UR Fall + LSTM mainline."
        )
    )
    parser.add_argument(
        "--dataset-config",
        required=True,
        help="Path to dataset intake config YAML, e.g. configs/external_datasets/fallvision_fall_keypoints.yaml",
    )
    parser.add_argument("--download", action="store_true", help="Download or register remote resources.")
    parser.add_argument("--extract", action="store_true", help="Extract archives into the dataset extracted/ tree.")
    parser.add_argument("--generate-manifest", action="store_true", help="Generate manifest JSON and CSV.")
    parser.add_argument("--generate-split", action="store_true", help="Generate a deterministic candidate split CSV.")
    parser.add_argument("--generate-stats", action="store_true", help="Generate JSON and Markdown stats reports.")
    parser.add_argument(
        "--generate-sample-report",
        action="store_true",
        help="Generate a small sample report and suggested offline debug command.",
    )
    parser.add_argument("--all", action="store_true", help="Run download/extract/manifest/split/stats/sample-report.")
    parser.add_argument(
        "--source-url",
        action="append",
        default=[],
        help="Optional remote archive/file URL. Repeatable. Mainly used for manual_or_url datasets such as Le2i.",
    )
    parser.add_argument(
        "--raw-archive",
        action="append",
        default=[],
        help="Optional local archive/file path to register under raw/. Repeatable.",
    )
    parser.add_argument("--sample-limit", type=int, default=8, help="Maximum number of sample files in the sample report.")
    parser.add_argument("--dry-run", action="store_true", help="Print actions without downloading or extracting.")
    parser.add_argument("--max-files", type=int, default=None, help="Optional cap forwarded to FallVision Dataverse selection.")
    parser.add_argument(
        "--max-files-per-group",
        type=int,
        default=None,
        help="Optional per-(label,scene) cap forwarded to FallVision Dataverse selection.",
    )
    parser.add_argument(
        "--fallvision-asset-type",
        choices=("keypoints", "videos", "both"),
        default=None,
        help="Override FallVision asset family.",
    )
    parser.add_argument(
        "--fallvision-variant",
        choices=("mask", "raw", "both"),
        default=None,
        help="Override FallVision video variant.",
    )
    parser.add_argument(
        "--fallvision-scene",
        choices=("bed", "chair", "stand", "all"),
        default=None,
        help="Override FallVision scene subgroup.",
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


def ensure_dirs(paths: list[Path], dry_run: bool) -> None:
    for path in paths:
        if dry_run:
            print(f"[dry-run] mkdir -p {path}")
            continue
        path.mkdir(parents=True, exist_ok=True)


def dataset_layout(cfg: dict[str, Any]) -> dict[str, Path]:
    storage = cfg["storage"]
    root = resolve_repo_path(storage["root"])
    return {
        "root": root,
        "raw": root / storage.get("raw_dir", "raw"),
        "extracted": root / storage.get("extracted_dir", "extracted"),
        "manifests": root / storage.get("manifests_dir", "manifests"),
        "reports": root / storage.get("reports_dir", "reports"),
        "splits": root / storage.get("splits_dir", "splits"),
    }


def strip_archive_suffix(path: Path) -> str:
    name = path.name
    for suffix in (".tar.gz", ".tar.bz2", ".tar.xz", ".tgz", ".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz"):
        if name.lower().endswith(suffix):
            return name[: -len(suffix)]
    return path.stem


def find_extractor() -> list[str] | None:
    for candidate in (["7z", "x", "-y"], ["unrar", "x"], ["unar"]):
        if shutil.which(candidate[0]):
            return candidate
    return None


def extract_archive(archive_path: Path, out_dir: Path, extractor: list[str] | None) -> None:
    suffixes = "".join(archive_path.suffixes[-2:]).lower()
    if zipfile.is_zipfile(archive_path):
        with zipfile.ZipFile(archive_path) as blob:
            blob.extractall(out_dir)
        return
    if tarfile.is_tarfile(archive_path):
        with tarfile.open(archive_path) as blob:
            blob.extractall(out_dir)
        return
    if archive_path.suffix.lower() in {".rar", ".7z"} or suffixes in {".rar", ".7z"}:
        if extractor is None:
            raise SystemExit(
                f"No extractor found for {archive_path.name}. Install one of: 7z, unrar, unar."
            )
        cmd = list(extractor)
        if extractor[0] == "7z":
            cmd.extend([f"-o{out_dir}", str(archive_path)])
        elif extractor[0] == "unrar":
            cmd.extend([str(archive_path), str(out_dir)])
        else:
            cmd.extend(["-o", str(out_dir), str(archive_path)])
        subprocess.run(cmd, check=True)
        return
    raise SystemExit(f"Unsupported archive format: {archive_path}")


def download_generic_url(url: str, target_path: Path, dry_run: bool) -> None:
    if dry_run:
        print(f"[dry-run] download {url} -> {target_path}")
        return
    target_path.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "kaiti-yolopose-framework/0.1",
            "Accept": "*/*",
        },
    )
    with urllib.request.urlopen(request) as response, target_path.open("wb") as out_file:
        shutil.copyfileobj(response, out_file)


def register_local_artifacts(raw_paths: list[str], raw_dir: Path, dry_run: bool) -> list[Path]:
    registered: list[Path] = []
    for raw in raw_paths:
        src = resolve_repo_path(raw)
        if not src.exists():
            raise SystemExit(f"raw archive/file does not exist: {src}")
        dst = raw_dir / src.name
        registered.append(dst)
        if src.resolve() == dst.resolve():
            continue
        if dry_run:
            print(f"[dry-run] copy {src} -> {dst}")
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    return registered


def run_fallvision_download(cfg: dict[str, Any], args: argparse.Namespace, layout: dict[str, Path]) -> None:
    download_cfg = cfg.get("download", {})
    fv = download_cfg.get("fallvision", {})
    cmd = [
        sys.executable,
        str(PROJECT_ROOT / "scripts" / "download_fallvision_assets.py"),
        "--out-root",
        rel_to_project(layout["raw"]),
        "--manifest",
        rel_to_project(layout["manifests"] / "download_selection.json"),
        "--asset-type",
        args.fallvision_asset_type or fv.get("asset_type", "keypoints"),
        "--label",
        fv.get("label", "both"),
        "--scene",
        args.fallvision_scene or fv.get("scene", "all"),
        "--variant",
        args.fallvision_variant or fv.get("variant", "mask"),
    ]
    if args.max_files is not None:
        cmd.extend(["--max-files", str(args.max_files)])
    elif fv.get("max_files") is not None:
        cmd.extend(["--max-files", str(fv["max_files"])])
    if args.max_files_per_group is not None:
        cmd.extend(["--max-files-per-group", str(args.max_files_per_group)])
    elif fv.get("max_files_per_group") is not None:
        cmd.extend(["--max-files-per-group", str(fv["max_files_per_group"])])
    if download_cfg.get("match"):
        cmd.extend(["--match", str(download_cfg["match"])])
    if args.dry_run:
        cmd.append("--dry-run")
    print("[intake] running:", " ".join(cmd))
    subprocess.run(cmd, check=True, cwd=PROJECT_ROOT)


def run_manual_or_url_download(cfg: dict[str, Any], args: argparse.Namespace, layout: dict[str, Path]) -> None:
    download_cfg = cfg.get("download", {})
    urls = list(download_cfg.get("source_urls", [])) + list(args.source_url)
    ensure_dirs([layout["raw"]], dry_run=args.dry_run)
    for index, url in enumerate(urls, start=1):
        parsed = urllib.parse.urlparse(url)
        filename = Path(parsed.path).name or f"download_{index}"
        target_path = layout["raw"] / filename
        download_generic_url(url, target_path, dry_run=args.dry_run)
    register_local_artifacts(args.raw_archive, layout["raw"], dry_run=args.dry_run)
    if not urls and not args.raw_archive:
        print(
            "[intake] no direct URL or local archive provided. "
            "Place archives under raw/ or rerun with --source-url / --raw-archive."
        )


def collect_files(scan_root: Path) -> list[Path]:
    if not scan_root.exists():
        return []
    return sorted(path for path in scan_root.rglob("*") if path.is_file())


def infer_fallvision_label(relpath: str) -> str:
    lowered = relpath.lower()
    if "/no fall/" in lowered or lowered.startswith("no fall/"):
        return "no_fall"
    if "/fall/" in lowered or lowered.startswith("fall/"):
        return "fall"
    return "unknown"


def infer_fallvision_scene(relpath: str) -> str:
    lowered = relpath.lower()
    for scene in ("bed", "chair", "stand"):
        if f"/{scene}/" in lowered or lowered.startswith(f"{scene}/"):
            return scene
    return "unknown"


def infer_fallvision_variant(relpath: str) -> str:
    lowered = relpath.lower()
    if "mask video" in lowered:
        return "mask"
    if "raw video" in lowered:
        return "raw"
    return "unknown"


def manifest_entries(cfg: dict[str, Any], layout: dict[str, Path]) -> list[dict[str, Any]]:
    family = str(cfg["dataset"].get("family", "generic"))
    scan_root = layout["extracted"] if layout["extracted"].exists() and collect_files(layout["extracted"]) else layout["raw"]
    entries: list[dict[str, Any]] = []
    for file_path in collect_files(scan_root):
        relpath = str(file_path.relative_to(scan_root))
        ext = file_path.suffix.lower()
        entry = {
            "stage": "extracted" if scan_root == layout["extracted"] else "raw",
            "relpath": relpath,
            "abspath": str(file_path),
            "size_bytes": int(file_path.stat().st_size),
            "extension": ext,
            "is_media": ext in MEDIA_EXTENSIONS,
            "is_csv": ext == ".csv",
            "is_archive": ext in ARCHIVE_EXTENSIONS or "".join(file_path.suffixes[-2:]).lower() in {".tar.gz", ".tar.bz2", ".tar.xz"},
            "usage": cfg["dataset"].get("usage", "unknown"),
        }
        if family == "fallvision":
            entry["label"] = infer_fallvision_label(relpath)
            entry["scene"] = infer_fallvision_scene(relpath)
            entry["variant"] = infer_fallvision_variant(relpath)
        else:
            entry["label"] = cfg["dataset"].get("label", "unknown")
            entry["scene"] = "unknown"
            entry["variant"] = "unknown"
        entries.append(entry)
    return entries


def write_json(path: Path, payload: Any, dry_run: bool = False) -> None:
    if dry_run:
        print(f"[dry-run] write json {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_text(path: Path, text: str, dry_run: bool = False) -> None:
    if dry_run:
        print(f"[dry-run] write text {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_manifest_files(cfg: dict[str, Any], layout: dict[str, Path], entries: list[dict[str, Any]], dry_run: bool) -> None:
    manifest_json = layout["manifests"] / "manifest.json"
    manifest_csv = layout["manifests"] / "manifest.csv"
    payload = {
        "dataset": cfg["dataset"],
        "storage_root": rel_to_project(layout["root"]),
        "entry_count": len(entries),
        "entries": entries,
    }
    write_json(manifest_json, payload, dry_run=dry_run)
    if dry_run:
        print(f"[dry-run] write csv {manifest_csv}")
        return
    manifest_csv.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "stage",
        "relpath",
        "size_bytes",
        "extension",
        "is_media",
        "is_csv",
        "is_archive",
        "label",
        "scene",
        "variant",
        "usage",
    ]
    with manifest_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for entry in entries:
            writer.writerow({key: entry.get(key) for key in fieldnames})


def deterministic_subset(relpath: str, usage: str) -> str:
    if usage == "external_validation":
        return "external_eval"
    if usage == "supplement_train":
        bucket = int(hashlib.md5(relpath.encode("utf-8")).hexdigest()[:8], 16) % 100
        return "candidate_train" if bucket < 80 else "candidate_holdout"
    return "pending_review"


def write_split_file(cfg: dict[str, Any], layout: dict[str, Path], entries: list[dict[str, Any]], dry_run: bool) -> None:
    split_path = layout["splits"] / "default_split.csv"
    usage = str(cfg["dataset"].get("usage", "unknown"))
    candidates = [entry for entry in entries if not entry["is_archive"] and (entry["is_csv"] or entry["is_media"])]
    if dry_run:
        print(f"[dry-run] write csv {split_path}")
        return
    split_path.parent.mkdir(parents=True, exist_ok=True)
    with split_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["relpath", "subset", "usage", "label", "scene", "asset_hint"])
        for entry in candidates:
            asset_hint = "media" if entry["is_media"] else "csv" if entry["is_csv"] else entry["extension"]
            writer.writerow(
                [
                    entry["relpath"],
                    deterministic_subset(entry["relpath"], usage),
                    usage,
                    entry.get("label", "unknown"),
                    entry.get("scene", "unknown"),
                    asset_hint,
                ]
            )


def build_stats(cfg: dict[str, Any], layout: dict[str, Path], entries: list[dict[str, Any]]) -> dict[str, Any]:
    ext_counter = Counter(entry["extension"] or "<none>" for entry in entries)
    label_counter = Counter(entry.get("label", "unknown") for entry in entries)
    scene_counter = Counter(entry.get("scene", "unknown") for entry in entries if entry.get("scene"))
    media_count = sum(1 for entry in entries if entry["is_media"])
    csv_count = sum(1 for entry in entries if entry["is_csv"])
    archive_count = sum(1 for entry in entries if entry["is_archive"])
    total_size = sum(int(entry["size_bytes"]) for entry in entries)
    return {
        "dataset": cfg["dataset"],
        "storage_root": rel_to_project(layout["root"]),
        "entry_count": len(entries),
        "total_size_bytes": total_size,
        "media_count": media_count,
        "csv_count": csv_count,
        "archive_count": archive_count,
        "extensions": dict(ext_counter.most_common()),
        "labels": dict(label_counter.most_common()),
        "scenes": dict(scene_counter.most_common()),
    }


def write_stats_reports(stats: dict[str, Any], layout: dict[str, Path], dry_run: bool) -> None:
    write_json(layout["reports"] / "dataset_stats.json", stats, dry_run=dry_run)
    lines = [
        f"# Dataset Stats: {stats['dataset'].get('display_name', stats['dataset'].get('key'))}",
        "",
        f"- storage root: `{stats['storage_root']}`",
        f"- total files: `{stats['entry_count']}`",
        f"- total size bytes: `{stats['total_size_bytes']}`",
        f"- media files: `{stats['media_count']}`",
        f"- csv files: `{stats['csv_count']}`",
        f"- archive files: `{stats['archive_count']}`",
        "",
        "## Extensions",
        "",
    ]
    for ext, count in stats["extensions"].items():
        lines.append(f"- `{ext}`: `{count}`")
    if stats["labels"]:
        lines.extend(["", "## Labels", ""])
        for label, count in stats["labels"].items():
            lines.append(f"- `{label}`: `{count}`")
    if stats["scenes"]:
        lines.extend(["", "## Scenes", ""])
        for scene, count in stats["scenes"].items():
            lines.append(f"- `{scene}`: `{count}`")
    write_text(layout["reports"] / "dataset_stats.md", "\n".join(lines) + "\n", dry_run=dry_run)


def media_probe(path: Path) -> dict[str, Any]:
    ext = path.suffix.lower()
    if ext not in MEDIA_EXTENSIONS:
        return {}
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        return {"probe_state": "open_failed"}
    try:
        return {
            "probe_state": "ok",
            "fps": float(cap.get(cv2.CAP_PROP_FPS)),
            "frame_count": int(cap.get(cv2.CAP_PROP_FRAME_COUNT)),
            "width": int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
            "height": int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
        }
    finally:
        cap.release()


def sample_report(cfg: dict[str, Any], layout: dict[str, Path], entries: list[dict[str, Any]], limit: int) -> str:
    dataset_key = str(cfg["dataset"]["key"])
    display_name = str(cfg["dataset"].get("display_name", dataset_key))
    family = str(cfg["dataset"].get("family", "generic"))
    sample_entries = [entry for entry in entries if not entry["is_archive"]][:limit]
    lines = [
        f"# Sample Report: {display_name}",
        "",
        f"- dataset key: `{dataset_key}`",
        f"- storage root: `{rel_to_project(layout['root'])}`",
        f"- sample count shown: `{len(sample_entries)}`",
        "",
    ]
    first_media: str | None = None
    if sample_entries:
        lines.extend(["## Samples", ""])
    for entry in sample_entries:
        relpath = entry["relpath"]
        lines.append(f"- `{relpath}`")
        if entry["is_media"] and first_media is None:
            first_media = relpath
        if entry["is_media"]:
            probe = media_probe(Path(entry["abspath"]))
            if probe:
                lines.append(
                    "  media:"
                    f" state={probe.get('probe_state')} fps={probe.get('fps', 0):.2f}"
                    f" frames={probe.get('frame_count', 0)} size={probe.get('width', 0)}x{probe.get('height', 0)}"
                )
        elif entry["is_csv"]:
            with Path(entry["abspath"]).open("r", encoding="utf-8", errors="ignore") as handle:
                line_count = sum(1 for _ in handle)
            lines.append(f"  csv: lines={line_count}")

    lines.extend(["", "## Offline Debug", ""])
    if first_media is not None:
        media_path = layout["extracted"] / first_media if (layout["extracted"] / first_media).exists() else layout["raw"] / first_media
        lines.extend(
            [
                "可直接用当前默认主线做离线调试：",
                "",
                "```bash",
                "cd /home/yhc/kaiti_yolopose_framework",
                "source .venv/bin/activate",
                "python scripts/run_pose_infer.py \\",
                "  --config configs/infer_pose_stream.yaml \\",
                f"  --source \"{rel_to_project(media_path)}\" \\",
                "  --device 0 \\",
                "  --save-debug-video",
                "```",
            ]
        )
    else:
        lines.append("当前资源中没有视频文件，无法直接跑 `run_pose_infer.py`。")
        if family == "fallvision":
            lines.extend(
                [
                    "如需离线视频调试，请改用 `FallVision` 视频调试配置：",
                    "",
                    "```bash",
                    "python scripts/prepare_external_dataset.py \\",
                    "  --dataset-config configs/external_datasets/fallvision_fall_videos_debug.yaml \\",
                    "  --download --extract --generate-manifest --generate-stats --generate-sample-report",
                    "```",
                ]
            )
        else:
            lines.extend(
                [
                    "请先提供视频资源 URL，或把本地视频压缩包放入该数据集的 `raw/` 目录，再重新执行资源整理流程。",
                ]
            )
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    args = parse_args()
    if args.all:
        args.download = True
        args.extract = True
        args.generate_manifest = True
        args.generate_split = True
        args.generate_stats = True
        args.generate_sample_report = True

    cfg_path = resolve_repo_path(args.dataset_config)
    cfg = load_yaml(cfg_path)
    layout = dataset_layout(cfg)
    ensure_dirs(list(layout.values()), dry_run=args.dry_run)

    strategy = str(cfg.get("download", {}).get("strategy", "manual_or_url"))

    if args.download:
        if strategy == "fallvision_dataverse":
            run_fallvision_download(cfg, args, layout)
        elif strategy == "manual_or_url":
            run_manual_or_url_download(cfg, args, layout)
        else:
            raise SystemExit(f"Unsupported download strategy: {strategy}")

    if args.extract:
        extractor = find_extractor()
        for archive_path in collect_files(layout["raw"]):
            suffix_joined = "".join(archive_path.suffixes[-2:]).lower()
            is_archive = archive_path.suffix.lower() in ARCHIVE_EXTENSIONS or suffix_joined in {".tar.gz", ".tar.bz2", ".tar.xz"}
            if not is_archive:
                continue
            rel = archive_path.relative_to(layout["raw"])
            extract_dir = layout["extracted"] / rel.parent / strip_archive_suffix(archive_path)
            marker = extract_dir / ".extracted.ok"
            if marker.exists():
                print(f"[skip extract] {extract_dir}")
                continue
            if args.dry_run:
                print(f"[dry-run] extract {archive_path} -> {extract_dir}")
                continue
            extract_dir.mkdir(parents=True, exist_ok=True)
            extract_archive(archive_path, extract_dir, extractor)
            marker.write_text("ok\n", encoding="utf-8")

    entries = manifest_entries(cfg, layout)
    if args.generate_manifest:
        write_manifest_files(cfg, layout, entries, dry_run=args.dry_run)
    if args.generate_split:
        write_split_file(cfg, layout, entries, dry_run=args.dry_run)
    if args.generate_stats:
        stats = build_stats(cfg, layout, entries)
        write_stats_reports(stats, layout, dry_run=args.dry_run)
    if args.generate_sample_report:
        report = sample_report(cfg, layout, entries, limit=max(1, args.sample_limit))
        write_text(layout["reports"] / "sample_report.md", report, dry_run=args.dry_run)

    summary = {
        "dataset_key": cfg["dataset"]["key"],
        "storage_root": rel_to_project(layout["root"]),
        "raw_dir": rel_to_project(layout["raw"]),
        "extracted_dir": rel_to_project(layout["extracted"]),
        "manifests_dir": rel_to_project(layout["manifests"]),
        "reports_dir": rel_to_project(layout["reports"]),
        "splits_dir": rel_to_project(layout["splits"]),
        "entry_count": len(entries),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
