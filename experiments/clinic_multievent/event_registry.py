"""Independent multi-event semantic registry, not a Clinic execution adapter.

Each event reuses the existing single-event transition implementation. Global
robot exclusivity, cargo ownership and explicit handover evidence are checked
before committing a transition. This module does not dispatch, reserve G1,
replace the MILP or claim that the original runtime accepts multiple events.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'src'))
from kaiti_task_sim.event_protocol import EventTaskProtocol, ProtocolError, canonical, finite


class MultiEventRegistry:
    def __init__(self, robots, *, position_ttl=10., supply=(6., 4.)):
        if not robots or any(not isinstance(r, str) or not r for r in robots):
            raise ValueError('Explicit nonempty robot capability roster required.')
        self.robots = {r:set(capabilities) for r, capabilities in robots.items()}
        self.position_ttl = position_ttl
        self.supply = tuple(supply)
        self.instances = {}
        self.handovers = {}
        self.seen = {}
        self.now = 0.
        self.imported_sources = {}

    def import_event(self, snapshot, source, registration=None):
        """Import observed single-event state without replaying or creating ACKs."""
        event = snapshot.get('event') or {}
        event_id = event.get('event_id')
        if (not event_id or event_id in self.instances
                or not isinstance(source, dict)
                or not source.get('path') or not source.get('sha256')):
            raise ProtocolError('New event identity and hash-bound observed source required.')
        path = Path(source['path'])
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != source['sha256']:
            raise ProtocolError('Imported historical source hash does not match.')
        original = json.loads(path.read_text())
        if original.get('protocol', original) != snapshot:
            raise ProtocolError('Imported business state differs from its actual source snapshot.')
        if registration is not None and registration != (
                original.get('evidence') or {}).get('registration'):
            raise ProtocolError('Imported registration differs from the actual source evidence.')
        if any(task.get('event_id') != event_id or not task_id.startswith(event_id+':')
               for task_id, task in snapshot.get('tasks', {}).items()):
            raise ProtocolError('Imported task identity does not match observed event.')
        if (event.get('space') or {}).get('provenance') == 'video_source_registered':
            if not registration:
                raise ProtocolError('Registered-video state needs its original explicit registration.')
            from kaiti_task_sim.clinic_visual_repair import RegisteredVideoProtocol
            instance = RegisteredVideoProtocol(
                position_ttl=self.position_ttl, supply=self.supply)
            instance.registration = deepcopy(registration)
        else:
            instance = EventTaskProtocol(
                position_ttl=self.position_ttl, supply=self.supply)
        instance.now = float(snapshot['time'])
        instance.world_revision = snapshot['world_revision']
        instance.event = deepcopy(event)
        instance.tasks = deepcopy(snapshot['tasks'])
        for task in instance.tasks.values():
            if task['state'] in {'RUNNING', 'CANCEL_REQUESTED'}:
                owner = task['owner']
                if owner not in self.robots or any(
                        other['owner'] == owner
                        and other['state'] in {'RUNNING', 'CANCEL_REQUESTED'}
                        for old in self.instances.values() for other in old.tasks.values()):
                    raise ProtocolError('Imported execution conflicts with the robot roster or existing commitments.')
        self.instances[event_id] = instance
        self.imported_sources[event_id] = dict(
            **deepcopy(source),
            historical_transport_deduplication='NOT_RECONSTRUCTED_FROM_A_BUSINESS_SNAPSHOT',
            actual_execution_history_replayed=False)
        self.now = max(self.now, instance.now)
        return self.snapshot()

    def snapshot(self):
        return deepcopy(dict(
            schema='clinic-multievent-registry/v1', time=self.now,
            events={event_id:instance.snapshot()
                    for event_id, instance in self.instances.items()},
            handovers=self.handovers, imported_sources=self.imported_sources,
            execution_authorized=False,
            scope='Independent semantic transitions only; shared-resource planning and runtime dispatch are separate gates.'))

    def planning_view(self):
        return dict(
            schema='clinic-multievent-planning-view/v1',
            events={event_id:instance.planning_view()
                    for event_id, instance in self.instances.items()},
            execution_authorized=False,
            adapter_status='Independent event-indexed view; not a drop-in legacy executor input.')

    def _advance_other_events(self, at, addressed, message_id):
        for event_id, instance in self.instances.items():
            if event_id == addressed:
                continue
            instance.apply(dict(
                schema='event-task/v1', kind='tick',
                message_id='__registry_tick__:'+message_id+':'+event_id, at=at))

    def _guard_start(self, message, instance):
        robot = message.get('robot_id')
        task = instance.tasks.get(message.get('task_id'))
        if task is None:
            raise ProtocolError('Feedback task does not belong to the addressed event.')
        if robot not in self.robots or not set(task['capabilities']).issubset(self.robots[robot]):
            raise ProtocolError('Robot is absent or lacks the task capabilities.')
        addressed = message['event_id']
        for event_id, other in self.instances.items():
            for active in other.tasks.values():
                if (active['state'] in {'RUNNING', 'CANCEL_REQUESTED'}
                        and active.get('owner') == robot):
                    raise ProtocolError('Robot has an unreleased execution commitment.')
            event = other.event or {}
            if (event.get('cargo_owner') == robot
                    and event.get('cargo_disposition') in {'IN_CUSTODY', 'REQUIRES_FOLLOWUP'}
                    and not (event_id == addressed and task['role'] == 'deliver')):
                raise ProtocolError('Cargo owner cannot start an unrelated event obligation.')

    def apply(self, message, verification=None):
        """Atomic application; an E2 rejection cannot mutate E1 or advance time."""
        if (message.get('schema') != 'event-task/v1'
                or not isinstance(message.get('message_id'), str)
                or not message['message_id']
                or message['message_id'].startswith('__registry_tick__')):
            raise ProtocolError('Original schema and a non-reserved message identity required.')
        at = message.get('at')
        if not finite(at) or not at >= self.now:
            raise ProtocolError('Global receive time must be finite and monotonic.')
        logical = canonical(dict(
            message={k:v for k, v in message.items() if k != 'at'},
            verification=verification))
        previous = self.seen.get(message['message_id'])
        if previous is not None and previous != logical:
            raise ProtocolError('Message identity reused for a different event or verdict.')
        event_id = message.get('event_id')
        kind = message.get('kind')
        if kind != 'tick' and (not isinstance(event_id, str) or not event_id):
            raise ProtocolError('Event identity is required.')
        draft = deepcopy(self)
        draft._advance_other_events(at, event_id, message['message_id'])
        if kind == 'tick' and event_id is None:
            result = dict(decision='GLOBAL_CLOCK_ADVANCED')
        else:
            if event_id not in draft.instances:
                if kind != 'observation':
                    raise ProtocolError('A new event requires its own observation.')
                draft.instances[event_id] = EventTaskProtocol(
                    position_ttl=draft.position_ttl, supply=draft.supply)
            instance = draft.instances[event_id]
            incoming = deepcopy(message)
            if previous is not None:
                instance.apply(dict(
                    schema='event-task/v1', kind='tick',
                    message_id='__registry_tick__duplicate:'+message['message_id']+':'+str(at),
                    at=at))
                result = dict(decision='DUPLICATE_MESSAGE')
            else:
                if kind == 'resolution' and instance.event:
                    if instance.event.get('verified') or any(
                            t['state'] in {'RUNNING', 'CANCEL_REQUESTED'}
                            for t in instance.tasks.values()):
                        raise ProtocolError('Closing active or verified obligations requires a supported safe terminal path.')
                if kind == 'feedback':
                    task = instance.tasks.get(incoming.get('task_id'))
                    if task is None or task.get('event_id') != event_id:
                        raise ProtocolError('Feedback identity does not match its event task.')
                    phase, role = incoming.get('phase'), task['role']
                    if phase == 'started':
                        draft._guard_start(incoming, instance)
                    if phase == 'succeeded' and role == 'verify':
                        if (not isinstance(verification, dict)
                                or verification.get('event_id') != event_id
                                or verification.get('result') not in {'fall', 'no_fall'}
                                or not verification.get('source')
                                or not verification.get('evidence_id')):
                            raise ProtocolError('Event-bound explicit verification evidence required.')
                        if 'result' in incoming and incoming['result'] != verification['result']:
                            raise ProtocolError('Conflicting verification results.')
                        incoming['result'] = verification['result']
                    if role == 'monitor' and phase in {'succeeded', 'cancelled'}:
                        delivery = instance.tasks.get(event_id+':deliver', {})
                        if delivery.get('state') != 'SUCCEEDED' or event_id not in draft.handovers:
                            raise ProtocolError('Monitoring cannot be released before this event delivery and handover evidence.')
                result = instance.apply(incoming)
        draft.now = float(at)
        draft.seen[message['message_id']] = logical
        self.__dict__.update(draft.__dict__)
        return dict(decision=result['decision'], snapshot=self.snapshot())

    def accept_handover(self, evidence):
        """Record an explicit receiver ACK, never synthesize one from success."""
        event_id, at = evidence.get('event_id'), evidence.get('at')
        if (not finite(at) or not at >= self.now
                or not evidence.get('source') or not evidence.get('evidence_id')):
            raise ProtocolError('Monotonic, sourced handover evidence required.')
        if event_id not in self.instances:
            raise ProtocolError('Unknown handover event.')
        instance = self.instances[event_id]
        delivery = instance.tasks.get(event_id+':deliver', {})
        if (delivery.get('state') != 'SUCCEEDED'
                or evidence.get('task_id') != event_id+':deliver'
                or evidence.get('robot_id') != delivery.get('owner')
                or evidence.get('attempt') != delivery.get('attempt')
                or evidence.get('task_revision') != delivery.get('execution_revision')):
            raise ProtocolError('Handover must match this event actual delivery identity and execution tokens.')
        old = self.handovers.get(event_id)
        if old is not None and canonical(old) != canonical(evidence):
            raise ProtocolError('Conflicting handover evidence cannot replace an accepted receipt.')
        draft = deepcopy(self)
        draft._advance_other_events(at, event_id, 'handover:'+evidence['evidence_id'])
        draft.handovers[event_id] = deepcopy(evidence)
        draft.now = float(at)
        self.__dict__.update(draft.__dict__)
        return self.snapshot()
