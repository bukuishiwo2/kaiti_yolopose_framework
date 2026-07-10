from __future__ import annotations

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from kaiti_planning.ltlf_monitor import (
    LtlfTraceMonitor,
    TraceVerdict,
    load_transition_tables,
)

TABLE_PATH = PROJECT_ROOT / "configs/generated/ltlf_transition_tables.json"


def _monitor(specification_id: str, scope_id: str = "scope-1") -> LtlfTraceMonitor:
    return LtlfTraceMonitor(load_transition_tables(TABLE_PATH)[specification_id], scope_id=scope_id)


def test_confirmed_event_positive_negative_and_prefix_semantics() -> None:
    monitor = _monitor("confirmed_event_eventually_verified", "event-E1")
    assert monitor.step({"fall_confirmed"}) == TraceVerdict.INCONCLUSIVE
    assert monitor.verdict(trace_ended=True) == TraceVerdict.VIOLATED
    assert monitor.step({"verify_done"}) == TraceVerdict.SATISFIED
    assert monitor.verdict(trace_ended=True) == TraceVerdict.SATISFIED


def test_scope_instances_do_not_satisfy_each_other() -> None:
    event_one = _monitor("confirmed_event_eventually_verified", "event-E1")
    event_two = _monitor("confirmed_event_eventually_verified", "event-E2")
    event_one.step({"fall_confirmed"})
    event_two.step({"fall_confirmed"})

    assert event_one.step({"verify_done"}) == TraceVerdict.SATISFIED
    assert event_two.step(set()) == TraceVerdict.INCONCLUSIVE
    assert event_two.verdict(trace_ended=True) == TraceVerdict.VIOLATED


def test_all_frozen_specifications_have_three_value_runtime_tables() -> None:
    tables = load_transition_tables(TABLE_PATH)
    expected_steps = {
        "confirmed_event_eventually_verified": ("fall_confirmed", "verify_done"),
        "required_response_eventually_delivered": ("response_required", "deliver_done"),
        "low_battery_eventually_charged": ("low_battery", "charge_done"),
        "interrupted_patrol_eventually_resolved": (
            "patrol_interrupted",
            "patrol_resumed",
        ),
    }
    assert set(tables) == set(expected_steps)
    for specification_id, (trigger, completion) in expected_steps.items():
        table = tables[specification_id]
        monitor = LtlfTraceMonitor(table, scope_id=f"test:{specification_id}")
        assert monitor.step({trigger}) == TraceVerdict.INCONCLUSIVE
        assert monitor.verdict(trace_ended=True) == TraceVerdict.VIOLATED
        assert monitor.step({completion}) == TraceVerdict.SATISFIED
        assert monitor.verdict(trace_ended=True) == TraceVerdict.SATISFIED
