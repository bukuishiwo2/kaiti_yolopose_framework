#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from yolopose.core.config import abs_path, load_yaml
from yolopose.pipeline.runner import PoseRunner


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run YOLO pose inference on image/video/stream.")
    parser.add_argument("--config", default="configs/infer_pose_stream.yaml", help="Path to infer config YAML.")
    parser.add_argument("--source", default=None, help="Override source from config.")
    parser.add_argument("--mode", choices=["predict", "track"], default=None, help="predict or track")
    parser.add_argument("--model", default=None, help="Override model weights path.")
    parser.add_argument("--device", default=None, help="Override device, e.g. cpu, 0, cuda:0")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    cfg_path = (PROJECT_ROOT / args.config).resolve() if not Path(args.config).is_absolute() else Path(args.config)
    cfg = load_yaml(cfg_path)

    if args.source is not None:
        if args.source.isdigit():
            cfg["source"] = int(args.source)
        else:
            cfg["source"] = args.source
    if args.mode is not None:
        cfg["mode"] = args.mode
    if args.model is not None:
        cfg["model"] = args.model
    if args.device is not None:
        cfg["device"] = args.device

    # Normalize local relative paths to absolute paths under project.
    cfg["source"] = abs_path(PROJECT_ROOT, cfg.get("source"))
    cfg["model"] = abs_path(PROJECT_ROOT, cfg.get("model"))

    # Friendlier error for missing local camera device.
    source = cfg.get("source")
    if isinstance(source, int):
        dev = Path(f"/dev/video{source}")
        if not dev.exists():
            raise SystemExit(
                f"Camera source {source} requested, but {dev} does not exist.\n"
                "Use --source <video_path> or plug in camera and check /dev/video*."
            )

    runner = PoseRunner(cfg=cfg, project_root=PROJECT_ROOT)
    runner.run()


if __name__ == "__main__":
    main()
