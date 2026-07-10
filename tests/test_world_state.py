from __future__ import annotations

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from kaiti_planning.milp_solver import initial_resource_states
from kaiti_planning.models import SemanticConfig, load_problem_from_yaml
from kaiti_planning.semantic_state import SemanticStateMachine
from kaiti_planning.world_state import EpisodeState, TaskLifecycle, WorldState


def _world() -> WorldState:
    problem = load_problem_from_yaml(PROJECT_ROOT / "configs/planner_graduation_v2.yaml")
    return WorldState(problem)


def test_initial_v2_problem_has_no_event_tasks() -> None:
    world = _world()
    assert world.active_task_ids() == ["T1", "T2", "T5"]
    assert not any(record.task.event_task for record in world.tasks.values())
    assert world.planning_problem().precedence == []


def test_uncertain_confirmed_and_duplicate_inputs_are_idempotent() -> None:
    world = _world()
    uncertain = world.ingest_perception(
        "event_uncertain", current_time=20.0, location_id="B", track_id=7
    )
    duplicate_uncertain = world.ingest_perception(
        "event_uncertain", current_time=21.0, location_id="B", track_id=7
    )
    confirmed = world.ingest_perception(
        "event_confirmed", current_time=30.0, location_id="B", track_id=7
    )
    duplicate_confirmed = world.ingest_perception(
        "event_confirmed", current_time=31.0, location_id="B", track_id=7
    )

    assert uncertain.event_id == confirmed.event_id
    assert uncertain.created_tasks == [f"observe:{uncertain.event_id}"]
    assert duplicate_uncertain.changed is False
    assert duplicate_uncertain.world_revision == uncertain.world_revision
    assert confirmed.created_tasks == [f"verify:{uncertain.event_id}"]
    assert confirmed.cancelled_tasks == [f"observe:{uncertain.event_id}"]
    assert duplicate_confirmed.changed is False
    assert len(world.events) == 1
    assert world.events[uncertain.event_id].state == EpisodeState.VERIFY_PENDING


def test_degraded_retains_active_episode_and_does_not_create_tasks() -> None:
    world = _world()
    confirmed = world.ingest_perception(
        "event_confirmed", current_time=30.0, location_id="B", track_id="track-1"
    )
    degraded = world.ingest_perception(
        "perception_degraded", current_time=31.0, location_id="B", track_id="track-1"
    )
    duplicate = world.ingest_perception(
        "perception_degraded", current_time=32.0, location_id="B", track_id="track-1"
    )

    assert degraded.event_id == confirmed.event_id
    assert degraded.created_tasks == []
    assert world.events[confirmed.event_id].state == EpisodeState.VERIFY_PENDING
    assert duplicate.changed is False
    assert len(world.events) == 1


def test_uncertain_to_normal_cancels_unstarted_observe() -> None:
    world = _world()
    uncertain = world.ingest_perception(
        "uncertain", current_time=10.0, location_id="B", track_id=1
    )
    normal = world.ingest_perception(
        "normal", current_time=12.0, location_id="B", track_id=1
    )
    observe_id = f"observe:{uncertain.event_id}"

    assert normal.cancelled_tasks == [observe_id]
    assert world.tasks[observe_id].lifecycle == TaskLifecycle.CANCELLED
    assert world.events[uncertain.event_id].state == EpisodeState.CLOSED
    assert observe_id not in world.active_task_ids()


def test_verification_outcomes_create_supply_or_retry_without_auto_close() -> None:
    world = _world()
    update = world.ingest_perception(
        "confirmed", current_time=30.0, location_id="B", track_id=1
    )
    event_id = update.event_id
    assert event_id is not None

    world.mark_task_active(f"verify:{event_id}", current_time=31.0)
    failed = world.record_verification(event_id, "navigation_failed", current_time=32.0)
    verify = world.tasks[f"verify:{event_id}"]
    assert failed.reason == "verify_retry_pending"
    assert world.events[event_id].state == EpisodeState.VERIFY_PENDING
    assert verify.lifecycle == TaskLifecycle.PENDING
    assert verify.attempt == 2

    supply = world.record_verification(event_id, "fall", current_time=40.0)
    duplicate = world.record_verification(event_id, "fall", current_time=41.0)
    assert set(supply.created_tasks) == {f"pickup:{event_id}", f"deliver:{event_id}"}
    assert duplicate.changed is False
    assert (f"verify:{event_id}", f"pickup:{event_id}") in world.precedence
    assert (f"pickup:{event_id}", f"deliver:{event_id}") in world.precedence
    assert world.events[event_id].state == EpisodeState.SUPPLY_PENDING


def test_verify_no_fall_is_the_only_verification_result_that_closes_event() -> None:
    world = _world()
    update = world.ingest_perception(
        "confirmed", current_time=30.0, location_id="B", track_id=1
    )
    event_id = update.event_id
    assert event_id is not None
    closed = world.record_verification(event_id, "no_fall", current_time=40.0)
    assert closed.reason == "event_closed_after_no_fall"
    assert world.events[event_id].state == EpisodeState.CLOSED
    assert world.events[event_id].close_reason == "verify_no_fall"


def test_semantic_degraded_output_preserves_confirmed_event_id() -> None:
    machine = SemanticStateMachine(
        SemanticConfig(
            theta_low=0.45,
            theta_high=0.75,
            quality_min=0.55,
            min_confirm_windows=1,
            min_clear_windows=1,
            hold_frames=1,
            cooldown_frames=1,
            visible_keypoint_threshold=6,
        )
    )
    confirmed = machine.update(
        {
            "seq_fall_score": 0.95,
            "seq_visible_keypoint_count": 8,
            "seq_window_ready": True,
            "seq_feature_valid": True,
            "seq_track_id": 1,
            "event_location": "B",
        }
    )
    degraded = machine.update(
        {
            "seq_fall_score": 0.95,
            "seq_visible_keypoint_count": 1,
            "seq_window_ready": False,
            "seq_feature_valid": False,
            "seq_track_id": 1,
            "event_location": "B",
        }
    )
    assert confirmed.event_id is not None
    assert degraded.event_id == confirmed.event_id


def test_world_and_plan_revisions_change_only_for_effective_updates() -> None:
    world = _world()
    problem = world.planning_problem()
    corridor = initial_resource_states(problem)["corridor_H"]
    assert world.world_revision == 0
    assert world.update_robot_battery("R1", 80.0) is False
    assert world.world_revision == 0
    assert world.update_robot_battery("R1", 79.0) is True
    assert world.world_revision == 1
    assert world.update_resource_state(corridor) is True
    revision = world.world_revision
    assert world.update_resource_state(corridor) is False
    assert world.world_revision == revision
    assert world.next_plan_revision() == 1
    assert world.next_plan_revision() == 2
