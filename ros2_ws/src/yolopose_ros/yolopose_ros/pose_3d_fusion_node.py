from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import json
import math
import time
from types import SimpleNamespace
from typing import Any

import numpy as np
import cv2
import rclpy
from rclpy.duration import Duration
from rclpy.node import Node
from rclpy.qos import HistoryPolicy, QoSProfile, ReliabilityPolicy
from rclpy.time import Time
from nav_msgs.msg import Odometry
from sensor_msgs.msg import CameraInfo, CompressedImage, Image
from std_msgs.msg import String
from tf2_ros import Buffer, TransformException, TransformListener

from yolopose_ros.pose_3d_geometry import (
    STABLE_JOINT_INDICES,
    backproject_pixel,
    compose_transforms,
    decode_depth_image,
    point_covariance_6x6,
    quaternion_yaw,
    robust_center,
    sample_depth,
    stamp_to_ns,
    transform_point,
)


@dataclass(frozen=True)
class DepthFrame:
    stamp_ns: int
    frame_id: str
    image: np.ndarray
    unit_scale: float


class Pose3DFusionNode(Node):
    """Fuse YOLO pixel keypoints with aligned Gemini depth and timestamped TF."""

    def __init__(self) -> None:
        super().__init__("pose_3d_fusion_node")
        self.declare_parameter("pose_event_topic", "/perception/events")
        self.declare_parameter("depth_topic", "/inference/depth/image_raw")
        self.declare_parameter(
            "depth_compressed_topic", "/camera/depth/image_raw/compressedDepth"
        )
        self.declare_parameter("use_compressed_depth", True)
        self.declare_parameter("camera_info_topic", "/camera/color/camera_info")
        self.declare_parameter("pose_3d_topic", "/perception/pose_observation_3d")
        self.declare_parameter("semantic_event_topic", "/perception/semantic_event_3d")
        self.declare_parameter("base_frame", "base_link")
        self.declare_parameter("base_footprint_frame", "base_footprint")
        self.declare_parameter("map_frame", "map")
        self.declare_parameter("odom_frame", "odom")
        self.declare_parameter("odom_topic", "/rtabmap/odom")
        self.declare_parameter("odom_sync_slop_sec", 0.30)
        self.declare_parameter("observer_robot_id", "R1")
        self.declare_parameter("sync_slop_sec", 0.05)
        self.declare_parameter("pending_timeout_sec", 2.0)
        self.declare_parameter("depth_cache_sec", 4.0)
        self.declare_parameter("tf_timeout_sec", 0.10)
        self.declare_parameter("keypoint_confidence", 0.30)
        self.declare_parameter("depth_min_m", 0.30)
        self.declare_parameter("depth_max_m", 8.00)
        self.declare_parameter("depth_window_radius_px", 2)
        self.declare_parameter("depth_window_min_samples", 5)
        self.declare_parameter("depth_mad_scale", 3.0)
        self.declare_parameter("stable_keypoints", list(STABLE_JOINT_INDICES))
        self.declare_parameter("min_valid_stable_keypoints", 2)
        self.declare_parameter("event_pose_expire_sec", 5.0)
        self.declare_parameter("publish_semantic_uncertain", True)
        self.declare_parameter("allow_urdf_camera_fallback", True)
        self.declare_parameter(
            "camera_translation_base_m",
            [0.19147247182847, -0.000068746226105, 0.0955],
        )
        self.declare_parameter(
            "camera_optical_rpy_base_rad",
            [-1.5707963267949, 0.0, -1.5707963267949],
        )
        self.declare_parameter("base_translation_footprint_m", [0.0, 0.0, 0.04])

        self._pose_event_topic = str(self.get_parameter("pose_event_topic").value)
        self._depth_topic = str(self.get_parameter("depth_topic").value)
        self._depth_compressed_topic = str(
            self.get_parameter("depth_compressed_topic").value
        )
        self._use_compressed_depth = bool(
            self.get_parameter("use_compressed_depth").value
        )
        self._camera_info_topic = str(self.get_parameter("camera_info_topic").value)
        self._base_frame = str(self.get_parameter("base_frame").value)
        self._base_footprint_frame = str(
            self.get_parameter("base_footprint_frame").value
        )
        self._map_frame = str(self.get_parameter("map_frame").value)
        self._odom_frame = str(self.get_parameter("odom_frame").value)
        self._odom_topic = str(self.get_parameter("odom_topic").value)
        self._odom_sync_slop_ns = int(
            float(self.get_parameter("odom_sync_slop_sec").value) * 1e9
        )
        self._observer_robot_id = str(self.get_parameter("observer_robot_id").value)
        self._sync_slop_ns = int(float(self.get_parameter("sync_slop_sec").value) * 1e9)
        self._pending_timeout_sec = float(self.get_parameter("pending_timeout_sec").value)
        self._depth_cache_ns = int(float(self.get_parameter("depth_cache_sec").value) * 1e9)
        self._tf_timeout_sec = float(self.get_parameter("tf_timeout_sec").value)
        self._keypoint_confidence = float(self.get_parameter("keypoint_confidence").value)
        self._depth_min_m = float(self.get_parameter("depth_min_m").value)
        self._depth_max_m = float(self.get_parameter("depth_max_m").value)
        self._depth_window_radius_px = int(
            self.get_parameter("depth_window_radius_px").value
        )
        self._depth_window_min_samples = int(
            self.get_parameter("depth_window_min_samples").value
        )
        self._depth_mad_scale = float(self.get_parameter("depth_mad_scale").value)
        self._stable_keypoints = tuple(
            int(value) for value in self.get_parameter("stable_keypoints").value
        )
        self._min_valid_stable = int(
            self.get_parameter("min_valid_stable_keypoints").value
        )
        self._event_pose_expire_ns = int(
            float(self.get_parameter("event_pose_expire_sec").value) * 1e9
        )
        self._publish_semantic_uncertain = bool(
            self.get_parameter("publish_semantic_uncertain").value
        )
        self._allow_urdf_camera_fallback = bool(
            self.get_parameter("allow_urdf_camera_fallback").value
        )
        self._urdf_base_transform = self._make_urdf_base_transform(
            self.get_parameter("camera_translation_base_m").value,
            self.get_parameter("camera_optical_rpy_base_rad").value,
        )
        self._footprint_from_base = self._make_urdf_base_transform(
            self.get_parameter("base_translation_footprint_m").value,
            [0.0, 0.0, 0.0],
        )

        self._pose_publisher = self.create_publisher(
            String, str(self.get_parameter("pose_3d_topic").value), 10
        )
        self._semantic_publisher = self.create_publisher(
            String, str(self.get_parameter("semantic_event_topic").value), 10
        )
        self._tf_buffer = Buffer(cache_time=Duration(seconds=10.0))
        self._tf_listener = TransformListener(self._tf_buffer, self)
        self._depth_cache: deque[tuple[int, DepthFrame]] = deque()
        self._odom_cache: deque[tuple[int, Odometry]] = deque()
        self._pending_events: deque[tuple[float, dict[str, Any]]] = deque()
        self._camera_info: CameraInfo | None = None
        self._perception_revision = 0

        sensor_qos = QoSProfile(
            history=HistoryPolicy.KEEP_LAST,
            depth=5,
            reliability=ReliabilityPolicy.BEST_EFFORT,
        )
        if self._use_compressed_depth:
            self.create_subscription(
                CompressedImage,
                self._depth_compressed_topic,
                self._on_compressed_depth,
                sensor_qos,
            )
        else:
            self.create_subscription(Image, self._depth_topic, self._on_depth, sensor_qos)
        self.create_subscription(
            CameraInfo, self._camera_info_topic, self._on_camera_info, sensor_qos
        )
        self.create_subscription(String, self._pose_event_topic, self._on_pose_event, 10)
        self.create_subscription(Odometry, self._odom_topic, self._on_odom, sensor_qos)
        self.create_timer(0.05, self._process_pending)
        self.get_logger().info(
            "3D pose fusion ready: events=%s depth=%s info=%s frames=%s/%s"
            % (
                self._pose_event_topic,
                self._depth_compressed_topic
                if self._use_compressed_depth
                else self._depth_topic,
                self._camera_info_topic,
                self._base_frame,
                self._map_frame,
            )
        )

    @staticmethod
    def _message_stamp_ns(message: Image | CameraInfo | Odometry) -> int:
        return int(message.header.stamp.sec) * 1_000_000_000 + int(
            message.header.stamp.nanosec
        )

    @staticmethod
    def _publish_json(publisher: Any, payload: dict[str, Any]) -> None:
        message = String()
        message.data = json.dumps(payload, ensure_ascii=True, allow_nan=False)
        publisher.publish(message)

    def _on_camera_info(self, message: CameraInfo) -> None:
        if int(message.width) > 0 and int(message.height) > 0 and float(message.k[0]) > 0.0:
            self._camera_info = message

    def _on_depth(self, message: Image) -> None:
        stamp_ns = self._message_stamp_ns(message)
        try:
            image, unit_scale = decode_depth_image(message)
        except (TypeError, ValueError) as exc:
            self.get_logger().error("Depth decoding failed: %s" % exc)
            return
        self._store_depth(
            DepthFrame(stamp_ns, str(message.header.frame_id), image.copy(), unit_scale)
        )

    def _on_odom(self, message: Odometry) -> None:
        stamp_ns = self._message_stamp_ns(message)
        self._odom_cache.append((stamp_ns, message))
        newest_allowed = stamp_ns - self._depth_cache_ns
        while self._odom_cache and self._odom_cache[0][0] < newest_allowed:
            self._odom_cache.popleft()

    def _on_compressed_depth(self, message: CompressedImage) -> None:
        stamp_ns = self._message_stamp_ns(message)
        png_signature = b"\x89PNG\r\n\x1a\n"
        offset = bytes(message.data).find(png_signature)
        if offset < 0:
            self.get_logger().error("Compressed depth message has no PNG payload")
            return
        encoded = np.frombuffer(message.data[offset:], dtype=np.uint8)
        image = cv2.imdecode(encoded, cv2.IMREAD_UNCHANGED)
        if image is None or image.dtype != np.uint16:
            self.get_logger().error("Compressed depth PNG is not uint16")
            return
        self._store_depth(
            DepthFrame(stamp_ns, str(message.header.frame_id), image, 0.001)
        )

    def _store_depth(self, frame: DepthFrame) -> None:
        stamp_ns = frame.stamp_ns
        self._depth_cache.append((stamp_ns, frame))
        newest_allowed = stamp_ns - self._depth_cache_ns
        while self._depth_cache and self._depth_cache[0][0] < newest_allowed:
            self._depth_cache.popleft()
        self._process_pending()

    def _on_pose_event(self, message: String) -> None:
        try:
            payload = json.loads(message.data)
        except json.JSONDecodeError:
            self.get_logger().warning("Ignoring malformed perception event JSON")
            return
        if not isinstance(payload, dict) or not isinstance(
            payload.get("pose_observations_2d"), list
        ):
            return
        if stamp_to_ns(payload.get("source_stamp")) is None:
            self.get_logger().warning("Ignoring pose event without source timestamp")
            return
        self._pending_events.append((time.monotonic(), payload))
        self._process_pending()

    def _nearest_depth(self, stamp_ns: int) -> tuple[DepthFrame | None, int | None]:
        if not self._depth_cache:
            return None, None
        depth_stamp_ns, frame = min(
            self._depth_cache, key=lambda item: abs(item[0] - stamp_ns)
        )
        delta_ns = abs(depth_stamp_ns - stamp_ns)
        if delta_ns > self._sync_slop_ns:
            return None, delta_ns
        return frame, delta_ns

    def _nearest_odom_transform(self, stamp_ns: int) -> Any | None:
        if not self._odom_cache:
            return None
        odom_stamp_ns, message = min(
            self._odom_cache, key=lambda item: abs(item[0] - stamp_ns)
        )
        if abs(odom_stamp_ns - stamp_ns) > self._odom_sync_slop_ns:
            return None
        pose = message.pose.pose
        odom_from_footprint = SimpleNamespace(
            translation=SimpleNamespace(
                x=float(pose.position.x),
                y=float(pose.position.y),
                z=float(pose.position.z),
            ),
            rotation=SimpleNamespace(
                x=float(pose.orientation.x),
                y=float(pose.orientation.y),
                z=float(pose.orientation.z),
                w=float(pose.orientation.w),
            ),
        )
        return compose_transforms(odom_from_footprint, self._footprint_from_base)

    def _lookup_transform(self, target: str, source: str, stamp_ns: int) -> Any:
        return self._tf_buffer.lookup_transform(
            target,
            source,
            Time(nanoseconds=stamp_ns),
            timeout=Duration(seconds=self._tf_timeout_sec),
        )

    def _lookup_latest_transform(self, target: str, source: str) -> Any:
        return self._tf_buffer.lookup_transform(
            target,
            source,
            Time(),
            timeout=Duration(seconds=self._tf_timeout_sec),
        )

    @staticmethod
    def _make_urdf_base_transform(translation: Any, rpy: Any) -> Any:
        tx, ty, tz = (float(value) for value in translation)
        roll, pitch, yaw = (float(value) for value in rpy)
        cr, sr = math.cos(roll / 2.0), math.sin(roll / 2.0)
        cp, sp = math.cos(pitch / 2.0), math.sin(pitch / 2.0)
        cy, sy = math.cos(yaw / 2.0), math.sin(yaw / 2.0)
        quaternion = SimpleNamespace(
            x=sr * cp * cy - cr * sp * sy,
            y=cr * sp * cy + sr * cp * sy,
            z=cr * cp * sy - sr * sp * cy,
            w=cr * cp * cy + sr * sp * sy,
        )
        return SimpleNamespace(
            translation=SimpleNamespace(x=tx, y=ty, z=tz),
            rotation=quaternion,
        )

    def _process_pending(self) -> None:
        if not self._pending_events:
            return
        retained: deque[tuple[float, dict[str, Any]]] = deque()
        now = time.monotonic()
        while self._pending_events:
            queued_at, event = self._pending_events.popleft()
            completed = self._try_fuse(event)
            if completed:
                continue
            if now - queued_at <= self._pending_timeout_sec:
                retained.append((queued_at, event))
            else:
                completed = self._try_fuse(event, allow_partial_tf=True)
                if not completed:
                    self._publish_unlocalized(event, "depth_invalid")
        self._pending_events = retained

    def _try_fuse(
        self, event: dict[str, Any], *, allow_partial_tf: bool = False
    ) -> bool:
        stamp_ns = stamp_to_ns(event.get("source_stamp"))
        if stamp_ns is None or self._camera_info is None:
            return False
        depth_frame, sync_delta_ns = self._nearest_depth(stamp_ns)
        if depth_frame is None:
            return False

        source_frame = str(depth_frame.frame_id or event.get("source_frame_id") or "")
        if not source_frame:
            return False
        base_transform_source = "tf"
        try:
            base_transform = self._lookup_transform(
                self._base_frame, source_frame, stamp_ns
            ).transform
        except TransformException:
            if not self._allow_urdf_camera_fallback:
                return False
            base_transform = self._urdf_base_transform
            base_transform_source = "urdf_fallback"

        map_from_base = None
        odom_from_base = None
        try:
            map_from_base = self._lookup_transform(
                self._map_frame, self._base_frame, stamp_ns
            ).transform
        except TransformException:
            try:
                map_from_footprint = self._lookup_transform(
                    self._map_frame, self._base_footprint_frame, stamp_ns
                ).transform
                map_from_base = compose_transforms(
                    map_from_footprint, self._footprint_from_base
                )
            except TransformException:
                pass
        try:
            odom_from_base = self._lookup_transform(
                self._odom_frame, self._base_frame, stamp_ns
            ).transform
        except TransformException:
            try:
                odom_from_footprint = self._lookup_transform(
                    self._odom_frame, self._base_footprint_frame, stamp_ns
                ).transform
                odom_from_base = compose_transforms(
                    odom_from_footprint, self._footprint_from_base
                )
            except TransformException:
                pass
        if odom_from_base is None:
            odom_from_base = self._nearest_odom_transform(stamp_ns)
        map_transform_source = "tf_exact" if map_from_base is not None else None
        if map_from_base is None and odom_from_base is not None:
            # RTAB-Map commonly publishes map->odom more slowly than camera frames.
            # Combine its latest correction with timestamp-nearest odometry instead
            # of rejecting an otherwise valid pose due to forward extrapolation.
            try:
                map_from_odom = self._lookup_transform(
                    self._map_frame, self._odom_frame, stamp_ns
                ).transform
                map_transform_source = "map_odom_exact_plus_odom"
            except TransformException:
                try:
                    map_from_odom = self._lookup_latest_transform(
                        self._map_frame, self._odom_frame
                    ).transform
                    map_transform_source = "map_odom_latest_plus_odom"
                except TransformException:
                    map_from_odom = None
            if map_from_odom is not None:
                map_from_base = compose_transforms(map_from_odom, odom_from_base)
        if not allow_partial_tf and (odom_from_base is None or map_from_base is None):
            return False

        persons = [
            self._fuse_person(
                observation,
                depth_image=depth_frame.image,
                unit_scale=depth_frame.unit_scale,
                camera_matrix=self._camera_info.k,
                base_transform=base_transform,
                odom_from_base=odom_from_base,
                map_from_base=map_from_base,
            )
            for observation in event.get("pose_observations_2d", [])
        ]
        output = {
            "stamp_ns": stamp_ns,
            "source_stamp": event.get("source_stamp"),
            "source_frame_id": source_frame,
            "base_frame_id": self._base_frame,
            "map_frame_id": self._map_frame,
            "odom_frame_id": self._odom_frame,
            "base_transform_valid": True,
            "base_transform_source": base_transform_source,
            "odom_transform_valid": odom_from_base is not None,
            "map_transform_valid": map_from_base is not None,
            "map_transform_source": map_transform_source,
            "observer_position_odom": (
                [
                    float(odom_from_base.translation.x),
                    float(odom_from_base.translation.y),
                    float(odom_from_base.translation.z),
                ]
                if odom_from_base is not None
                else None
            ),
            "observer_position_map": (
                [
                    float(map_from_base.translation.x),
                    float(map_from_base.translation.y),
                    float(map_from_base.translation.z),
                ]
                if map_from_base is not None
                else None
            ),
            "depth_stamp_ns": depth_frame.stamp_ns,
            "rgb_depth_delta_ms": float(sync_delta_ns or 0) / 1e6,
            "camera_info_frame_id": self._camera_info.header.frame_id,
            "camera_intrinsics": {
                "fx": float(self._camera_info.k[0]),
                "fy": float(self._camera_info.k[4]),
                "cx": float(self._camera_info.k[2]),
                "cy": float(self._camera_info.k[5]),
            },
            "person_count": len(persons),
            "persons": persons,
            "source_perception": {
                "frame_sequence_id": event.get("frame_sequence_id"),
                "stable_fall_detected": bool(event.get("stable_fall_detected")),
                "seq_stable_fall_detected": bool(
                    event.get("seq_stable_fall_detected")
                ),
            },
        }
        self._publish_json(self._pose_publisher, output)
        self._publish_semantic_events(event, persons, stamp_ns, map_from_base)
        return True

    def _fuse_person(
        self,
        observation: dict[str, Any],
        *,
        depth_image: np.ndarray,
        unit_scale: float,
        camera_matrix: Any,
        base_transform: Any,
        odom_from_base: Any | None,
        map_from_base: Any | None,
    ) -> dict[str, Any]:
        joints: list[dict[str, Any]] = []
        for keypoint in observation.get("keypoints", []):
            joint = {
                "index": int(keypoint.get("index", -1)),
                "name": str(keypoint.get("name", "")),
                "pixel": [float(keypoint.get("u", 0.0)), float(keypoint.get("v", 0.0))],
                "confidence": float(keypoint.get("confidence", 0.0)),
                "valid": False,
                "reason": "keypoint_confidence_low",
                "depth_m": None,
                "depth_sample_count": 0,
                "position_camera": None,
                "position_base": None,
                "position_odom": None,
                "position_map": None,
                "position_std_m": None,
            }
            if joint["confidence"] < self._keypoint_confidence:
                joints.append(joint)
                continue
            depth = sample_depth(
                depth_image,
                u=joint["pixel"][0],
                v=joint["pixel"][1],
                unit_scale=unit_scale,
                radius_px=self._depth_window_radius_px,
                min_samples=self._depth_window_min_samples,
                min_depth_m=self._depth_min_m,
                max_depth_m=self._depth_max_m,
                mad_scale=self._depth_mad_scale,
            )
            joint["depth_sample_count"] = depth.sample_count
            joint["reason"] = depth.reason
            if not depth.valid or depth.depth_m is None:
                joints.append(joint)
                continue
            point_camera = backproject_pixel(
                u=joint["pixel"][0],
                v=joint["pixel"][1],
                depth_m=depth.depth_m,
                camera_matrix=camera_matrix,
            )
            point_base = transform_point(point_camera, base_transform)
            joint.update(
                {
                    "valid": True,
                    "reason": "ok",
                    "depth_m": depth.depth_m,
                    "position_camera": point_camera,
                    "position_base": point_base,
                    "position_odom": (
                        transform_point(point_base, odom_from_base)
                        if odom_from_base is not None
                        else None
                    ),
                    "position_map": (
                        transform_point(point_base, map_from_base)
                        if map_from_base is not None
                        else None
                    ),
                    "position_std_m": depth.std_m,
                }
            )
            joints.append(joint)

        center_camera, center_indices, center_reason = robust_center(
            joints,
            field="position_camera",
            stable_indices=self._stable_keypoints,
            min_stable=self._min_valid_stable,
        )
        center_base, _, _ = robust_center(
            joints,
            field="position_base",
            stable_indices=center_indices,
            min_stable=1,
        )
        center_odom, _, _ = robust_center(
            joints,
            field="position_odom",
            stable_indices=center_indices,
            min_stable=1,
        )
        center_map, _, _ = robust_center(
            joints,
            field="position_map",
            stable_indices=center_indices,
            min_stable=1,
        )
        valid_joints = [joint for joint in joints if joint["valid"]]
        std_values = [
            float(joint["position_std_m"])
            for joint in valid_joints
            if joint["position_std_m"] is not None
        ]
        center_std_m = max(0.05, float(np.median(std_values))) if std_values else 0.50
        distance_3d = None
        distance_planar = None
        if center_base is not None:
            distance_3d = math.sqrt(sum(float(value) ** 2 for value in center_base))
            distance_planar = math.hypot(float(center_base[0]), float(center_base[1]))
        pose_valid_base = center_base is not None
        pose_valid_map = center_map is not None
        quality = min(
            1.0,
            (len(valid_joints) / 17.0)
            * max(0.0, min(1.0, float(observation.get("bbox_confidence", 0.0)))),
        )
        return {
            "detection_index": int(observation.get("detection_index", 0)),
            "track_id": observation.get("track_id"),
            "bbox_xyxy": observation.get("bbox_xyxy"),
            "bbox_confidence": float(observation.get("bbox_confidence", 0.0)),
            "visible_keypoint_count": int(
                observation.get("visible_keypoint_count", 0)
            ),
            "valid_3d_keypoint_count": len(valid_joints),
            "observation_quality": quality,
            "pose_valid": pose_valid_map,
            "pose_valid_base": pose_valid_base,
            "pose_valid_map": pose_valid_map,
            "pose_reason": (
                center_reason
                if pose_valid_map
                else "tf_unavailable"
                if pose_valid_base
                else "depth_invalid"
            ),
            "center_joint_indices": center_indices,
            "center_camera": center_camera,
            "center_base": center_base,
            "center_odom": center_odom,
            "center_map": center_map,
            "center_std_m": center_std_m,
            "distance_3d_to_robot_m": distance_3d,
            "distance_planar_to_robot_m": distance_planar,
            "joints": joints,
        }

    @staticmethod
    def _selected_fall_track(event: dict[str, Any]) -> Any:
        for key in ("seq_fall_top_candidate", "fall_top_candidate"):
            candidate = event.get(key)
            if isinstance(candidate, dict) and candidate.get("track_id") is not None:
                return candidate.get("track_id")
        return event.get("seq_track_id")

    def _publish_semantic_events(
        self,
        event: dict[str, Any],
        persons: list[dict[str, Any]],
        stamp_ns: int,
        observer_transform: Any | None,
    ) -> None:
        stable_fall = bool(
            event.get("seq_stable_fall_detected") or event.get("stable_fall_detected")
        )
        raw_fall = bool(
            event.get("seq_raw_fall_detected") or event.get("raw_fall_detected")
        )
        if not stable_fall and not (raw_fall and self._publish_semantic_uncertain):
            return
        selected_track = self._selected_fall_track(event)
        selected = None
        if selected_track is not None:
            selected = next(
                (
                    person
                    for person in persons
                    if str(person.get("track_id")) == str(selected_track)
                ),
                None,
            )
        if selected is None and persons:
            selected = max(persons, key=lambda person: person["bbox_confidence"])
        if selected is None:
            return

        pose_valid = bool(selected["pose_valid"])
        semantic_state = (
            "event_confirmed"
            if stable_fall and pose_valid
            else "perception_degraded"
            if stable_fall
            else "event_uncertain"
        )
        reason_code = "ok" if pose_valid else "depth_invalid"
        self._perception_revision += 1
        track_label = str(
            selected.get("track_id")
            if selected.get("track_id") is not None
            else f"det-{selected['detection_index']}"
        )
        confidence = max(
            float(event.get("seq_probability_calibrated", 0.0) or 0.0),
            float(event.get("fall_max_score", 0.0) or 0.0),
        )
        observer_pose = None
        if observer_transform is not None:
            observer_pose = [
                float(observer_transform.translation.x),
                float(observer_transform.translation.y),
                quaternion_yaw(observer_transform.rotation),
            ]
        payload = {
            "stamp_ns": stamp_ns,
            "frame_id": self._map_frame,
            "event_id": f"fall-{track_label}",
            "track_id": track_label,
            "event_type": "fall",
            "semantic_state": semantic_state,
            "confidence": max(0.0, min(1.0, confidence)),
            "observation_quality": float(selected["observation_quality"]),
            "pose_valid": pose_valid,
            "position": selected["center_map"] if pose_valid else None,
            "covariance": (
                point_covariance_6x6(float(selected["center_std_m"]))
                if pose_valid
                else None
            ),
            "observer_robot_id": self._observer_robot_id,
            "observer_pose_map": observer_pose,
            "observation_distance_m": (
                float(selected["distance_planar_to_robot_m"])
                if pose_valid
                else None
            ),
            "region_id": "unassigned",
            "region_probability": 0.0,
            "valid_until_ns": stamp_ns + self._event_pose_expire_ns,
            "perception_revision": self._perception_revision,
            "reason_code": reason_code,
        }
        self._publish_json(self._semantic_publisher, payload)

    def _publish_unlocalized(self, event: dict[str, Any], reason: str) -> None:
        stamp_ns = stamp_to_ns(event.get("source_stamp"))
        payload = {
            "stamp_ns": stamp_ns,
            "source_stamp": event.get("source_stamp"),
            "source_frame_id": event.get("source_frame_id"),
            "base_frame_id": self._base_frame,
            "map_frame_id": self._map_frame,
            "person_count": len(event.get("pose_observations_2d", [])),
            "persons": [],
            "pose_valid": False,
            "reason_code": reason,
        }
        self._publish_json(self._pose_publisher, payload)


def main(args=None) -> None:
    rclpy.init(args=args)
    node: Pose3DFusionNode | None = None
    try:
        node = Pose3DFusionNode()
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        if node is not None:
            node.destroy_node()
        time.sleep(0.05)
        if rclpy.ok():
            rclpy.shutdown()
