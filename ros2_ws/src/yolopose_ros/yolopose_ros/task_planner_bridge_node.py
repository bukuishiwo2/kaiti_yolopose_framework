from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Any

import rclpy
from rclpy.node import Node
from std_msgs.msg import String


ACTION_TO_STATE = {
    "monitor": ("idle", "monitoring_request"),
    "wait_for_update": ("waiting", "waiting_for_perception_update"),
    "trigger_safe_mode": ("dispatching_safe_mode", "safe_mode_requested"),
    "hold": ("holding", "planner_hold"),
}


class TaskPlannerBridgeNode(Node):
    """Minimal task-layer placeholder that acknowledges supervisor requests."""

    def __init__(self) -> None:
        super().__init__("task_planner_bridge_node")

        self.declare_parameter("planner_request_topic", "/task_planner/request")
        self.declare_parameter("planner_status_topic", "/task_planner/status")
        self.declare_parameter("planner_mode", "plansys2_placeholder")
        self.declare_parameter("status_publish_period_sec", 1.0)
        self.declare_parameter("request_timeout_sec", 5.0)

        self._request_topic = str(self.get_parameter("planner_request_topic").value)
        self._status_topic = str(self.get_parameter("planner_status_topic").value)
        self._planner_mode = str(self.get_parameter("planner_mode").value)
        self._status_publish_period_sec = float(
            self.get_parameter("status_publish_period_sec").value
        )
        self._request_timeout_sec = float(self.get_parameter("request_timeout_sec").value)

        self._status_pub = self.create_publisher(String, self._status_topic, 10)
        self._request_sub = self.create_subscription(
            String, self._request_topic, self._on_request, 10
        )
        self._status_timer = self.create_timer(
            self._status_publish_period_sec, self._on_status_timer
        )

        self._last_request_monotonic: float | None = None
        self._last_request: dict[str, Any] | None = None
        self._last_status_key: tuple[str, str] | None = None

        self.get_logger().info(
            "Task planner bridge ready: request_topic=%s status_topic=%s planner_mode=%s"
            % (self._request_topic, self._status_topic, self._planner_mode)
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

    def _build_status(
        self,
        requested_action: str,
        reason: str,
        request: dict[str, Any] | None,
    ) -> dict[str, Any]:
        planner_state, default_reason = ACTION_TO_STATE.get(
            requested_action,
            ("invalid_request", "unsupported_requested_action"),
        )
        if not reason:
            reason = default_reason
        return {
            "ts": self._timestamp(),
            "role": "task_planner_bridge",
            "planner_mode": self._planner_mode,
            "planner_state": planner_state,
            "active_action": requested_action,
            "reason": reason,
            "request_topic": self._request_topic,
            "source_request": request,
        }

    def _publish_status(self, payload: dict[str, Any]) -> None:
        msg = String()
        msg.data = json.dumps(payload, ensure_ascii=True)
        self._status_pub.publish(msg)

        status_key = (str(payload["planner_state"]), str(payload["reason"]))
        if status_key != self._last_status_key:
            self.get_logger().info(
                "Task planner status: state=%s reason=%s"
                % (payload["planner_state"], payload["reason"])
            )
            self._last_status_key = status_key

    def _publish_for_request(self, request: dict[str, Any]) -> None:
        requested_action = str(request.get("requested_action", "")).strip().lower()
        reason = str(request.get("reason", "")).strip()
        status = self._build_status(requested_action, reason, request)
        self._publish_status(status)

    def _build_timeout_status(self, reason: str) -> dict[str, Any]:
        return self._build_status("wait_for_update", reason, self._last_request)

    def _on_request(self, msg: String) -> None:
        self._last_request_monotonic = time.monotonic()
        self._last_request = self._parse_payload(msg.data)
        self._publish_for_request(self._last_request)

    def _on_status_timer(self) -> None:
        if self._last_request_monotonic is None:
            self._publish_status(self._build_timeout_status("waiting_for_supervisor_request"))
            return

        if (time.monotonic() - self._last_request_monotonic) > self._request_timeout_sec:
            self._publish_status(self._build_timeout_status("planner_request_timeout"))
            return

        if self._last_request is not None:
            self._publish_for_request(self._last_request)


def main(args=None) -> None:
    rclpy.init(args=args)
    node: TaskPlannerBridgeNode | None = None
    try:
        node = TaskPlannerBridgeNode()
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        if node is not None:
            node.destroy_node()
        time.sleep(0.05)
        if rclpy.ok():
            rclpy.shutdown()
