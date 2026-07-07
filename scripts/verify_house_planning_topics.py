#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from typing import Any

import rclpy
from rclpy.node import Node
from std_msgs.msg import String


@dataclass
class TopicExpectation:
    topic: str
    required_keys: tuple[str, ...]


DEFAULT_EXPECTATIONS = [
    TopicExpectation(
        "/planning/semantic_state",
        ("ts", "semantic_state", "predicate", "quality_score"),
    ),
    TopicExpectation("/planning/spatial_state", ("ts", "resource_states", "source")),
    TopicExpectation("/planning/plan", ("ts", "solver_status", "assignments", "plan_kind")),
    TopicExpectation("/planning/execution_feedback", ("ts", "feedback_state", "reason")),
]


class PlanningTopicVerifier(Node):
    def __init__(self, args: argparse.Namespace) -> None:
        super().__init__("planning_topic_verifier")
        self.args = args
        self._expectations = DEFAULT_EXPECTATIONS
        self._latest_payloads: dict[str, dict[str, Any]] = {}
        self._message_counts: dict[str, int] = {exp.topic: 0 for exp in self._expectations}
        for expectation in self._expectations:
            self.create_subscription(
                String,
                expectation.topic,
                self._make_callback(expectation.topic),
                10,
            )

    def _make_callback(self, topic: str):
        def _callback(msg: String) -> None:
            try:
                parsed = json.loads(msg.data)
            except json.JSONDecodeError:
                parsed = {"raw": msg.data}
            if isinstance(parsed, dict):
                self._latest_payloads[topic] = parsed
            else:
                self._latest_payloads[topic] = {"raw": parsed}
            self._message_counts[topic] += 1

        return _callback

    def run(self) -> int:
        deadline = time.monotonic() + self.args.timeout_sec
        while rclpy.ok() and time.monotonic() < deadline:
            rclpy.spin_once(self, timeout_sec=0.2)
            if all(topic.topic in self._latest_payloads for topic in self._expectations):
                break

        missing_topics = [
            exp.topic for exp in self._expectations if exp.topic not in self._latest_payloads
        ]
        if missing_topics:
            print(
                json.dumps(
                    {
                        "ok": False,
                        "reason": "missing_topics",
                        "missing_topics": missing_topics,
                        "message_counts": self._message_counts,
                    },
                    ensure_ascii=True,
                    indent=2,
                )
            )
            return 1

        key_errors: dict[str, list[str]] = {}
        for expectation in self._expectations:
            payload = self._latest_payloads[expectation.topic]
            missing_keys = [key for key in expectation.required_keys if key not in payload]
            if missing_keys:
                key_errors[expectation.topic] = missing_keys

        result = {
            "ok": not key_errors,
            "message_counts": self._message_counts,
            "topics": {
                exp.topic: {
                    "required_keys": list(exp.required_keys),
                    "present_keys": sorted(self._latest_payloads[exp.topic].keys()),
                }
                for exp in self._expectations
            },
        }
        if key_errors:
            result["reason"] = "missing_keys"
            result["missing_keys"] = key_errors
            print(json.dumps(result, ensure_ascii=True, indent=2))
            return 2

        print(json.dumps(result, ensure_ascii=True, indent=2))
        return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify that the house planning precheck publishes the four /planning/* topics."
    )
    parser.add_argument("--timeout-sec", type=float, default=20.0)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    rclpy.init()
    node = PlanningTopicVerifier(args)
    try:
        return node.run()
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
