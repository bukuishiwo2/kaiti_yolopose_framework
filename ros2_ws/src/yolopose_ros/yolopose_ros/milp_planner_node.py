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


class MilpPlannerNode(Node):
    def __init__(self) -> None:
        super().__init__("milp_planner_node")
        self.declare_parameter("project_root", _default_project_root())
        self.declare_parameter("planner_config_path", "configs/planner_minimal_experiment.yaml")
        self.declare_parameter("semantic_state_topic", "/planning/semantic_state")
        self.declare_parameter("spatial_state_topic", "/planning/spatial_state")
        self.declare_parameter("plan_topic", "/planning/plan")
        self.declare_parameter("publish_period_sec", 2.0)
        self.declare_parameter("backend", "pulp")

        self._project_root = Path(str(self.get_parameter("project_root").value)).resolve()
        src_root = self._project_root / "src"
        if str(src_root) not in sys.path:
            sys.path.insert(0, str(src_root))

        from kaiti_planning.milp_solver import ResourceState, solve_milp
        from kaiti_planning.models import load_problem_from_yaml

        self._solve_milp = solve_milp
        self._resource_state_cls = ResourceState

        cfg_path = self._project_root / str(self.get_parameter("planner_config_path").value)
        self._problem = load_problem_from_yaml(cfg_path)
        self._backend = str(self.get_parameter("backend").value)
        self._publisher = self.create_publisher(String, str(self.get_parameter("plan_topic").value), 10)
        self.create_subscription(String, str(self.get_parameter("semantic_state_topic").value), self._on_semantic, 10)
        self.create_subscription(String, str(self.get_parameter("spatial_state_topic").value), self._on_spatial, 10)
        self._timer = self.create_timer(float(self.get_parameter("publish_period_sec").value), self._on_timer)
        self._latest_semantic: dict[str, Any] | None = None
        self._latest_spatial: dict[str, Any] | None = None

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

    def _on_semantic(self, msg: String) -> None:
        self._latest_semantic = self._parse_payload(msg.data)

    def _on_spatial(self, msg: String) -> None:
        self._latest_spatial = self._parse_payload(msg.data)

    def _resource_states_from_payload(self) -> dict[str, Any] | None:
        if self._latest_spatial is None:
            return None
        raw_states = self._latest_spatial.get("resource_states", {})
        result = {}
        for resource_id, payload in raw_states.items():
            if not isinstance(payload, dict):
                continue
            result[resource_id] = self._resource_state_cls(
                resource_id=str(payload.get("resource_id", resource_id)),
                predicate=str(payload.get("predicate", "")),
                state=str(payload.get("state", "")),
                available_from=float(payload.get("available_from", 0.0)),
                wait_time=float(payload.get("wait_time", 0.0)),
                metadata=dict(payload.get("metadata", {})),
            )
        return result

    def _on_timer(self) -> None:
        try:
            result = self._solve_milp(
                self._problem,
                backend=self._backend,
                resource_states=self._resource_states_from_payload(),
                plan_kind="ros2_periodic",
            )
            payload = {
                "ts": self._timestamp(),
                "role": "milp_planner_node",
                "source_semantic_state": self._latest_semantic,
                "source_spatial_state": self._latest_spatial,
                **result.to_dict(),
            }
        except Exception as exc:  # pylint: disable=broad-except
            payload = {
                "ts": self._timestamp(),
                "role": "milp_planner_node",
                "planner_mode": "milp",
                "plan_kind": "ros2_periodic",
                "solver_status": "error",
                "objective_value": None,
                "assignments": [],
                "metrics": {},
                "notes": [f"planner_error:{exc}"],
                "source_semantic_state": self._latest_semantic,
                "source_spatial_state": self._latest_spatial,
            }
        msg = String()
        msg.data = json.dumps(payload, ensure_ascii=True)
        self._publisher.publish(msg)


def main(args=None) -> None:
    rclpy.init(args=args)
    node: MilpPlannerNode | None = None
    try:
        node = MilpPlannerNode()
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        if node is not None:
            node.destroy_node()
        time.sleep(0.05)
        if rclpy.ok():
            rclpy.shutdown()
