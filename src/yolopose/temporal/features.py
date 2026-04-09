from __future__ import annotations

from typing import Any

import numpy as np

POSE_KPT_COUNT = 17
POSE_FEATURE_DIM = POSE_KPT_COUNT * 3 + 3  # x, y, conf for each keypoint + aspect_ratio + log_area + present


def _clip_conf(value: Any) -> float:
    try:
        x = float(value)
    except (TypeError, ValueError):
        return 0.0
    return float(min(1.0, max(0.0, x)))


def encode_person_feature(
    box_xyxy: Any,
    kpt_xy: Any,
    kpt_conf: Any,
    keypoint_conf_threshold: float = 0.3,
) -> np.ndarray:
    x1, y1, x2, y2 = [float(v) for v in box_xyxy]
    w = max(1e-6, x2 - x1)
    h = max(1e-6, y2 - y1)
    cx = 0.5 * (x1 + x2)
    cy = 0.5 * (y1 + y2)
    scale = max(w, h, 1e-6)

    feat: list[float] = []
    for idx in range(POSE_KPT_COUNT):
        conf = _clip_conf(kpt_conf[idx])
        if conf >= keypoint_conf_threshold:
            norm_x = (float(kpt_xy[idx][0]) - cx) / scale
            norm_y = (float(kpt_xy[idx][1]) - cy) / scale
        else:
            norm_x = 0.0
            norm_y = 0.0
            conf = 0.0
        feat.extend([norm_x, norm_y, conf])

    aspect_ratio = w / h
    log_area = float(np.log(max(1.0, w * h)))
    feat.extend([aspect_ratio, log_area, 1.0])
    return np.asarray(feat, dtype=np.float32)


def empty_person_feature() -> np.ndarray:
    return np.zeros((POSE_FEATURE_DIM,), dtype=np.float32)


def _to_track_id(value: Any) -> int | None:
    try:
        tid = float(value)
    except (TypeError, ValueError):
        return None
    if np.isnan(tid):
        return None
    return int(tid)


def extract_person_candidates(result: Any, keypoint_conf_threshold: float = 0.3) -> list[dict[str, Any]]:
    boxes = getattr(result, 'boxes', None)
    keypoints = getattr(result, 'keypoints', None)
    if boxes is None or keypoints is None or keypoints.xy is None or keypoints.conf is None:
        return []

    boxes_xyxy = boxes.xyxy
    boxes_id = getattr(boxes, 'id', None)
    kp_xy = keypoints.xy
    kp_conf = keypoints.conf

    candidates: list[dict[str, Any]] = []
    n = min(len(boxes_xyxy), len(kp_xy), len(kp_conf))
    for i in range(n):
        x1, y1, x2, y2 = [float(v) for v in boxes_xyxy[i]]
        area = max(0.0, (x2 - x1) * (y2 - y1))
        feature = encode_person_feature(
            boxes_xyxy[i],
            kp_xy[i],
            kp_conf[i],
            keypoint_conf_threshold=keypoint_conf_threshold,
        )
        track_id = None
        if boxes_id is not None and i < len(boxes_id):
            track_id = _to_track_id(boxes_id[i])
        candidates.append(
            {
                'index': i,
                'track_id': track_id,
                'area': float(area),
                'box_xyxy': [x1, y1, x2, y2],
                'feature': feature,
            }
        )
    candidates.sort(key=lambda item: item['area'], reverse=True)
    return candidates


def extract_primary_person_feature(result: Any, keypoint_conf_threshold: float = 0.3) -> tuple[np.ndarray, dict[str, Any] | None]:
    candidates = extract_person_candidates(result, keypoint_conf_threshold=keypoint_conf_threshold)
    if not candidates:
        return empty_person_feature(), None
    best = candidates[0]
    return np.asarray(best['feature'], dtype=np.float32), best
