from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Iterable
from types import SimpleNamespace

import numpy as np


STABLE_JOINT_INDICES = (5, 6, 11, 12)


@dataclass(frozen=True)
class DepthSample:
    valid: bool
    depth_m: float | None
    sample_count: int
    std_m: float | None
    reason: str


def stamp_to_ns(stamp: dict[str, Any] | None) -> int | None:
    if not isinstance(stamp, dict):
        return None
    try:
        return int(stamp["sec"]) * 1_000_000_000 + int(stamp["nanosec"])
    except (KeyError, TypeError, ValueError):
        return None


def decode_depth_image(message: Any) -> tuple[np.ndarray, float]:
    """Return a metric depth image and the raw-to-metre scale."""

    encoding = str(message.encoding).upper()
    if encoding in {"16UC1", "MONO16"}:
        dtype = np.dtype(">u2" if bool(message.is_bigendian) else "<u2")
        scale = 0.001
    elif encoding == "32FC1":
        dtype = np.dtype(">f4" if bool(message.is_bigendian) else "<f4")
        scale = 1.0
    else:
        raise ValueError(f"unsupported_depth_encoding:{message.encoding}")

    itemsize = dtype.itemsize
    minimum_step = int(message.width) * itemsize
    if int(message.step) < minimum_step:
        raise ValueError("invalid_depth_step")
    image = np.ndarray(
        shape=(int(message.height), int(message.width)),
        dtype=dtype,
        buffer=message.data,
        strides=(int(message.step), itemsize),
    )
    return image, scale


def sample_depth(
    depth_image: np.ndarray,
    *,
    u: float,
    v: float,
    unit_scale: float,
    radius_px: int = 2,
    min_samples: int = 5,
    min_depth_m: float = 0.30,
    max_depth_m: float = 8.0,
    mad_scale: float = 3.0,
) -> DepthSample:
    if not math.isfinite(u) or not math.isfinite(v):
        return DepthSample(False, None, 0, None, "pixel_non_finite")

    height, width = depth_image.shape[:2]
    center_u = int(round(u))
    center_v = int(round(v))
    if center_u < 0 or center_u >= width or center_v < 0 or center_v >= height:
        return DepthSample(False, None, 0, None, "pixel_out_of_bounds")

    radius = max(0, int(radius_px))
    left = max(0, center_u - radius)
    right = min(width, center_u + radius + 1)
    top = max(0, center_v - radius)
    bottom = min(height, center_v + radius + 1)
    values_m = depth_image[top:bottom, left:right].astype(np.float64).reshape(-1) * float(
        unit_scale
    )
    valid = values_m[
        np.isfinite(values_m)
        & (values_m >= float(min_depth_m))
        & (values_m <= float(max_depth_m))
    ]
    if len(valid) < int(min_samples):
        return DepthSample(False, None, int(len(valid)), None, "insufficient_depth_samples")

    median = float(np.median(valid))
    absolute_deviation = np.abs(valid - median)
    mad = float(np.median(absolute_deviation))
    if mad > 0.0 and mad_scale > 0.0:
        robust_sigma = 1.4826 * mad
        filtered = valid[absolute_deviation <= float(mad_scale) * robust_sigma]
        if len(filtered) >= int(min_samples):
            valid = filtered
            median = float(np.median(valid))
            mad = float(np.median(np.abs(valid - median)))

    std_m = max(0.005, 1.4826 * mad)
    return DepthSample(True, median, int(len(valid)), std_m, "ok")


def backproject_pixel(
    *,
    u: float,
    v: float,
    depth_m: float,
    camera_matrix: Iterable[float],
) -> list[float]:
    matrix = list(camera_matrix)
    if len(matrix) != 9:
        raise ValueError("camera_matrix_must_have_9_elements")
    fx, fy, cx, cy = float(matrix[0]), float(matrix[4]), float(matrix[2]), float(matrix[5])
    if fx <= 0.0 or fy <= 0.0:
        raise ValueError("camera_focal_length_invalid")
    return [
        (float(u) - cx) * float(depth_m) / fx,
        (float(v) - cy) * float(depth_m) / fy,
        float(depth_m),
    ]


def transform_point(point: Iterable[float], transform: Any) -> list[float]:
    point_array = np.asarray(list(point), dtype=np.float64)
    if point_array.shape != (3,):
        raise ValueError("point_must_have_3_elements")
    translation = transform.translation
    quaternion = transform.rotation
    x, y, z, w = (
        float(quaternion.x),
        float(quaternion.y),
        float(quaternion.z),
        float(quaternion.w),
    )
    norm = math.sqrt(x * x + y * y + z * z + w * w)
    if norm <= 1e-12:
        raise ValueError("transform_quaternion_invalid")
    x, y, z, w = x / norm, y / norm, z / norm, w / norm
    rotation = np.asarray(
        [
            [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
        ],
        dtype=np.float64,
    )
    transformed = rotation @ point_array + np.asarray(
        [float(translation.x), float(translation.y), float(translation.z)],
        dtype=np.float64,
    )
    return [float(value) for value in transformed]


def compose_transforms(outer: Any, inner: Any) -> Any:
    """Compose A<-B (outer) with B<-C (inner), returning A<-C."""

    translated = transform_point(
        [inner.translation.x, inner.translation.y, inner.translation.z], outer
    )
    a = outer.rotation
    b = inner.rotation
    quaternion = SimpleNamespace(
        x=float(a.w * b.x + a.x * b.w + a.y * b.z - a.z * b.y),
        y=float(a.w * b.y - a.x * b.z + a.y * b.w + a.z * b.x),
        z=float(a.w * b.z + a.x * b.y - a.y * b.x + a.z * b.w),
        w=float(a.w * b.w - a.x * b.x - a.y * b.y - a.z * b.z),
    )
    return SimpleNamespace(
        translation=SimpleNamespace(x=translated[0], y=translated[1], z=translated[2]),
        rotation=quaternion,
    )


def robust_center(
    joints: list[dict[str, Any]],
    *,
    field: str,
    stable_indices: Iterable[int] = STABLE_JOINT_INDICES,
    min_stable: int = 2,
) -> tuple[list[float] | None, list[int], str]:
    stable_set = {int(index) for index in stable_indices}
    selected = [
        joint
        for joint in joints
        if int(joint.get("index", -1)) in stable_set
        and bool(joint.get("valid"))
        and isinstance(joint.get(field), list)
        and len(joint[field]) == 3
    ]
    reason = "ok"
    if len(selected) < int(min_stable):
        selected = [
            joint
            for joint in joints
            if bool(joint.get("valid"))
            and isinstance(joint.get(field), list)
            and len(joint[field]) == 3
        ]
        reason = "fallback_all_valid_keypoints"
    if not selected:
        return None, [], "no_valid_keypoints"
    values = np.asarray([joint[field] for joint in selected], dtype=np.float64)
    center = np.median(values, axis=0)
    return [float(value) for value in center], [int(joint["index"]) for joint in selected], reason


def point_covariance_6x6(std_m: float) -> list[float]:
    variance = max(0.05, min(0.50, float(std_m))) ** 2
    covariance = [0.0] * 36
    covariance[0] = variance
    covariance[7] = variance
    covariance[14] = variance
    covariance[21] = 1.0
    covariance[28] = 1.0
    covariance[35] = 1.0
    return covariance


def quaternion_yaw(rotation: Any) -> float:
    x, y, z, w = (
        float(rotation.x),
        float(rotation.y),
        float(rotation.z),
        float(rotation.w),
    )
    return math.atan2(2.0 * (w * z + x * y), 1.0 - 2.0 * (y * y + z * z))
