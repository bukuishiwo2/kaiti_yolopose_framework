from __future__ import annotations

import json
import os
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image
from std_msgs.msg import String


TERMINAL_PIPELINE_STATES = {"completed", "error", "unavailable"}


def _default_project_root() -> str:
    env_value = os.environ.get("KAITI_PROJECT_ROOT", "").strip()
    if env_value:
        return env_value
    return str(Path(__file__).resolve().parents[4])


class PoseStreamNode(Node):
    """Bridge node with minimal multi-input support for the ROS2 skeleton."""

    def __init__(self) -> None:
        super().__init__("pose_stream_node")

        self.declare_parameter(
            "project_root",
            _default_project_root(),
        )
        self.declare_parameter("infer_config", "configs/infer_pose_stream.yaml")
        self.declare_parameter("event_topic", "/perception/events")
        self.declare_parameter("input_mode", "mock")
        self.declare_parameter("mock_publish_period_sec", 1.0)
        self.declare_parameter("heartbeat_interval_sec", 2.0)
        self.declare_parameter("video_file_path", "")
        self.declare_parameter("camera_device", "")
        self.declare_parameter("camera_index", -1)
        self.declare_parameter("ros_image_topic", "/camera/image_raw")
        self.declare_parameter("ros_image_timeout_sec", 3.0)
        self.declare_parameter("visualization_enabled", False)
        self.declare_parameter("visualization_topic", "/perception/debug_image")
        self.declare_parameter("supervisor_status_topic", "/system/supervisor/status")

        raw_project_root = str(self.get_parameter("project_root").value).strip()
        self._project_root = Path(raw_project_root or _default_project_root()).resolve()
        self._infer_config = str(self.get_parameter("infer_config").value)
        self._event_topic = str(self.get_parameter("event_topic").value)
        self._input_mode = str(self.get_parameter("input_mode").value).strip().lower()
        self._mock_publish_period_sec = float(self.get_parameter("mock_publish_period_sec").value)
        self._heartbeat_interval_sec = float(self.get_parameter("heartbeat_interval_sec").value)
        self._video_file_path = str(self.get_parameter("video_file_path").value).strip()
        self._camera_device = str(self.get_parameter("camera_device").value).strip()
        self._camera_index = int(self.get_parameter("camera_index").value)
        self._ros_image_topic = str(self.get_parameter("ros_image_topic").value).strip()
        self._ros_image_timeout_sec = float(self.get_parameter("ros_image_timeout_sec").value)
        self._visualization_enabled = bool(self.get_parameter("visualization_enabled").value)
        self._visualization_topic = str(self.get_parameter("visualization_topic").value).strip()
        self._supervisor_status_topic = str(self.get_parameter("supervisor_status_topic").value).strip()
        if self._input_mode not in {"mock", "video_file", "camera", "ros_image"}:
            self.get_logger().warning(
                "Unsupported input_mode=%s, fallback to mock" % self._input_mode
            )
            self._input_mode = "mock"

        self.publisher = self.create_publisher(String, self._event_topic, 10)
        self._visualization_publisher = None
        if self._visualization_enabled:
            self._visualization_publisher = self.create_publisher(
                Image, self._visualization_topic, 10
            )
            self.create_subscription(
                String,
                self._supervisor_status_topic,
                self._on_supervisor_status,
                10,
            )

        self._frame_id = 0
        self._pipeline_state = "starting"
        self._status_reason = "startup"
        self._resolved_source: str | int | None = None
        self._runner: Any | None = None
        self._runner_thread: threading.Thread | None = None
        self._status_timer = None
        self._last_ros_image_monotonic: float | None = None
        self._latest_supervisor_overlay = {
            "planner_action": "-",
            "reason": "-",
        }

        self.get_logger().info(
            "Pose stream starting: input_mode=%s event_topic=%s visualization=%s"
            % (self._input_mode, self._event_topic, self._visualization_enabled)
        )

        if self._input_mode == "mock":
            self._pipeline_state = "mock_running"
            self._status_reason = "mock_mode"
            self.create_timer(self._mock_publish_period_sec, self._publish_mock_event)
            return

        self._status_timer = self.create_timer(self._heartbeat_interval_sec, self._on_status_timer)
        if self._input_mode == "ros_image":
            self._start_ros_image_mode()
            return
        self._start_runner_thread()

    def _timestamp(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _publish_payload(self, payload: dict[str, Any]) -> None:
        msg = String()
        msg.data = json.dumps(payload, ensure_ascii=True)
        self.publisher.publish(msg)

    def _on_supervisor_status(self, msg: String) -> None:
        try:
            payload = json.loads(msg.data)
            if isinstance(payload, dict):
                self._latest_supervisor_overlay = {
                    "planner_action": str(payload.get("planner_action", "-")),
                    "reason": str(payload.get("reason", "-")),
                }
        except json.JSONDecodeError:
            return

    def _publish_mock_event(self) -> None:
        self._frame_id += 1
        self._publish_payload(
            {
                "ts": self._timestamp(),
                "role": "pose_stream_node",
                "event_type": "perception_event",
                "input_mode": "mock",
                "pipeline_state": "mock_running",
                "perception_available": True,
                "reason": "mock_tick",
                "frame_id": self._frame_id,
                "source": "mock://perception",
                "person_count": 0,
                "person_present": False,
                "raw_person_present": False,
                "stable_person_present": False,
                "state_changed": False,
                "raw_fall_detected": False,
                "stable_fall_detected": False,
                "fall_state_changed": False,
                "fall_person_candidates": 0,
                "fall_max_score": 0.0,
                "seq_raw_fall_detected": False,
                "seq_stable_fall_detected": False,
                "seq_fall_state_changed": False,
                "seq_fall_score": 0.0,
            }
        )

    def _publish_terminal_heartbeat(self) -> None:
        if self._pipeline_state not in TERMINAL_PIPELINE_STATES:
            return
        self._publish_payload(
            {
                "ts": self._timestamp(),
                "role": "pose_stream_node",
                "event_type": "perception_status",
                "input_mode": self._input_mode,
                "pipeline_state": self._pipeline_state,
                "perception_available": False,
                "reason": self._status_reason,
                "source": self._resolved_source,
                "person_present": None,
                "stable_person_present": None,
                "stable_fall_detected": False,
                "seq_stable_fall_detected": False,
            }
        )

    def _publish_ros_image_waiting_status(self, reason: str, pipeline_state: str) -> None:
        self._publish_payload(
            {
                "ts": self._timestamp(),
                "role": "pose_stream_node",
                "event_type": "perception_status",
                "input_mode": self._input_mode,
                "pipeline_state": pipeline_state,
                "perception_available": False,
                "reason": reason,
                "source": self._resolved_source,
                "person_present": None,
                "stable_person_present": None,
                "stable_fall_detected": False,
                "seq_stable_fall_detected": False,
            }
        )

    def _resolve_path(self, value: str) -> Path:
        path = Path(value)
        if path.is_absolute():
            return path
        return (self._project_root / path).resolve()

    def _resolve_runtime_source(self) -> tuple[str | int | None, str | None]:
        if self._input_mode == "video_file":
            if not self._video_file_path:
                return None, "video_file_path_not_set"
            video_path = self._resolve_path(self._video_file_path)
            if not video_path.exists():
                return None, "video_file_not_found"
            return str(video_path), None

        if self._input_mode == "camera":
            if self._camera_device:
                camera_path = Path(self._camera_device)
                if not camera_path.exists():
                    return None, "camera_device_not_found"
                return str(camera_path), None
            if self._camera_index >= 0:
                camera_path = Path(f"/dev/video{self._camera_index}")
                if not camera_path.exists():
                    return None, f"camera_index_not_found:{camera_path}"
                return str(camera_path), None
            return None, "camera_source_not_set"

        return None, "unsupported_input_mode"

    def _load_runner(self, source: str | int | None) -> Any:
        project_src = str(self._project_root / "src")
        if project_src not in sys.path:
            sys.path.insert(0, project_src)

        from yolopose.core.config import abs_path, load_yaml  # pylint: disable=import-error
        from yolopose.pipeline.runner import PoseRunner  # pylint: disable=import-error

        cfg_path = self._resolve_path(self._infer_config)
        cfg = load_yaml(cfg_path)
        model_path = cfg.get("model")
        if model_path:
            cfg["model"] = abs_path(self._project_root, model_path)
        cfg["source"] = source if source is not None else "ros_image"

        return PoseRunner(
            cfg=cfg,
            project_root=self._project_root,
            event_callback=self._publish_runner_event,
            visualization_callback=self._publish_visualization_frame,
        )

    def _start_ros_image_mode(self) -> None:
        self._resolved_source = self._ros_image_topic
        try:
            self._runner = self._load_runner(self._ros_image_topic)
        except Exception as exc:  # pylint: disable=broad-except
            self._pipeline_state = "error"
            self._status_reason = f"runner_init_failed:{exc}"
            self.get_logger().error("Pose stream init failed: %s" % exc)
            self._publish_terminal_heartbeat()
            return

        self._pipeline_state = "starting"
        self._status_reason = "waiting_for_ros_image"
        self.create_subscription(Image, self._ros_image_topic, self._on_ros_image, 1)
        self.get_logger().info("Pose stream subscribed to ros_image_topic=%s" % self._ros_image_topic)

    def _start_runner_thread(self) -> None:
        source, reason = self._resolve_runtime_source()
        self._resolved_source = source
        if reason is not None:
            self._pipeline_state = "unavailable"
            self._status_reason = reason
            self.get_logger().warning("Pose stream unavailable: %s" % reason)
            self._publish_terminal_heartbeat()
            return

        try:
            runner = self._load_runner(source)
        except Exception as exc:  # pylint: disable=broad-except
            self._pipeline_state = "error"
            self._status_reason = f"runner_init_failed:{exc}"
            self.get_logger().error("Pose stream init failed: %s" % exc)
            self._publish_terminal_heartbeat()
            return

        self._pipeline_state = "running"
        self._status_reason = "runner_active"
        self._runner_thread = threading.Thread(
            target=self._run_runner, args=(runner,), daemon=True
        )
        self._runner_thread.start()

    @staticmethod
    def _decode_ros_image(msg: Image) -> np.ndarray:
        frame = np.frombuffer(msg.data, dtype=np.uint8)
        if msg.encoding == "bgr8":
            frame = frame.reshape((msg.height, msg.step // 3, 3))
            return frame[:, : msg.width, :].copy()
        if msg.encoding == "rgb8":
            frame = frame.reshape((msg.height, msg.step // 3, 3))
            frame = frame[:, : msg.width, :].copy()
            return cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
        if msg.encoding == "mono8":
            frame = frame.reshape((msg.height, msg.step))
            frame = frame[:, : msg.width].copy()
            return cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
        raise ValueError(f"unsupported_ros_image_encoding:{msg.encoding}")

    def _on_ros_image(self, msg: Image) -> None:
        if self._runner is None:
            return

        try:
            frame = self._decode_ros_image(msg)
            event = self._runner.infer_frame(
                frame,
                source=f"ros://{self._ros_image_topic}",
            )
        except Exception as exc:  # pylint: disable=broad-except
            self._pipeline_state = "error"
            self._status_reason = f"ros_image_infer_failed:{exc}"
            self.get_logger().error("ROS image inference failed: %s" % exc)
            self._publish_terminal_heartbeat()
            return

        self._last_ros_image_monotonic = time.monotonic()
        self._pipeline_state = "running"
        self._status_reason = "ros_image_active"
        event["ros_image_topic"] = self._ros_image_topic
        event["ros_header_frame_id"] = msg.header.frame_id
        self._publish_runner_event(event)

    def _publish_visualization_frame(self, result: Any, record: dict[str, Any]) -> None:
        if self._visualization_publisher is None:
            return

        frame = result.plot(boxes=True, labels=False, probs=False, kpt_line=True)
        boxes = getattr(result, "boxes", None)
        track_ids = getattr(boxes, "id", None) if boxes is not None else None
        xyxy = getattr(boxes, "xyxy", None) if boxes is not None else None
        if track_ids is not None and xyxy is not None:
            for idx in range(min(len(track_ids), len(xyxy))):
                track_value = track_ids[idx]
                if track_value is None:
                    continue
                try:
                    track_id = int(track_value.item())
                except Exception:  # pylint: disable=broad-except
                    continue
                box = xyxy[idx]
                x1 = int(float(box[0]))
                y1 = int(float(box[1]))
                cv2.putText(
                    frame,
                    f"id:{track_id}",
                    (x1, max(18, y1 - 8)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.55,
                    (255, 255, 0),
                    2,
                    cv2.LINE_AA,
                )

        supervisor_action = self._latest_supervisor_overlay["planner_action"]
        supervisor_reason = self._latest_supervisor_overlay["reason"]
        lines = [
            f"frame={record.get('frame_id')} persons={record.get('person_count')}",
            (
                "rule "
                f"score={float(record.get('fall_max_score', 0.0)):.2f} "
                f"raw={int(bool(record.get('raw_fall_detected')))} "
                f"stable={int(bool(record.get('stable_fall_detected')))}"
            ),
            (
                "seq "
                f"score={float(record.get('seq_fall_score', 0.0)):.2f} "
                f"raw={int(bool(record.get('seq_raw_fall_detected')))} "
                f"stable={int(bool(record.get('seq_stable_fall_detected')))}"
            ),
            (
                "supervisor "
                f"action={supervisor_action} "
                f"reason={supervisor_reason}"
            ),
        ]
        for idx, line in enumerate(lines):
            y = 28 + idx * 24
            cv2.putText(
                frame,
                line,
                (12, y),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.62,
                (0, 0, 0),
                4,
                cv2.LINE_AA,
            )
            cv2.putText(
                frame,
                line,
                (12, y),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.62,
                (0, 255, 0) if idx < 3 else (0, 200, 255),
                2,
                cv2.LINE_AA,
            )

        msg = Image()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = "perception_debug_frame"
        msg.height = int(frame.shape[0])
        msg.width = int(frame.shape[1])
        msg.encoding = "bgr8"
        msg.is_bigendian = 0
        msg.step = int(frame.shape[1] * frame.shape[2])
        msg.data = frame.tobytes()
        self._visualization_publisher.publish(msg)

    def _on_status_timer(self) -> None:
        if self._input_mode != "ros_image":
            self._publish_terminal_heartbeat()
            return

        if self._pipeline_state == "error":
            self._publish_terminal_heartbeat()
            return

        if self._last_ros_image_monotonic is None:
            self._publish_ros_image_waiting_status("waiting_for_ros_image", "starting")
            return

        if (time.monotonic() - self._last_ros_image_monotonic) > self._ros_image_timeout_sec:
            self._pipeline_state = "unavailable"
            self._status_reason = "ros_image_timeout"
            self._publish_ros_image_waiting_status("ros_image_timeout", "unavailable")

    def _publish_runner_event(self, event: dict[str, Any]) -> None:
        payload = dict(event)
        payload.setdefault("ts", self._timestamp())
        payload["role"] = "pose_stream_node"
        payload["event_type"] = "perception_event"
        payload["input_mode"] = self._input_mode
        payload["pipeline_state"] = "running"
        payload["perception_available"] = True
        payload["person_present"] = payload.get("stable_person_present")
        payload["source"] = payload.get("source", self._resolved_source)
        self._publish_payload(payload)

    def _run_runner(self, runner: Any) -> None:
        try:
            runner.run()
        except Exception as exc:  # pylint: disable=broad-except
            self._pipeline_state = "error"
            self._status_reason = f"runner_failed:{exc}"
            self.get_logger().error("Pose stream runtime failed: %s" % exc)
            self._publish_terminal_heartbeat()
            return

        self._pipeline_state = "completed"
        self._status_reason = "runner_finished"
        self.get_logger().info("Pose stream runner exited")
        self._publish_terminal_heartbeat()


def main(args=None) -> None:
    rclpy.init(args=args)
    node: PoseStreamNode | None = None
    try:
        node = PoseStreamNode()
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        if node is not None:
            node.destroy_node()
        time.sleep(0.05)
        if rclpy.ok():
            rclpy.shutdown()
