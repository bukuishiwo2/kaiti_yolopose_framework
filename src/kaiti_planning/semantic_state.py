from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .models import SemanticConfig, SemanticStateOutput


@dataclass
class _Counters:
    confirm_hits: int = 0
    clear_hits: int = 0
    hold_remaining: int = 0
    cooldown_remaining: int = 0
    next_event_index: int = 1
    last_track_id: int | None = None


class SemanticStateMachine:
    def __init__(self, cfg: SemanticConfig):
        self.cfg = cfg
        self._state = "normal"
        self._event_id: str | None = None
        self._counters = _Counters()

    def _quality_score(self, event: dict[str, Any]) -> tuple[float, dict[str, float]]:
        visible_count = max(0, int(event.get("seq_visible_keypoint_count", 0) or 0))
        visible_ratio = min(1.0, visible_count / max(1, int(self.cfg.visible_keypoint_threshold)))
        track_id = event.get("seq_track_id")
        track_continuity = 1.0 if track_id is not None and track_id == self._counters.last_track_id else 0.6
        self._counters.last_track_id = track_id if track_id is not None else self._counters.last_track_id
        window_ready = 1.0 if bool(event.get("seq_window_ready", False)) else 0.0
        feature_valid = 1.0 if bool(event.get("seq_feature_valid", False)) else 0.0
        geometry_valid = 1.0 if visible_count >= max(3, self.cfg.visible_keypoint_threshold // 2) else 0.0
        score = (
            0.30 * visible_ratio
            + 0.20 * track_continuity
            + 0.20 * window_ready
            + 0.20 * feature_valid
            + 0.10 * geometry_valid
        )
        return score, {
            "visible_ratio": visible_ratio,
            "track_continuity": track_continuity,
            "window_ready": window_ready,
            "feature_valid": feature_valid,
            "geometry_valid": geometry_valid,
        }

    def update(self, event: dict[str, Any]) -> SemanticStateOutput:
        raw_score = float(event.get("seq_fall_score", event.get("fall_score", 0.0)) or 0.0)
        quality_score, _ = self._quality_score(event)
        location = str(event.get("event_location") or event.get("location") or "B")

        if self._counters.cooldown_remaining > 0:
            self._counters.cooldown_remaining -= 1

        if quality_score < float(self.cfg.quality_min):
            self._state = "perception_degraded"
            predicate = "perception_degraded"
            self._counters.confirm_hits = 0
            self._counters.clear_hits = 0
            self._counters.hold_remaining = 0
            self._event_id = None
            return SemanticStateOutput(
                semantic_state=self._state,
                predicate=predicate,
                event_id=None,
                event_location=location,
                fall_score=round(raw_score, 4),
                quality_score=round(quality_score, 4),
                source_event=event,
            )

        if raw_score >= float(self.cfg.theta_high) and self._counters.cooldown_remaining == 0:
            self._counters.confirm_hits += 1
            self._counters.clear_hits = 0
            if self._counters.confirm_hits >= int(self.cfg.min_confirm_windows):
                self._state = "event_confirmed"
                self._counters.hold_remaining = int(self.cfg.hold_frames)
                if self._event_id is None:
                    self._event_id = f"event_{self._counters.next_event_index:03d}"
                    self._counters.next_event_index += 1
                return SemanticStateOutput(
                    semantic_state=self._state,
                    predicate="fall_confirmed",
                    event_id=self._event_id,
                    event_location=location,
                    fall_score=round(raw_score, 4),
                    quality_score=round(quality_score, 4),
                    source_event=event,
                )

        if self._state == "event_confirmed" and self._counters.hold_remaining > 0:
            self._counters.hold_remaining -= 1
            return SemanticStateOutput(
                semantic_state=self._state,
                predicate="fall_confirmed",
                event_id=self._event_id,
                event_location=location,
                fall_score=round(raw_score, 4),
                quality_score=round(quality_score, 4),
                source_event=event,
            )

        if float(self.cfg.theta_low) < raw_score < float(self.cfg.theta_high):
            self._state = "event_uncertain"
            self._counters.confirm_hits = 0
            self._counters.clear_hits = 0
            return SemanticStateOutput(
                semantic_state=self._state,
                predicate="fall_uncertain",
                event_id=None,
                event_location=location,
                fall_score=round(raw_score, 4),
                quality_score=round(quality_score, 4),
                source_event=event,
            )

        if raw_score <= float(self.cfg.theta_low):
            self._counters.clear_hits += 1
            self._counters.confirm_hits = 0
            if self._counters.clear_hits >= int(self.cfg.min_clear_windows):
                if self._state == "event_confirmed":
                    self._counters.cooldown_remaining = int(self.cfg.cooldown_frames)
                self._state = "normal"
                self._event_id = None
                return SemanticStateOutput(
                    semantic_state=self._state,
                    predicate="event_closed" if event.get("event_closed") else None,
                    event_id=None,
                    event_location=location,
                    fall_score=round(raw_score, 4),
                    quality_score=round(quality_score, 4),
                    source_event=event,
                )

        return SemanticStateOutput(
            semantic_state=self._state,
            predicate=None if self._state == "normal" else "fall_uncertain",
            event_id=self._event_id,
            event_location=location,
            fall_score=round(raw_score, 4),
            quality_score=round(quality_score, 4),
            source_event=event,
        )
