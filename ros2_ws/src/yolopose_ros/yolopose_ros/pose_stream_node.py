from __future__ import annotations

import json
import os
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import rclpy
from rclpy.node import Node
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
        self.declare_parameter("event_topic", "/kaiti/perception/events")
        self.declare_parameter("input_mode", "mock")
        self.declare_parameter("mock_publish_period_sec", 1.0)
        self.declare_parameter("heartbeat_interval_sec", 2.0)
        self.declare_parameter("video_file_path", "")
        self.declare_parameter("camera_device", "")
        self.declare_parameter("camera_index", -1)

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
        if self._input_mode not in {"mock", "video_file", "camera"}:
            self.get_logger().warning(
                "Unsupported input_mode=%s, fallback to mock" % self._input_mode
            )
            self._input_mode = "mock"

        self.publisher = self.create_publisher(String, self._event_topic, 10)

        self._frame_id = 0
        self._pipeline_state = "starting"
        self._status_reason = "startup"
        self._resolved_source: str | int | None = None
        self._runner_thread: threading.Thread | None = None
        self._status_timer = None

        self.get_logger().info(
            "Pose stream starting: input_mode=%s event_topic=%s"
            % (self._input_mode, self._event_topic)
        )

        if self._input_mode == "mock":
            self._pipeline_state = "mock_running"
            self._status_reason = "mock_mode"
            self.create_timer(self._mock_publish_period_sec, self._publish_mock_event)
            return

        self._status_timer = self.create_timer(
            self._heartbeat_interval_sec, self._publish_terminal_heartbeat
        )
        self._start_runner_thread()

    def _timestamp(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _publish_payload(self, payload: dict[str, Any]) -> None:
        msg = String()
        msg.data = json.dumps(payload, ensure_ascii=True)
        self.publisher.publish(msg)

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
                return self._camera_index, None
            return None, "camera_source_not_set"

        return None, "unsupported_input_mode"

    def _load_runner(self, source: str | int) -> Any:
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
        cfg["source"] = source

        return PoseRunner(
            cfg=cfg,
            project_root=self._project_root,
            event_callback=self._publish_runner_event,
        )

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
