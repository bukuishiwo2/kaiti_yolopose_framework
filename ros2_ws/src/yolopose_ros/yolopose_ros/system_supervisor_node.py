from __future__ import annotations

import json
from typing import Any

import rclpy
from rclpy.node import Node
from std_msgs.msg import String


class SystemSupervisorNode(Node):
    """Minimal system-level supervisor stub.

    It standardizes perception events and exposes the handoff point to the
    future planner layer. The node intentionally does not implement real
    planning yet; it only makes the message boundary explicit.
    """

    def __init__(self) -> None:
        super().__init__("system_supervisor_node")

        self.declare_parameter("perception_event_topic", "/kaiti/perception/events")
        self.declare_parameter("supervisor_status_topic", "/kaiti/system/supervisor/status")
        self.declare_parameter("planner_request_topic", "/kaiti/task_planner/request")
        self.declare_parameter("planner_mode", "plansys2_placeholder")

        self._perception_event_topic = self.get_parameter("perception_event_topic").value
        self._status_topic = self.get_parameter("supervisor_status_topic").value
        self._planner_request_topic = self.get_parameter("planner_request_topic").value
        self._planner_mode = self.get_parameter("planner_mode").value

        self._status_pub = self.create_publisher(String, self._status_topic, 10)
        self._event_sub = self.create_subscription(
            String, self._perception_event_topic, self._on_event, 10
        )

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

        if fall_flag:
            planner_action = "trigger_safe_mode"
            reason = "fall_detected"
        elif person_present is False:
            planner_action = "wait_for_update"
            reason = "no_person_present"
        else:
            planner_action = "monitor"
            reason = "stable"

        return {
            "role": "system_supervisor",
            "planner_mode": self._planner_mode,
            "planner_request_topic": self._planner_request_topic,
            "planner_action": planner_action,
            "reason": reason,
            "source_event": event,
        }

    def _on_event(self, msg: String) -> None:
        event = self._parse_payload(msg.data)
        status = self._build_status(event)

        out = String()
        out.data = json.dumps(status, ensure_ascii=True)
        self._status_pub.publish(out)

        self.get_logger().info(
            "Supervisor event received: action=%s reason=%s"
            % (status["planner_action"], status["reason"])
        )


def main(args=None) -> None:
    rclpy.init(args=args)
    node = SystemSupervisorNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()
