#!/usr/bin/env python3
from __future__ import annotations

import argparse
import contextlib
from pathlib import Path
import sys
from typing import Any

import cv2

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from yolopose.core.config import abs_path, load_yaml
from yolopose.pipeline.runner import PoseRunner


class DebugVideoWriter:
    """Standalone OSD writer for offline video inference."""

    def __init__(self, project_root: Path, source: str | int, output_path: str | None = None):
        self.project_root = project_root
        self.source = source
        self.output_path = self._resolve_output_path(output_path)
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self._writer: cv2.VideoWriter | None = None
        self._fps = self._resolve_fps()

    def _resolve_output_path(self, output_path: str | None) -> Path:
        if output_path:
            path = Path(output_path)
            if not path.is_absolute():
                path = (self.project_root / path).resolve()
            return path
        if isinstance(self.source, str):
            source_path = Path(self.source)
            stem = source_path.stem if source_path.suffix else source_path.name.replace("/", "_")
        else:
            stem = f"camera_{self.source}"
        return (self.project_root / "outputs" / "vis_debug" / f"{stem}_debug.mp4").resolve()

    def _resolve_fps(self) -> float:
        if isinstance(self.source, str):
            source_path = Path(self.source)
            if source_path.exists():
                cap = cv2.VideoCapture(str(source_path))
                try:
                    fps = float(cap.get(cv2.CAP_PROP_FPS))
                    if fps > 1e-3:
                        return fps
                finally:
                    cap.release()
        return 10.0

    def _ensure_writer(self, frame: Any) -> None:
        if self._writer is not None:
            return
        height, width = int(frame.shape[0]), int(frame.shape[1])
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        self._writer = cv2.VideoWriter(str(self.output_path), fourcc, self._fps, (width, height))
        if not self._writer.isOpened():
            raise RuntimeError(f"failed_to_open_debug_video_writer:{self.output_path}")

    @staticmethod
    def _draw_track_labels(frame: Any, result: Any) -> None:
        boxes = getattr(result, "boxes", None)
        track_ids = getattr(boxes, "id", None) if boxes is not None else None
        xyxy = getattr(boxes, "xyxy", None) if boxes is not None else None
        if track_ids is None or xyxy is None:
            return
        for idx in range(min(len(track_ids), len(xyxy))):
            track_value = track_ids[idx]
            if track_value is None:
                continue
            try:
                track_id = int(track_value.item())
            except Exception:  # pylint: disable=broad-except
                continue
            box = xyxy[idx]
            x1 = int(float(box[0]))
            y1 = int(float(box[1]))
            cv2.putText(
                frame,
                f"id:{track_id}",
                (x1, max(18, y1 - 8)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                (255, 255, 0),
                2,
                cv2.LINE_AA,
            )

    def __call__(self, result: Any, record: dict[str, Any]) -> None:
        frame = result.plot(boxes=True, labels=False, probs=False, kpt_line=True)
        self._draw_track_labels(frame, result)
        self._ensure_writer(frame)

        seq_track_id = record.get("seq_track_id")
        seq_track_label = "-" if seq_track_id in (None, "") else str(seq_track_id)
        seq_skip_reason = str(record.get("seq_skip_reason", "")).strip() or "-"
        seq_invalid_reason = str(record.get("seq_invalid_reason", "")).strip() or "-"
        lines = [
            f"frame={record.get('frame_id')} persons={record.get('person_count')}",
            (
                "rule "
                f"score={float(record.get('fall_max_score', 0.0)):.2f} "
                f"raw={int(bool(record.get('raw_fall_detected')))} "
                f"stable={int(bool(record.get('stable_fall_detected')))}"
            ),
            (
                "seq "
                f"score={float(record.get('seq_fall_score', 0.0)):.2f} "
                f"raw={int(bool(record.get('seq_raw_fall_detected')))} "
                f"stable={int(bool(record.get('seq_stable_fall_detected')))}"
            ),
            (
                "seq dbg "
                f"loaded={int(bool(record.get('seq_model_loaded', record.get('seq_fall_model_loaded', False))))} "
                f"ready={int(bool(record.get('seq_window_ready')))} "
                f"win={int(record.get('seq_window_size', 0))}/{int(record.get('seq_sequence_len', 0))} "
                f"mode={record.get('seq_debug_mode', '-')}"
            ),
            (
                "seq dbg "
                f"track={seq_track_label} "
                f"valid={int(bool(record.get('seq_feature_valid')))} "
                f"kpts={int(record.get('seq_visible_keypoint_count', 0))} "
                f"skip={seq_skip_reason} "
                f"invalid={seq_invalid_reason}"
            ),
            "supervisor action=offline reason=standalone_infer",
        ]
        for idx, line in enumerate(lines):
            y = 28 + idx * 24
            cv2.putText(
                frame,
                line,
                (12, y),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.56,
                (0, 0, 0),
                4,
                cv2.LINE_AA,
            )
            cv2.putText(
                frame,
                line,
                (12, y),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.56,
                (0, 255, 0) if idx < 4 else (0, 200, 255),
                2,
                cv2.LINE_AA,
            )
        self._writer.write(frame)

    def close(self) -> None:
        if self._writer is not None:
            self._writer.release()
            self._writer = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run YOLO pose inference on image/video/stream.")
    parser.add_argument("--config", default="configs/infer_pose_stream.yaml", help="Path to infer config YAML.")
    parser.add_argument("--source", default=None, help="Override source from config.")
    parser.add_argument("--mode", choices=["predict", "track"], default=None, help="predict or track")
    parser.add_argument("--model", default=None, help="Override model weights path.")
    parser.add_argument("--device", default=None, help="Override device, e.g. cpu, 0, cuda:0")
    parser.add_argument(
        "--save-debug-video",
        action="store_true",
        help="Save offline debug video with OSD similar to ROS2 /perception/debug_image.",
    )
    parser.add_argument(
        "--debug-output",
        default=None,
        help="Optional output path for the offline debug video.",
    )
    parser.add_argument(
        "--keep-default-visualization",
        action="store_true",
        help="Keep Ultralytics default outputs/vis/* alongside the debug video.",
    )
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

    if args.save_debug_video and not args.keep_default_visualization:
        cfg["save_visualization"] = False

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

    debug_writer = None
    if args.save_debug_video:
        debug_writer = DebugVideoWriter(
            project_root=PROJECT_ROOT,
            source=cfg["source"],
            output_path=args.debug_output,
        )
        print(f"[debug-video] output={debug_writer.output_path}")

    runner = PoseRunner(
        cfg=cfg,
        project_root=PROJECT_ROOT,
        visualization_callback=debug_writer,
    )
    try:
        runner.run()
    finally:
        if debug_writer is not None:
            with contextlib.suppress(Exception):
                debug_writer.close()


if __name__ == "__main__":
    main()
