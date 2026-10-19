from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import sys

import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parents[1]
for source_root in (
    PROJECT_ROOT / "src",
    PROJECT_ROOT / "ros2_ws/src/yolopose_ros",
):
    if str(source_root) not in sys.path:
        sys.path.insert(0, str(source_root))

from yolopose.temporal.features import extract_pose_observations_2d  # noqa: E402
from yolopose_ros.pose_3d_geometry import (  # noqa: E402
    backproject_pixel,
    compose_transforms,
    point_covariance_6x6,
    robust_center,
    sample_depth,
    transform_point,
)


def test_extract_pose_observations_preserves_pixels_and_track() -> None:
    result = SimpleNamespace(
        orig_shape=(720, 1280),
        boxes=SimpleNamespace(
            xyxy=np.asarray([[10.0, 20.0, 110.0, 220.0]], dtype=np.float32),
            conf=np.asarray([0.91], dtype=np.float32),
            id=np.asarray([7.0], dtype=np.float32),
        ),
        keypoints=SimpleNamespace(
            xy=np.asarray([[[100.0 + i, 200.0 + i] for i in range(17)]], dtype=np.float32),
            conf=np.asarray([[0.9] * 17], dtype=np.float32),
        ),
    )
    observations = extract_pose_observations_2d(result, keypoint_conf_threshold=0.3)
    assert len(observations) == 1
    assert observations[0]["track_id"] == 7
    assert observations[0]["image_width"] == 1280
    assert observations[0]["image_height"] == 720
    assert observations[0]["keypoints"][5]["name"] == "left_shoulder"
    assert observations[0]["keypoints"][5]["u"] == 105.0
    assert observations[0]["visible_keypoint_count"] == 17


def test_depth_window_rejects_outlier_and_backprojects() -> None:
    image = np.full((9, 9), 2000, dtype=np.uint16)
    image[4, 4] = 65000
    sample = sample_depth(
        image,
        u=4,
        v=4,
        unit_scale=0.001,
        radius_px=2,
        min_samples=5,
        min_depth_m=0.3,
        max_depth_m=8.0,
    )
    assert sample.valid
    assert sample.depth_m == 2.0
    point = backproject_pixel(
        u=642.0,
        v=363.0,
        depth_m=2.0,
        camera_matrix=[692.0, 0.0, 642.0, 0.0, 692.0, 363.0, 0.0, 0.0, 1.0],
    )
    assert point == [0.0, 0.0, 2.0]


def test_transform_and_robust_center_use_stable_torso_joints() -> None:
    transform = SimpleNamespace(
        translation=SimpleNamespace(x=1.0, y=2.0, z=3.0),
        rotation=SimpleNamespace(x=0.0, y=0.0, z=0.0, w=1.0),
    )
    assert transform_point([0.1, 0.2, 0.3], transform) == [1.1, 2.2, 3.3]
    inner = SimpleNamespace(
        translation=SimpleNamespace(x=0.0, y=0.0, z=0.04),
        rotation=SimpleNamespace(x=0.0, y=0.0, z=0.0, w=1.0),
    )
    composed = compose_transforms(transform, inner)
    assert transform_point([0.0, 0.0, 0.0], composed) == [1.0, 2.0, 3.04]
    joints = [
        {"index": 5, "valid": True, "position_map": [1.0, 2.0, 0.0]},
        {"index": 6, "valid": True, "position_map": [3.0, 4.0, 0.0]},
        {"index": 0, "valid": True, "position_map": [100.0, 100.0, 1.0]},
    ]
    center, indices, reason = robust_center(joints, field="position_map")
    assert center == [2.0, 3.0, 0.0]
    assert indices == [5, 6]
    assert reason == "ok"


def test_covariance_is_nonzero_protocol_shape() -> None:
    covariance = point_covariance_6x6(0.01)
    assert len(covariance) == 36
    assert covariance[0] == covariance[7] == covariance[14] == 0.05**2
    assert covariance[35] == 1.0
