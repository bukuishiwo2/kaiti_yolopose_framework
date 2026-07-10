from __future__ import annotations

import json
import sys
import time
import uuid
from pathlib import Path
from typing import Any

import rclpy
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy
from std_msgs.msg import String


def _default_project_root() -> str:
    return str(Path(__file__).resolve().parents[4])


class MilpPlannerNode(Node):
    """World-revision-driven ROS adapter for the formal v2 planner."""

    def __init__(self) -> None:
        super().__init__("milp_planner_node")
        self.declare_parameter("project_root", _default_project_root())
        self.declare_parameter("planner_config_path", "configs/planner_graduation_v2.yaml")
        self.declare_parameter("semantic_state_topic", "/planning/semantic_state")
        self.declare_parameter("spatial_state_topic", "/planning/spatial_state")
        self.declare_parameter("execution_feedback_topic", "/planning/execution_feedback")
        self.declare_parameter("plan_topic", "/planning/plan")
        self.declare_parameter("health_topic", "/planning/planner_health")
        self.declare_parameter("solve_debounce_sec", 0.25)
        self.declare_parameter("health_period_sec", 2.0)
        self.declare_parameter("plan_valid_sec", 600.0)
        self.declare_parameter("plan_id", "house-v2")
        self.declare_parameter("planner_instance_id", "")
        self.declare_parameter("verification_result_on_success", "")
        self.declare_parameter("backend", "pulp")

        self._project_root = Path(str(self.get_parameter("project_root").value)).resolve()
        src_root = self._project_root / "src"
        if str(src_root) not in sys.path:
            sys.path.insert(0, str(src_root))

        from kaiti_planning.dynamic_repair import RevisionPlanningCoordinator
        from kaiti_planning.milp_solver import initial_resource_states
        from kaiti_planning.models import ResourceState, load_problem_from_yaml
        from kaiti_planning.world_state import TaskLifecycle, WorldState

        config_path = self._project_root / str(self.get_parameter("planner_config_path").value)
        problem = load_problem_from_yaml(config_path)
        self._world = WorldState(problem)
        self._coordinator = RevisionPlanningCoordinator(self._world)
        self._resource_state_cls = ResourceState
        self._task_lifecycle_cls = TaskLifecycle
        self._resource_states = initial_resource_states(problem)
        self._backend = str(self.get_parameter("backend").value)
        self._plan_id = str(self.get_parameter("plan_id").value).strip() or "house-v2"
        configured_instance = str(self.get_parameter("planner_instance_id").value).strip()
        self._planner_instance_id = configured_instance or str(uuid.uuid4())
        self._verify_success_result = str(
            self.get_parameter("verification_result_on_success").value
        ).strip()
        self._solve_debounce_sec = max(
            0.0, float(self.get_parameter("solve_debounce_sec").value)
        )
        self._plan_valid_sec = max(1.0, float(self.get_parameter("plan_valid_sec").value))
        self._start_ros_time = self._ros_seconds()
        self._pending_trigger = True
        self._pending_reason = "initial_world"
        self._last_trigger_monotonic = time.monotonic()
        self._last_spatial_signature: tuple[Any, ...] | None = None
        self._seen_completed_tasks: set[str] = set()
        self._latest_semantic: dict[str, Any] | None = None
        self._latest_spatial: dict[str, Any] | None = None
        self._last_plan_payload: dict[str, Any] | None = None

        plan_qos = QoSProfile(
            history=HistoryPolicy.KEEP_LAST,
            depth=1,
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
        )
        self._plan_publisher = self.create_publisher(
            String, str(self.get_parameter("plan_topic").value), plan_qos
        )
        self._health_publisher = self.create_publisher(
            String, str(self.get_parameter("health_topic").value), 10
        )
        self.create_subscription(
            String,
            str(self.get_parameter("semantic_state_topic").value),
            self._on_semantic,
            10,
        )
        self.create_subscription(
            String,
            str(self.get_parameter("spatial_state_topic").value),
            self._on_spatial,
            10,
        )
        self.create_subscription(
            String,
            str(self.get_parameter("execution_feedback_topic").value),
            self._on_execution_feedback,
            10,
        )
        self._solve_timer = self.create_timer(0.1, self._on_solve_timer)
        self._health_timer = self.create_timer(
            float(self.get_parameter("health_period_sec").value), self._publish_health
        )
        self.get_logger().info(
            "v2 planner ready: instance=%s plan_id=%s config=%s"
            % (self._planner_instance_id, self._plan_id, config_path)
        )

    def _ros_seconds(self) -> float:
        return float(self.get_clock().now().nanoseconds) / 1_000_000_000.0

    def _logical_time(self) -> float:
        return max(0.0, self._ros_seconds() - self._start_ros_time)

    @staticmethod
    def _parse_payload(payload: str) -> dict[str, Any] | None:
        try:
            value = json.loads(payload)
        except json.JSONDecodeError:
            return None
        return value if isinstance(value, dict) else None

    @staticmethod
    def _publish(publisher, payload: dict[str, Any]) -> None:
        message = String()
        message.data = json.dumps(payload, ensure_ascii=True)
        publisher.publish(message)

    def _schedule_solve(self, reason: str) -> None:
        self._pending_trigger = True
        self._pending_reason = reason
        self._last_trigger_monotonic = time.monotonic()

    def _on_semantic(self, message: String) -> None:
        payload = self._parse_payload(message.data)
        if payload is None:
            return
        self._latest_semantic = payload
        source = payload.get("source_event", {})
        if not isinstance(source, dict):
            source = {}
        track_id = source.get("seq_track_id", source.get("track_id"))
        update = self._world.ingest_perception(
            str(payload.get("semantic_state", "normal")),
            current_time=self._logical_time(),
            location_id=str(payload.get("event_location") or "B"),
            track_id=track_id,
            external_event_id=(str(payload["event_id"]) if payload.get("event_id") else None),
        )
        if update.changed:
            self._schedule_solve("semantic:%s" % update.reason)

    def _on_spatial(self, message: String) -> None:
        payload = self._parse_payload(message.data)
        if payload is None:
            return
        self._latest_spatial = payload
        raw_states = payload.get("resource_states", {})
        if not isinstance(raw_states, dict):
            return
        rows = []
        for resource_id, raw in sorted(raw_states.items()):
            if not isinstance(raw, dict):
                continue
            state_name = str(raw.get("state", ""))
            wait_time = max(0.0, float(raw.get("wait_time", 0.0)))
            rows.append(
                (
                    str(resource_id),
                    state_name,
                    str(raw.get("predicate", "")),
                )
            )
        signature = tuple(rows)
        if signature == self._last_spatial_signature:
            return
        self._last_spatial_signature = signature

        parsed_states = {}
        now = self._logical_time()
        for resource_id, raw in sorted(raw_states.items()):
            if not isinstance(raw, dict):
                continue
            state_name = str(raw.get("state", ""))
            wait_time = max(0.0, float(raw.get("wait_time", 0.0)))
            available_from = 0.0 if state_name in {"free", "available", "reachable"} else now + wait_time
            state = self._resource_state_cls(
                resource_id=str(raw.get("resource_id", resource_id)),
                predicate=str(raw.get("predicate", "")),
                state=state_name,
                available_from=available_from,
                wait_time=wait_time,
                metadata=dict(raw.get("metadata", {})),
            )
            parsed_states[state.resource_id] = state
        changed = False
        for resource_id, state in parsed_states.items():
            self._resource_states[resource_id] = state
            changed = self._world.update_resource_state(state) or changed
        if changed:
            self._schedule_solve("spatial_revision")

    def _on_execution_feedback(self, message: String) -> None:
        payload = self._parse_payload(message.data)
        if payload is None:
            return
        source = payload.get("source_status", {})
        if not isinstance(source, dict):
            return
        completed = source.get("completed_task_ids", [])
        if not isinstance(completed, list):
            return
        changed = False
        for task_id_value in completed:
            task_id = str(task_id_value)
            if task_id in self._seen_completed_tasks or task_id not in self._world.tasks:
                continue
            self._seen_completed_tasks.add(task_id)
            record = self._world.tasks[task_id]
            if task_id.startswith("verify:") and self._verify_success_result:
                event_id = task_id.split(":", 1)[1]
                self._world.record_verification(
                    event_id,
                    self._verify_success_result,
                    current_time=self._logical_time(),
                )
            elif record.lifecycle != self._task_lifecycle_cls.COMPLETED:
                self._world.mark_task_completed(task_id, current_time=self._logical_time())
            changed = True
        if changed:
            self._schedule_solve("execution_completed")

    def _on_solve_timer(self) -> None:
        if not self._pending_trigger:
            return
        if (time.monotonic() - self._last_trigger_monotonic) < self._solve_debounce_sec:
            return
        self._pending_trigger = False
        solved = self._coordinator.solve_latest(
            resource_states=self._resource_states,
            current_time=self._logical_time(),
        )
        if not solved.get("published"):
            if solved.get("reason") == "stale_world_revision":
                self._schedule_solve("retry_stale_revision")
            return
        result = dict(solved["plan"])
        problem = self._world.planning_problem()
        task_map = problem.task_by_id()
        tasks = []
        for assignment in result.get("assignments", []):
            row = dict(assignment)
            task = task_map.get(str(row.get("task", "")))
            if task is not None:
                row["task_type"] = task.type
            record = self._world.tasks.get(str(row.get("task", "")))
            row["attempt"] = record.attempt if record is not None else 1
            tasks.append(row)
        generated = self._logical_time()
        payload = {
            "role": "milp_planner_node",
            "planner_instance_id": self._planner_instance_id,
            "plan_id": self._plan_id,
            "revision": int(solved["plan_revision"]),
            "world_revision": int(solved["world_revision"]),
            "generated_at": generated,
            "valid_from": generated,
            "expires_at": generated + self._plan_valid_sec,
            "trigger_reason": self._pending_reason,
            "source_semantic_state": self._latest_semantic,
            "source_spatial_state": self._latest_spatial,
            **result,
            "tasks": tasks,
        }
        self._last_plan_payload = payload
        self._publish(self._plan_publisher, payload)
        self.get_logger().info(
            "Published plan revision=%d world_revision=%d status=%s tasks=%d"
            % (
                payload["revision"],
                payload["world_revision"],
                payload.get("solver_status"),
                len(tasks),
            )
        )

    def _publish_health(self) -> None:
        self._publish(
            self._health_publisher,
            {
                "role": "milp_planner_node",
                "planner_instance_id": self._planner_instance_id,
                "plan_id": self._plan_id,
                "world_revision": self._world.world_revision,
                "plan_revision": self._world.plan_revision,
                "pending_trigger": self._pending_trigger,
                "last_solver_status": (
                    self._last_plan_payload.get("solver_status")
                    if self._last_plan_payload
                    else None
                ),
            },
        )


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
