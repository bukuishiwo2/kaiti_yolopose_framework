from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def load_yaml(path: str | Path) -> dict[str, Any]:
    cfg_path = Path(path).expanduser().resolve()
    with cfg_path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def abs_path(base_dir: Path, value: str | int | None) -> str | int | None:
    if isinstance(value, int) or value is None:
        return value
    if "://" in value:
        return value
    if "*" in value:
        return value
    candidate = Path(value)
    if candidate.exists() or candidate.is_absolute():
        return str(candidate)
    # Keep plain model aliases (e.g. yolo11n-pose.pt) untouched for Ultralytics auto-download.
    if candidate.parent == Path("."):
        return value
    return str((base_dir / candidate).resolve())


def normalize_torch_device(value: str | int | None, cuda_available: bool) -> str:
    if value is None:
        return "cuda:0" if cuda_available else "cpu"
    if isinstance(value, int):
        return f"cuda:{value}" if cuda_available else "cpu"

    raw = str(value).strip()
    if raw == "":
        return "cuda:0" if cuda_available else "cpu"
    if raw.lower() == "cpu":
        return "cpu"
    if raw.lower().startswith("cuda"):
        return raw if cuda_available else "cpu"
    if raw.isdigit():
        return f"cuda:{raw}" if cuda_available else "cpu"
    return raw
