from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator

import torch
from ultralytics import YOLO

from yolopose.pipeline.fall_detector import FallDetector, FallDetectorConfig
from yolopose.pipeline.stabilizer import BooleanStabilizer, StabilizerConfig
from yolopose.temporal.sequence_fall_detector import SequenceFallDetector, SequenceFallDetectorConfig


class PoseRunner:
    def __init__(
        self,
        cfg: dict[str, Any],
        project_root: Path,
        event_callback: Callable[[dict[str, Any]], None] | None = None,
    ):
        self.cfg = cfg
        self.project_root = project_root
        self.event_callback = event_callback
        self.model = YOLO(cfg["model"])
        self._print_runtime_info()
        stab_cfg = cfg.get("stabilizer", {})
        self.min_persons = int(stab_cfg.get("min_persons", 1))
        self.stabilizer = BooleanStabilizer(
            StabilizerConfig(
                min_true_frames=int(stab_cfg.get("min_true_frames", 3)),
                min_false_frames=int(stab_cfg.get("min_false_frames", 5)),
            )
        )
        fall_cfg_dict = cfg.get("fall_detector", {})
        self.fall_detector = FallDetector(
            FallDetectorConfig(
                enabled=bool(fall_cfg_dict.get("enabled", False)),
                keypoint_conf_threshold=float(fall_cfg_dict.get("keypoint_conf_threshold", 0.3)),
                bbox_aspect_ratio_threshold=float(fall_cfg_dict.get("bbox_aspect_ratio_threshold", 1.2)),
                torso_vertical_ratio_threshold=float(fall_cfg_dict.get("torso_vertical_ratio_threshold", 0.22)),
                hip_to_ankle_vertical_ratio_threshold=float(
                    fall_cfg_dict.get("hip_to_ankle_vertical_ratio_threshold", 0.38)
                ),
                min_signals_to_fall=int(fall_cfg_dict.get("min_signals_to_fall", 2)),
                min_true_frames=int(fall_cfg_dict.get("min_true_frames", 5)),
                min_false_frames=int(fall_cfg_dict.get("min_false_frames", 8)),
                use_track_stabilization=bool(fall_cfg_dict.get("use_track_stabilization", True)),
                track_ttl_frames=int(fall_cfg_dict.get("track_ttl_frames", 45)),
            )
        )
        seq_cfg_dict = cfg.get("sequence_fall_detector", {})
        self.sequence_fall_detector = SequenceFallDetector(
            SequenceFallDetectorConfig(
                enabled=bool(seq_cfg_dict.get("enabled", False)),
                model_path=seq_cfg_dict.get("model_path"),
                device=str(seq_cfg_dict.get("device")) if seq_cfg_dict.get("device") is not None else cfg.get("device"),
                seq_len=int(seq_cfg_dict.get("seq_len", 32)),
                score_threshold=float(seq_cfg_dict.get("score_threshold", 0.5)),
                keypoint_conf_threshold=float(seq_cfg_dict.get("keypoint_conf_threshold", 0.3)),
                min_true_frames=int(seq_cfg_dict.get("min_true_frames", 3)),
                min_false_frames=int(seq_cfg_dict.get("min_false_frames", 5)),
                use_track_sequences=bool(seq_cfg_dict.get("use_track_sequences", True)),
                track_ttl_frames=int(seq_cfg_dict.get("track_ttl_frames", 45)),
            ),
            project_root=project_root,
        )

    def _print_runtime_info(self) -> None:
        req_device = self.cfg.get("device")
        print(
            "[runtime] "
            f"requested_device={req_device} "
            f"torch_cuda_build={torch.version.cuda} "
            f"cuda_available={torch.cuda.is_available()} "
            f"cuda_device_count={torch.cuda.device_count() if torch.cuda.is_available() else 0}"
        )

    def _predict_iter(self) -> Iterator[Any]:
        common_args = dict(
            source=self.cfg["source"],
            stream=True,
            conf=float(self.cfg.get("conf", 0.25)),
            iou=float(self.cfg.get("iou", 0.7)),
            imgsz=int(self.cfg.get("imgsz", 640)),
            device=self.cfg.get("device"),
            half=bool(self.cfg.get("half", False)),
            classes=self.cfg.get("classes"),
            vid_stride=int(self.cfg.get("vid_stride", 1)),
            stream_buffer=bool(self.cfg.get("stream_buffer", False)),
            show=bool(self.cfg.get("show", False)),
            save=bool(self.cfg.get("save_visualization", False)),
            project=str((self.project_root / self.cfg.get("output_dir", "outputs/vis")).resolve()),
            verbose=bool(self.cfg.get("verbose", True)),
        )

        mode = self.cfg.get("mode", "predict")
        if mode == "track":
            common_args["tracker"] = self.cfg.get("tracker", "bytetrack.yaml")
            return self.model.track(**common_args)
        return self.model.predict(**common_args)

    def run(self) -> None:
        output_jsonl = self.cfg.get("save_jsonl")
        output_fp = None
        if output_jsonl:
            output_path = (self.project_root / output_jsonl).resolve()
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_fp = output_path.open("w", encoding="utf-8")

        try:
            for frame_id, result in enumerate(self._predict_iter(), start=1):
                person_count = int(len(result.boxes)) if result.boxes is not None else 0
                raw_present = person_count >= self.min_persons
                stable_present, changed = self.stabilizer.update(raw_present)
                fall_info = self.fall_detector.infer(result)
                seq_fall_info = self.sequence_fall_detector.infer(result)

                record = {
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "frame_id": frame_id,
                    "source": str(getattr(result, "path", self.cfg["source"])),
                    "person_count": person_count,
                    "raw_person_present": raw_present,
                    "stable_person_present": stable_present,
                    "state_changed": changed,
                }
                record.update(fall_info)
                record.update(seq_fall_info)

                if output_fp:
                    output_fp.write(json.dumps(record, ensure_ascii=True) + "\n")
                if self.event_callback is not None:
                    self.event_callback(record)

                if changed:
                    print(
                        f"[event] frame={frame_id} stable_person_present={stable_present} "
                        f"person_count={person_count}"
                    )
                if fall_info["fall_state_changed"]:
                    print(
                        f"[fall] frame={frame_id} stable_fall_detected={fall_info['stable_fall_detected']} "
                        f"raw_fall_detected={fall_info['raw_fall_detected']} "
                        f"fall_person_candidates={fall_info['fall_person_candidates']} "
                        f"fall_max_score={fall_info['fall_max_score']:.2f}"
                    )
                if seq_fall_info["seq_fall_state_changed"]:
                    print(
                        f"[seq-fall] frame={frame_id} "
                        f"seq_stable_fall_detected={seq_fall_info['seq_stable_fall_detected']} "
                        f"seq_raw_fall_detected={seq_fall_info['seq_raw_fall_detected']} "
                        f"seq_fall_score={seq_fall_info['seq_fall_score']:.2f}"
                    )
        finally:
            if output_fp:
                output_fp.close()
