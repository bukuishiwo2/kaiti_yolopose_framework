from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import rclpy
from nav_msgs.msg import OccupancyGrid
from rclpy.node import Node
from std_msgs.msg import String


def _default_project_root() -> str:
    return str(Path(__file__).resolve().parents[4])


class SpatialStateNode(Node):
    def __init__(self) -> None:
        super().__init__("spatial_state_node")
        self.declare_parameter("project_root", _default_project_root())
        self.declare_parameter("planner_config_path", "configs/planner_minimal_experiment.yaml")
        self.declare_parameter("region_config_path", "configs/planner_regions.yaml")
        self.declare_parameter("spatial_state_topic", "/planning/spatial_state")
        self.declare_parameter("costmap_topic", "/global_costmap/costmap")
        self.declare_parameter("publish_period_sec", 1.0)
        self.declare_parameter("costmap_timeout_sec", 5.0)
        self.declare_parameter("use_costmap_topic", True)

        self._project_root = Path(str(self.get_parameter("project_root").value)).resolve()
        src_root = self._project_root / "src"
        if str(src_root) not in sys.path:
            sys.path.insert(0, str(src_root))

        from kaiti_planning.models import load_problem_from_yaml
        from kaiti_planning.spatial_state import SpatialStateEstimator, load_region_specs

        cfg_path = self._project_root / str(self.get_parameter("planner_config_path").value)
        region_path = self._project_root / str(self.get_parameter("region_config_path").value)
        problem = load_problem_from_yaml(cfg_path)
        region_specs = load_region_specs(region_path)
        self._estimator = SpatialStateEstimator(problem, region_specs=region_specs)
        self._topic = str(self.get_parameter("spatial_state_topic").value)
        self._period = float(self.get_parameter("publish_period_sec").value)
        self._costmap_topic = str(self.get_parameter("costmap_topic").value)
        self._costmap_timeout_sec = float(self.get_parameter("costmap_timeout_sec").value)
        self._use_costmap_topic = bool(self.get_parameter("use_costmap_topic").value)
        self._publisher = self.create_publisher(String, self._topic, 10)
        self._timer = self.create_timer(self._period, self._on_timer)
        self._last_costmap_monotonic: float | None = None
        self._last_snapshot_source = "bootstrap"

        if self._use_costmap_topic:
            self.create_subscription(OccupancyGrid, self._costmap_topic, self._on_costmap, 10)

    @staticmethod
    def _timestamp() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _publish_snapshot(self, *, source: str) -> None:
        payload = {
            "ts": self._timestamp(),
            "role": "spatial_state_node",
            **self._estimator.snapshot(source=source).to_dict(),
        }
        msg = String()
        msg.data = json.dumps(payload, ensure_ascii=True)
        self._publisher.publish(msg)

    def _on_costmap(self, msg: OccupancyGrid) -> None:
        self._last_costmap_monotonic = time.monotonic()
        current_time = float(self.get_clock().now().nanoseconds) / 1_000_000_000.0
        self._estimator.update_from_occupancy_grid(
            grid_data=list(msg.data),
            width=int(msg.info.width),
            height=int(msg.info.height),
            resolution=float(msg.info.resolution),
            origin_x=float(msg.info.origin.position.x),
            origin_y=float(msg.info.origin.position.y),
            current_time=current_time,
            source=f"costmap:{self._costmap_topic}",
        )
        self._last_snapshot_source = f"costmap:{self._costmap_topic}"
        self._publish_snapshot(source=self._last_snapshot_source)

    def _on_timer(self) -> None:
        if not self._use_costmap_topic:
            self._publish_snapshot(source="ros2_periodic_no_costmap")
            return

        if self._last_costmap_monotonic is None:
            self._publish_snapshot(source="waiting_for_costmap")
            return

        if (time.monotonic() - self._last_costmap_monotonic) > self._costmap_timeout_sec:
            self._publish_snapshot(source="costmap_timeout")
            return

        self._publish_snapshot(source=self._last_snapshot_source)


def main(args=None) -> None:
    rclpy.init(args=args)
    node: SpatialStateNode | None = None
    try:
        node = SpatialStateNode()
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        if node is not None:
            node.destroy_node()
        time.sleep(0.05)
        if rclpy.ok():
            rclpy.shutdown()
