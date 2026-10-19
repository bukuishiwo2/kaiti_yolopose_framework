from __future__ import annotations

from typing import Any

import numpy as np

POSE_KPT_COUNT = 17
POSE_FEATURE_DIM = POSE_KPT_COUNT * 3 + 3  # x, y, conf for each keypoint + aspect_ratio + log_area + present
COCO_KEYPOINT_NAMES = (
    "nose",
    "left_eye",
    "right_eye",
    "left_ear",
    "right_ear",
    "left_shoulder",
    "right_shoulder",
    "left_elbow",
    "right_elbow",
    "left_wrist",
    "right_wrist",
    "left_hip",
    "right_hip",
    "left_knee",
    "right_knee",
    "left_ankle",
    "right_ankle",
)


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
        visible_keypoint_count = int(
            sum(
                1
                for idx in range(POSE_KPT_COUNT)
                if _clip_conf(kp_conf[i][idx]) >= float(keypoint_conf_threshold)
            )
        )
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
                'visible_keypoint_count': visible_keypoint_count,
                'feature_valid': bool(visible_keypoint_count > 0),
            }
        )
    candidates.sort(key=lambda item: item['area'], reverse=True)
    return candidates


def extract_pose_observations_2d(
    result: Any,
    keypoint_conf_threshold: float = 0.3,
) -> list[dict[str, Any]]:
    """Serialize YOLO pose detections without losing original pixel geometry."""

    boxes = getattr(result, "boxes", None)
    keypoints = getattr(result, "keypoints", None)
    if boxes is None or keypoints is None or keypoints.xy is None or keypoints.conf is None:
        return []

    boxes_xyxy = boxes.xyxy
    boxes_conf = getattr(boxes, "conf", None)
    boxes_id = getattr(boxes, "id", None)
    kp_xy = keypoints.xy
    kp_conf = keypoints.conf
    orig_shape = getattr(result, "orig_shape", None)
    image_height = int(orig_shape[0]) if orig_shape is not None else 0
    image_width = int(orig_shape[1]) if orig_shape is not None else 0

    observations: list[dict[str, Any]] = []
    count = min(len(boxes_xyxy), len(kp_xy), len(kp_conf))
    for detection_index in range(count):
        track_id = None
        if boxes_id is not None and detection_index < len(boxes_id):
            track_id = _to_track_id(boxes_id[detection_index])
        bbox_confidence = 0.0
        if boxes_conf is not None and detection_index < len(boxes_conf):
            bbox_confidence = _clip_conf(boxes_conf[detection_index])

        joints: list[dict[str, Any]] = []
        visible_count = 0
        for joint_index, joint_name in enumerate(COCO_KEYPOINT_NAMES):
            confidence = _clip_conf(kp_conf[detection_index][joint_index])
            visible = confidence >= float(keypoint_conf_threshold)
            visible_count += int(visible)
            joints.append(
                {
                    "index": joint_index,
                    "name": joint_name,
                    "u": float(kp_xy[detection_index][joint_index][0]),
                    "v": float(kp_xy[detection_index][joint_index][1]),
                    "confidence": confidence,
                    "visible": visible,
                }
            )

        observations.append(
            {
                "detection_index": detection_index,
                "track_id": track_id,
                "bbox_xyxy": [float(value) for value in boxes_xyxy[detection_index]],
                "bbox_confidence": bbox_confidence,
                "visible_keypoint_count": visible_count,
                "image_width": image_width,
                "image_height": image_height,
                "keypoints": joints,
            }
        )
    return observations


def extract_primary_person_feature(result: Any, keypoint_conf_threshold: float = 0.3) -> tuple[np.ndarray, dict[str, Any] | None]:
    candidates = extract_person_candidates(result, keypoint_conf_threshold=keypoint_conf_threshold)
    if not candidates:
        return empty_person_feature(), None
    best = candidates[0]
    return np.asarray(best['feature'], dtype=np.float32), best
