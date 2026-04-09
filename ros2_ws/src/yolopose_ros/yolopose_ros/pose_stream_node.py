from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import rclpy
from rclpy.node import Node
from std_msgs.msg import String


class PoseStreamNode(Node):
    """Bridge node: runs pose pipeline and publishes stable person-presence events."""

    def __init__(self) -> None:
        super().__init__("pose_stream_node")

        self.declare_parameter("project_root", "/home/yhc/kaiti_yolopose_framework")
        self.declare_parameter("infer_config", "configs/infer_pose_stream.yaml")
        self.declare_parameter("event_topic", "/yolopose/events")

        project_root = Path(self.get_parameter("project_root").value)
        infer_cfg = self.get_parameter("infer_config").value
        self._event_topic = self.get_parameter("event_topic").value

        sys.path.insert(0, str(project_root / "src"))
        from yolopose.core.config import abs_path, load_yaml  # pylint: disable=import-error
        from yolopose.pipeline.runner import PoseRunner  # pylint: disable=import-error

        cfg_path = project_root / infer_cfg if not Path(infer_cfg).is_absolute() else Path(infer_cfg)
        cfg = load_yaml(cfg_path)
        cfg["source"] = abs_path(project_root, cfg.get("source"))
        cfg["model"] = abs_path(project_root, cfg.get("model"))

        self.publisher = self.create_publisher(String, self._event_topic, 10)
        self.runner = PoseRunner(cfg=cfg, project_root=project_root)

    def run(self) -> None:
        # Minimal v1 behavior: run pipeline and publish a terminal status message.
        self.get_logger().info("Starting YOLO pose pipeline...")
        self.runner.run()
        msg = String()
        msg.data = json.dumps({"status": "finished"}, ensure_ascii=True)
        self.publisher.publish(msg)


def main(args=None) -> None:
    rclpy.init(args=args)
    node = PoseStreamNode()
    try:
        node.run()
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()
