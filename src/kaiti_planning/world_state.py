from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any

from .models import PlanningProblem, ResourceState, SemanticStateOutput, Task


class PerceptionState(str, Enum):
    NORMAL = "normal"
    UNCERTAIN = "uncertain"
    CONFIRMED = "confirmed"
    DEGRADED = "degraded"


class EpisodeState(str, Enum):
    CANDIDATE = "candidate"
    OBSERVE_PENDING = "observe_pending"
    VERIFY_PENDING = "verify_pending"
    VERIFY_ACTIVE = "verify_active"
    VERIFIED = "verified"
    SUPPLY_PENDING = "supply_pending"
    COMPLETED = "completed"
    CLOSED = "closed"
    ESCALATED = "escalated"


class TaskLifecycle(str, Enum):
    PENDING = "pending"
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


TERMINAL_EPISODE_STATES = {
    EpisodeState.COMPLETED,
    EpisodeState.CLOSED,
    EpisodeState.ESCALATED,
}


@dataclass
class EventEpisode:
    event_id: str
    location_id: str
    state: EpisodeState
    perception_state: PerceptionState
    created_at: float
    updated_at: float
    track_id: str | None = None
    task_ids: list[str] = field(default_factory=list)
    retry_count: int = 0
    close_reason: str | None = None
    revision: int = 1

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["state"] = self.state.value
        payload["perception_state"] = self.perception_state.value
        return payload


@dataclass
class TaskRecord:
    task: Task
    lifecycle: TaskLifecycle = TaskLifecycle.PENDING
    event_id: str | None = None
    origin: str = "base"
    attempt: int = 1
    cancel_requested: bool = False
    last_error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "task": asdict(self.task),
            "lifecycle": self.lifecycle.value,
            "event_id": self.event_id,
            "origin": self.origin,
            "attempt": self.attempt,
            "cancel_requested": self.cancel_requested,
            "last_error": self.last_error,
        }


@dataclass
class WorldUpdate:
    changed: bool
    world_revision: int
    event_id: str | None
    created_tasks: list[str] = field(default_factory=list)
    cancelled_tasks: list[str] = field(default_factory=list)
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def normalize_perception_state(value: str | PerceptionState) -> PerceptionState:
    if isinstance(value, PerceptionState):
        return value
    mapping = {
        "normal": PerceptionState.NORMAL,
        "uncertain": PerceptionState.UNCERTAIN,
        "event_uncertain": PerceptionState.UNCERTAIN,
        "confirmed": PerceptionState.CONFIRMED,
        "event_confirmed": PerceptionState.CONFIRMED,
        "degraded": PerceptionState.DEGRADED,
        "perception_degraded": PerceptionState.DEGRADED,
    }
    try:
        return mapping[str(value)]
    except KeyError as exc:
        raise ValueError(f"unsupported perception state: {value}") from exc


class EventTaskFactory:
    DEFAULT_POLICY: dict[str, Any] = {
        "supply_location": "S",
        "observe": {
            "duration": 10.0,
            "deadline_offset": 60.0,
            "priority_weight": 6.0,
        },
        "verify": {
            "duration": 15.0,
            "deadline_offset": 60.0,
            "priority_weight": 10.0,
        },
        "pickup": {
            "duration": 8.0,
            "deadline_offset": 90.0,
            "priority_weight": 8.0,
        },
        "deliver": {
            "duration": 15.0,
            "deadline_offset": 120.0,
            "priority_weight": 8.0,
        },
        "location_resources": {
            "B": ["corridor_H", "event_zone_B"],
        },
        "supply_resources": ["supply_point_S"],
    }

    def __init__(self, problem: PlanningProblem) -> None:
        self.problem = problem
        self.policy = deepcopy(self.DEFAULT_POLICY)
        configured = problem.meta.get("event_task_policy", {})
        for key, value in configured.items():
            if isinstance(value, dict) and isinstance(self.policy.get(key), dict):
                self.policy[key].update(value)
            else:
                self.policy[key] = deepcopy(value)

    def _timing(self, kind: str, current_time: float) -> tuple[float, float, float]:
        policy = self.policy[kind]
        return (
            float(policy["duration"]),
            float(current_time) + float(policy["deadline_offset"]),
            float(policy["priority_weight"]),
        )

    def _location_resources(self, location_id: str) -> list[str]:
        return list(self.policy.get("location_resources", {}).get(location_id, []))

    def observe(self, episode: EventEpisode, current_time: float) -> Task:
        duration, deadline, priority = self._timing("observe", current_time)
        return Task(
            id=f"observe:{episode.event_id}",
            type="observe",
            location=episode.location_id,
            release=float(current_time),
            duration=duration,
            deadline=deadline,
            priority_weight=priority,
            capabilities=["move", "camera"],
            resources=self._location_resources(episode.location_id),
            event_task=True,
        )

    def verify(self, episode: EventEpisode, current_time: float) -> Task:
        duration, deadline, priority = self._timing("verify", current_time)
        return Task(
            id=f"verify:{episode.event_id}",
            type="verify_fall",
            location=episode.location_id,
            release=float(current_time),
            duration=duration,
            deadline=deadline,
            priority_weight=priority,
            capabilities=["move", "camera"],
            resources=self._location_resources(episode.location_id),
            event_task=True,
        )

    def pickup(self, episode: EventEpisode, current_time: float) -> Task:
        duration, deadline, priority = self._timing("pickup", current_time)
        supply_location = str(self.policy["supply_location"])
        return Task(
            id=f"pickup:{episode.event_id}",
            type="pickup_supply",
            location=supply_location,
            release=float(current_time),
            duration=duration,
            deadline=deadline,
            priority_weight=priority,
            capabilities=["move", "carry"],
            resources=list(self.policy.get("supply_resources", [])),
            pickup_location=supply_location,
            event_task=True,
        )

    def deliver(self, episode: EventEpisode, current_time: float) -> Task:
        duration, deadline, priority = self._timing("deliver", current_time)
        return Task(
            id=f"deliver:{episode.event_id}",
            type="deliver_supply",
            location=episode.location_id,
            release=float(current_time),
            duration=duration,
            deadline=deadline,
            priority_weight=priority,
            capabilities=["move", "carry"],
            resources=self._location_resources(episode.location_id),
            pickup_location=str(self.policy["supply_location"]),
            event_task=True,
        )


class WorldState:
    def __init__(self, problem: PlanningProblem) -> None:
        self.base_problem = deepcopy(problem)
        self.robots = {robot.id: deepcopy(robot) for robot in problem.robots}
        self.resources = {
            resource.id: ResourceState(
                resource_id=resource.id,
                predicate=resource.id,
                state=resource.state,
            )
            for resource in problem.resources
        }
        self.tasks = {
            task.id: TaskRecord(task=deepcopy(task))
            for task in problem.tasks
        }
        self.events: dict[str, EventEpisode] = {}
        self.precedence: set[tuple[str, str]] = set(problem.precedence)
        self.world_revision = 0
        self.plan_revision = 0
        self._next_event_index = 1
        self._active_by_track: dict[str, str] = {}
        self.task_factory = EventTaskFactory(problem)

    def _bump_world(self) -> None:
        self.world_revision += 1

    def next_plan_revision(self) -> int:
        self.plan_revision += 1
        return self.plan_revision

    def update_resource_state(self, state: ResourceState) -> bool:
        previous = self.resources.get(state.resource_id)
        if previous == state:
            return False
        self.resources[state.resource_id] = deepcopy(state)
        self._bump_world()
        return True

    def update_robot_battery(self, robot_id: str, battery: float) -> bool:
        robot = self.robots[robot_id]
        value = float(battery)
        if abs(float(robot.battery) - value) <= 1e-6:
            return False
        robot.battery = value
        self._bump_world()
        return True

    def _new_event_id(self, external_event_id: str | None) -> str:
        if external_event_id and external_event_id not in self.events:
            return external_event_id
        while True:
            candidate = f"event_{self._next_event_index:06d}"
            self._next_event_index += 1
            if candidate not in self.events:
                return candidate

    def _find_active_episode(
        self,
        *,
        external_event_id: str | None,
        track_id: str | None,
        location_id: str,
    ) -> EventEpisode | None:
        if track_id and track_id in self._active_by_track:
            episode = self.events.get(self._active_by_track[track_id])
            if episode and episode.state not in TERMINAL_EPISODE_STATES:
                return episode
        if external_event_id:
            episode = self.events.get(external_event_id)
            if episode and episode.state not in TERMINAL_EPISODE_STATES:
                return episode
        candidates = [
            episode
            for episode in self.events.values()
            if episode.location_id == location_id
            and episode.state not in TERMINAL_EPISODE_STATES
        ]
        return max(candidates, key=lambda item: item.updated_at) if candidates else None

    def _create_episode(
        self,
        *,
        state: PerceptionState,
        current_time: float,
        location_id: str,
        track_id: str | None,
        external_event_id: str | None,
    ) -> EventEpisode:
        event_id = self._new_event_id(external_event_id)
        episode = EventEpisode(
            event_id=event_id,
            location_id=location_id,
            state=EpisodeState.CANDIDATE,
            perception_state=state,
            created_at=float(current_time),
            updated_at=float(current_time),
            track_id=track_id,
        )
        self.events[event_id] = episode
        if track_id:
            self._active_by_track[track_id] = event_id
        return episode

    def _register_task(self, task: Task, episode: EventEpisode) -> bool:
        if task.id in self.tasks:
            return False
        self.tasks[task.id] = TaskRecord(task=task, event_id=episode.event_id, origin="event")
        episode.task_ids.append(task.id)
        return True

    def _cancel_pending(self, episode: EventEpisode, prefixes: tuple[str, ...]) -> list[str]:
        cancelled = []
        for task_id in episode.task_ids:
            record = self.tasks[task_id]
            if not task_id.startswith(prefixes):
                continue
            if record.lifecycle == TaskLifecycle.PENDING:
                record.lifecycle = TaskLifecycle.CANCELLED
                cancelled.append(task_id)
            elif record.lifecycle == TaskLifecycle.ACTIVE:
                record.cancel_requested = True
        return cancelled

    def ingest_perception(
        self,
        state: str | PerceptionState,
        *,
        current_time: float,
        location_id: str = "B",
        track_id: str | int | None = None,
        external_event_id: str | None = None,
    ) -> WorldUpdate:
        perception = normalize_perception_state(state)
        track_key = None if track_id is None else str(track_id)
        episode = self._find_active_episode(
            external_event_id=external_event_id,
            track_id=track_key,
            location_id=location_id,
        )
        created_tasks: list[str] = []
        cancelled_tasks: list[str] = []
        changed = False
        reason = "perception_refresh"

        if perception in {PerceptionState.UNCERTAIN, PerceptionState.CONFIRMED} and episode is None:
            episode = self._create_episode(
                state=perception,
                current_time=current_time,
                location_id=location_id,
                track_id=track_key,
                external_event_id=external_event_id,
            )
            changed = True
            reason = "episode_created"

        if episode is None:
            return WorldUpdate(False, self.world_revision, None, reason="no_active_episode")

        if track_key and not episode.track_id:
            episode.track_id = track_key
            self._active_by_track[track_key] = episode.event_id
            changed = True
        if episode.perception_state != perception:
            episode.perception_state = perception
            changed = True

        if perception == PerceptionState.UNCERTAIN:
            task = self.task_factory.observe(episode, current_time)
            if self._register_task(task, episode):
                created_tasks.append(task.id)
                changed = True
            if episode.state != EpisodeState.OBSERVE_PENDING:
                episode.state = EpisodeState.OBSERVE_PENDING
                changed = True
            reason = "observe_pending"
        elif perception == PerceptionState.CONFIRMED:
            cancelled_tasks.extend(self._cancel_pending(episode, ("observe:",)))
            task = self.task_factory.verify(episode, current_time)
            if self._register_task(task, episode):
                created_tasks.append(task.id)
                changed = True
            if episode.state not in {
                EpisodeState.VERIFY_PENDING,
                EpisodeState.VERIFY_ACTIVE,
                EpisodeState.VERIFIED,
                EpisodeState.SUPPLY_PENDING,
                EpisodeState.COMPLETED,
            }:
                episode.state = EpisodeState.VERIFY_PENDING
                changed = True
            reason = "verify_pending"
        elif perception == PerceptionState.DEGRADED:
            reason = "active_episode_retained_during_degraded"
        elif perception == PerceptionState.NORMAL:
            if episode.state in {EpisodeState.CANDIDATE, EpisodeState.OBSERVE_PENDING}:
                cancelled_tasks.extend(self._cancel_pending(episode, ("observe:",)))
                episode.state = EpisodeState.CLOSED
                episode.close_reason = "uncertain_cleared"
                changed = True
                reason = "uncertain_episode_closed"

        if cancelled_tasks:
            changed = True
        episode.updated_at = float(current_time)
        if changed:
            episode.revision += 1
            self._bump_world()
        return WorldUpdate(
            changed,
            self.world_revision,
            episode.event_id,
            created_tasks=created_tasks,
            cancelled_tasks=cancelled_tasks,
            reason=reason,
        )

    def ingest_semantic_output(
        self,
        output: SemanticStateOutput,
        *,
        current_time: float,
    ) -> WorldUpdate:
        source = output.source_event
        track_id = source.get("seq_track_id", source.get("track_id"))
        return self.ingest_perception(
            output.semantic_state,
            current_time=current_time,
            location_id=str(output.event_location or "B"),
            track_id=track_id,
            external_event_id=output.event_id,
        )

    def record_verification(
        self,
        event_id: str,
        result: str,
        *,
        current_time: float,
    ) -> WorldUpdate:
        episode = self.events[event_id]
        created_tasks: list[str] = []
        cancelled_tasks: list[str] = []
        changed = False
        normalized = str(result).lower()
        verify_record = self.tasks[f"verify:{event_id}"]

        if normalized in {"fall", "fall_confirmed", "needs_response"}:
            if verify_record.lifecycle != TaskLifecycle.COMPLETED:
                verify_record.lifecycle = TaskLifecycle.COMPLETED
                changed = True
            pickup = self.task_factory.pickup(episode, current_time)
            deliver = self.task_factory.deliver(episode, current_time)
            for task in (pickup, deliver):
                if self._register_task(task, episode):
                    created_tasks.append(task.id)
                    changed = True
            precedence_count = len(self.precedence)
            self.precedence.add((f"verify:{event_id}", pickup.id))
            self.precedence.add((pickup.id, deliver.id))
            if len(self.precedence) != precedence_count:
                changed = True
            if episode.state != EpisodeState.SUPPLY_PENDING:
                episode.state = EpisodeState.SUPPLY_PENDING
                changed = True
            reason = "supply_tasks_pending"
        elif normalized in {"no_fall", "false_alarm"}:
            if verify_record.lifecycle != TaskLifecycle.COMPLETED:
                verify_record.lifecycle = TaskLifecycle.COMPLETED
                changed = True
            cancelled_tasks.extend(self._cancel_pending(episode, ("pickup:", "deliver:")))
            if episode.state != EpisodeState.CLOSED or episode.close_reason != "verify_no_fall":
                episode.state = EpisodeState.CLOSED
                episode.close_reason = "verify_no_fall"
                changed = True
            reason = "event_closed_after_no_fall"
        elif normalized in {"failed", "navigation_failed", "action_failed"}:
            verify_record.lifecycle = TaskLifecycle.PENDING
            verify_record.attempt += 1
            verify_record.last_error = normalized
            episode.retry_count += 1
            episode.state = EpisodeState.VERIFY_PENDING
            changed = True
            reason = "verify_retry_pending"
        else:
            raise ValueError(f"unsupported verification result: {result}")

        episode.updated_at = float(current_time)
        if changed or cancelled_tasks:
            episode.revision += 1
            self._bump_world()
        return WorldUpdate(
            changed or bool(cancelled_tasks),
            self.world_revision,
            event_id,
            created_tasks=created_tasks,
            cancelled_tasks=cancelled_tasks,
            reason=reason,
        )

    def mark_task_active(self, task_id: str, *, current_time: float) -> None:
        record = self.tasks[task_id]
        if record.lifecycle == TaskLifecycle.ACTIVE:
            return
        record.lifecycle = TaskLifecycle.ACTIVE
        if record.event_id and task_id.startswith("verify:"):
            episode = self.events[record.event_id]
            episode.state = EpisodeState.VERIFY_ACTIVE
            episode.updated_at = float(current_time)
            episode.revision += 1
        self._bump_world()

    def mark_task_completed(self, task_id: str, *, current_time: float) -> None:
        record = self.tasks[task_id]
        if record.lifecycle == TaskLifecycle.COMPLETED:
            return
        record.lifecycle = TaskLifecycle.COMPLETED
        if record.event_id and task_id.startswith("deliver:"):
            episode = self.events[record.event_id]
            episode.state = EpisodeState.COMPLETED
            episode.updated_at = float(current_time)
            episode.revision += 1
        self._bump_world()

    def close_event(self, event_id: str, *, current_time: float, reason: str) -> WorldUpdate:
        episode = self.events[event_id]
        cancelled = self._cancel_pending(episode, ("observe:", "verify:", "pickup:", "deliver:"))
        changed = episode.state != EpisodeState.CLOSED or episode.close_reason != reason
        episode.state = EpisodeState.CLOSED
        episode.close_reason = reason
        episode.updated_at = float(current_time)
        if changed or cancelled:
            episode.revision += 1
            self._bump_world()
        return WorldUpdate(
            changed or bool(cancelled),
            self.world_revision,
            event_id,
            cancelled_tasks=cancelled,
            reason=reason,
        )

    def active_task_ids(self) -> list[str]:
        return sorted(
            task_id
            for task_id, record in self.tasks.items()
            if record.lifecycle in {TaskLifecycle.PENDING, TaskLifecycle.ACTIVE}
        )

    def planning_problem(self) -> PlanningProblem:
        problem = deepcopy(self.base_problem)
        active_ids = set(self.active_task_ids())
        problem.tasks = [deepcopy(self.tasks[task_id].task) for task_id in sorted(active_ids)]
        problem.precedence = sorted(
            (before, after)
            for before, after in self.precedence
            if before in active_ids and after in active_ids
        )
        problem.robots = [deepcopy(robot) for robot in self.robots.values()]
        return problem

    def snapshot(self) -> dict[str, Any]:
        return {
            "world_revision": self.world_revision,
            "plan_revision": self.plan_revision,
            "robots": sorted(self.robots),
            "resources": {
                resource_id: asdict(state)
                for resource_id, state in sorted(self.resources.items())
            },
            "events": {
                event_id: episode.to_dict()
                for event_id, episode in sorted(self.events.items())
            },
            "tasks": {
                task_id: record.to_dict()
                for task_id, record in sorted(self.tasks.items())
            },
            "active_task_ids": self.active_task_ids(),
        }
