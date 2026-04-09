from __future__ import annotations

from dataclasses import dataclass


@dataclass
class StabilizerConfig:
    min_true_frames: int = 3
    min_false_frames: int = 5


class BooleanStabilizer:
    """Turn noisy per-frame booleans into stable state transitions."""

    def __init__(self, cfg: StabilizerConfig):
        self.cfg = cfg
        self._true_count = 0
        self._false_count = 0
        self._state = False

    @property
    def state(self) -> bool:
        return self._state

    def update(self, raw_value: bool) -> tuple[bool, bool]:
        changed = False
        if raw_value:
            self._true_count += 1
            self._false_count = 0
            if not self._state and self._true_count >= self.cfg.min_true_frames:
                self._state = True
                changed = True
        else:
            self._false_count += 1
            self._true_count = 0
            if self._state and self._false_count >= self.cfg.min_false_frames:
                self._state = False
                changed = True

        return self._state, changed
