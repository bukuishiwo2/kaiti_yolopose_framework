#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import sys

from ultralytics import YOLO

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def load_yaml(path: Path) -> dict:
    import yaml

    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train YOLO pose model.")
    parser.add_argument("--config", default="configs/train_pose.yaml", help="Train config YAML path.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    cfg_path = PROJECT_ROOT / args.config if not Path(args.config).is_absolute() else Path(args.config)
    cfg = load_yaml(cfg_path.resolve())

    model = YOLO(cfg["model"])
    model.train(
        data=str((PROJECT_ROOT / cfg["data"]).resolve()),
        epochs=int(cfg.get("epochs", 100)),
        imgsz=int(cfg.get("imgsz", 640)),
        batch=int(cfg.get("batch", 16)),
        device=cfg.get("device", 0),
        workers=int(cfg.get("workers", 8)),
        project=str((PROJECT_ROOT / cfg.get("project", "outputs/train")).resolve()),
        name=cfg.get("name", "yolopose_baseline"),
    )


if __name__ == "__main__":
    main()
