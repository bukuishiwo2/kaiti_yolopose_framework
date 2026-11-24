"""LTLf controlled negative traces are not actual multi-event execution evidence."""
from copy import deepcopy
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from trace_monitor import EventTraceMonitor


def feed(monitor, event, at, propositions, **extra):
    monitor.feed(dict(
        event_id=event, at=at, propositions=propositions,
        source_kind='CONTROLLED_TEST', **extra))


def test_cross_event_delivery_does_not_discharge_other_custody():
    m = EventTraceMonitor()
    feed(m, 'E1', 1., ['fall_confirmed', 'pickup_done'])
    feed(m, 'E2', 1., ['fall_confirmed', 'pickup_done'])
    feed(m, 'E1', 2., ['deliver_done'])
    assert m.monitors['E2']['custody_eventually_delivered'].verdict(trace_ended=False).value == 'INCONCLUSIVE'
    assert 'deliver_done' not in m.events['E2']['latched']


def test_plan_revision_and_checkpoint_inherit_monitor_obligation():
    m = EventTraceMonitor()
    feed(m, 'E1', 1., ['fall_confirmed', 'monitor_started'])
    saved = m.checkpoint()
    restored = EventTraceMonitor.restore(saved)
    restored.feed(dict(kind='plan_revision', at=2., revision=8))
    assert restored.events['E1']['monitor_active']
    feed(restored, 'E1', 3., [], monitor_active=False)
    report = restored.report()
    assert report['events']['E1']['rules']['monitor_obligation_continuity'] == 'VIOLATED'
    assert restored.plan_revisions[-1]['revision'] == 8


def test_wrong_identity_is_rejected_and_plan_forecast_is_not_an_ack():
    m = EventTraceMonitor()
    feed(m, 'E1', 1., ['fall_confirmed', 'pickup_done'])
    m.feed(dict(event_id='E1', at=2., source_kind='PLAN_PREDICTION',
                propositions=['deliver_done', 'event_completed']))
    assert 'deliver_done' not in m.events['E1']['latched']
    assert m.report()['status'] == 'NOT_ACTUAL_EXECUTION_EVIDENCE'
    feed(m, 'E2', 3., ['deliver_done'], task_id='E1:deliver')
    assert m.report()['status'] == 'VIOLATED_IDENTITY_OR_TIME'


def test_truncated_trace_keeps_pending_response_not_fake_satisfied():
    m = EventTraceMonitor()
    feed(m, 'E1', 1., ['fall_confirmed', 'monitor_started'])
    report = m.report(trace_ended=True)
    assert report['events']['E1']['rules']['confirmed_response_eventually_completed'] == 'INCONCLUSIVE'
    assert report['new_multievent_actual_execution'] is False


def test_wrong_close_and_early_receiver_ack_are_temporal_violations():
    m = EventTraceMonitor()
    feed(m, 'E1', 1., ['candidate_open'])
    feed(m, 'E1', 2., ['event_completed'])
    assert m.report()['events']['E1']['rules']['completed_requires_own_evidence'] == 'VIOLATED'
    n = EventTraceMonitor()
    feed(n, 'E2', 1., ['handover_done'])
    assert n.report()['events']['E2']['rules']['handover_requires_own_delivery'] == 'VIOLATED'
