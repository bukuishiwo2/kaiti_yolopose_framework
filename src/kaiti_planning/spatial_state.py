from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .models import PlanningProblem, ResourceState, SpatialConfig, SpatialStateOutput
from .milp_solver import initial_resource_states


@dataclass
class RegionBounds:
    x_min: float
    x_max: float
    y_min: float
    y_max: float


@dataclass
class RegionSpec:
    id: str
    kind: str
    resource_id: str
    bounds: RegionBounds
    width_axis: str = "y"
    min_passage_width: float = 0.8
    free_threshold: float = 0.25
    blocked_threshold: float = 0.65
    temporary_wait_sec: float = 20.0
    blocked_wait_sec: float = 60.0
    occupied_value_threshold: int = 50
    unknown_as_occupied: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SpatialReplayFrame:
    time: float
    obstacles: list[dict[str, Any]]
    notes: str = ""


@dataclass
class SpatialReplayConfig:
    width: int
    height: int
    resolution: float
    origin_x: float
    origin_y: float
    default_value: int
    frames: list[SpatialReplayFrame]


def load_region_specs(path: str | Path) -> dict[str, RegionSpec]:
    with Path(path).open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}
    specs: dict[str, RegionSpec] = {}
    for item in raw.get("regions", []):
        bounds = RegionBounds(**item["bounds"])
        payload = dict(item)
        payload["bounds"] = bounds
        specs[str(item["id"])] = RegionSpec(**payload)
    return specs


def load_spatial_replay_config(path: str | Path) -> SpatialReplayConfig:
    with Path(path).open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}
    frames = [
        SpatialReplayFrame(
            time=float(item["time"]),
            obstacles=list(item.get("obstacles", [])),
            notes=str(item.get("notes", "")),
        )
        for item in raw.get("frames", [])
    ]
    return SpatialReplayConfig(
        width=int(raw["grid"]["width"]),
        height=int(raw["grid"]["height"]),
        resolution=float(raw["grid"]["resolution"]),
        origin_x=float(raw["grid"].get("origin_x", 0.0)),
        origin_y=float(raw["grid"].get("origin_y", 0.0)),
        default_value=int(raw["grid"].get("default_value", 0)),
        frames=frames,
    )


def build_grid_from_replay_frame(cfg: SpatialReplayConfig, frame: SpatialReplayFrame) -> list[int]:
    grid = [int(cfg.default_value)] * (cfg.width * cfg.height)
    for obstacle in frame.obstacles:
        value = int(obstacle.get("value", 100))
        x_min = float(obstacle["x_min"])
        x_max = float(obstacle["x_max"])
        y_min = float(obstacle["y_min"])
        y_max = float(obstacle["y_max"])
        for row in range(cfg.height):
            cy = cfg.origin_y + (row + 0.5) * cfg.resolution
            if cy < y_min or cy > y_max:
                continue
            for col in range(cfg.width):
                cx = cfg.origin_x + (col + 0.5) * cfg.resolution
                if x_min <= cx <= x_max and y_min <= cy <= y_max:
                    grid[row * cfg.width + col] = value
    return grid


class SpatialStateEstimator:
    def __init__(
        self,
        problem: PlanningProblem,
        *,
        region_specs: dict[str, RegionSpec] | None = None,
    ):
        self.problem = problem
        self.cfg: SpatialConfig = problem.spatial
        self._resource_states = initial_resource_states(problem)
        self._region_specs = region_specs or {}
        self._region_states: dict[str, dict[str, Any]] = {}
        self._occupied_since: dict[str, float | None] = {}
        self._last_update_time: float = 0.0
        self._seed_default_region_states()

    def _seed_default_region_states(self) -> None:
        corridor_predicate = "corridor_free"
        charger_predicate = "charger_available"
        for resource in self.problem.resources:
            if resource.id == "corridor_H":
                self._region_states[resource.id] = {
                    "state": "free",
                    "predicate": corridor_predicate,
                    "occupancy_ratio_ema": 0.0,
                    "available_from": 0.0,
                    "wait_time": 0.0,
                }
            elif resource.id == "charger_D":
                self._region_states[resource.id] = {
                    "state": "available",
                    "predicate": charger_predicate,
                    "occupancy_ratio_ema": 0.0,
                    "available_from": 0.0,
                    "wait_time": 0.0,
                }
            else:
                self._region_states[resource.id] = {
                    "state": "available",
                    "predicate": f"{resource.id}_available",
                    "occupancy_ratio_ema": 0.0,
                    "available_from": 0.0,
                    "wait_time": 0.0,
                }
            self._occupied_since[resource.id] = None

    @property
    def resource_states(self) -> dict[str, ResourceState]:
        return deepcopy(self._resource_states)

    def update_from_measurement(
        self,
        region_id: str,
        *,
        occupancy_ratio: float,
        min_width: float,
        path_cost: float,
        available_from: float = 0.0,
        wait_time: float = 0.0,
    ) -> SpatialStateOutput:
        region = self._region_states.setdefault(region_id, {})
        prev_ema = float(region.get("occupancy_ratio_ema", occupancy_ratio))
        ema = float(self.cfg.ema_lambda) * occupancy_ratio + (1.0 - float(self.cfg.ema_lambda)) * prev_ema
        if ema <= float(self.cfg.occupancy_threshold_free) and min_width >= float(self.cfg.min_passage_width):
            state = "free"
            predicate = "corridor_free" if "corridor" in region_id else "region_reachable"
        elif ema >= float(self.cfg.occupancy_threshold_blocked) or min_width < float(self.cfg.min_passage_width):
            state = "blocked"
            predicate = "corridor_blocked" if "corridor" in region_id else "region_unreachable"
        else:
            state = "temporary_occupied"
            predicate = "corridor_temporary"

        region.update(
            {
                "state": state,
                "predicate": predicate,
                "occupancy_ratio_ema": round(ema, 4),
                "available_from": float(available_from),
                "wait_time": float(wait_time),
                "path_cost": float(path_cost),
                "min_width": float(min_width),
            }
        )
        self._resource_states[region_id] = ResourceState(
            resource_id=region_id,
            predicate=predicate,
            state=state,
            available_from=float(available_from),
            wait_time=float(wait_time),
            metadata={"path_cost": float(path_cost), "min_width": float(min_width)},
        )
        return self.snapshot(source="measurement")

    def update_from_occupancy_grid(
        self,
        *,
        grid_data: list[int],
        width: int,
        height: int,
        resolution: float,
        origin_x: float,
        origin_y: float,
        current_time: float,
        source: str,
    ) -> SpatialStateOutput:
        self._last_update_time = float(current_time)
        if not self._region_specs:
            return self.snapshot(source=source)

        for spec in self._region_specs.values():
            region_cells = self._region_cell_values(
                spec=spec,
                grid_data=grid_data,
                width=width,
                height=height,
                resolution=resolution,
                origin_x=origin_x,
                origin_y=origin_y,
            )
            occupancy_ratio = self._occupancy_ratio(spec, region_cells)
            min_width = self._min_passage_width(spec, region_cells, resolution)
            path_cost = self._path_cost_for_region(spec.resource_id)
            self._update_region_from_metrics(
                spec=spec,
                occupancy_ratio=occupancy_ratio,
                min_width=min_width,
                path_cost=path_cost,
                current_time=current_time,
            )

        return self.snapshot(source=source)

    def _region_cell_values(
        self,
        *,
        spec: RegionSpec,
        grid_data: list[int],
        width: int,
        height: int,
        resolution: float,
        origin_x: float,
        origin_y: float,
    ) -> list[list[int]]:
        cells: list[list[int]] = []
        for row in range(height):
            cy = origin_y + (row + 0.5) * resolution
            if cy < spec.bounds.y_min or cy > spec.bounds.y_max:
                continue
            row_values: list[int] = []
            for col in range(width):
                cx = origin_x + (col + 0.5) * resolution
                if cx < spec.bounds.x_min or cx > spec.bounds.x_max:
                    continue
                row_values.append(int(grid_data[row * width + col]))
            if row_values:
                cells.append(row_values)
        return cells

    @staticmethod
    def _cell_is_occupied(value: int, spec: RegionSpec) -> bool:
        if value < 0:
            return bool(spec.unknown_as_occupied)
        return value >= int(spec.occupied_value_threshold)

    def _occupancy_ratio(self, spec: RegionSpec, cells: list[list[int]]) -> float:
        flat = [value for row in cells for value in row]
        if not flat:
            return 1.0
        occupied = sum(1 for value in flat if self._cell_is_occupied(value, spec))
        return float(occupied) / float(len(flat))

    def _min_passage_width(self, spec: RegionSpec, cells: list[list[int]], resolution: float) -> float:
        if not cells:
            return 0.0
        if spec.width_axis == "x":
            lines = cells
        else:
            max_cols = max(len(row) for row in cells)
            lines = []
            for col_idx in range(max_cols):
                line = []
                for row in cells:
                    if col_idx < len(row):
                        line.append(row[col_idx])
                if line:
                    lines.append(line)
        if not lines:
            return 0.0
        free_widths = []
        for line in lines:
            free_count = sum(1 for value in line if not self._cell_is_occupied(value, spec))
            free_widths.append(free_count * resolution)
        return min(free_widths) if free_widths else 0.0

    def _path_cost_for_region(self, resource_id: str) -> float:
        if resource_id == "corridor_H":
            return float(self.problem.travel_times["C"]["B"])
        if resource_id == "charger_D":
            return float(self.problem.travel_times["B"]["D"])
        return 0.0

    def _update_region_from_metrics(
        self,
        *,
        spec: RegionSpec,
        occupancy_ratio: float,
        min_width: float,
        path_cost: float,
        current_time: float,
    ) -> None:
        region = self._region_states.setdefault(spec.resource_id, {})
        prev_ema = float(region.get("occupancy_ratio_ema", occupancy_ratio))
        ema = float(self.cfg.ema_lambda) * occupancy_ratio + (1.0 - float(self.cfg.ema_lambda)) * prev_ema

        if spec.kind == "corridor":
            state, predicate = self._corridor_state(spec, ema, min_width)
        elif spec.kind == "charger":
            state = "available" if ema <= float(spec.free_threshold) else "occupied"
            predicate = "charger_available" if state == "available" else "charger_occupied"
        else:
            state = "reachable" if ema < float(spec.blocked_threshold) else "blocked"
            predicate = "region_reachable" if state == "reachable" else "region_blocked"

        if state in {"temporary_occupied", "blocked", "occupied"}:
            if self._occupied_since.get(spec.resource_id) is None:
                self._occupied_since[spec.resource_id] = float(current_time)
            occupied_duration = float(current_time) - float(self._occupied_since[spec.resource_id] or current_time)
        else:
            self._occupied_since[spec.resource_id] = None
            occupied_duration = 0.0

        if state == "temporary_occupied":
            wait_time = max(float(spec.temporary_wait_sec), occupied_duration)
            available_from = float(current_time) + wait_time
        elif state in {"blocked", "occupied"}:
            wait_time = max(float(spec.blocked_wait_sec), occupied_duration)
            available_from = float(current_time) + wait_time
        else:
            wait_time = 0.0
            available_from = float(current_time)

        region.update(
            {
                "state": state,
                "predicate": predicate,
                "occupancy_ratio": round(float(occupancy_ratio), 4),
                "occupancy_ratio_ema": round(float(ema), 4),
                "min_width": round(float(min_width), 4),
                "path_cost": round(float(path_cost), 4),
                "available_from": round(float(available_from), 4),
                "wait_time": round(float(wait_time), 4),
                "occupied_duration": round(float(occupied_duration), 4),
                "kind": spec.kind,
            }
        )
        self._resource_states[spec.resource_id] = ResourceState(
            resource_id=spec.resource_id,
            predicate=predicate,
            state=state,
            available_from=float(available_from),
            wait_time=float(wait_time),
            metadata={
                "path_cost": float(path_cost),
                "min_width": float(min_width),
                "occupancy_ratio": float(occupancy_ratio),
                "occupancy_ratio_ema": float(ema),
                "occupied_duration": float(occupied_duration),
            },
        )

    @staticmethod
    def _corridor_state(spec: RegionSpec, ema: float, min_width: float) -> tuple[str, str]:
        if ema <= float(spec.free_threshold) and min_width >= float(spec.min_passage_width):
            return "free", "corridor_free"
        if ema >= float(spec.blocked_threshold) or min_width <= float(spec.min_passage_width) * 0.4:
            return "blocked", "corridor_blocked"
        return "temporary_occupied", "corridor_temporary"

    def apply_dynamic_event(self, event: dict[str, Any], current_time: float) -> SpatialStateOutput:
        if event.get("kind") == "resource":
            resource_id = str(event["resource_id"])
            state = str(event["state"])
            available_from = float(event.get("available_from", current_time))
            wait_time = float(event.get("wait_time", max(0.0, available_from - current_time)))
            if resource_id == "corridor_H":
                predicate = {
                    "free": "corridor_free",
                    "temporary_occupied": "corridor_temporary",
                    "blocked": "corridor_blocked",
                }.get(state, "corridor_blocked")
            elif resource_id == "charger_D":
                predicate = "charger_available" if state in {"available", "free"} else "charger_unavailable"
            else:
                predicate = f"{resource_id}_{state}"
            self._resource_states[resource_id] = ResourceState(
                resource_id=resource_id,
                predicate=predicate,
                state=state,
                available_from=available_from,
                wait_time=wait_time,
                metadata={"event_time": current_time},
            )
            self._region_states[resource_id] = {
                "state": state,
                "predicate": predicate,
                "available_from": available_from,
                "wait_time": wait_time,
            }
        return self.snapshot(source="dynamic_script")

    def snapshot(self, *, source: str) -> SpatialStateOutput:
        return SpatialStateOutput(
            region_states=deepcopy(self._region_states),
            resource_states=deepcopy(self._resource_states),
            travel_times=deepcopy(self.problem.travel_times),
            source=source,
        )
