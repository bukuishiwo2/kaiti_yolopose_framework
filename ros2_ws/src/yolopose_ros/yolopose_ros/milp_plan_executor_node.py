"""Single-robot online executor for MILP plans using Nav2 goals.

主要功能:
- 订阅 `/planning/plan`，抽取指定机器人对应的任务序列。
- 按顺序把任务地点转换成 `NavigateToPose` 目标，驱动 Nav2 执行。
- 发布执行状态到独立 topic，供 `/planning/execution_feedback` 汇聚。

适用阶段:
- 在当前单机器人 Gazebo house 仿真中验证 `MILP -> Nav2 -> feedback` 闭环。
- 为后续 PlanSys2 生命周期接入提供可替换的最小在线执行器。

不负责:
- 不做全局任务分配。
- 不替代后续 PlanSys2 动作生命周期。
"""

from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import rclpy
import yaml
from action_msgs.msg import GoalStatus
from geometry_msgs.msg import PoseStamped
from nav_msgs.msg import OccupancyGrid
from nav2_msgs.action import NavigateToPose
from rcl_interfaces.msg import SetParametersResult
from rclpy.action import ActionClient
from rclpy.duration import Duration
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy
from rclpy.time import Time
from std_msgs.msg import String
from tf2_ros import Buffer, TransformException, TransformListener


def _default_project_root() -> str:
    return str(Path(__file__).resolve().parents[4])


@dataclass(frozen=True)
class Waypoint:
    frame_id: str
    x: float
    y: float
    z: float
    qx: float
    qy: float
    qz: float
    qw: float


@dataclass(frozen=True)
class TaskStep:
    task_id: str
    task_type: str
    location_id: str
    step_name: str
    attempt: int = 1


@dataclass(frozen=True)
class MapBounds:
    frame_id: str
    x_min: float
    x_max: float
    y_min: float
    y_max: float
    width: int
    height: int
    resolution: float


class MilpPlanExecutorNode(Node):
    def __init__(self) -> None:
        super().__init__("milp_plan_executor_node")

        self.declare_parameter("project_root", _default_project_root())
        self.declare_parameter("planner_config_path", "configs/planner_minimal_experiment.yaml")
        self.declare_parameter("waypoint_config_path", "configs/planner_waypoints.yaml")
        self.declare_parameter("plan_topic", "/planning/plan")
        self.declare_parameter("planner_status_topic", "/planning/executor_status")
        self.declare_parameter("nav2_action_name", "/navigate_to_pose")
        self.declare_parameter("map_topic", "/map")
        self.declare_parameter("controlled_robot_id", "R2")
        self.declare_parameter("execution_enabled", False)
        self.declare_parameter("allow_plan_refresh_during_execution", False)
        self.declare_parameter("require_tf_ready", True)
        self.declare_parameter("require_waypoint_in_map", True)
        self.declare_parameter("waypoint_map_margin_m", 0.10)
        self.declare_parameter("base_frame_id", "base_link")
        self.declare_parameter("tf_wait_timeout_sec", 0.2)
        self.declare_parameter("publish_period_sec", 1.0)
        self.declare_parameter("task_hold_sec", 1.0)
        self.declare_parameter("plan_stale_sec", 600.0)
        self.declare_parameter("max_nav_retries_per_step", 0)

        self._project_root = Path(str(self.get_parameter("project_root").value)).resolve()
        src_root = self._project_root / "src"
        if str(src_root) not in sys.path:
            sys.path.insert(0, str(src_root))

        from kaiti_planning.models import load_problem_from_yaml
        from kaiti_planning.execution_protocol import (
            RevisionGate,
            can_apply_deferred_revision,
            expand_assignments,
        )

        cfg_path = self._project_root / str(self.get_parameter("planner_config_path").value)
        self._problem = load_problem_from_yaml(cfg_path)
        self._task_map = self._problem.task_by_id()
        self._expand_execution_assignments = expand_assignments
        self._can_apply_deferred_revision = can_apply_deferred_revision
        self._revision_gate = RevisionGate()

        waypoint_path = self._project_root / str(self.get_parameter("waypoint_config_path").value)
        self._waypoints = self._load_waypoints(waypoint_path)

        self._plan_topic = str(self.get_parameter("plan_topic").value)
        self._planner_status_topic = str(self.get_parameter("planner_status_topic").value)
        self._nav2_action_name = str(self.get_parameter("nav2_action_name").value)
        self._map_topic = str(self.get_parameter("map_topic").value)
        self._controlled_robot_id = str(self.get_parameter("controlled_robot_id").value).strip()
        self._execution_enabled = bool(self.get_parameter("execution_enabled").value)
        self._allow_plan_refresh_during_execution = bool(
            self.get_parameter("allow_plan_refresh_during_execution").value
        )
        self._require_tf_ready = bool(self.get_parameter("require_tf_ready").value)
        self._require_waypoint_in_map = bool(self.get_parameter("require_waypoint_in_map").value)
        self._waypoint_map_margin_m = max(0.0, float(self.get_parameter("waypoint_map_margin_m").value))
        self._base_frame_id = str(self.get_parameter("base_frame_id").value).strip() or "base_link"
        self._tf_wait_timeout_sec = max(0.0, float(self.get_parameter("tf_wait_timeout_sec").value))
        self._task_hold_sec = max(0.0, float(self.get_parameter("task_hold_sec").value))
        self._plan_stale_sec = max(1.0, float(self.get_parameter("plan_stale_sec").value))
        self._max_nav_retries_per_step = max(0, int(self.get_parameter("max_nav_retries_per_step").value))

        self._status_pub = self.create_publisher(String, self._planner_status_topic, 10)
        plan_qos = QoSProfile(
            history=HistoryPolicy.KEEP_LAST,
            depth=1,
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
        )
        self.create_subscription(String, self._plan_topic, self._on_plan, plan_qos)
        map_qos = QoSProfile(
            history=HistoryPolicy.KEEP_LAST,
            depth=1,
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
        )
        self.create_subscription(OccupancyGrid, self._map_topic, self._on_map, map_qos)
        self._action_client = ActionClient(self, NavigateToPose, self._nav2_action_name)
        self._tf_buffer = Buffer()
        self._tf_listener = TransformListener(self._tf_buffer, self)
        self._timer = self.create_timer(float(self.get_parameter("publish_period_sec").value), self._on_timer)
        self.add_on_set_parameters_callback(self._on_parameters_changed)

        self._latest_plan_payload: dict[str, Any] | None = None
        self._latest_plan_monotonic: float | None = None
        self._active_plan_signature: tuple[tuple[str, float, float], ...] | None = None
        self._pending_plan_assignments: list[dict[str, Any]] | None = None
        self._pending_plan_identity = None
        self._active_plan_identity = None
        self._execution_queue: list[TaskStep] = []
        self._pending_goal = False
        self._active_goal_handle = None
        self._active_step: TaskStep | None = None
        self._hold_until_monotonic: float | None = None
        self._completed_task_ids: set[str] = set()
        self._completed_step_keys: set[tuple[str, str, int]] = set()
        self._nav_retry_counts: dict[tuple[str, str, int], int] = {}
        self._dispatched_goal_history: list[dict[str, Any]] = []
        self._terminal_failure_reason: str | None = None
        self._latest_map_bounds: MapBounds | None = None
        self._last_status_key: tuple[str, str, str] | None = None

        self.get_logger().info(
            "MILP plan executor ready: robot_id=%s plan_topic=%s nav2_action=%s enabled=%s"
            % (
                self._controlled_robot_id,
                self._plan_topic,
                self._nav2_action_name,
                self._execution_enabled,
            )
        )

    @staticmethod
    def _timestamp() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _parse_payload(payload: str) -> dict[str, Any] | None:
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            return None
        return data if isinstance(data, dict) else None

    @staticmethod
    def _safe_float(value: Any, default: float = 0.0) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _assignment_signature(assignments: list[dict[str, Any]]) -> tuple[tuple[str, float, float], ...]:
        rows = []
        for item in assignments:
            rows.append(
                (
                    str(item.get("task", "")).strip(),
                    round(MilpPlanExecutorNode._safe_float(item.get("start")), 3),
                    round(MilpPlanExecutorNode._safe_float(item.get("finish")), 3),
                )
            )
        return tuple(rows)

    def _load_waypoints(self, path: Path) -> dict[str, Waypoint]:
        with path.open("r", encoding="utf-8") as handle:
            raw = yaml.safe_load(handle) or {}
        waypoints: dict[str, Waypoint] = {}
        for key, payload in (raw.get("waypoints") or {}).items():
            if not isinstance(payload, dict):
                continue
            waypoints[str(key)] = Waypoint(
                frame_id=str(payload.get("frame_id", "map")).strip() or "map",
                x=float(payload["x"]),
                y=float(payload["y"]),
                z=float(payload.get("z", 0.0)),
                qx=float(payload.get("qx", 0.0)),
                qy=float(payload.get("qy", 0.0)),
                qz=float(payload.get("qz", 0.0)),
                qw=float(payload.get("qw", 1.0)),
            )
        return waypoints

    def _build_status(
        self,
        *,
        planner_state: str,
        reason: str,
        active_action: str = "",
    ) -> dict[str, Any]:
        return {
            "ts": self._timestamp(),
            "role": "milp_plan_executor_node",
            "planner_mode": "milp_nav2_executor",
            "planner_state": planner_state,
            "active_action": active_action,
            "reason": reason,
            "controlled_robot_id": self._controlled_robot_id,
            "execution_enabled": self._execution_enabled,
            "allow_plan_refresh_during_execution": self._allow_plan_refresh_during_execution,
            "active_step": {
                "task_id": self._active_step.task_id,
                "task_type": self._active_step.task_type,
                "location_id": self._active_step.location_id,
                "step_name": self._active_step.step_name,
                "attempt": self._active_step.attempt,
            }
            if self._active_step is not None
            else None,
            "completed_task_ids": sorted(self._completed_task_ids),
            "queue_length": len(self._execution_queue),
            "queue_preview": [
                {
                    "task_id": step.task_id,
                    "task_type": step.task_type,
                    "location_id": step.location_id,
                    "step_name": step.step_name,
                }
                for step in self._execution_queue[:10]
            ],
            "completed_step_keys": [
                {"task_id": task_id, "step_name": step_name, "attempt": attempt}
                for task_id, step_name, attempt in sorted(self._completed_step_keys)
            ],
            "nav_retry_counts": {
                f"{task_id}:{step_name}:{attempt}": count
                for (task_id, step_name, attempt), count in sorted(self._nav_retry_counts.items())
            },
            "dispatched_goal_history": self._dispatched_goal_history[-20:],
            "terminal_failure_reason": self._terminal_failure_reason,
            "map_bounds": {
                "frame_id": self._latest_map_bounds.frame_id,
                "x_min": self._latest_map_bounds.x_min,
                "x_max": self._latest_map_bounds.x_max,
                "y_min": self._latest_map_bounds.y_min,
                "y_max": self._latest_map_bounds.y_max,
                "width": self._latest_map_bounds.width,
                "height": self._latest_map_bounds.height,
                "resolution": self._latest_map_bounds.resolution,
            }
            if self._latest_map_bounds is not None
            else None,
            "source_plan_meta": self._plan_meta(self._latest_plan_payload),
            "active_plan_identity": {
                "planner_instance_id": self._active_plan_identity.planner_instance_id,
                "plan_id": self._active_plan_identity.plan_id,
                "revision": self._active_plan_identity.revision,
                "world_revision": self._active_plan_identity.world_revision,
            }
            if self._active_plan_identity is not None
            else None,
        }

    @staticmethod
    def _plan_meta(payload: dict[str, Any] | None) -> dict[str, Any] | None:
        if not payload:
            return None
        assignments = payload.get("tasks")
        if not isinstance(assignments, list):
            assignments = payload.get("assignments")
        return {
            "solver_status": payload.get("solver_status"),
            "plan_kind": payload.get("plan_kind"),
            "assignment_count": len(assignments) if isinstance(assignments, list) else 0,
            "note_count": len(payload.get("notes", [])) if isinstance(payload.get("notes"), list) else 0,
            "planner_instance_id": payload.get("planner_instance_id"),
            "plan_id": payload.get("plan_id"),
            "revision": payload.get("revision"),
            "world_revision": payload.get("world_revision"),
        }

    def _on_parameters_changed(self, parameters) -> SetParametersResult:
        controlled_robot_id = self._controlled_robot_id
        execution_enabled = self._execution_enabled
        allow_plan_refresh_during_execution = self._allow_plan_refresh_during_execution
        require_tf_ready = self._require_tf_ready
        require_waypoint_in_map = self._require_waypoint_in_map
        waypoint_map_margin_m = self._waypoint_map_margin_m
        base_frame_id = self._base_frame_id
        tf_wait_timeout_sec = self._tf_wait_timeout_sec
        task_hold_sec = self._task_hold_sec
        plan_stale_sec = self._plan_stale_sec
        max_nav_retries_per_step = self._max_nav_retries_per_step

        for parameter in parameters:
            if parameter.name == "controlled_robot_id":
                controlled_robot_id = str(parameter.value).strip()
            elif parameter.name == "execution_enabled":
                execution_enabled = bool(parameter.value)
            elif parameter.name == "allow_plan_refresh_during_execution":
                allow_plan_refresh_during_execution = bool(parameter.value)
            elif parameter.name == "require_tf_ready":
                require_tf_ready = bool(parameter.value)
            elif parameter.name == "require_waypoint_in_map":
                require_waypoint_in_map = bool(parameter.value)
            elif parameter.name == "waypoint_map_margin_m":
                waypoint_map_margin_m = max(0.0, float(parameter.value))
            elif parameter.name == "base_frame_id":
                base_frame_id = str(parameter.value).strip()
            elif parameter.name == "tf_wait_timeout_sec":
                tf_wait_timeout_sec = max(0.0, float(parameter.value))
            elif parameter.name == "task_hold_sec":
                task_hold_sec = max(0.0, float(parameter.value))
            elif parameter.name == "plan_stale_sec":
                plan_stale_sec = max(1.0, float(parameter.value))
            elif parameter.name == "max_nav_retries_per_step":
                max_nav_retries_per_step = max(0, int(parameter.value))

        if not controlled_robot_id:
            return SetParametersResult(successful=False, reason="controlled_robot_id must be non-empty")

        self._controlled_robot_id = controlled_robot_id
        self._execution_enabled = execution_enabled
        self._allow_plan_refresh_during_execution = allow_plan_refresh_during_execution
        self._require_tf_ready = require_tf_ready
        self._require_waypoint_in_map = require_waypoint_in_map
        self._waypoint_map_margin_m = waypoint_map_margin_m
        self._base_frame_id = base_frame_id or "base_link"
        self._tf_wait_timeout_sec = tf_wait_timeout_sec
        self._task_hold_sec = task_hold_sec
        self._plan_stale_sec = plan_stale_sec
        self._max_nav_retries_per_step = max_nav_retries_per_step
        self.get_logger().info(
            "Updated executor parameters: robot_id=%s enabled=%s allow_refresh=%s require_tf=%s task_hold_sec=%.2f plan_stale_sec=%.2f max_retries=%d"
            % (
                self._controlled_robot_id,
                self._execution_enabled,
                self._allow_plan_refresh_during_execution,
                self._require_tf_ready,
                self._task_hold_sec,
                self._plan_stale_sec,
                self._max_nav_retries_per_step,
            )
        )
        return SetParametersResult(successful=True)

    def _publish_status(self, *, planner_state: str, reason: str, active_action: str = "") -> None:
        payload = self._build_status(
            planner_state=planner_state,
            reason=reason,
            active_action=active_action,
        )
        msg = String()
        msg.data = json.dumps(payload, ensure_ascii=True)
        self._status_pub.publish(msg)

        status_key = (planner_state, reason, active_action)
        if status_key != self._last_status_key:
            self.get_logger().info(
                "MILP executor status: state=%s reason=%s action=%s"
                % (planner_state, reason, active_action)
            )
            self._last_status_key = status_key

    def _on_plan(self, msg: String) -> None:
        payload = self._parse_payload(msg.data)
        if payload is None:
            return

        acceptance = self._revision_gate.evaluate(payload)
        if not acceptance.accepted:
            self.get_logger().info("Ignoring plan: %s" % acceptance.reason)
            return

        assignments = payload.get("tasks")
        if not isinstance(assignments, list):
            assignments = payload.get("assignments")
        if not isinstance(assignments, list):
            return

        filtered = [
            item for item in assignments
            if isinstance(item, dict)
            and str(item.get("robot", "")).strip() == self._controlled_robot_id
        ]
        filtered.sort(
            key=lambda item: (
                self._safe_float(item.get("start")),
                str(item.get("task", "")),
            )
        )

        self._latest_plan_payload = payload
        self._latest_plan_monotonic = time.monotonic()
        signature = self._assignment_signature(filtered)

        if self._pending_goal or self._active_goal_handle is not None or self._execution_queue:
            self._pending_plan_assignments = filtered
            self._pending_plan_identity = acceptance.identity
            self.get_logger().info(
                "Received revision %d during execution; deferring it until the current queue completes (%d assignments)"
                % (
                    acceptance.identity.revision,
                    len(filtered),
                )
            )
            return

        self._apply_plan(filtered, signature, acceptance.identity)

    def _on_map(self, msg: OccupancyGrid) -> None:
        resolution = float(msg.info.resolution)
        width = int(msg.info.width)
        height = int(msg.info.height)
        x_min = float(msg.info.origin.position.x)
        y_min = float(msg.info.origin.position.y)
        self._latest_map_bounds = MapBounds(
            frame_id=str(msg.header.frame_id or "map"),
            x_min=x_min,
            x_max=x_min + width * resolution,
            y_min=y_min,
            y_max=y_min + height * resolution,
            width=width,
            height=height,
            resolution=resolution,
        )

    def _apply_plan(
        self,
        assignments: list[dict[str, Any]],
        signature: tuple[tuple[str, float, float], ...],
        identity,
    ) -> None:
        self._execution_queue = self._expand_assignments(assignments)
        self._active_plan_signature = signature
        self._active_plan_identity = identity
        self._pending_plan_assignments = None
        self._pending_plan_identity = None
        self._hold_until_monotonic = None
        if not self._completed_task_ids:
            self._completed_step_keys.clear()
            self._nav_retry_counts.clear()
            self._dispatched_goal_history.clear()
            self._terminal_failure_reason = None
        self._active_step = None
        self.get_logger().info(
            "Loaded MILP execution queue for robot %s: %s"
            % (
                self._controlled_robot_id,
                " -> ".join(
                    f"{step.task_id}:{step.step_name}@{step.location_id}"
                    for step in self._execution_queue
                )
                or "<empty>",
            )
        )

    def _expand_assignments(self, assignments: list[dict[str, Any]]) -> list[TaskStep]:
        specs = self._expand_execution_assignments(
            assignments,
            robot_id=self._controlled_robot_id,
            task_registry=self._task_map,
            completed_step_keys=self._completed_step_keys,
        )
        return [
            TaskStep(
                task_id=spec.task_id,
                task_type=spec.task_type,
                location_id=spec.location_id,
                step_name=spec.step_name,
                attempt=spec.attempt,
            )
            for spec in specs
        ]

    @staticmethod
    def _step_key(step: TaskStep) -> tuple[str, str, int]:
        return (step.task_id, step.step_name, step.attempt)

    def _build_nav_goal(self, waypoint: Waypoint) -> NavigateToPose.Goal:
        pose = PoseStamped()
        pose.header.frame_id = waypoint.frame_id
        pose.header.stamp = self.get_clock().now().to_msg()
        pose.pose.position.x = waypoint.x
        pose.pose.position.y = waypoint.y
        pose.pose.position.z = waypoint.z
        pose.pose.orientation.x = waypoint.qx
        pose.pose.orientation.y = waypoint.qy
        pose.pose.orientation.z = waypoint.qz
        pose.pose.orientation.w = waypoint.qw

        goal = NavigateToPose.Goal()
        goal.pose = pose
        goal.behavior_tree = ""
        return goal

    def _tf_ready(self, waypoint: Waypoint) -> bool:
        if not self._require_tf_ready:
            return True
        try:
            self._tf_buffer.lookup_transform(
                waypoint.frame_id,
                self._base_frame_id,
                Time(),
                timeout=Duration(seconds=self._tf_wait_timeout_sec),
            )
        except TransformException:
            return False
        return True

    def _waypoint_in_map(self, waypoint: Waypoint) -> tuple[bool, str]:
        if not self._require_waypoint_in_map:
            return True, "map_bounds_check_disabled"
        if self._latest_map_bounds is None:
            return False, "waiting_for_map_bounds"
        if waypoint.frame_id != self._latest_map_bounds.frame_id:
            return False, f"waypoint_frame_mismatch:{waypoint.frame_id}!={self._latest_map_bounds.frame_id}"

        margin = self._waypoint_map_margin_m
        x_min = self._latest_map_bounds.x_min + margin
        x_max = self._latest_map_bounds.x_max - margin
        y_min = self._latest_map_bounds.y_min + margin
        y_max = self._latest_map_bounds.y_max - margin
        inside = x_min <= waypoint.x <= x_max and y_min <= waypoint.y <= y_max
        reason = (
            "waypoint_inside_map_bounds"
            if inside
            else (
                "waypoint_outside_map_bounds:"
                f"x={waypoint.x:.3f},y={waypoint.y:.3f},"
                f"x_range=[{x_min:.3f},{x_max:.3f}],"
                f"y_range=[{y_min:.3f},{y_max:.3f}]"
            )
        )
        return inside, reason

    def _dispatch_next_step(self) -> None:
        if not self._execution_queue:
            self._active_step = None
            self._publish_status(planner_state="completed", reason="execution_queue_complete")
            return

        next_step = self._execution_queue[0]
        waypoint = self._waypoints.get(next_step.location_id)
        if waypoint is None:
            self._active_step = next_step
            self._publish_status(
                planner_state="action_failed",
                reason=f"missing_waypoint:{next_step.location_id}",
                active_action=next_step.task_id,
            )
            self._execution_queue.pop(0)
            return

        self._active_step = next_step
        waypoint_ok, waypoint_reason = self._waypoint_in_map(waypoint)
        if not waypoint_ok:
            self._publish_status(
                planner_state="holding",
                reason=waypoint_reason,
                active_action=next_step.task_id,
            )
            return

        if not self._tf_ready(waypoint):
            self._publish_status(
                planner_state="holding",
                reason=f"tf_unavailable:{waypoint.frame_id}->{self._base_frame_id}",
                active_action=next_step.task_id,
            )
            return

        if not self._action_client.wait_for_server(timeout_sec=0.2):
            self._publish_status(
                planner_state="navigation_failed",
                reason="nav2_action_unavailable",
                active_action=next_step.task_id,
            )
            return

        self._pending_goal = True
        self._dispatched_goal_history.append(
            {
                "task_id": next_step.task_id,
                "step_name": next_step.step_name,
                "location_id": next_step.location_id,
                "x": waypoint.x,
                "y": waypoint.y,
                "frame_id": waypoint.frame_id,
                "dispatch_index": len(self._dispatched_goal_history) + 1,
                "attempt": next_step.attempt,
                "nav_retry_index": self._nav_retry_counts.get(self._step_key(next_step), 0),
                "plan_revision": (
                    self._active_plan_identity.revision
                    if self._active_plan_identity is not None
                    else None
                ),
            }
        )
        send_future = self._action_client.send_goal_async(
            self._build_nav_goal(waypoint),
            feedback_callback=self._on_feedback,
        )
        send_future.add_done_callback(self._on_goal_response)
        self._publish_status(
            planner_state="executing",
            reason=f"dispatching:{next_step.location_id}",
            active_action=next_step.task_id,
        )

    def _on_feedback(self, feedback_msg) -> None:
        feedback = feedback_msg.feedback
        self.get_logger().debug(
            "MILP executor feedback: task=%s distance_remaining=%.3f recoveries=%d"
            % (
                self._active_step.task_id if self._active_step is not None else "",
                feedback.distance_remaining,
                feedback.number_of_recoveries,
            )
        )

    def _on_goal_response(self, future) -> None:
        self._pending_goal = False
        try:
            goal_handle = future.result()
        except Exception as exc:  # noqa: BLE001 - ROS futures surface transport errors here.
            reason = f"nav2_goal_send_error:{type(exc).__name__}"
            self._terminal_failure_reason = (
                f"{self._active_step.task_id}:{self._active_step.step_name}:{reason}"
                if self._active_step is not None
                else reason
            )
            self._publish_status(
                planner_state="action_failed",
                reason=self._terminal_failure_reason,
                active_action=self._active_step.task_id if self._active_step is not None else "",
            )
            self._active_goal_handle = None
            return
        if not goal_handle.accepted:
            self._terminal_failure_reason = (
                f"{self._active_step.task_id}:{self._active_step.step_name}:nav2_goal_rejected"
                if self._active_step is not None
                else "nav2_goal_rejected"
            )
            self._publish_status(
                planner_state="action_failed",
                reason=self._terminal_failure_reason,
                active_action=self._active_step.task_id if self._active_step is not None else "",
            )
            self._active_goal_handle = None
            return

        self._active_goal_handle = goal_handle
        result_future = goal_handle.get_result_async()
        result_future.add_done_callback(self._on_goal_result)

    def _on_goal_result(self, future) -> None:
        try:
            result = future.result()
        except Exception as exc:  # noqa: BLE001 - ROS futures surface transport errors here.
            finished_step = self._active_step
            self._active_goal_handle = None
            reason = f"nav2_result_error:{type(exc).__name__}"
            self._terminal_failure_reason = (
                f"{finished_step.task_id}:{finished_step.step_name}:{reason}"
                if finished_step is not None
                else reason
            )
            self._publish_status(
                planner_state="action_failed",
                reason=self._terminal_failure_reason,
                active_action=finished_step.task_id if finished_step is not None else "",
            )
            return
        status = int(result.status)
        finished_step = self._active_step
        self._active_goal_handle = None

        if finished_step is None:
            return

        if status != GoalStatus.STATUS_SUCCEEDED:
            step_key = self._step_key(finished_step)
            retry_count = self._nav_retry_counts.get(step_key, 0)
            if retry_count < self._max_nav_retries_per_step:
                self._nav_retry_counts[step_key] = retry_count + 1
                self._publish_status(
                    planner_state="navigation_failed",
                    reason=f"nav2_status:{status}:retry:{retry_count + 1}",
                    active_action=finished_step.task_id,
                )
                return
            self._publish_status(
                planner_state="action_failed",
                reason=f"nav2_status:{status}:retry_limit_reached",
                active_action=finished_step.task_id,
            )
            self._terminal_failure_reason = f"{finished_step.task_id}:{finished_step.step_name}:nav2_status:{status}"
            return

        self._execution_queue.pop(0)
        self._completed_step_keys.add(self._step_key(finished_step))
        next_task_id = self._execution_queue[0].task_id if self._execution_queue else None
        if next_task_id != finished_step.task_id:
            self._completed_task_ids.add(finished_step.task_id)
            self._hold_until_monotonic = time.monotonic() + self._task_hold_sec
            self._publish_status(
                planner_state="holding",
                reason=f"task_completed:{finished_step.task_id}",
                active_action=finished_step.task_id,
            )
        else:
            self._dispatch_next_step()

    def _maybe_apply_pending_plan(self) -> None:
        if not self._can_apply_deferred_revision(
            has_pending_plan=self._pending_plan_assignments is not None,
            queue_length=len(self._execution_queue),
            goal_pending=self._pending_goal,
            goal_active=self._active_goal_handle is not None,
        ):
            return
        signature = self._assignment_signature(self._pending_plan_assignments)
        self._apply_plan(
            self._pending_plan_assignments,
            signature,
            self._pending_plan_identity,
        )

    def _on_timer(self) -> None:
        if not self._execution_enabled:
            self._publish_status(planner_state="idle", reason="execution_disabled")
            return

        if self._terminal_failure_reason is not None:
            self._publish_status(
                planner_state="action_failed",
                reason=self._terminal_failure_reason,
                active_action=self._active_step.task_id if self._active_step is not None else "",
            )
            return

        self._maybe_apply_pending_plan()

        if self._latest_plan_monotonic is None:
            self._publish_status(planner_state="idle", reason="waiting_for_plan")
            return

        if (
            not self._execution_queue
            and (time.monotonic() - self._latest_plan_monotonic) > self._plan_stale_sec
        ):
            self._publish_status(planner_state="holding", reason="plan_stale")
            return

        if self._pending_goal or self._active_goal_handle is not None:
            self._publish_status(
                planner_state="executing",
                reason="nav2_goal_active",
                active_action=self._active_step.task_id if self._active_step is not None else "",
            )
            return

        if self._hold_until_monotonic is not None and time.monotonic() < self._hold_until_monotonic:
            self._publish_status(
                planner_state="holding",
                reason="task_hold_interval",
                active_action=self._active_step.task_id if self._active_step is not None else "",
            )
            return

        self._hold_until_monotonic = None
        self._dispatch_next_step()


def main(args=None) -> None:
    rclpy.init(args=args)
    node: MilpPlanExecutorNode | None = None
    try:
        node = MilpPlanExecutorNode()
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        if node is not None:
            node.destroy_node()
        time.sleep(0.05)
        if rclpy.ok():
            rclpy.shutdown()
