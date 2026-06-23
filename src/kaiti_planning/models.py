from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class PlannerWeights:
    alpha_travel: float = 1.0
    beta_delay: float = 1.0
    gamma_interrupt: float = 1.0
    delta_resource: float = 1.0
    eta_energy: float = 1.0
    mu_change: float = 1.0


@dataclass
class EnergyModel:
    safe_battery: float
    full_battery: float
    move_cost_per_sec: float
    task_costs: dict[str, float]
    charge_gain: dict[str, float]


@dataclass
class Robot:
    id: str
    start: str
    battery: float
    capabilities: list[str]
    current_task: str = ""


@dataclass
class Task:
    id: str
    type: str
    location: str
    release: float
    duration: float
    deadline: float
    priority_weight: float
    capabilities: list[str]
    resources: list[str]
    must_complete: bool = True
    pickup_location: str | None = None
    event_task: bool = False
    interrupt_penalty: float = 0.0


@dataclass
class Resource:
    id: str
    kind: str
    capacity: int
    state: str
    release_buffer: float = 0.0


@dataclass
class ResourceState:
    resource_id: str
    predicate: str
    state: str
    available_from: float = 0.0
    wait_time: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class DynamicEvent:
    time: float
    kind: str
    payload: dict[str, Any]


@dataclass
class SemanticConfig:
    theta_low: float
    theta_high: float
    quality_min: float
    min_confirm_windows: int
    min_clear_windows: int
    hold_frames: int
    cooldown_frames: int
    visible_keypoint_threshold: int


@dataclass
class SpatialConfig:
    occupancy_threshold_free: float
    occupancy_threshold_blocked: float
    min_passage_width: float
    ema_lambda: float


@dataclass
class PlanningProblem:
    meta: dict[str, Any]
    weights: PlannerWeights
    energy: EnergyModel
    robots: list[Robot]
    tasks: list[Task]
    resources: list[Resource]
    precedence: list[tuple[str, str]]
    travel_times: dict[str, dict[str, float]]
    dynamic_events: list[DynamicEvent]
    semantic: SemanticConfig
    spatial: SpatialConfig

    def task_by_id(self) -> dict[str, Task]:
        return {task.id: task for task in self.tasks}

    def robot_by_id(self) -> dict[str, Robot]:
        return {robot.id: robot for robot in self.robots}

    def resource_by_id(self) -> dict[str, Resource]:
        return {resource.id: resource for resource in self.resources}


@dataclass
class TaskAssignment:
    robot: str
    task: str
    start: float
    finish: float
    location: str
    resources: list[str]
    energy_after: float | None = None


@dataclass
class PlanResult:
    solver_status: str
    objective_value: float | None
    assignments: list[TaskAssignment]
    metrics: dict[str, float]
    planner_mode: str = "milp"
    plan_kind: str = "static"
    current_time: float = 0.0
    notes: list[str] = field(default_factory=list)
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "solver_status": self.solver_status,
            "objective_value": self.objective_value,
            "planner_mode": self.planner_mode,
            "plan_kind": self.plan_kind,
            "current_time": self.current_time,
            "assignments": [asdict(item) for item in self.assignments],
            "metrics": self.metrics,
            "notes": self.notes,
            "diagnostics": self.diagnostics,
        }


@dataclass
class SemanticStateOutput:
    semantic_state: str
    predicate: str | None
    event_id: str | None
    event_location: str | None
    fall_score: float
    quality_score: float
    source_event: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SpatialStateOutput:
    region_states: dict[str, dict[str, Any]]
    resource_states: dict[str, ResourceState]
    travel_times: dict[str, dict[str, float]]
    source: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "region_states": self.region_states,
            "resource_states": {
                key: asdict(value) for key, value in self.resource_states.items()
            },
            "travel_times": self.travel_times,
            "source": self.source,
        }


def load_problem_from_yaml(path: str | Path) -> PlanningProblem:
    cfg_path = Path(path)
    with cfg_path.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle)

    weights = PlannerWeights(**raw["weights"])
    energy = EnergyModel(**raw["energy"])
    robots = [Robot(**item) for item in raw["robots"]]
    tasks = [Task(**item) for item in raw["tasks"]]
    resources = [Resource(**item) for item in raw["resources"]]
    precedence = [
        (str(item["before"]), str(item["after"])) for item in raw.get("precedence", [])
    ]
    dynamic_events = []
    for item in raw.get("dynamic_script", []):
        payload = dict(item)
        time_value = float(payload.pop("time"))
        kind = str(payload.pop("kind"))
        dynamic_events.append(DynamicEvent(time=time_value, kind=kind, payload=payload))

    semantic = SemanticConfig(**raw["semantic"])
    spatial = SpatialConfig(**raw["spatial"])

    return PlanningProblem(
        meta=dict(raw.get("meta", {})),
        weights=weights,
        energy=energy,
        robots=robots,
        tasks=tasks,
        resources=resources,
        precedence=precedence,
        travel_times=raw["travel_times"],
        dynamic_events=dynamic_events,
        semantic=semantic,
        spatial=spatial,
    )
