from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import rclpy
from geometry_msgs.msg import PoseWithCovarianceStamped
from nav_msgs.msg import OccupancyGrid
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy
from std_msgs.msg import String


def _default_project_root() -> str:
    return str(Path(__file__).resolve().parents[4])


class SpatialStateNode(Node):
    def __init__(self) -> None:
        super().__init__("spatial_state_node")
        self.declare_parameter("project_root", _default_project_root())
        self.declare_parameter("planner_config_path", "configs/planner_minimal_experiment.yaml")
        self.declare_parameter("region_config_path", "configs/planner_regions_house.yaml")
        self.declare_parameter("spatial_state_topic", "/planning/spatial_state")
        self.declare_parameter("map_topic", "/map")
        self.declare_parameter("robot_pose_topic", "/amcl_pose")
        self.declare_parameter("costmap_topic", "/global_costmap/costmap")
        self.declare_parameter("publish_period_sec", 1.0)
        self.declare_parameter("costmap_timeout_sec", 5.0)
        self.declare_parameter("use_costmap_topic", True)
        self.declare_parameter("costmap_baseline_samples", 5)
        self.declare_parameter("self_footprint_clear_radius", 0.60)

        self._project_root = Path(str(self.get_parameter("project_root").value)).resolve()
        src_root = self._project_root / "src"
        if str(src_root) not in sys.path:
            sys.path.insert(0, str(src_root))

        from kaiti_planning.models import load_problem_from_yaml
        from kaiti_planning.spatial_state import (
            SpatialStateEstimator,
            clear_robot_footprint,
            compose_static_dynamic_grid,
            load_region_specs,
        )

        cfg_path = self._project_root / str(self.get_parameter("planner_config_path").value)
        region_path = self._project_root / str(self.get_parameter("region_config_path").value)
        problem = load_problem_from_yaml(cfg_path)
        region_specs = load_region_specs(region_path)
        self._estimator = SpatialStateEstimator(problem, region_specs=region_specs)
        self._topic = str(self.get_parameter("spatial_state_topic").value)
        self._period = float(self.get_parameter("publish_period_sec").value)
        self._map_topic = str(self.get_parameter("map_topic").value)
        self._robot_pose_topic = str(self.get_parameter("robot_pose_topic").value)
        self._costmap_topic = str(self.get_parameter("costmap_topic").value)
        self._costmap_timeout_sec = float(self.get_parameter("costmap_timeout_sec").value)
        self._use_costmap_topic = bool(self.get_parameter("use_costmap_topic").value)
        self._baseline_sample_target = max(
            1, int(self.get_parameter("costmap_baseline_samples").value)
        )
        self._compose_static_dynamic_grid = compose_static_dynamic_grid
        self._clear_robot_footprint = clear_robot_footprint
        self._self_footprint_clear_radius = max(
            0.0, float(self.get_parameter("self_footprint_clear_radius").value)
        )
        self._publisher = self.create_publisher(String, self._topic, 10)
        self._timer = self.create_timer(self._period, self._on_timer)
        self._last_costmap_monotonic: float | None = None
        self._last_snapshot_source = "bootstrap"
        self._static_map: OccupancyGrid | None = None
        self._costmap_baseline: list[int] | None = None
        self._baseline_sample_count = 0
        self._latest_robot_xy: tuple[float, float] | None = None

        grid_qos = QoSProfile(
            history=HistoryPolicy.KEEP_LAST,
            depth=1,
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
        )
        self.create_subscription(OccupancyGrid, self._map_topic, self._on_map, grid_qos)
        self.create_subscription(
            PoseWithCovarianceStamped,
            self._robot_pose_topic,
            self._on_robot_pose,
            10,
        )

        if self._use_costmap_topic:
            self.create_subscription(OccupancyGrid, self._costmap_topic, self._on_costmap, grid_qos)

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
        if self._static_map is None:
            self._last_snapshot_source = "waiting_for_static_map"
            return
        if not self._same_geometry(self._static_map, msg):
            self._last_snapshot_source = "costmap_geometry_mismatch_using_static_map"
            return

        current_grid = list(msg.data)
        if self._costmap_baseline is None:
            self._costmap_baseline = current_grid
            self._baseline_sample_count = 1
        elif self._baseline_sample_count < self._baseline_sample_target:
            self._costmap_baseline = [
                max(previous, current)
                for previous, current in zip(self._costmap_baseline, current_grid)
            ]
            self._baseline_sample_count += 1
        fused_grid = self._compose_static_dynamic_grid(
            static_grid=list(self._static_map.data),
            costmap_grid=current_grid,
            costmap_baseline=self._costmap_baseline,
        )
        if self._latest_robot_xy is not None and self._self_footprint_clear_radius > 0.0:
            fused_grid = self._clear_robot_footprint(
                fused_grid=fused_grid,
                static_grid=list(self._static_map.data),
                width=int(msg.info.width),
                height=int(msg.info.height),
                resolution=float(msg.info.resolution),
                origin_x=float(msg.info.origin.position.x),
                origin_y=float(msg.info.origin.position.y),
                robot_x=self._latest_robot_xy[0],
                robot_y=self._latest_robot_xy[1],
                radius=self._self_footprint_clear_radius,
            )
        current_time = float(self.get_clock().now().nanoseconds) / 1_000_000_000.0
        self._estimator.update_from_occupancy_grid(
            grid_data=fused_grid,
            width=int(msg.info.width),
            height=int(msg.info.height),
            resolution=float(msg.info.resolution),
            origin_x=float(msg.info.origin.position.x),
            origin_y=float(msg.info.origin.position.y),
            current_time=current_time,
            source="fused_static_map_and_costmap_delta",
        )
        self._last_snapshot_source = "fused_static_map_and_costmap_delta"
        self._publish_snapshot(source=self._last_snapshot_source)

    @staticmethod
    def _same_geometry(left: OccupancyGrid, right: OccupancyGrid) -> bool:
        return (
            int(left.info.width) == int(right.info.width)
            and int(left.info.height) == int(right.info.height)
            and abs(float(left.info.resolution) - float(right.info.resolution)) <= 1e-9
            and abs(float(left.info.origin.position.x) - float(right.info.origin.position.x)) <= 1e-6
            and abs(float(left.info.origin.position.y) - float(right.info.origin.position.y)) <= 1e-6
        )

    def _on_map(self, msg: OccupancyGrid) -> None:
        if self._static_map is not None and not self._same_geometry(self._static_map, msg):
            self._costmap_baseline = None
            self._baseline_sample_count = 0
        self._static_map = msg
        current_time = float(self.get_clock().now().nanoseconds) / 1_000_000_000.0
        self._estimator.update_from_occupancy_grid(
            grid_data=list(msg.data),
            width=int(msg.info.width),
            height=int(msg.info.height),
            resolution=float(msg.info.resolution),
            origin_x=float(msg.info.origin.position.x),
            origin_y=float(msg.info.origin.position.y),
            current_time=current_time,
            source=f"static_map:{self._map_topic}",
        )
        self._last_snapshot_source = f"static_map:{self._map_topic}"
        self._publish_snapshot(source=self._last_snapshot_source)

    def _on_robot_pose(self, msg: PoseWithCovarianceStamped) -> None:
        if msg.header.frame_id and msg.header.frame_id != "map":
            return
        self._latest_robot_xy = (
            float(msg.pose.pose.position.x),
            float(msg.pose.pose.position.y),
        )

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
