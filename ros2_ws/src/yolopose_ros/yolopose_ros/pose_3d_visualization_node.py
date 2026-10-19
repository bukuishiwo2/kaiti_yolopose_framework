from __future__ import annotations

from collections import deque
from array import array
import json
import math
import time
from typing import Any

import cv2
import numpy as np
import rclpy
from geometry_msgs.msg import Point
from rclpy.node import Node
from rclpy.qos import (
    DurabilityPolicy,
    HistoryPolicy,
    QoSProfile,
    ReliabilityPolicy,
    qos_profile_sensor_data,
)
from sensor_msgs.msg import CompressedImage, Image
from std_msgs.msg import String
from visualization_msgs.msg import Marker, MarkerArray


SKELETON_EDGES = (
    (0, 1), (0, 2), (1, 3), (2, 4),
    (5, 6), (5, 7), (7, 9), (6, 8), (8, 10),
    (5, 11), (6, 12), (11, 12),
    (11, 13), (13, 15), (12, 14), (14, 16),
)


class Pose3DVisualizationNode(Node):
    """Render metric pose labels on the camera image and publish RViz markers."""

    def __init__(self) -> None:
        super().__init__("pose_3d_visualization_node")
        cv2.setNumThreads(1)
        self.declare_parameter("debug_image_topic", "/perception/debug_image")
        self.declare_parameter("debug_compressed_topic", "/perception/debug_image/compressed")
        self.declare_parameter("pose_3d_topic", "/perception/pose_observation_3d")
        self.declare_parameter("annotated_image_topic", "/perception/pose_3d_debug_image")
        self.declare_parameter(
            "annotated_compressed_topic", "/perception/pose_3d_debug_image/compressed"
        )
        self.declare_parameter("marker_topic", "/perception/pose_3d_markers")
        self.declare_parameter("image_cache_size", 6)
        self.declare_parameter("max_observation_age_sec", 1.0)
        self.declare_parameter("image_sync_slop_sec", 0.20)
        self.declare_parameter("jpeg_quality", 85)
        self.declare_parameter("joint_label_mode", "panel")
        self.declare_parameter("max_display_persons", 1)
        self.declare_parameter("marker_hold_sec", 1.2)
        self.declare_parameter("marker_smoothing_alpha", 0.75)
        self.declare_parameter("marker_require_map", True)
        self.declare_parameter("show_track_id", False)

        self._image_cache: deque[tuple[int, Image]] = deque(
            maxlen=int(self.get_parameter("image_cache_size").value)
        )
        self._sync_slop_ns = int(
            float(self.get_parameter("image_sync_slop_sec").value) * 1e9
        )
        self._jpeg_quality = int(self.get_parameter("jpeg_quality").value)
        self._max_display_persons = max(
            1, int(self.get_parameter("max_display_persons").value)
        )
        self._marker_hold_sec = max(
            0.0, float(self.get_parameter("marker_hold_sec").value)
        )
        self._smoothing_alpha = min(
            1.0,
            max(0.0, float(self.get_parameter("marker_smoothing_alpha").value)),
        )
        self._marker_require_map = bool(
            self.get_parameter("marker_require_map").value
        )
        self._show_track_id = bool(self.get_parameter("show_track_id").value)
        self._last_valid_marker_monotonic: float | None = None
        self._markers_visible = False
        self._needs_initial_clear = True
        self._last_image_pose = None
        self._last_annotated_stamp = None
        self._smoothed_points: dict[tuple[int, str], list[float]] = {}
        self._image_publisher = self.create_publisher(
            Image, str(self.get_parameter("annotated_image_topic").value), 5
        )
        self._compressed_publisher = self.create_publisher(
            CompressedImage,
            str(self.get_parameter("annotated_compressed_topic").value),
            qos_profile_sensor_data,
        )
        marker_qos = QoSProfile(
            history=HistoryPolicy.KEEP_LAST,
            depth=1,
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
        )
        self._marker_publisher = self.create_publisher(
            MarkerArray, str(self.get_parameter("marker_topic").value), marker_qos
        )
        self.create_subscription(
            Image,
            str(self.get_parameter("debug_image_topic").value),
            self._on_image,
            5,
        )
        self.create_subscription(
            CompressedImage, str(self.get_parameter("debug_compressed_topic").value),
            self._on_compressed_image,
            QoSProfile(depth=1, reliability=ReliabilityPolicy.BEST_EFFORT),
        )
        self.create_subscription(
            String,
            str(self.get_parameter("pose_3d_topic").value),
            self._on_pose,
            1,
        )
        self.create_timer(0.1, self._expire_stale_markers)
        self.get_logger().info(
            "3D visualization ready: image=%s markers=%s"
            % (
                self.get_parameter("annotated_image_topic").value,
                self.get_parameter("marker_topic").value,
            )
        )

    @staticmethod
    def _stamp_ns(message: Image) -> int:
        return int(message.header.stamp.sec) * 1_000_000_000 + int(
            message.header.stamp.nanosec
        )

    def _on_image(self, message: Image) -> None:
        self._image_cache.append((self._stamp_ns(message), message))
        if self._last_image_pose is not None:
            self._publish_annotated_image(self._last_image_pose)

    def _on_compressed_image(self, message: CompressedImage) -> None:
        frame = cv2.imdecode(np.frombuffer(message.data, np.uint8), cv2.IMREAD_COLOR)
        if frame is None:
            return
        image = Image()
        image.header = message.header
        image.height, image.width = frame.shape[:2]
        image.encoding, image.step = 'bgr8', int(frame.shape[1] * 3)
        # ROS byte-array assignment avoids validating millions of Python ints.
        image.data = array('B', frame.tobytes())
        self._on_image(image)

    def _on_pose(self, message: String) -> None:
        try:
            payload = json.loads(message.data)
        except json.JSONDecodeError:
            return
        if not isinstance(payload, dict):
            return
        age = (self.get_clock().now().nanoseconds - int(payload.get("stamp_ns", 0))) / 1e9
        if not -0.15 <= age <= float(self.get_parameter("max_observation_age_sec").value):
            return
        self._last_image_pose = payload
        self._publish_markers(payload)
        self._publish_annotated_image(payload)

    def _nearest_image(self, stamp_ns: int) -> Image | None:
        if not self._image_cache:
            return None
        image_stamp, message = min(
            self._image_cache, key=lambda item: abs(item[0] - stamp_ns)
        )
        if abs(image_stamp - stamp_ns) > self._sync_slop_ns:
            return None
        return message

    @staticmethod
    def _decode_bgr(message: Image) -> np.ndarray | None:
        if message.encoding not in {"bgr8", "rgb8"}:
            return None
        expected = int(message.height) * int(message.step)
        data = np.frombuffer(message.data, dtype=np.uint8)
        if data.size < expected or int(message.step) < int(message.width) * 3:
            return None
        frame = data[:expected].reshape((message.height, message.step))
        frame = frame[:, : message.width * 3].reshape(
            (message.height, message.width, 3)
        ).copy()
        if message.encoding == "rgb8":
            frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
        return frame

    @staticmethod
    def _outlined_text(
        frame: np.ndarray,
        text: str,
        origin: tuple[int, int],
        color: tuple[int, int, int],
        scale: float = 0.42,
    ) -> None:
        cv2.putText(
            frame, text, origin, cv2.FONT_HERSHEY_SIMPLEX, scale,
            (0, 0, 0), 3, cv2.LINE_AA,
        )
        cv2.putText(
            frame, text, origin, cv2.FONT_HERSHEY_SIMPLEX, scale,
            color, 1, cv2.LINE_AA,
        )

    def _publish_annotated_image(self, payload: dict[str, Any]) -> None:
        stamp_ns = int(payload.get("stamp_ns") or 0)
        if stamp_ns == self._last_annotated_stamp:
            return
        source = self._nearest_image(stamp_ns)
        if source is None:
            return
        frame = self._decode_bgr(source)
        if frame is None:
            return

        transform_status = (
            "map" if payload.get("map_transform_valid")
            else "odom" if payload.get("odom_transform_valid")
            else "base" if payload.get("base_transform_valid")
            else "unavailable"
        )
        sync_value = payload.get("rgb_depth_delta_ms")
        sync_label = f"{float(sync_value):.1f} ms" if sync_value is not None else "N/A"
        age_ms = (self.get_clock().now().nanoseconds - stamp_ns) / 1e6
        clock_label = time.strftime('%H:%M:%S', time.localtime(stamp_ns / 1e9))
        self._outlined_text(
            frame,
            f"3D={transform_status} dt={sync_label} source={clock_label} age={age_ms:.0f}ms",
            (12, frame.shape[0] - 18),
            (50, 255, 255),
            0.55,
        )
        for person_index, person in enumerate(payload.get("persons", [])):
            distance = person.get("distance_3d_to_robot_m")
            planar = person.get("distance_planar_to_robot_m")
            center_base = person.get("center_base")
            track_id = person.get("track_id")
            title = (
                f"id={track_id if track_id is not None else person_index} "
                f"D3={float(distance):.2f}m Dxy={float(planar):.2f}m"
                if distance is not None and planar is not None
                else f"id={track_id if track_id is not None else person_index} 3D invalid"
            )
            if center_base is not None:
                title += " base=(%.2f,%.2f,%.2f)m" % tuple(center_base)
            box = person.get("bbox_xyxy") or [12, 80 + person_index * 26, 0, 0]
            self._outlined_text(
                frame, title, (max(5, int(box[0])), max(20, int(box[1]) - 10)),
                (0, 255, 255), 0.52,
            )
            valid_joints = [joint for joint in person.get("joints", [])
                            if joint.get("valid") and joint.get("position_base") is not None]
            panel_mode = str(self.get_parameter("joint_label_mode").value) == 'panel'
            if panel_mode and person_index == 0 and valid_joints:
                panel_x = max(5, frame.shape[1] - 280)
                panel_bottom = min(frame.shape[0] - 45, 40 + 22 * len(valid_joints))
                cv2.rectangle(frame, (panel_x - 5, 5),
                              (frame.shape[1] - 5, panel_bottom), (20, 20, 20), -1)
                self._outlined_text(frame, 'Joint range from base_link', (panel_x, 25),
                                    (255, 255, 255), 0.5)
            for joint_row, joint in enumerate(valid_joints):
                if not joint.get("valid") or joint.get("position_base") is None:
                    continue
                pixel = joint.get("pixel") or [0, 0]
                point = joint["position_base"]
                joint_distance = math.sqrt(sum(float(value) ** 2 for value in point))
                u, v = int(round(float(pixel[0]))), int(round(float(pixel[1])))
                label = f"{joint.get('name', joint.get('index'))}:{joint_distance:.2f}m"
                if panel_mode and person_index == 0:
                    self._outlined_text(frame, label, (panel_x, 48 + joint_row * 22),
                                        (255, 255, 0), 0.45)
                else:
                    self._outlined_text(frame, label, (u + 4, v - 4), (255, 255, 0))

        output = Image()
        output.header = source.header
        output.height, output.width = frame.shape[:2]
        output.encoding = "bgr8"
        output.is_bigendian = 0
        output.step = int(output.width * 3)
        if self._image_publisher.get_subscription_count():
            output.data = array('B', frame.tobytes())
            self._image_publisher.publish(output)
        self._last_annotated_stamp = stamp_ns

        ok, encoded = cv2.imencode(
            ".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, self._jpeg_quality]
        )
        if ok:
            compressed = CompressedImage()
            compressed.header = source.header
            compressed.format = "jpeg"
            compressed.data = encoded.tobytes()
            self._compressed_publisher.publish(compressed)

    @staticmethod
    def _point(values: list[float]) -> Point:
        point = Point()
        point.x, point.y, point.z = (float(value) for value in values)
        return point

    @staticmethod
    def _base_marker(frame_id: str, stamp: Any, marker_id: int, marker_type: int) -> Marker:
        marker = Marker()
        marker.header.frame_id = frame_id
        marker.header.stamp = stamp
        marker.ns = "human_pose_3d"
        marker.id = marker_id
        marker.type = marker_type
        marker.action = Marker.ADD
        marker.pose.orientation.w = 1.0
        marker.color.a = 1.0
        return marker

    def _clear_markers(self, frame_id: str = "map") -> None:
        clear = Marker()
        clear.header.frame_id = frame_id
        clear.header.stamp = self.get_clock().now().to_msg()
        clear.action = Marker.DELETEALL
        markers = MarkerArray()
        markers.markers.append(clear)
        self._marker_publisher.publish(markers)
        self._markers_visible = False
        self._needs_initial_clear = False
        self._smoothed_points.clear()

    def _expire_stale_markers(self) -> None:
        if not self._markers_visible or self._last_valid_marker_monotonic is None:
            return
        if (
            time.monotonic() - self._last_valid_marker_monotonic
            >= self._marker_hold_sec
        ):
            self._clear_markers()

    def _smooth_point(
        self, slot: int, key: str, values: list[float]
    ) -> list[float]:
        current = [float(value) for value in values]
        cache_key = (slot, key)
        previous = self._smoothed_points.get(cache_key)
        if previous is None or self._smoothing_alpha >= 1.0:
            smoothed = current
        else:
            alpha = self._smoothing_alpha
            smoothed = [
                alpha * value + (1.0 - alpha) * old
                for value, old in zip(current, previous)
            ]
        self._smoothed_points[cache_key] = smoothed
        return smoothed

    def _publish_markers(self, payload: dict[str, Any]) -> None:
        source_stamp = payload.get("source_stamp") or {}
        stamp = self.get_clock().now().to_msg()
        if isinstance(source_stamp, dict):
            stamp.sec = int(source_stamp.get("sec", 0))
            stamp.nanosec = int(source_stamp.get("nanosec", 0))
        if payload.get("map_transform_valid"):
            frame_id, field, observer = (
                str(payload.get("map_frame_id") or "map"),
                "position_map",
                payload.get("observer_position_map"),
            )
        elif self._marker_require_map:
            return
        elif payload.get("odom_transform_valid"):
            frame_id, field, observer = (
                str(payload.get("odom_frame_id") or "odom"),
                "position_odom",
                payload.get("observer_position_odom"),
            )
        else:
            frame_id, field, observer = (
                str(payload.get("base_frame_id") or "base_link"),
                "position_base",
                [0.0, 0.0, 0.0],
            )

        center_field = {
            "position_map": "center_map",
            "position_odom": "center_odom",
            "position_base": "center_base",
        }[field]
        persons = [
            person
            for person in payload.get("persons", [])
            if person.get(center_field) is not None
        ]
        persons.sort(
            key=lambda person: (
                float(person.get("observation_quality") or 0.0),
                float(person.get("bbox_confidence") or 0.0),
                int(person.get("valid_3d_keypoint_count") or 0),
            ),
            reverse=True,
        )
        persons = persons[: self._max_display_persons]
        if not persons:
            return

        markers = MarkerArray()
        if self._needs_initial_clear:
            clear = Marker()
            clear.header.frame_id = frame_id
            clear.header.stamp = stamp
            clear.action = Marker.DELETEALL
            markers.markers.append(clear)
            self._needs_initial_clear = False
        marker_id = 1
        active_smoothing_keys: set[tuple[int, str]] = set()
        for person_index, person in enumerate(persons):
            joints_by_index = {
                int(joint["index"]): joint
                for joint in person.get("joints", [])
                if joint.get("valid") and joint.get(field) is not None
            }
            spheres = self._base_marker(frame_id, stamp, marker_id, Marker.SPHERE_LIST)
            marker_id += 1
            spheres.scale.x = spheres.scale.y = spheres.scale.z = 0.09
            spheres.color.r, spheres.color.g, spheres.color.b = 0.1, 0.9, 0.2
            smoothed_joints = {}
            for joint_index, joint in joints_by_index.items():
                smooth_key = f"joint_{joint_index}"
                smoothed_joints[joint_index] = self._smooth_point(
                    person_index, smooth_key, joint[field]
                )
                active_smoothing_keys.add((person_index, smooth_key))
            spheres.points = [
                self._point(point) for point in smoothed_joints.values()
            ]
            markers.markers.append(spheres)

            bones = self._base_marker(frame_id, stamp, marker_id, Marker.LINE_LIST)
            marker_id += 1
            bones.scale.x = 0.045
            bones.color.r, bones.color.g, bones.color.b = 0.1, 0.65, 1.0
            for start, end in SKELETON_EDGES:
                if start in smoothed_joints and end in smoothed_joints:
                    bones.points.extend(
                        [
                            self._point(smoothed_joints[start]),
                            self._point(smoothed_joints[end]),
                        ]
                    )
            markers.markers.append(bones)

            center = self._smooth_point(
                person_index, "center", person[center_field]
            )
            active_smoothing_keys.add((person_index, "center"))
            center_marker = self._base_marker(frame_id, stamp, marker_id, Marker.SPHERE)
            marker_id += 1
            center_marker.pose.position = self._point(center)
            center_marker.scale.x = center_marker.scale.y = center_marker.scale.z = 0.18
            center_marker.color.r, center_marker.color.g, center_marker.color.b = 1.0, 0.2, 0.1
            markers.markers.append(center_marker)

            label = self._base_marker(frame_id, stamp, marker_id, Marker.TEXT_VIEW_FACING)
            marker_id += 1
            label.pose.position = self._point([center[0], center[1], center[2] + 0.30])
            label.scale.z = 0.22
            label.color.r = label.color.g = label.color.b = 1.0
            track_suffix = (
                " id=%s" % person.get("track_id")
                if self._show_track_id and person.get("track_id") is not None
                else ""
            )
            label.text = "Human%s  D=%.2f m" % (
                track_suffix,
                float(person.get("distance_3d_to_robot_m") or 0.0),
            )
            label.text += "\nsource %s age %.0fms" % (
                time.strftime('%H:%M:%S', time.localtime(int(payload['stamp_ns']) / 1e9)),
                (self.get_clock().now().nanoseconds - int(payload['stamp_ns'])) / 1e6,
            )
            markers.markers.append(label)

            if observer is not None:
                ray = self._base_marker(frame_id, stamp, marker_id, Marker.LINE_LIST)
                marker_id += 1
                ray.scale.x = 0.025
                ray.color.r, ray.color.g, ray.color.b = 1.0, 0.7, 0.0
                ray.points = [self._point(observer), self._point(center)]
                markers.markers.append(ray)
        self._smoothed_points = {
            key: value
            for key, value in self._smoothed_points.items()
            if key in active_smoothing_keys
        }
        self._marker_publisher.publish(markers)
        self._last_valid_marker_monotonic = time.monotonic()
        self._markers_visible = True


def main(args=None) -> None:
    rclpy.init(args=args)
    node = Pose3DVisualizationNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
