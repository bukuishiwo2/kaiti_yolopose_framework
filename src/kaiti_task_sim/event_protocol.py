"""Independent event/task contract reference; no ROS or production imports.

Input is semantic evidence, not images. Spatial service points are supplied by
an upstream validator; this module does not claim collision/path validation.
"""
from copy import deepcopy
import hashlib
import json
import math

SCHEMA = 'event-task/v1'
TERMINAL = {'SUCCEEDED', 'CANCELLED'}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


class ProtocolError(ValueError):
    pass


class EventTaskProtocol:
    """One episode per replay. Identity is supplied upstream, never inferred here."""
    def __init__(self, position_ttl=10., supply=(6., 4.)):
        if not finite(position_ttl) or position_ttl <= 0:
            raise ProtocolError('positive position_ttl required')
        if len(supply) != 2 or not all(finite(v) for v in supply):
            raise ProtocolError('finite supply point required')
        self.position_ttl = position_ttl
        self.supply = list(supply)
        self.now = 0.
        self.world_revision = 0
        self.event = None
        self.tasks = {}
        self.seen = {}
        self.receipts = set()

    def snapshot(self):
        return deepcopy(dict(schema=SCHEMA, time=self.now, world_revision=self.world_revision,
                             event=self.event, tasks=self.tasks))

    def _business(self):
        event = deepcopy(self.event)
        if event:
            for k in ('last_seen_at', 'position_source_at', 'revision'):
                event.pop(k, None)
        return dict(event=event, tasks=self.tasks)

    def apply(self, message):
        """Atomic transition: rejected messages cannot partially mutate the state."""
        draft = deepcopy(self)
        before = canonical(draft._business())
        before_plan = draft.planning_view()
        before_plan.pop('world_revision')
        old_tasks = deepcopy(draft.tasks)
        decision = draft._receive(deepcopy(message))
        draft._reconcile()
        changed = before != canonical(draft._business())
        after_plan = draft.planning_view()
        after_plan.pop('world_revision')
        planning_changed = canonical(before_plan) != canonical(after_plan)
        if changed:
            draft.world_revision += 1
            if draft.event:
                draft.event['revision'] += 1
        operations = []
        for task_id, task in draft.tasks.items():
            old = old_tasks.get(task_id)
            if old is None:
                operations.append(dict(task_id=task_id, operation='GENERATE', state=task['state']))
            elif old != task:
                operations.append(dict(task_id=task_id, operation='UPDATE', before=old['state'],
                                       state=task['state'], revision=task['revision'], reason=task['blockers']))
            else:
                operations.append(dict(task_id=task_id, operation='KEEP', state=task['state']))
        self.__dict__.update(draft.__dict__)
        return dict(decision=decision, changed=changed, planning_changed=planning_changed,
                    operations=operations, snapshot=self.snapshot())

    def _receive(self, m):
        if m.get('schema') != SCHEMA or not isinstance(m.get('message_id'), str) or not m['message_id']:
            raise ProtocolError('schema and nonempty message_id required')
        at = m.get('at')
        if not finite(at) or at < self.now:
            raise ProtocolError('monotonic receive time required')
        kind = m.get('kind')
        if kind not in {'observation', 'feedback', 'resolution', 'tick'}:
            raise ProtocolError('unknown kind')
        # Transport receive time is not part of logical-message identity.
        digest = hashlib.sha256(canonical({k:v for k,v in m.items() if k != 'at'}).encode()).hexdigest()
        previous = self.seen.get(m['message_id'])
        if previous and previous != digest:
            raise ProtocolError('message_id reused for a different payload')
        self.now = float(at)
        if previous:
            return 'DUPLICATE_MESSAGE'
        event_id = m.get('event_id')
        if kind != 'tick' and (not isinstance(event_id, str) or not event_id):
            raise ProtocolError('event_id required')
        if self.event and kind != 'tick' and event_id != self.event['event_id']:
            raise ProtocolError('this replay supports one supplied episode identity')
        if kind == 'observation':
            decision = self._observation(m)
        elif kind == 'feedback':
            decision = self._feedback(m)
        elif kind == 'resolution':
            if not self.event or m.get('result') not in {'no_fall', 'resolved'}:
                raise ProtocolError('explicit valid resolution required')
            self.event['closed_reason'] = m['result']
            self.event['lifecycle'] = 'CLOSED'
            decision = 'RESOLVED'
        else:
            decision = 'CLOCK_ADVANCED'
        self.seen[m['message_id']] = digest
        return decision

    def _observation(self, m):
        source_at = m.get('source_at')
        if not finite(source_at) or source_at < 0 or source_at > self.now:
            raise ProtocolError('observation source time must be finite and not future')
        status = m.get('status')
        if status not in {'confirmed', 'occluded'}:
            raise ProtocolError('confirmed or occluded expected; closure must be explicit')
        if not self.event:
            if status != 'confirmed':
                raise ProtocolError('occlusion cannot create an event')
            self.event = dict(event_id=m['event_id'], lifecycle='OPEN', perception=status,
                              revision=0, last_seen_at=source_at, position_source_at=None,
                              space=None, space_revision=0, position_valid=False,
                              verified=False, closed_reason=None, cargo_owner=None,
                              cargo_disposition='NONE')
        e = self.event
        if e['lifecycle'] in {'CLOSED', 'COMPLETED'}:
            return 'TERMINAL_EVENT_KEPT'
        if source_at < e['last_seen_at']:
            return 'STALE_OBSERVATION'
        if source_at == e['last_seen_at'] and e['space'] is not None:
            # Equal stamps can be redelivered, not used to revise geometry.
            if status != e['perception'] or ('space' in m and m['space'] != e['space']):
                raise ProtocolError('conflicting observation at the same source time')
        e['last_seen_at'] = source_at
        e['perception'] = status
        if status == 'occluded':
            return 'OCCLUSION_KEEP'
        space = m.get('space')
        if not isinstance(space, dict) or not isinstance(space.get('valid'), bool):
            raise ProtocolError('space.valid required')
        if space['valid']:
            if space.get('frame') != 'map':
                raise ProtocolError('map coordinates required')
            self._point(space.get('event_xy'))
            if not isinstance(space.get('service_points'), dict):
                raise ProtocolError('supplied service_points required')
            for role, point in space['service_points'].items():
                if role not in {'verify', 'monitor', 'deliver'}:
                    raise ProtocolError('unknown spatial task role')
                self._point(point)
        if space != e['space']:
            e['space_revision'] += 1
        e['space'] = deepcopy(space)
        e['position_source_at'] = source_at
        return 'OBSERVATION_ACCEPTED'

    @staticmethod
    def _point(point):
        if not isinstance(point, list) or len(point) != 2 or not all(finite(v) for v in point):
            raise ProtocolError('finite xy list required')

    def _new_task(self, role):
        e = self.event
        task_id = e['event_id'] + ':' + role
        if task_id in self.tasks:
            return
        self.tasks[task_id] = dict(task_id=task_id, event_id=e['event_id'], role=role,
            state='PENDING', revision=0, attempt=1, generated_at=self.now,
            capabilities=['move', 'camera' if role in {'verify', 'monitor'} else 'carry'],
            completion_dependencies=[] if role == 'verify' else
                [e['event_id'] + (':pickup' if role == 'deliver' else ':verify')],
            runtime_guards=['valid_target'] + (['monitor_active'] if role in {'pickup','deliver'} else []),
            duration_mode='until_delivery_and_finish_ack' if role == 'monitor' else 'service_ack',
            target=None, target_valid=False, required_owner=None, owner=None,
            execution_revision=None, execution_target=None, blockers=[], cancel_reason=None,
            started_at=None, finished_at=None)

    def _role(self, role):
        return self.tasks.get(self.event['event_id'] + ':' + role)

    def _active_monitor(self):
        monitor = self._role('monitor')
        return bool(monitor and monitor['state'] == 'RUNNING' and monitor['target_valid'])

    def _target(self, role):
        e = self.event
        if not e['position_valid'] or e['lifecycle'] == 'CLOSED':
            return None
        point = self.supply if role == 'pickup' else e['space']['service_points'].get(role)
        if point is None:
            return None
        return dict(frame='map', xy=list(point), space_revision=e['space_revision'])

    def _reconcile(self):
        if not self.event:
            return
        e = self.event
        stamp = e['position_source_at']
        e['position_valid'] = bool(e['space'] and e['space']['valid'] and stamp is not None and
                                   0 <= self.now-stamp <= self.position_ttl)
        if e['lifecycle'] == 'COMPLETED':
            return
        if e['lifecycle'] != 'CLOSED' and e['position_valid']:
            self._new_task('verify')
            if e['verified']:
                for role in ('monitor', 'pickup', 'deliver'):
                    self._new_task(role)
        # Stable order ensures monitor validity/cancellation affects courier guards.
        for role in ('verify', 'monitor', 'pickup', 'deliver'):
            task = self._role(role)
            if not task or task['state'] in TERMINAL:
                continue
            target = self._target(role)
            required = e['cargo_owner'] if role == 'deliver' else None
            if task['revision'] == 0 or target != task['target'] or required != task['required_owner']:
                task['target'] = target
                task['required_owner'] = required
                task['revision'] += 1
            task['target_valid'] = target is not None
            blockers = []
            if e['lifecycle'] == 'CLOSED':
                blockers.append('event_closed')
            if not e['position_valid']:
                blockers.append('position_invalid_or_expired')
            elif target is None:
                blockers.append('service_point_missing')
            for dep in task['completion_dependencies']:
                if self.tasks.get(dep, {}).get('state') != 'SUCCEEDED':
                    blockers.append('dependency:' + dep)
            if role in {'pickup','deliver'} and not self._active_monitor():
                blockers.append('monitor_not_active')
            task['blockers'] = blockers
            if task['state'] == 'CANCEL_REQUESTED':
                continue  # Restore cannot silently revoke an outstanding cancellation.
            if task['state'] == 'RUNNING':
                moved = task['execution_target'] != target
                if blockers or moved:
                    task['state'] = 'CANCEL_REQUESTED'
                    task['cancel_reason'] = 'target_changed' if moved and not blockers else ','.join(blockers)
            elif e['lifecycle'] == 'CLOSED':
                task['state'] = 'CANCELLED'
            else:
                task['state'] = 'PENDING' if blockers else 'READY'
        if e['closed_reason'] and e['cargo_owner']:
            delivery = self._role('deliver')
            if not delivery or delivery['state'] != 'SUCCEEDED':
                e['cargo_disposition'] = 'REQUIRES_FOLLOWUP'
        if e['lifecycle'] != 'CLOSED' and all(self._role(r) and self._role(r)['state']=='SUCCEEDED'
                                            for r in ('verify','monitor','pickup','deliver')):
            e['lifecycle'] = 'COMPLETED'

    def _feedback(self, m):
        task = self.tasks.get(m.get('task_id'))
        if task is None or not self.event:
            raise ProtocolError('feedback for unknown task')
        phase = m.get('phase')
        robot = m.get('robot_id')
        if phase not in {'started', 'succeeded', 'cancelled'} or not isinstance(robot, str) or not robot:
            raise ProtocolError('valid phase and robot_id required')
        if any(not isinstance(m.get(k),int) or isinstance(m[k],bool) or m[k]<1
               for k in ('attempt','task_revision')):
            raise ProtocolError('positive integer execution tokens required')
        signature = canonical({k:m.get(k) for k in ('task_id','attempt','task_revision','phase','robot_id','result')})
        if signature in self.receipts:
            return 'DUPLICATE_FEEDBACK'
        if task['attempt'] != m.get('attempt'):
            raise ProtocolError('stale execution attempt')
        expected = task['execution_revision'] if task['state'] in {'RUNNING','CANCEL_REQUESTED'} else task['revision']
        if m.get('task_revision') != expected:
            raise ProtocolError('stale task revision')
        # Reconcile against receive-time freshness before authorizing any start.
        self._reconcile()
        if phase == 'started':
            if task['state'] != 'READY' or self.event['lifecycle'] != 'OPEN':
                raise ProtocolError('task is not ready')
            if task['required_owner'] and robot != task['required_owner']:
                raise ProtocolError('delivery must keep cargo owner')
            if task['role'] in {'pickup','deliver'} and robot == self._role('monitor')['owner']:
                raise ProtocolError('monitor and courier must be distinct')
            if task['role'] == 'monitor':
                courier = self._role('pickup')
                if courier and courier['owner'] == robot:
                    raise ProtocolError('monitor and courier must be distinct')
            if any(t['state'] in {'RUNNING','CANCEL_REQUESTED'} and t['owner']==robot for t in self.tasks.values()):
                raise ProtocolError('robot has unreleased execution')
            task.update(state='RUNNING',owner=robot,execution_revision=task['revision'],
                        execution_target=deepcopy(task['target']),started_at=self.now)
        elif phase == 'cancelled':
            if task['state'] != 'CANCEL_REQUESTED' or robot != task['owner']:
                raise ProtocolError('cancellation acknowledgement does not match active execution')
            task.update(state='CANCELLED' if self.event['lifecycle']=='CLOSED' else 'PENDING',
                        owner=None,execution_revision=None,execution_target=None,started_at=None,
                        cancel_reason=None,attempt=task['attempt']+1)
        else:
            if task['state'] != 'RUNNING' or robot != task['owner']:
                raise ProtocolError('success requires matching running execution, not cancellation request')
            role = task['role']
            if role == 'monitor' and self._role('deliver')['state'] != 'SUCCEEDED':
                raise ProtocolError('monitor must cover delivery completion')
            if role == 'verify':
                if m.get('result') not in {'fall','no_fall'}:
                    raise ProtocolError('verification verdict required')
                if m['result'] == 'fall':
                    self.event['verified'] = True
                else:
                    self.event.update(lifecycle='CLOSED',closed_reason='no_fall')
            if role == 'pickup':
                self.event.update(cargo_owner=robot,cargo_disposition='IN_CUSTODY')
            if role == 'deliver':
                self.event['cargo_disposition'] = 'DELIVERED'
            task.update(state='SUCCEEDED',finished_at=self.now)
        self.receipts.add(signature)
        return 'FEEDBACK_ACCEPTED'

    def planning_view(self):
        """Contract only: pending future tasks are schedulable, not executable yet.

        Consumers MUST compile completion_dependencies, runtime_guards and
        relations. This is intentionally not a drop-in legacy MILP input.
        """
        e = self.event
        future = [deepcopy(t) for t in self.tasks.values() if t['state'] in {'PENDING','READY'} and t['target_valid']]
        reservations = [deepcopy(t) for t in self.tasks.values() if t['state'] in {'RUNNING','CANCEL_REQUESTED'}]
        return dict(schema=SCHEMA,world_revision=self.world_revision,tasks=future,
                    active_commitments=reservations,
                    completed_facts=[deepcopy(t) for t in self.tasks.values() if t['state']=='SUCCEEDED'],
                    relations=[] if not e or not self._role('monitor') else [
                        dict(kind='monitor_covers_delivery',monitor=e['event_id']+':monitor',pickup=e['event_id']+':pickup',deliver=e['event_id']+':deliver'),
                        dict(kind='same_courier_distinct_monitor',pickup=e['event_id']+':pickup',deliver=e['event_id']+':deliver',monitor=e['event_id']+':monitor')])
