from __future__ import annotations

import time

import rclpy
from geometry_msgs.msg import PoseStamped
from nav2_msgs.action import NavigateToPose
from rcl_interfaces.msg import ParameterDescriptor
from rclpy.action import ActionClient
from rclpy.node import Node
from std_msgs.msg import String

from yolopose_ros.planner_nav2_dispatcher_logic import (
    ACTION_GOAL_MAP,
    DEFAULT_NEED_REOBSERVE_REASONS,
    DEFAULT_TRIGGER_SAFE_MODE_REASONS,
    DispatcherConfig,
    DispatchDecision,
    DispatchDecisionKind,
    NamedGoal,
    as_bool,
    as_normalized_set,
    evaluate_dispatch_request,
    parse_goal_pose,
    parse_request_payload,
)


class PlannerNav2DispatcherNode(Node):
    """Controlled bridge from planner requests to Nav2 goals."""

    def __init__(self) -> None:
        super().__init__("planner_nav2_dispatcher_node")

        self.declare_parameter("planner_request_topic", "/task_planner/request")
        self.declare_parameter("nav2_action_name", "/navigate_to_pose")
        self.declare_parameter("dispatch_enabled", False)
        self.declare_parameter(
            "allowed_actions",
            "",
            ParameterDescriptor(dynamic_typing=True),
        )
        self.declare_parameter("goal_frame_id", "map")
        self.declare_parameter("cooldown_sec", 5.0)
        self.declare_parameter(
            "safe_mode_staging_pose_xyzw",
            [1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0],
        )
        self.declare_parameter(
            "reobserve_vantage_pose_xyzw",
            [0.5, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0],
        )
        self.declare_parameter("safe_mode_staging_frame_id", "map")
        self.declare_parameter("reobserve_vantage_frame_id", "map")
        self.declare_parameter("safe_mode_staging_behavior_tree", "")
        self.declare_parameter("reobserve_vantage_behavior_tree", "")
        self.declare_parameter(
            "trigger_safe_mode_allowed_reasons",
            sorted(DEFAULT_TRIGGER_SAFE_MODE_REASONS),
        )
        self.declare_parameter(
            "need_reobserve_allowed_reasons",
            sorted(DEFAULT_NEED_REOBSERVE_REASONS),
        )

        self._request_topic = str(self.get_parameter("planner_request_topic").value)
        self._nav2_action_name = str(self.get_parameter("nav2_action_name").value)
        self._config = self._load_config()

        self._action_client = ActionClient(self, NavigateToPose, self._nav2_action_name)
        self._request_sub = self.create_subscription(
            String, self._request_topic, self._on_request, 10
        )

        self._active_goal_handle = None
        self._pending_goal = False
        self._last_signature: tuple[str, str, str] | None = None
        self._last_dispatch_monotonic: float | None = None
        self._last_log_key: tuple[str, str, str, str] | None = None

        self.get_logger().info(
            "Planner Nav2 dispatcher ready: request_topic=%s nav2_action=%s "
            "dispatch_enabled=%s allowed_actions=%s goal_frame=%s"
            % (
                self._request_topic,
                self._nav2_action_name,
                self._config.dispatch_enabled,
                sorted(self._config.allowed_actions),
                self._config.goal_frame_id,
            )
        )

    def _load_config(self) -> DispatcherConfig:
        dispatch_enabled = as_bool(self.get_parameter("dispatch_enabled").value)
        allowed_actions = as_normalized_set(self.get_parameter("allowed_actions").value)
        goal_frame_id = str(self.get_parameter("goal_frame_id").value).strip() or "map"
        cooldown_sec = max(0.0, float(self.get_parameter("cooldown_sec").value))

        named_goals: dict[str, NamedGoal] = {}
        safe_goal = parse_goal_pose(
            name="safe_mode_staging",
            frame_id=str(self.get_parameter("safe_mode_staging_frame_id").value),
            pose_xyzw=self.get_parameter("safe_mode_staging_pose_xyzw").value,
            behavior_tree=str(self.get_parameter("safe_mode_staging_behavior_tree").value),
        )
        if safe_goal is not None:
            named_goals[safe_goal.name] = safe_goal

        reobserve_goal = parse_goal_pose(
            name="reobserve_vantage",
            frame_id=str(self.get_parameter("reobserve_vantage_frame_id").value),
            pose_xyzw=self.get_parameter("reobserve_vantage_pose_xyzw").value,
            behavior_tree=str(self.get_parameter("reobserve_vantage_behavior_tree").value),
        )
        if reobserve_goal is not None:
            named_goals[reobserve_goal.name] = reobserve_goal

        return DispatcherConfig(
            dispatch_enabled=dispatch_enabled,
            allowed_actions=allowed_actions,
            goal_frame_id=goal_frame_id,
            cooldown_sec=cooldown_sec,
            action_goal_map=dict(ACTION_GOAL_MAP),
            named_goals=named_goals,
            trigger_safe_mode_reasons=as_normalized_set(
                self.get_parameter("trigger_safe_mode_allowed_reasons").value
            ),
            need_reobserve_reasons=as_normalized_set(
                self.get_parameter("need_reobserve_allowed_reasons").value
            ),
        )

    def _active_or_pending_goal(self) -> bool:
        return self._pending_goal or self._active_goal_handle is not None

    def _log_decision(self, decision: DispatchDecision) -> None:
        log_key = (
            str(decision.kind.value),
            decision.requested_action,
            decision.reason,
            decision.decision_reason,
        )
        if log_key == self._last_log_key:
            return
        self._last_log_key = log_key

        if decision.kind == DispatchDecisionKind.DISPATCH:
            self.get_logger().info(
                "Nav2 dispatch accepted: action=%s reason=%s goal=%s"
                % (decision.requested_action, decision.reason, decision.goal_name)
            )
        elif decision.kind == DispatchDecisionKind.CANCEL:
            self.get_logger().info(
                "Nav2 dispatch cancel requested: action=%s reason=%s"
                % (decision.requested_action, decision.reason)
            )
        else:
            self.get_logger().info(
                "Nav2 dispatch rejected: action=%s reason=%s decision=%s goal=%s"
                % (
                    decision.requested_action,
                    decision.reason,
                    decision.decision_reason,
                    decision.goal_name or "",
                )
            )

    def _on_request(self, msg: String) -> None:
        request, error = parse_request_payload(msg.data)
        if request is None:
            decision = DispatchDecision(
                kind=DispatchDecisionKind.REJECT,
                requested_action="",
                reason="",
                decision_reason=error or "invalid_request",
            )
            self._log_decision(decision)
            return

        decision = evaluate_dispatch_request(
            request=request,
            config=self._config,
            now_monotonic=time.monotonic(),
            active_goal=self._active_or_pending_goal(),
            last_signature=self._last_signature,
            last_dispatch_monotonic=self._last_dispatch_monotonic,
        )
        self._log_decision(decision)

        if decision.kind == DispatchDecisionKind.CANCEL:
            self._cancel_active_goal()
            return
        if decision.kind == DispatchDecisionKind.DISPATCH and decision.goal is not None:
            self._send_goal(decision)

    def _build_nav2_goal(self, goal: NamedGoal) -> NavigateToPose.Goal:
        pose = PoseStamped()
        pose.header.frame_id = goal.frame_id
        pose.header.stamp = self.get_clock().now().to_msg()
        pose.pose.position.x = goal.x
        pose.pose.position.y = goal.y
        pose.pose.position.z = goal.z
        pose.pose.orientation.x = goal.qx
        pose.pose.orientation.y = goal.qy
        pose.pose.orientation.z = goal.qz
        pose.pose.orientation.w = goal.qw

        nav_goal = NavigateToPose.Goal()
        nav_goal.pose = pose
        nav_goal.behavior_tree = goal.behavior_tree
        return nav_goal

    def _send_goal(self, decision: DispatchDecision) -> None:
        if decision.goal is None or decision.signature is None:
            return
        if not self._action_client.wait_for_server(timeout_sec=0.1):
            self.get_logger().warning(
                "Nav2 action server unavailable: action=%s" % self._nav2_action_name
            )
            return

        self._pending_goal = True
        self._last_signature = decision.signature
        self._last_dispatch_monotonic = time.monotonic()
        send_future = self._action_client.send_goal_async(
            self._build_nav2_goal(decision.goal),
            feedback_callback=self._on_feedback,
        )
        send_future.add_done_callback(self._on_goal_response)

    def _on_goal_response(self, future) -> None:
        self._pending_goal = False
        goal_handle = future.result()
        if not goal_handle.accepted:
            self.get_logger().warning("Nav2 goal rejected by action server")
            self._active_goal_handle = None
            return

        self._active_goal_handle = goal_handle
        self.get_logger().info("Nav2 goal accepted by action server")
        result_future = goal_handle.get_result_async()
        result_future.add_done_callback(self._on_goal_result)

    def _on_feedback(self, feedback_msg) -> None:
        feedback = feedback_msg.feedback
        self.get_logger().debug(
            "Nav2 feedback: distance_remaining=%.3f recoveries=%d"
            % (feedback.distance_remaining, feedback.number_of_recoveries)
        )

    def _on_goal_result(self, future) -> None:
        result = future.result()
        self.get_logger().info("Nav2 goal finished: status=%s" % result.status)
        self._active_goal_handle = None

    def _cancel_active_goal(self) -> None:
        if self._active_goal_handle is None:
            return
        cancel_future = self._active_goal_handle.cancel_goal_async()
        cancel_future.add_done_callback(self._on_cancel_response)

    def _on_cancel_response(self, future) -> None:
        response = future.result()
        self.get_logger().info(
            "Nav2 goal cancel response: goals_canceling=%d"
            % len(response.goals_canceling)
        )
        if not response.goals_canceling:
            self._active_goal_handle = None


def main(args=None) -> None:
    rclpy.init(args=args)
    node: PlannerNav2DispatcherNode | None = None
    try:
        node = PlannerNav2DispatcherNode()
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        if node is not None:
            node.destroy_node()
        time.sleep(0.05)
        if rclpy.ok():
            rclpy.shutdown()
