from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import torch

from yolopose.core.config import normalize_torch_device
from yolopose.pipeline.stabilizer import BooleanStabilizer, StabilizerConfig
from yolopose.temporal.features import POSE_FEATURE_DIM, empty_person_feature, extract_person_candidates, extract_primary_person_feature
from yolopose.temporal.model import PoseFallLSTM


@dataclass
class SequenceFallDetectorConfig:
    enabled: bool = False
    model_path: str | None = None
    device: str | None = None
    seq_len: int = 32
    score_threshold: float = 0.5
    keypoint_conf_threshold: float = 0.3
    min_true_frames: int = 3
    min_false_frames: int = 5
    use_track_sequences: bool = True
    track_ttl_frames: int = 45


@dataclass
class _TrackBufferState:
    features: deque
    stabilizer: BooleanStabilizer
    last_seen_frame: int
    latest_score: float = 0.0


class SequenceFallDetector:
    def __init__(self, cfg: SequenceFallDetectorConfig, project_root: Path):
        self.cfg = cfg
        self.project_root = project_root
        self._frame_idx = 0
        self._global_changed = False
        self._global_state = False
        self._global_score = 0.0
        self._global_buffer: deque = deque(maxlen=int(cfg.seq_len))
        self._global_stabilizer = BooleanStabilizer(
            StabilizerConfig(min_true_frames=int(cfg.min_true_frames), min_false_frames=int(cfg.min_false_frames))
        )
        self._track_states: dict[int, _TrackBufferState] = {}
        self.model: PoseFallLSTM | None = None
        self.model_loaded = False
        self.model_device = 'cpu'
        self.feature_dim = POSE_FEATURE_DIM
        self._load_model()

    def _load_model(self) -> None:
        if not self.cfg.enabled or not self.cfg.model_path:
            return
        model_path = Path(self.cfg.model_path)
        if not model_path.is_absolute():
            model_path = (self.project_root / model_path).resolve()
        if not model_path.exists():
            return

        checkpoint = torch.load(str(model_path), map_location='cpu', weights_only=False)
        self.model = PoseFallLSTM.from_checkpoint(checkpoint)
        self.feature_dim = int(checkpoint.get('feature_dim', POSE_FEATURE_DIM))
        self.cfg.seq_len = int(checkpoint.get('seq_len', self.cfg.seq_len))
        if 'threshold' in checkpoint and float(self.cfg.score_threshold) == 0.5:
            self.cfg.score_threshold = float(checkpoint.get('threshold', self.cfg.score_threshold))

        self.model_device = normalize_torch_device(self.cfg.device, cuda_available=torch.cuda.is_available())

        self.model.to(self.model_device)
        self.model.eval()
        self.model_loaded = True

    def _new_track_state(self) -> _TrackBufferState:
        return _TrackBufferState(
            features=deque(maxlen=int(self.cfg.seq_len)),
            stabilizer=BooleanStabilizer(
                StabilizerConfig(min_true_frames=int(self.cfg.min_true_frames), min_false_frames=int(self.cfg.min_false_frames))
            ),
            last_seen_frame=self._frame_idx,
        )

    def _score_sequence(self, features: list[Any]) -> float:
        if not self.model_loaded or self.model is None or len(features) < int(self.cfg.seq_len):
            return 0.0
        seq_array = np.stack(features, axis=0).astype(np.float32)
        x = torch.from_numpy(seq_array).to(self.model_device).unsqueeze(0)
        with torch.inference_mode():
            logits = self.model(x)
            score = torch.sigmoid(logits).item()
        return float(score)

    def _base_output(self) -> dict[str, Any]:
        return {
            'seq_fall_detector_enabled': bool(self.cfg.enabled),
            'seq_fall_model_loaded': bool(self.model_loaded),
            'seq_fall_track_mode_used': False,
            'seq_raw_fall_detected': False,
            'seq_stable_fall_detected': False,
            'seq_fall_state_changed': False,
            'seq_fall_score': 0.0,
            'seq_fall_threshold': float(self.cfg.score_threshold),
            'seq_fall_person_candidates': 0,
            'seq_fall_top_candidate': None,
            'seq_active_track_ids': [],
            'seq_active_track_count': 0,
        }

    def _infer_global(self, result: Any) -> dict[str, Any]:
        feature, meta = extract_primary_person_feature(
            result,
            keypoint_conf_threshold=float(self.cfg.keypoint_conf_threshold),
        )
        self._global_buffer.append(feature)
        score = self._score_sequence(list(self._global_buffer))
        raw = score >= float(self.cfg.score_threshold)
        stable, changed = self._global_stabilizer.update(raw)
        self._global_state = bool(stable)
        self._global_score = float(score)

        out = self._base_output()
        out.update(
            {
                'seq_fall_detector_enabled': True,
                'seq_fall_model_loaded': bool(self.model_loaded),
                'seq_raw_fall_detected': bool(raw),
                'seq_stable_fall_detected': bool(stable),
                'seq_fall_state_changed': bool(changed),
                'seq_fall_score': float(score),
                'seq_fall_person_candidates': int(1 if meta is not None else 0),
                'seq_fall_top_candidate': None if meta is None else {'track_id': meta.get('track_id'), 'score': float(score), 'area': float(meta.get('area', 0.0))},
            }
        )
        return out

    def _infer_tracks(self, result: Any) -> dict[str, Any]:
        candidates = extract_person_candidates(result, keypoint_conf_threshold=float(self.cfg.keypoint_conf_threshold))
        seen_track_ids: set[int] = set()
        top_candidate: dict[str, Any] | None = None
        top_score = 0.0
        any_changed = False

        for person in candidates:
            track_id = person.get('track_id')
            if track_id is None:
                continue
            seen_track_ids.add(track_id)
            state = self._track_states.get(track_id)
            if state is None:
                state = self._new_track_state()
                self._track_states[track_id] = state
            state.features.append(person['feature'])
            state.last_seen_frame = self._frame_idx
            score = self._score_sequence(list(state.features))
            state.latest_score = float(score)
            raw = score >= float(self.cfg.score_threshold)
            stable, changed = state.stabilizer.update(raw)
            any_changed = any_changed or bool(changed)
            if score >= top_score:
                top_score = float(score)
                top_candidate = {'track_id': track_id, 'score': float(score), 'area': float(person.get('area', 0.0))}

        for track_id in list(self._track_states.keys()):
            if track_id in seen_track_ids:
                continue
            state = self._track_states[track_id]
            state.features.append(empty_person_feature())
            raw = False
            stable, changed = state.stabilizer.update(raw)
            any_changed = any_changed or bool(changed)
            if (self._frame_idx - state.last_seen_frame) > int(self.cfg.track_ttl_frames):
                self._track_states.pop(track_id, None)

        active_track_ids = sorted([tid for tid, state in self._track_states.items() if state.stabilizer.state])
        stable_state = len(active_track_ids) > 0
        changed_global = stable_state != self._global_state
        self._global_state = stable_state

        out = self._base_output()
        out.update(
            {
                'seq_fall_detector_enabled': True,
                'seq_fall_model_loaded': bool(self.model_loaded),
                'seq_fall_track_mode_used': True,
                'seq_raw_fall_detected': bool(top_score >= float(self.cfg.score_threshold)),
                'seq_stable_fall_detected': bool(stable_state),
                'seq_fall_state_changed': bool(any_changed or changed_global),
                'seq_fall_score': float(top_score),
                'seq_fall_person_candidates': int(len([p for p in candidates if p.get('track_id') is not None])),
                'seq_fall_top_candidate': top_candidate,
                'seq_active_track_ids': active_track_ids,
                'seq_active_track_count': int(len(active_track_ids)),
            }
        )
        return out

    def infer(self, result: Any) -> dict[str, Any]:
        self._frame_idx += 1

        if not self.cfg.enabled:
            return self._base_output()

        if not self.model_loaded:
            out = self._base_output()
            out.update({'seq_fall_detector_enabled': True, 'seq_fall_model_loaded': False})
            return out

        boxes = getattr(result, 'boxes', None)
        if boxes is None or len(boxes) == 0:
            if self.cfg.use_track_sequences and self._track_states:
                return self._infer_tracks(result)
            return self._infer_global(result)

        track_ids = getattr(boxes, 'id', None)
        if self.cfg.use_track_sequences and track_ids is not None:
            return self._infer_tracks(result)
        return self._infer_global(result)
