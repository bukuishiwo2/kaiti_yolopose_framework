"""Event-isolated LTLf acceptance of hash-bound actual Clinic feedback.

Actual logs are streamed; no historical full log is copied. Plan timestamps
never become execution propositions. Facts survive plan revisions/checkpoints.
The monitor validates temporal obligations; MILP choices, navigation guards,
resource leases and detailed execution identity remain separate checks.
"""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT/'src'))
from kaiti_planning.ltlf_monitor import LtlfTraceMonitor, load_transition_tables

TABLE = HERE/'ltlf_transition_tables.json'
SOURCE = HERE/'ltlf_specifications.json'
LATCHED = {
    'verify_done', 'fall_confirmed', 'pickup_done', 'deliver_done',
    'handover_done', 'monitor_done', 'response_complete', 'event_completed',
    'event_closed_negative', 'event_cancelled_safe'}
PULSES = {'candidate_open', 'monitor_started', 'pickup_started', 'deliver_started'}


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1048576), b''):
            h.update(block)
    return h.hexdigest()


class EventTraceMonitor:
    def __init__(self):
        payload = json.loads(TABLE.read_text())
        if payload['source_sha256'] != sha(SOURCE):
            raise ValueError('LTLf specification/table drift.')
        self.tables = load_transition_tables(TABLE)
        self.events = {}
        self.monitors = {}
        self.issues = []
        self.ignored_predictions = 0
        self.actual_fact_count = 0
        self.test_fact_count = 0
        self.plan_revisions = []

    def _event(self, event_id):
        if event_id not in self.events:
            self.events[event_id] = dict(
                latched=[], monitor_active=False, at=-1.,
                coverage={}, first_rule_violation={}, facts=0)
            self.monitors[event_id] = {
                key:LtlfTraceMonitor(table, scope_id=event_id)
                for key, table in self.tables.items()}
        return self.events[event_id]

    def issue(self, kind, reason, source=None):
        self.issues.append(dict(kind=kind, reason=reason, source=source))

    def feed(self, fact):
        if fact.get('source_kind') == 'PLAN_PREDICTION':
            self.ignored_predictions += 1
            return
        if fact.get('kind') == 'plan_revision':
            self.plan_revisions.append({
                key:deepcopy(fact.get(key)) for key in (
                    'at', 'revision', 'observed_transition_index',
                    'revision_provenance', 'source')})
            return
        if fact.get('source_kind') not in {'ACTUAL_ACK', 'CONTROLLED_TEST'}:
            self.issue('MISSING_EVIDENCE', 'Unrecognized observation provenance.', fact)
            return
        event_id = fact.get('event_id')
        if not isinstance(event_id, str) or not event_id:
            self.issue('INVALID_IDENTITY', 'Event ID missing.', fact)
            return
        task = fact.get('task_id')
        if task is not None and (not task.startswith(event_id+':')):
            self.issue('INVALID_IDENTITY', 'Receipt task/event identity mismatch.', fact)
            return
        state = self._event(event_id)
        if fact['at'] < state['at']:
            self.issue('INVALID_TIME', 'Event time moved backwards.', fact)
            return
        propositions = set(fact.get('propositions', []))
        if propositions-LATCHED-PULSES-{'monitor_active'}:
            raise ValueError('Unknown event-level semantic fact.')
        state['latched'] = sorted(set(state['latched']) | (propositions & LATCHED))
        if 'monitor_started' in propositions:
            state['monitor_active'] = True
        if 'monitor_active' in fact:
            state['monitor_active'] = bool(fact['monitor_active'])
        facts = set(state['latched']) | (propositions & PULSES)
        if state['monitor_active']:
            facts.add('monitor_active')
        if {'verify_done', 'monitor_done', 'pickup_done',
                'deliver_done', 'handover_done'}.issubset(facts):
            state['latched'] = sorted(set(state['latched']) | {'response_complete'})
            facts.add('response_complete')
        for proposition in facts:
            state['coverage'][proposition] = state['coverage'].get(proposition, 0)+1
        for key, monitor in self.monitors[event_id].items():
            active = facts & set(monitor.table.atomic_propositions)
            verdict = monitor.step(active)
            if verdict.value == 'VIOLATED' and key not in state['first_rule_violation']:
                state['first_rule_violation'][key] = dict(
                    at=fact['at'], source=deepcopy(fact.get('source')))
        state['at'], state['facts'] = fact['at'], state['facts']+1
        if fact['source_kind'] == 'ACTUAL_ACK':
            self.actual_fact_count += 1
        else:
            self.test_fact_count += 1

    def checkpoint(self):
        return dict(
            table_sha256=sha(TABLE), events=deepcopy(self.events),
            automata={event_id:{
                key:dict(state=m.state, step_count=m.step_count)
                for key, m in monitors.items()}
                for event_id, monitors in self.monitors.items()},
            issues=deepcopy(self.issues), plan_revisions=deepcopy(self.plan_revisions),
            ignored_predictions=self.ignored_predictions,
            actual_fact_count=self.actual_fact_count, test_fact_count=self.test_fact_count)

    @classmethod
    def restore(cls, checkpoint):
        result = cls()
        if checkpoint['table_sha256'] != sha(TABLE):
            raise ValueError('Cannot restore across a changed formal specification.')
        for event_id in checkpoint['events']:
            result._event(event_id)
        result.events = deepcopy(checkpoint['events'])
        for event_id, monitors in checkpoint['automata'].items():
            for key, value in monitors.items():
                result.monitors[event_id][key].state = value['state']
                result.monitors[event_id][key].step_count = value['step_count']
        for key in ('issues', 'plan_revisions', 'ignored_predictions',
                    'actual_fact_count', 'test_fact_count'):
            setattr(result, key, deepcopy(checkpoint[key]))
        return result

    def report(self, trace_ended=False):
        events = {}
        for event_id, state in self.events.items():
            terminal = bool(
                set(state['latched']) & {'event_completed', 'event_closed_negative',
                                        'event_cancelled_safe'})
            verdicts = {
                key:monitor.verdict(trace_ended=trace_ended and terminal).value
                for key, monitor in self.monitors[event_id].items()}
            events[event_id] = dict(
                terminal_observed=terminal, rules=verdicts,
                coverage=state['coverage'], first_violation=state['first_rule_violation'],
                outstanding_rules=[key for key, value in verdicts.items()
                                   if value == 'INCONCLUSIVE'],
                observed_facts=state['facts'])
        hard_issues = any(i['kind'] in {'INVALID_IDENTITY', 'INVALID_TIME'}
                          for i in self.issues)
        missing = any(i['kind'] == 'MISSING_EVIDENCE' for i in self.issues)
        violation = any(
            value == 'VIOLATED' for event in events.values()
            for value in event['rules'].values())
        if hard_issues:
            status = 'VIOLATED_IDENTITY_OR_TIME'
        elif missing:
            status = 'UNKNOWN_EVIDENCE_INCOMPLETE'
        elif violation:
            status = 'VIOLATED_TEMPORAL_RULE'
        elif not events or not self.actual_fact_count or self.test_fact_count:
            status = 'NOT_ACTUAL_EXECUTION_EVIDENCE'
        elif all(event['terminal_observed'] for event in events.values()) and trace_ended:
            status = 'PASS_ACTUAL_TRACE_TEMPORAL_SCOPE'
        else:
            status = 'INCONCLUSIVE_PREFIX'
        return dict(
            status=status, events=events, issues=self.issues,
            plan_revisions_seen=self.plan_revisions,
            ignored_plan_predictions=self.ignored_predictions,
            actual_fact_count=self.actual_fact_count, controlled_test_facts=self.test_fact_count,
            interpretation='Temporal semantic scope only. Untested rules/physical motion/cross-source identity and exact receiver-token binding are not certified.',
            new_multievent_actual_execution=False)


def stream_trace(path, output):
    output.mkdir(parents=True, exist_ok=False)
    original_sha = sha(path)
    replay_protocol = dict(
        source=str(path), source_sha256=original_sha, frozen_before_replay=True,
        source_manifest={str(p):sha(p) for p in (
            Path(__file__), TABLE, SOURCE,
            ROOT/'src/kaiti_planning/ltlf_monitor.py')},
        prediction_facts_accepted=False, clock='ACTUAL_EPISODE_TIME')
    with (output/'protocol.json').open('x') as stream:
        json.dump(replay_protocol, stream, ensure_ascii=False, indent=2)
    monitor = EventTraceMonitor()
    worker_receipts = {}
    excerpts = []
    transition_index = 0
    last_actual_revision = None
    final_state = None
    with path.open() as stream:
        for number, line in enumerate(stream, 1):
            row = json.loads(line)
            phase, at = row.get('phase'), row.get('episode_time')
            if not isinstance(at, (float, int)):
                continue
            provenance = dict(
                line=number, line_sha256=hashlib.sha256(line.encode()).hexdigest(),
                phase=phase, episode_time=at)
            if phase in {'plan_committed', 'visual_repair_committed'}:
                transition_index += 1
                monitor.feed(dict(
                    kind='plan_revision', at=at,
                    revision=row.get('plan_revision'),
                    observed_transition_index=transition_index,
                    revision_provenance='ACTUAL_LOG_FIELD' if row.get('plan_revision') is not None else 'REVISION_NOT_RECORDED_TRANSITION_ONLY',
                    source=provenance))
            if phase == 'online_commitment_check':
                actual_revision = row.get('check', {}).get('plan_revision')
                if actual_revision is not None and actual_revision != last_actual_revision:
                    monitor.feed(dict(
                        kind='plan_revision', at=at, revision=actual_revision,
                        revision_provenance='ACTUAL_ONLINE_COMMITMENT_SNAPSHOT',
                        source=provenance))
                    last_actual_revision = actual_revision
            if phase == 'service_feedback':
                feedback = row.get('feedback') or {}
                if feedback.get('protocol_task_id'):
                    key = (
                        feedback['protocol_task_id'], feedback.get('phase'),
                        feedback.get('robot') or row.get('robot'),
                        feedback.get('task_revision'), feedback.get('attempt'))
                    worker_receipts[key] = dict(source=provenance, feedback=feedback)
            if phase == 'visual_candidate_created':
                fact = dict(event_id=row.get('event_id'), at=at,
                            source_kind='ACTUAL_ACK',
                            propositions=['candidate_open'], source=provenance)
                monitor.feed(fact)
                excerpts.append(fact)
            elif phase == 'visual_execution_protocol_feedback':
                message = row.get('message') or {}
                snapshot = row.get('output', {}).get('snapshot') or {}
                event = snapshot.get('event') or {}
                event_id, task_id = message.get('event_id'), message.get('task_id')
                task = snapshot.get('tasks', {}).get(task_id) or {}
                if (event.get('event_id') != event_id or task.get('event_id') != event_id
                        or not task_id or not task_id.startswith(str(event_id)+':')):
                    monitor.issue('INVALID_IDENTITY', 'Protocol/task/event identity mismatch.', provenance)
                    continue
                key = (
                    task_id, message.get('phase'), message.get('robot_id'),
                    message.get('task_revision'), message.get('attempt'))
                if key not in worker_receipts:
                    monitor.issue('MISSING_EVIDENCE', 'No matching actual worker ACK for protocol transition.', provenance)
                    continue
                role, action = task.get('role'), message.get('phase')
                facts = []
                if action == 'started' and role in {'monitor', 'pickup', 'deliver'}:
                    facts.append(role+'_started')
                if action == 'succeeded':
                    facts.append(dict(verify='verify_done', monitor='monitor_done',
                                      pickup='pickup_done', deliver='deliver_done')[role])
                    if role == 'verify':
                        if not row.get('verdict_source'):
                            monitor.issue('MISSING_EVIDENCE', 'Verify success has no explicit verdict provenance.', provenance)
                        elif event.get('verified'):
                            facts.append('fall_confirmed')
                        elif event.get('closed_reason') == 'no_fall':
                            facts.append('event_closed_negative')
                if event.get('lifecycle') == 'COMPLETED':
                    facts.append('event_completed')
                fact = dict(
                    event_id=event_id, task_id=task_id, at=at,
                    source_kind='ACTUAL_ACK', propositions=facts,
                    source=provenance, actual_worker_source=worker_receipts[key]['source'],
                    execution_token=dict(
                        owner=message.get('robot_id'), revision=message.get('task_revision'),
                        attempt=message.get('attempt')),
                    monitor_active=(
                        snapshot.get('tasks', {}).get(event_id+':monitor', {}).get('state')
                        in {'RUNNING', 'CANCEL_REQUESTED'}))
                monitor.feed(fact)
                excerpts.append(fact)
                final_state = snapshot
            elif phase == 'scripted_handover_ack':
                event_id = row.get('event_id')
                state = monitor.events.get(event_id)
                if not state or 'deliver_done' not in state['latched']:
                    monitor.issue('MISSING_EVIDENCE', 'Receiver ACK lacks its own preceding actual delivery.', provenance)
                    continue
                fact = dict(
                    event_id=event_id, at=at, source_kind='ACTUAL_ACK',
                    propositions=['handover_done'], source=provenance,
                    qualification='Controlled scenario receiver evidence; original log binds event ID, not a separate receiver execution token.')
                monitor.feed(fact)
                excerpts.append(fact)
    report = monitor.report(trace_ended=True)
    if sha(path) != original_sha:
        raise RuntimeError('Actual source trace changed during replay.')
    report.update(source=str(path), source_sha256=sha(path),
                  lines_streamed=number,
                  actual_terminal_protocol=final_state.get('event') if final_state else None,
                  source_logs_copied=False, rules_table_sha256=sha(TABLE))
    for name, value in (
            ('report.json', report), ('actual_fact_excerpts.json', excerpts),
            ('checkpoint.json', monitor.checkpoint())):
        with (output/name).open('x') as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write(chr(10))
    print(json.dumps(dict(source=str(path), status=report['status'],
                          actual_fact_count=report['actual_fact_count']), ensure_ascii=False))
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('source', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    stream_trace(args.source, args.output)
