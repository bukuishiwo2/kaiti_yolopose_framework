#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from ultralytics import YOLO
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export trained pose model.")
    parser.add_argument("--config", default="configs/export_onnx.yaml", help="Export config YAML path.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    cfg_path = PROJECT_ROOT / args.config if not Path(args.config).is_absolute() else Path(args.config)
    with cfg_path.resolve().open("r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    model = YOLO(str((PROJECT_ROOT / cfg["weights"]).resolve()))
    model.export(
        format=cfg.get("format", "onnx"),
        imgsz=int(cfg.get("imgsz", 640)),
        half=bool(cfg.get("half", False)),
        dynamic=bool(cfg.get("dynamic", True)),
        simplify=bool(cfg.get("simplify", True)),
    )


if __name__ == "__main__":
    main()
