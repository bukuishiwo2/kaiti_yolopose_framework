#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import zipfile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
GENERATOR_VERSION = "2.0.0"
DEFAULT_MANIFEST = PROJECT_ROOT / "docs/generated/graduation_research_plan_v2.manifest.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check graduation research plan Markdown/DOCX synchronization.")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--require-clean-git", action="store_true")
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resolve_manifest_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else PROJECT_ROOT / path


def main() -> None:
    args = parse_args()
    manifest_path = args.manifest.resolve()
    if not manifest_path.exists():
        raise SystemExit(f"SYNC_ERROR manifest_missing:{manifest_path}")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    errors: list[str] = []
    if manifest.get("generator_version") != GENERATOR_VERSION:
        errors.append(
            f"generator_version:{manifest.get('generator_version')}!={GENERATOR_VERSION}"
        )

    source = resolve_manifest_path(str(manifest.get("source_path", ""))).resolve()
    output = resolve_manifest_path(str(manifest.get("output_path", ""))).resolve()
    if not source.exists():
        errors.append(f"source_missing:{source}")
    elif sha256(source) != manifest.get("source_sha256"):
        errors.append("source_sha256_mismatch")

    if not output.exists():
        errors.append(f"output_missing:{output}")
    elif sha256(output) != manifest.get("output_sha256"):
        errors.append("output_sha256_mismatch")
    else:
        try:
            with zipfile.ZipFile(output) as archive:
                document_xml = archive.read("word/document.xml").decode("utf-8")
            title = str(manifest.get("title", ""))
            title_tokens = [token for token in ("动态家居环境", "多机器人", "局部修复") if token in title]
            for token in title_tokens:
                if token not in document_xml:
                    errors.append(f"docx_title_token_missing:{token}")
        except (OSError, KeyError, zipfile.BadZipFile) as exc:
            errors.append(f"invalid_docx:{exc}")

    if args.require_clean_git:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=PROJECT_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        if result.stdout.strip():
            errors.append("git_worktree_dirty")

    if errors:
        print(json.dumps({"in_sync": False, "errors": errors}, ensure_ascii=False, indent=2))
        raise SystemExit(1)

    print(
        json.dumps(
            {
                "in_sync": True,
                "research_plan_version": manifest.get("research_plan_version"),
                "source_path": manifest.get("source_path"),
                "source_sha256": manifest.get("source_sha256"),
                "output_path": manifest.get("output_path"),
                "output_sha256": manifest.get("output_sha256"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
