#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from kaiti_planning.models import load_problem_from_yaml
from kaiti_planning.world_state import WorldState


def _summary(world: WorldState, label: str, update: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "label": label,
        "world_revision": world.world_revision,
        "plan_revision": world.plan_revision,
        "update": update,
        "active_tasks": world.active_task_ids(),
        "events": {
            event_id: {
                "state": episode.state.value,
                "perception_state": episode.perception_state.value,
                "retry_count": episode.retry_count,
                "task_ids": list(episode.task_ids),
            }
            for event_id, episode in world.events.items()
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay the v2 event episode lifecycle.")
    parser.add_argument("--config", default="configs/planner_graduation_v2.yaml")
    args = parser.parse_args()

    world = WorldState(load_problem_from_yaml(REPO_ROOT / args.config))
    timeline = [_summary(world, "initial")]

    uncertain = world.ingest_perception(
        "uncertain", current_time=20.0, location_id="B", track_id="person-1"
    )
    timeline.append(_summary(world, "uncertain", uncertain.to_dict()))
    degraded = world.ingest_perception(
        "degraded", current_time=25.0, location_id="B", track_id="person-1"
    )
    timeline.append(_summary(world, "degraded_retains_episode", degraded.to_dict()))
    confirmed = world.ingest_perception(
        "confirmed", current_time=30.0, location_id="B", track_id="person-1"
    )
    timeline.append(_summary(world, "confirmed", confirmed.to_dict()))

    event_id = confirmed.event_id
    if event_id is None:
        raise RuntimeError("confirmed event did not produce an episode")
    verify_id = f"verify:{event_id}"
    world.mark_task_active(verify_id, current_time=32.0)
    failed = world.record_verification(event_id, "navigation_failed", current_time=33.0)
    timeline.append(_summary(world, "verify_retry", failed.to_dict()))
    supply = world.record_verification(event_id, "fall", current_time=40.0)
    timeline.append(_summary(world, "supply_created", supply.to_dict()))

    world.mark_task_active(f"pickup:{event_id}", current_time=50.0)
    world.mark_task_completed(f"pickup:{event_id}", current_time=58.0)
    world.mark_task_active(f"deliver:{event_id}", current_time=60.0)
    world.mark_task_completed(f"deliver:{event_id}", current_time=75.0)
    timeline.append(_summary(world, "event_completed"))

    print(json.dumps({"timeline": timeline}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
