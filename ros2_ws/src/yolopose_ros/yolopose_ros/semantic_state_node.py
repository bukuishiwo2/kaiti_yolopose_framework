from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import rclpy
from rclpy.node import Node
from std_msgs.msg import String


def _default_project_root() -> str:
    return str(Path(__file__).resolve().parents[4])


class SemanticStateNode(Node):
    def __init__(self) -> None:
        super().__init__("semantic_state_node")
        self.declare_parameter("project_root", _default_project_root())
        self.declare_parameter("planner_config_path", "configs/planner_minimal_experiment.yaml")
        self.declare_parameter("perception_event_topic", "/perception/events")
        self.declare_parameter("semantic_state_topic", "/planning/semantic_state")
        self.declare_parameter("publish_period_sec", 1.0)
        self.declare_parameter("perception_timeout_sec", 3.0)

        self._project_root = Path(str(self.get_parameter("project_root").value)).resolve()
        src_root = self._project_root / "src"
        if str(src_root) not in sys.path:
            sys.path.insert(0, str(src_root))

        from kaiti_planning.models import load_problem_from_yaml
        from kaiti_planning.semantic_state import SemanticStateMachine

        cfg_path = self._project_root / str(self.get_parameter("planner_config_path").value)
        problem = load_problem_from_yaml(cfg_path)
        self._machine = SemanticStateMachine(problem.semantic)

        self._perception_topic = str(self.get_parameter("perception_event_topic").value)
        self._semantic_topic = str(self.get_parameter("semantic_state_topic").value)
        self._publish_period_sec = float(self.get_parameter("publish_period_sec").value)
        self._perception_timeout_sec = float(self.get_parameter("perception_timeout_sec").value)

        self._publisher = self.create_publisher(String, self._semantic_topic, 10)
        self._subscription = self.create_subscription(String, self._perception_topic, self._on_event, 10)
        self._timer = self.create_timer(self._publish_period_sec, self._on_timer)
        self._last_event_monotonic: float | None = None
        self._last_payload: dict[str, Any] | None = None

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

    def _emit_state(self, event: dict[str, Any]) -> None:
        result = self._machine.update(event)
        payload = {
            "ts": self._timestamp(),
            "role": "semantic_state_node",
            **result.to_dict(),
        }
        self._last_payload = payload
        self._publish(payload)

    def _on_event(self, msg: String) -> None:
        self._last_event_monotonic = time.monotonic()
        event = self._parse_payload(msg.data)
        self._emit_state(event)

    def _on_timer(self) -> None:
        if self._last_event_monotonic is None or (
            time.monotonic() - self._last_event_monotonic
        ) > self._perception_timeout_sec:
            self._emit_state(
                {
                    "seq_fall_score": 0.0,
                    "seq_visible_keypoint_count": 0,
                    "seq_window_ready": False,
                    "seq_feature_valid": False,
                    "event_location": "unknown",
                    "reason": "waiting_for_perception",
                }
            )


def main(args=None) -> None:
    rclpy.init(args=args)
    node: SemanticStateNode | None = None
    try:
        node = SemanticStateNode()
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        if node is not None:
            node.destroy_node()
        time.sleep(0.05)
        if rclpy.ok():
            rclpy.shutdown()
