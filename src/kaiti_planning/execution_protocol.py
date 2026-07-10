from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


FEASIBLE_PLAN_STATUSES = {"OPTIMAL", "FEASIBLE", "TIME_LIMIT_FEASIBLE"}


@dataclass(frozen=True, order=True)
class PlanIdentity:
    planner_instance_id: str
    plan_id: str
    revision: int
    world_revision: int

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "PlanIdentity":
        planner_instance_id = str(payload.get("planner_instance_id", "")).strip()
        plan_id = str(payload.get("plan_id", "")).strip()
        if not planner_instance_id or not plan_id:
            raise ValueError("plan identity requires planner_instance_id and plan_id")
        return cls(
            planner_instance_id=planner_instance_id,
            plan_id=plan_id,
            revision=int(payload.get("revision", -1)),
            world_revision=int(payload.get("world_revision", -1)),
        )


@dataclass(frozen=True)
class PlanAcceptance:
    accepted: bool
    reason: str
    identity: PlanIdentity | None


@dataclass(frozen=True)
class ExecutionStepSpec:
    task_id: str
    task_type: str
    location_id: str
    step_name: str
    attempt: int = 1

    @property
    def key(self) -> tuple[str, str, int]:
        return (self.task_id, self.step_name, self.attempt)


class RevisionGate:
    """Accept only monotonic revisions from one explicit planning session."""

    def __init__(self) -> None:
        self.latest: PlanIdentity | None = None

    def evaluate(self, payload: Mapping[str, Any]) -> PlanAcceptance:
        if str(payload.get("solver_status", "")) not in FEASIBLE_PLAN_STATUSES:
            return PlanAcceptance(False, "plan_not_feasible", None)
        try:
            identity = PlanIdentity.from_payload(payload)
        except (TypeError, ValueError):
            return PlanAcceptance(False, "invalid_plan_identity", None)
        if identity.revision < 0 or identity.world_revision < 0:
            return PlanAcceptance(False, "negative_revision", identity)
        if self.latest is None:
            self.latest = identity
            return PlanAcceptance(True, "first_revision", identity)
        same_session = (
            identity.planner_instance_id == self.latest.planner_instance_id
            and identity.plan_id == self.latest.plan_id
        )
        if not same_session:
            if not bool(payload.get("reset_execution", False)):
                return PlanAcceptance(False, "different_planning_session_requires_reset", identity)
            self.latest = identity
            return PlanAcceptance(True, "explicit_session_reset", identity)
        if identity.revision == self.latest.revision:
            return PlanAcceptance(False, "duplicate_revision", identity)
        if identity.revision < self.latest.revision:
            return PlanAcceptance(False, "stale_revision", identity)
        if identity.world_revision < self.latest.world_revision:
            return PlanAcceptance(False, "stale_world_revision", identity)
        self.latest = identity
        return PlanAcceptance(True, "new_revision", identity)


def can_apply_deferred_revision(
    *,
    has_pending_plan: bool,
    queue_length: int,
    goal_pending: bool,
    goal_active: bool,
) -> bool:
    """A new revision may replace a queue only at a complete queue boundary."""
    return (
        has_pending_plan
        and queue_length == 0
        and not goal_pending
        and not goal_active
    )


def _infer_task_type(task_id: str, assignment: Mapping[str, Any], task: Any | None) -> str:
    explicit = str(assignment.get("task_type", assignment.get("type", ""))).strip()
    if explicit:
        return explicit
    if task is not None:
        return str(task.type)
    prefix = task_id.split(":", 1)[0]
    return {
        "observe": "observe",
        "verify": "verify_fall",
        "pickup": "pickup_supply",
        "deliver": "deliver_supply",
    }.get(prefix, prefix or "unknown")


def expand_assignments(
    assignments: list[dict[str, Any]],
    *,
    robot_id: str,
    task_registry: Mapping[str, Any],
    completed_step_keys: set[tuple[str, str, int]] | None = None,
) -> list[ExecutionStepSpec]:
    completed = completed_step_keys or set()
    steps: list[ExecutionStepSpec] = []
    emitted: set[tuple[str, str, int]] = set()
    task_order_rank = {"observe": 0, "verify": 1, "pickup": 2, "deliver": 3}
    ordered = sorted(
        [
            item
            for item in assignments
            if isinstance(item, dict) and str(item.get("robot", "")).strip() == robot_id
        ],
        key=lambda item: (
            float(item.get("start", 0.0)),
            task_order_rank.get(str(item.get("task", "")).split(":", 1)[0], 10),
            str(item.get("task", "")),
        ),
    )
    for item in ordered:
        task_id = str(item.get("task", "")).strip()
        if not task_id:
            continue
        task = task_registry.get(task_id)
        task_type = _infer_task_type(task_id, item, task)
        attempt = max(1, int(item.get("attempt", 1)))

        # Legacy delivery tasks may contain an implicit pickup location.  V2
        # uses an explicit pickup:event task and therefore does not expand it.
        pickup_location = getattr(task, "pickup_location", None) if task is not None else None
        if pickup_location and not task_id.startswith("pickup:"):
            step = ExecutionStepSpec(
                task_id=task_id,
                task_type=task_type,
                location_id=str(pickup_location),
                step_name="pickup_location",
                attempt=attempt,
            )
            if step.key not in completed and step.key not in emitted:
                steps.append(step)
                emitted.add(step.key)

        location = str(item.get("location", "")).strip()
        if not location and task is not None:
            location = str(task.location)
        if not location:
            continue
        step = ExecutionStepSpec(
            task_id=task_id,
            task_type=task_type,
            location_id=location,
            step_name="task_location",
            attempt=attempt,
        )
        if step.key not in completed and step.key not in emitted:
            steps.append(step)
            emitted.add(step.key)
    return steps
