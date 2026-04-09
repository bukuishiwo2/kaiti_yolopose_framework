from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any

from yolopose.pipeline.stabilizer import BooleanStabilizer, StabilizerConfig


@dataclass
class FallDetectorConfig:
    enabled: bool = False
    keypoint_conf_threshold: float = 0.3
    bbox_aspect_ratio_threshold: float = 1.2
    torso_vertical_ratio_threshold: float = 0.22
    hip_to_ankle_vertical_ratio_threshold: float = 0.38
    min_signals_to_fall: int = 2
    min_true_frames: int = 5
    min_false_frames: int = 8
    use_track_stabilization: bool = True
    track_ttl_frames: int = 45


@dataclass
class _TrackState:
    stabilizer: BooleanStabilizer
    last_seen_frame: int


class FallDetector:
    """Heuristic fall detector based on person box shape and pose keypoint geometry."""

    def __init__(self, cfg: FallDetectorConfig):
        self.cfg = cfg
        self.stabilizer = BooleanStabilizer(
            StabilizerConfig(
                min_true_frames=int(cfg.min_true_frames),
                min_false_frames=int(cfg.min_false_frames),
            )
        )
        self._frame_idx = 0
        self._track_states: dict[int, _TrackState] = {}
        self._global_track_state = False

    @staticmethod
    def _midpoint(a: tuple[float, float], b: tuple[float, float]) -> tuple[float, float]:
        return (0.5 * (a[0] + b[0]), 0.5 * (a[1] + b[1]))

    def _kpt_visible(self, conf_row: Any, idx: int) -> bool:
        return float(conf_row[idx]) >= self.cfg.keypoint_conf_threshold

    @staticmethod
    def _to_track_id(x: Any) -> int | None:
        try:
            val = float(x)
        except (TypeError, ValueError):
            return None
        if math.isnan(val):
            return None
        return int(val)

    def _new_track_stabilizer(self) -> BooleanStabilizer:
        return BooleanStabilizer(
            StabilizerConfig(
                min_true_frames=int(self.cfg.min_true_frames),
                min_false_frames=int(self.cfg.min_false_frames),
            )
        )

    def _infer_global(self, result: Any, candidates: list[dict[str, Any]], max_score: float) -> dict[str, Any]:
        raw_fall = len(candidates) > 0
        stable_state, changed = self.stabilizer.update(raw_fall)
        top = max(candidates, key=lambda x: x["score"]) if candidates else None
        return {
            "fall_detector_enabled": True,
            "fall_track_mode_used": False,
            "raw_fall_detected": bool(raw_fall),
            "stable_fall_detected": bool(stable_state),
            "fall_state_changed": bool(changed),
            "fall_person_candidates": int(len(candidates)),
            "fall_max_score": float(max_score),
            "fall_top_candidate": top,
            "fall_active_track_ids": [],
            "fall_active_track_count": 0,
        }

    def _infer_per_track(
        self,
        candidates: list[dict[str, Any]],
        all_people: list[dict[str, Any]],
    ) -> dict[str, Any]:
        seen_track_ids: set[int] = set()
        per_track_changed = False

        for person in all_people:
            track_id = person.get("track_id")
            if track_id is None:
                continue

            seen_track_ids.add(track_id)
            state = self._track_states.get(track_id)
            if state is None:
                state = _TrackState(stabilizer=self._new_track_stabilizer(), last_seen_frame=self._frame_idx)
                self._track_states[track_id] = state

            stable, changed = state.stabilizer.update(bool(person["fall_candidate"]))
            state.last_seen_frame = self._frame_idx
            person["track_stable_fall"] = bool(stable)
            person["track_state_changed"] = bool(changed)
            per_track_changed = per_track_changed or bool(changed)

        for tid in list(self._track_states.keys()):
            if tid in seen_track_ids:
                continue
            state = self._track_states[tid]
            stable, changed = state.stabilizer.update(False)
            per_track_changed = per_track_changed or bool(changed)
            if (self._frame_idx - state.last_seen_frame) > int(self.cfg.track_ttl_frames):
                self._track_states.pop(tid, None)

        active_track_ids = sorted([tid for tid, s in self._track_states.items() if s.stabilizer.state])
        stable_state = len(active_track_ids) > 0
        changed_global = stable_state != self._global_track_state
        self._global_track_state = stable_state

        top = max(candidates, key=lambda x: x["score"]) if candidates else None
        max_score = max((float(x["score"]) for x in all_people), default=0.0)

        return {
            "fall_detector_enabled": True,
            "fall_track_mode_used": True,
            "raw_fall_detected": bool(len(candidates) > 0),
            "stable_fall_detected": bool(stable_state),
            "fall_state_changed": bool(changed_global or per_track_changed),
            "fall_person_candidates": int(len(candidates)),
            "fall_max_score": float(max_score),
            "fall_top_candidate": top,
            "fall_active_track_ids": active_track_ids,
            "fall_active_track_count": int(len(active_track_ids)),
        }

    def _analyze_person(self, box_xyxy: Any, kpt_xy: Any, kpt_conf: Any) -> dict[str, Any]:
        x1, y1, x2, y2 = [float(v) for v in box_xyxy]
        w = max(1e-6, x2 - x1)
        h = max(1e-6, y2 - y1)

        aspect_ratio = w / h
        wide_box = aspect_ratio >= self.cfg.bbox_aspect_ratio_threshold

        # COCO indices: shoulders(5,6), hips(11,12), ankles(15,16)
        required = [5, 6, 11, 12, 15, 16]
        if not all(self._kpt_visible(kpt_conf, idx) for idx in required):
            return {
                "fall_candidate": bool(wide_box),
                "score": float(1.0 if wide_box else 0.0),
                "signals_true": int(1 if wide_box else 0),
                "wide_box": bool(wide_box),
                "torso_flat": False,
                "legs_folded_or_flat": False,
                "aspect_ratio": float(aspect_ratio),
                "torso_vertical_ratio": None,
                "hip_to_ankle_vertical_ratio": None,
            }

        l_sh = (float(kpt_xy[5][0]), float(kpt_xy[5][1]))
        r_sh = (float(kpt_xy[6][0]), float(kpt_xy[6][1]))
        l_hip = (float(kpt_xy[11][0]), float(kpt_xy[11][1]))
        r_hip = (float(kpt_xy[12][0]), float(kpt_xy[12][1]))
        l_ank = (float(kpt_xy[15][0]), float(kpt_xy[15][1]))
        r_ank = (float(kpt_xy[16][0]), float(kpt_xy[16][1]))

        sh_c = self._midpoint(l_sh, r_sh)
        hip_c = self._midpoint(l_hip, r_hip)
        ank_c = self._midpoint(l_ank, r_ank)

        torso_vertical_ratio = abs(sh_c[1] - hip_c[1]) / h
        hip_to_ankle_vertical_ratio = abs(ank_c[1] - hip_c[1]) / h

        torso_flat = torso_vertical_ratio <= self.cfg.torso_vertical_ratio_threshold
        legs_folded_or_flat = hip_to_ankle_vertical_ratio <= self.cfg.hip_to_ankle_vertical_ratio_threshold

        signals_true = int(wide_box) + int(torso_flat) + int(legs_folded_or_flat)
        fall_candidate = signals_true >= int(self.cfg.min_signals_to_fall)

        return {
            "fall_candidate": bool(fall_candidate),
            "score": float(signals_true / 3.0),
            "signals_true": int(signals_true),
            "wide_box": bool(wide_box),
            "torso_flat": bool(torso_flat),
            "legs_folded_or_flat": bool(legs_folded_or_flat),
            "aspect_ratio": float(aspect_ratio),
            "torso_vertical_ratio": float(torso_vertical_ratio),
            "hip_to_ankle_vertical_ratio": float(hip_to_ankle_vertical_ratio),
        }

    def infer(self, result: Any) -> dict[str, Any]:
        self._frame_idx += 1

        if not self.cfg.enabled:
            return {
                "fall_detector_enabled": False,
                "fall_track_mode_used": False,
                "raw_fall_detected": False,
                "stable_fall_detected": False,
                "fall_state_changed": False,
                "fall_person_candidates": 0,
                "fall_max_score": 0.0,
                "fall_top_candidate": None,
                "fall_active_track_ids": [],
                "fall_active_track_count": 0,
            }

        if result.boxes is None or len(result.boxes) == 0:
            stable_state, changed = self.stabilizer.update(False)
            self._global_track_state = False
            return {
                "fall_detector_enabled": True,
                "fall_track_mode_used": False,
                "raw_fall_detected": False,
                "stable_fall_detected": bool(stable_state),
                "fall_state_changed": bool(changed),
                "fall_person_candidates": 0,
                "fall_max_score": 0.0,
                "fall_top_candidate": None,
                "fall_active_track_ids": [],
                "fall_active_track_count": 0,
            }

        kpts = result.keypoints
        if kpts is None or kpts.xy is None or kpts.conf is None:
            # Without keypoints, keep conservative output and rely on stabilizer decay.
            stable_state, changed = self.stabilizer.update(False)
            self._global_track_state = False
            return {
                "fall_detector_enabled": True,
                "fall_track_mode_used": False,
                "raw_fall_detected": False,
                "stable_fall_detected": bool(stable_state),
                "fall_state_changed": bool(changed),
                "fall_person_candidates": 0,
                "fall_max_score": 0.0,
                "fall_top_candidate": None,
                "fall_active_track_ids": [],
                "fall_active_track_count": 0,
            }

        boxes_xyxy = result.boxes.xyxy
        boxes_id = getattr(result.boxes, "id", None)
        kp_xy = kpts.xy
        kp_conf = kpts.conf

        candidates: list[dict[str, Any]] = []
        all_people: list[dict[str, Any]] = []
        max_score = 0.0

        n = min(len(boxes_xyxy), len(kp_xy), len(kp_conf))
        any_track_id = False
        for i in range(n):
            person = self._analyze_person(
                box_xyxy=boxes_xyxy[i],
                kpt_xy=kp_xy[i],
                kpt_conf=kp_conf[i],
            )
            person["person_index"] = int(i)
            if boxes_id is not None and i < len(boxes_id):
                track_id = self._to_track_id(boxes_id[i])
                person["track_id"] = track_id
                any_track_id = any_track_id or (track_id is not None)
            else:
                person["track_id"] = None

            max_score = max(max_score, float(person["score"]))
            if person["fall_candidate"]:
                candidates.append(person)
            all_people.append(person)

        if self.cfg.use_track_stabilization and any_track_id:
            return self._infer_per_track(candidates=candidates, all_people=all_people)

        return self._infer_global(result=result, candidates=candidates, max_score=max_score)
