from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Any

import rclpy
from rclpy.node import Node
from std_msgs.msg import String


class ExecutionFeedbackBridgeNode(Node):
    def __init__(self) -> None:
        super().__init__("execution_feedback_bridge_node")
        self.declare_parameter("planner_status_topic", "/task_planner/status")
        self.declare_parameter("execution_feedback_topic", "/planning/execution_feedback")
        self.declare_parameter("publish_period_sec", 1.0)
        self.declare_parameter("status_timeout_sec", 5.0)

        self._planner_status_topic = str(self.get_parameter("planner_status_topic").value)
        self._feedback_topic = str(self.get_parameter("execution_feedback_topic").value)
        self._status_timeout_sec = float(self.get_parameter("status_timeout_sec").value)

        self._publisher = self.create_publisher(String, self._feedback_topic, 10)
        self.create_subscription(String, self._planner_status_topic, self._on_status, 10)
        self._timer = self.create_timer(float(self.get_parameter("publish_period_sec").value), self._on_timer)
        self._last_status_monotonic: float | None = None
        self._last_status_payload: dict[str, Any] | None = None

    @staticmethod
    def _timestamp() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _parse_payload(payload: str) -> dict[str, Any]:
        try:
            value = json.loads(payload)
            return value if isinstance(value, dict) else {"raw": value}
        except json.JSONDecodeError:
            return {"raw": payload}

    def _publish(self, payload: dict[str, Any]) -> None:
        msg = String()
        msg.data = json.dumps(payload, ensure_ascii=True)
        self._publisher.publish(msg)

    def _emit_feedback(self, payload: dict[str, Any] | None, reason: str) -> None:
        source = payload or {}
        state = str(source.get("planner_state", "idle"))
        if not payload:
            state = "idle"
        feedback = {
            "ts": self._timestamp(),
            "role": "execution_feedback_bridge_node",
            "feedback_state": state,
            "active_action": str(source.get("active_action", "")),
            "reason": reason,
            "source_status": source,
        }
        self._publish(feedback)

    def _on_status(self, msg: String) -> None:
        self._last_status_monotonic = time.monotonic()
        self._last_status_payload = self._parse_payload(msg.data)
        self._emit_feedback(self._last_status_payload, str(self._last_status_payload.get("reason", "status_update")))

    def _on_timer(self) -> None:
        if self._last_status_monotonic is None or (
            time.monotonic() - self._last_status_monotonic
        ) > self._status_timeout_sec:
            self._emit_feedback(self._last_status_payload, "waiting_for_planner_status")


def main(args=None) -> None:
    rclpy.init(args=args)
    node: ExecutionFeedbackBridgeNode | None = None
    try:
        node = ExecutionFeedbackBridgeNode()
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        if node is not None:
            node.destroy_node()
        time.sleep(0.05)
        if rclpy.ok():
            rclpy.shutdown()
