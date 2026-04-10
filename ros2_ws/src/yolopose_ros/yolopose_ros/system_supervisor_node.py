from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Any

import rclpy
from rclpy.node import Node
from std_msgs.msg import String


TERMINAL_PERCEPTION_STATES = {"completed", "error", "unavailable"}


class SystemSupervisorNode(Node):
    """Minimal supervisor that keeps a stable status/request output boundary."""

    def __init__(self) -> None:
        super().__init__("system_supervisor_node")

        self.declare_parameter("perception_event_topic", "/kaiti/perception/events")
        self.declare_parameter("supervisor_status_topic", "/kaiti/system/supervisor/status")
        self.declare_parameter("planner_request_topic", "/kaiti/task_planner/request")
        self.declare_parameter("planner_mode", "plansys2_placeholder")
        self.declare_parameter("perception_timeout_sec", 3.0)
        self.declare_parameter("status_publish_period_sec", 1.0)

        self._perception_event_topic = str(self.get_parameter("perception_event_topic").value)
        self._status_topic = str(self.get_parameter("supervisor_status_topic").value)
        self._planner_request_topic = str(self.get_parameter("planner_request_topic").value)
        self._planner_mode = str(self.get_parameter("planner_mode").value)
        self._perception_timeout_sec = float(self.get_parameter("perception_timeout_sec").value)
        self._status_publish_period_sec = float(self.get_parameter("status_publish_period_sec").value)

        self._status_pub = self.create_publisher(String, self._status_topic, 10)
        self._planner_request_pub = self.create_publisher(String, self._planner_request_topic, 10)
        self._event_sub = self.create_subscription(
            String, self._perception_event_topic, self._on_event, 10
        )
        self._monitor_timer = self.create_timer(
            self._status_publish_period_sec, self._on_monitor_timer
        )

        self._last_event_monotonic: float | None = None
        self._last_status_key: tuple[str, str] | None = None

        self.get_logger().info(
            "Supervisor ready: perception_topic=%s status_topic=%s planner_topic=%s planner_mode=%s"
            % (
                self._perception_event_topic,
                self._status_topic,
                self._planner_request_topic,
                self._planner_mode,
            )
        )

    @staticmethod
    def _timestamp() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _parse_payload(payload: str) -> dict[str, Any]:
        try:
            data = json.loads(payload)
            if isinstance(data, dict):
                return data
            return {"raw": data}
        except json.JSONDecodeError:
            return {"raw": payload}

    def _build_status(self, event: dict[str, Any]) -> dict[str, Any]:
        fall_flag = bool(event.get("stable_fall_detected") or event.get("seq_stable_fall_detected"))
        person_present = event.get("person_present")
        if person_present is None:
            person_present = event.get("stable_person_present")

        perception_available = event.get("perception_available")
        pipeline_state = str(event.get("pipeline_state", "")).strip().lower()
        reason = str(event.get("reason", "")).strip()

        if perception_available is False or pipeline_state in TERMINAL_PERCEPTION_STATES:
            planner_action = "hold"
            supervisor_state = "degraded"
            if not reason:
                reason = f"perception_{pipeline_state or 'unavailable'}"
        elif fall_flag:
            planner_action = "trigger_safe_mode"
            supervisor_state = "alert"
            reason = "fall_detected"
        elif person_present is False:
            planner_action = "wait_for_update"
            supervisor_state = "monitoring"
            reason = "no_person_present"
        else:
            planner_action = "monitor"
            supervisor_state = "monitoring"
            if not reason:
                reason = "stable"

        return {
            "ts": self._timestamp(),
            "role": "system_supervisor",
            "supervisor_state": supervisor_state,
            "planner_mode": self._planner_mode,
            "planner_request_topic": self._planner_request_topic,
            "planner_action": planner_action,
            "reason": reason,
            "source_event": event,
        }

    def _build_planner_request(self, status: dict[str, Any]) -> dict[str, Any]:
        return {
            "ts": status["ts"],
            "role": "system_supervisor",
            "planner_mode": status["planner_mode"],
            "requested_action": status["planner_action"],
            "reason": status["reason"],
        }

    def _publish_json(self, publisher, payload: dict[str, Any]) -> None:
        msg = String()
        msg.data = json.dumps(payload, ensure_ascii=True)
        publisher.publish(msg)

    def _publish_status(self, event: dict[str, Any]) -> None:
        status = self._build_status(event)
        self._publish_json(self._status_pub, status)
        self._publish_json(self._planner_request_pub, self._build_planner_request(status))

        status_key = (str(status["planner_action"]), str(status["reason"]))
        if status_key != self._last_status_key:
            self.get_logger().info(
                "Supervisor status: action=%s reason=%s"
                % (status["planner_action"], status["reason"])
            )
            self._last_status_key = status_key

    def _build_timeout_event(self, reason: str) -> dict[str, Any]:
        return {
            "ts": self._timestamp(),
            "event_type": "perception_status",
            "perception_available": False,
            "pipeline_state": "unavailable",
            "reason": reason,
        }

    def _on_event(self, msg: String) -> None:
        self._last_event_monotonic = time.monotonic()
        event = self._parse_payload(msg.data)
        self._publish_status(event)

    def _on_monitor_timer(self) -> None:
        if self._last_event_monotonic is None:
            self._publish_status(self._build_timeout_event("waiting_for_perception"))
            return

        if (time.monotonic() - self._last_event_monotonic) > self._perception_timeout_sec:
            self._publish_status(self._build_timeout_event("perception_timeout"))


def main(args=None) -> None:
    rclpy.init(args=args)
    node: SystemSupervisorNode | None = None
    try:
        node = SystemSupervisorNode()
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        if node is not None:
            node.destroy_node()
        time.sleep(0.05)
        if rclpy.ok():
            rclpy.shutdown()
