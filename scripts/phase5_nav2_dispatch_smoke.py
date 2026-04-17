#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone

import rclpy
from action_msgs.msg import GoalStatus, GoalStatusArray
from nav2_msgs.action import NavigateToPose
from rclpy.action import ActionClient
from rclpy.node import Node
from std_msgs.msg import String


ACTIVE_STATUSES = {
    GoalStatus.STATUS_ACCEPTED,
    GoalStatus.STATUS_EXECUTING,
}
CANCEL_STATUSES = {
    GoalStatus.STATUS_CANCELING,
    GoalStatus.STATUS_CANCELED,
}
TERMINAL_STATUSES = {
    GoalStatus.STATUS_SUCCEEDED,
    GoalStatus.STATUS_CANCELED,
    GoalStatus.STATUS_ABORTED,
}


@dataclass
class StatusSnapshot:
    goal_id: str
    status: int


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _goal_id_hex(status) -> str:
    return bytes(status.goal_info.goal_id.uuid).hex()


def _status_name(status: int) -> str:
    names = {
        GoalStatus.STATUS_UNKNOWN: "UNKNOWN",
        GoalStatus.STATUS_ACCEPTED: "ACCEPTED",
        GoalStatus.STATUS_EXECUTING: "EXECUTING",
        GoalStatus.STATUS_CANCELING: "CANCELING",
        GoalStatus.STATUS_SUCCEEDED: "SUCCEEDED",
        GoalStatus.STATUS_CANCELED: "CANCELED",
        GoalStatus.STATUS_ABORTED: "ABORTED",
    }
    return names.get(status, f"UNRECOGNIZED_{status}")


class Phase5Nav2DispatchSmoke(Node):
    def __init__(self, args: argparse.Namespace) -> None:
        super().__init__("phase5_nav2_dispatch_smoke")
        self.args = args
        self._request_pub = self.create_publisher(String, args.request_topic, 10)
        self._status_sub = self.create_subscription(
            GoalStatusArray,
            f"{args.nav2_action}/_action/status",
            self._on_status,
            10,
        )
        self._action_client = ActionClient(self, NavigateToPose, args.nav2_action)
        self._latest_status: dict[str, int] = {}
        self._tracked_goal_id: str | None = None
        self._baseline_goal_ids: set[str] = set()
        self._terminal_before_cancel_logged = False

    def _on_status(self, msg: GoalStatusArray) -> None:
        for status in msg.status_list:
            self._latest_status[_goal_id_hex(status)] = int(status.status)

    def _spin_until(self, predicate, timeout_sec: float, label: str) -> bool:
        deadline = time.monotonic() + timeout_sec
        while rclpy.ok() and time.monotonic() < deadline:
            rclpy.spin_once(self, timeout_sec=0.1)
            if predicate():
                return True
        self.get_logger().error("Timed out waiting for %s" % label)
        return False

    def _spin_for(self, duration_sec: float) -> None:
        deadline = time.monotonic() + duration_sec
        while rclpy.ok() and time.monotonic() < deadline:
            rclpy.spin_once(self, timeout_sec=0.1)

    def _wait_for_request_subscribers(self) -> bool:
        return self._spin_until(
            lambda: self._request_pub.get_subscription_count() >= self.args.min_request_subscribers,
            self.args.ready_timeout_sec,
            "request subscribers on %s" % self.args.request_topic,
        )

    def _wait_for_nav2_action_server(self) -> bool:
        deadline = time.monotonic() + self.args.ready_timeout_sec
        while rclpy.ok() and time.monotonic() < deadline:
            if self._action_client.wait_for_server(timeout_sec=0.2):
                return True
            rclpy.spin_once(self, timeout_sec=0.1)
        self.get_logger().error("Timed out waiting for Nav2 action server %s" % self.args.nav2_action)
        return False

    def _publish_request(self, requested_action: str, reason: str) -> None:
        payload = {
            "ts": _utc_timestamp(),
            "role": "phase5_nav2_dispatch_smoke",
            "planner_mode": self.args.planner_mode,
            "requested_action": requested_action,
            "reason": reason,
        }
        msg = String()
        msg.data = json.dumps(payload, ensure_ascii=True, separators=(",", ":"))
        self._request_pub.publish(msg)
        self.get_logger().info("Published request: %s" % msg.data)

    def _active_goal_snapshot(self) -> StatusSnapshot | None:
        for goal_id, status in self._latest_status.items():
            if goal_id not in self._baseline_goal_ids and status in ACTIVE_STATUSES:
                return StatusSnapshot(goal_id=goal_id, status=status)
        return None

    def _tracked_goal_status(self) -> int | None:
        if self._tracked_goal_id is None:
            return None
        return self._latest_status.get(self._tracked_goal_id)

    def _wait_for_active_goal_after_trigger(self) -> bool:
        self._spin_for(0.5)
        self._baseline_goal_ids = set(self._latest_status)
        self.get_logger().info("Recorded %d pre-existing Nav2 goal status ids" % len(self._baseline_goal_ids))

        for attempt in range(1, self.args.trigger_attempts + 1):
            self._publish_request("trigger_safe_mode", self.args.trigger_reason)
            if self._spin_until(
                lambda: self._active_goal_snapshot() is not None,
                self.args.active_goal_timeout_sec,
                "Nav2 active goal after trigger attempt %d" % attempt,
            ):
                snapshot = self._active_goal_snapshot()
                if snapshot is None:
                    return False
                self._tracked_goal_id = snapshot.goal_id
                self.get_logger().info(
                    "Observed Nav2 active goal: goal_id=%s status=%s"
                    % (snapshot.goal_id, _status_name(snapshot.status))
                )
                return True
            if attempt < self.args.trigger_attempts:
                self.get_logger().warning(
                    "No active goal observed after trigger attempt %d; retrying" % attempt
                )
                time.sleep(self.args.retry_sleep_sec)
        return False

    def _wait_for_cancel_after_hold(self) -> bool:
        if self.args.hold_delay_sec > 0:
            self.get_logger().info("Waiting %.2fs before hold request" % self.args.hold_delay_sec)
            end_time = time.monotonic() + self.args.hold_delay_sec
            while rclpy.ok() and time.monotonic() < end_time:
                rclpy.spin_once(self, timeout_sec=0.1)

        for attempt in range(1, self.args.hold_attempts + 1):
            self._publish_request("hold", self.args.hold_reason)
            if self._spin_until(
                self._tracked_goal_is_canceling,
                self.args.cancel_timeout_sec,
                "canceling/canceled status after hold attempt %d" % attempt,
            ):
                status = self._tracked_goal_status()
                self.get_logger().info(
                    "Observed tracked goal status after hold: goal_id=%s status=%s"
                    % (self._tracked_goal_id, _status_name(status if status is not None else -1))
                )
                return True
            if attempt < self.args.hold_attempts:
                self.get_logger().warning(
                    "No canceling/canceled status observed after hold attempt %d; retrying" % attempt
                )
                time.sleep(self.args.retry_sleep_sec)
        return False

    def _tracked_goal_is_canceling(self) -> bool:
        status = self._tracked_goal_status()
        if status is None:
            return False
        if status in TERMINAL_STATUSES and status not in CANCEL_STATUSES:
            if not self._terminal_before_cancel_logged:
                self._terminal_before_cancel_logged = True
                self.get_logger().error(
                    "Tracked goal reached terminal status before cancel: goal_id=%s status=%s"
                    % (self._tracked_goal_id, _status_name(status))
                )
            return False
        return status in CANCEL_STATUSES

    def run(self) -> int:
        self.get_logger().info(
            "Phase 5 Nav2 dispatch smoke starting: request_topic=%s nav2_action=%s"
            % (self.args.request_topic, self.args.nav2_action)
        )
        if not self._wait_for_request_subscribers():
            return 2
        self.get_logger().info(
            "Request subscribers ready: count=%d" % self._request_pub.get_subscription_count()
        )

        if not self._wait_for_nav2_action_server():
            return 3
        self.get_logger().info("Nav2 action server ready: %s" % self.args.nav2_action)

        if not self._wait_for_active_goal_after_trigger():
            return 4

        if self.args.skip_hold:
            self.get_logger().info("Skipping hold phase by request")
            return 0

        if not self._wait_for_cancel_after_hold():
            return 5

        self.get_logger().info("Phase 5 Nav2 dispatch smoke completed")
        return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Runtime smoke helper for Phase 5: publish trigger_safe_mode, wait for a "
            "Nav2 active goal, then publish hold and wait for cancel/terminal status."
        )
    )
    parser.add_argument("--request-topic", default="/task_planner/request")
    parser.add_argument("--nav2-action", default="/navigate_to_pose")
    parser.add_argument("--planner-mode", default="plansys2_placeholder")
    parser.add_argument("--trigger-reason", default="fall_detected")
    parser.add_argument("--hold-reason", default="planner_hold")
    parser.add_argument("--min-request-subscribers", type=int, default=2)
    parser.add_argument("--ready-timeout-sec", type=float, default=30.0)
    parser.add_argument("--active-goal-timeout-sec", type=float, default=8.0)
    parser.add_argument("--cancel-timeout-sec", type=float, default=8.0)
    parser.add_argument("--trigger-attempts", type=int, default=3)
    parser.add_argument("--hold-attempts", type=int, default=3)
    parser.add_argument("--retry-sleep-sec", type=float, default=1.0)
    parser.add_argument("--hold-delay-sec", type=float, default=1.0)
    parser.add_argument("--skip-hold", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    rclpy.init()
    node = Phase5Nav2DispatchSmoke(args)
    try:
        return node.run()
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
