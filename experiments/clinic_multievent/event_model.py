"""Event-indexed remaining-interval MILP in an independent experimental entry.

The unchanged native model supplies assignment, route, capability, energy,
dependency and transport constraints. Its future-event guard is retained:
positive events still need a complete remaining monitor/pickup/deliver graph.
An observed active monitor is represented explicitly as a remaining interval,
with its actual execution identity retained separately, never as a new start.

Required additions to a prepared native problem:
event_index, assignment_weights, allowed_robots, hard_owners, state_version.
active_bindings and issued_bindings preserve observed executions; resource_leases
bind actual lease holders to remaining task intervals. Future availability and
all output times are planning forecasts. This module cannot dispatch or close
an actual event and does not implement monitoring or physical cargo handover.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import os
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
WORKSPACE = Path(os.environ.get('CLINIC_WORKSPACE', '/home/yhc/clinic_planning_ws')).expanduser()
TOOLS = WORKSPACE/'tools'
if not TOOLS.is_dir():
    TOOLS = ROOT/'experiments/clinic/tools'
if not TOOLS.is_dir():
    raise FileNotFoundError('Clinic tools are not available; set CLINIC_WORKSPACE or use the uploaded experiments/clinic snapshot')
sys.path.insert(0, str(TOOLS))
import aligned_solver as native
import aligned_contract as original_check

FROZEN_WEIGHTS = dict(response=4., completion=.1, normal_wait=.1,
                      owner=2., shift=.05, travel=.1)
OPEN_PHASES = {'CANDIDATE', 'CONFIRMED', 'ACTIVE'}


def digest(value):
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def preflight(p):
    """Return BLOCKED for unsupported state expression, not solver infeasibility."""
    errors = []
    def require(ok, message):
        if not ok:
            errors.append(message)
    require(p.get('assignment_weights') == FROZEN_WEIGHTS,
            'Existing shared objective weights must be retained.')
    expected = {
        'travel':.1, 'normal_delay':.1, 'response':0., 'wait':0.,
        'energy':0., 'owner':2., 'shift':.05, 'adjacency':0., 'return':0.
    }
    require(p.get('weights') == expected,
            'Native objective must use the frozen allocation-adapter contract.')
    require(isinstance(p.get('state_version'), int), 'An explicit state version is required.')
    events = p.get('event_index', {})
    require(bool(events), 'An event-indexed obligation ledger is required.')
    referenced = {}
    for event_id, event in events.items():
        require(event.get('event_id') == event_id, 'Event-index identity mismatch: '+event_id)
        phase = event.get('phase')
        require(phase in OPEN_PHASES | {'COMPLETED', 'CLOSED_NEGATIVE'},
                'Unknown event phase: '+event_id)
        roles = event.get('tasks', {})
        if phase in OPEN_PHASES:
            require(event.get('position_valid') is True,
                    'Invalid event position: '+event_id)
            require(event.get('position_source') in {'video_source_registered', 'sensor_estimated'},
                    'Explicit position provenance required: '+event_id)
        needed = ('verify',) if phase == 'CANDIDATE' else (
            ('monitor', 'pickup', 'deliver') if phase in {'CONFIRMED', 'ACTIVE'} else ())
        for role, job in roles.items():
            if job in p['tasks']:
                task = p['tasks'][job]
                require(task.get('event_id') == event_id and task['kind'] == role,
                        'Task/event/role identity mismatch: '+job)
                require(job not in referenced, 'Task used by multiple events: '+job)
                referenced[job] = event_id
        for role in needed:
            require(roles.get(role) in p['tasks'],
                    'Missing remaining '+role+' obligation: '+event_id)
        if phase == 'CANDIDATE':
            require(not any(roles.get(r) in p['tasks'] for r in ('monitor', 'pickup', 'deliver')),
                    'An unconfirmed event cannot release response services: '+event_id)
        if phase in {'CONFIRMED', 'ACTIVE'}:
            require(event.get('confirmed_at') is not None and event.get('verification_source'),
                    'Explicit confirmation clock/source required: '+event_id)
            require(event.get('handover_required') is True,
                    'An event-specific handover obligation cannot be removed: '+event_id)
        if phase in {'COMPLETED', 'CLOSED_NEGATIVE'}:
            require(not any(job in p['tasks'] for job in roles.values()),
                    'Terminal event still has optimizable service obligations: '+event_id)
            require(bool(event.get('terminal_evidence')),
                    'A terminal event needs its own actual or labelled fixture evidence: '+event_id)
            evidence = event.get('terminal_evidence') or {}
            require(isinstance(evidence, dict)
                    and evidence.get('event_id') == event_id
                    and bool(evidence.get('source')) and bool(evidence.get('evidence_id')),
                    'Terminal evidence must be bound to its own event: '+event_id)
            if phase == 'COMPLETED' and isinstance(evidence, dict):
                receipts = evidence.get('role_receipts', {})
                require(all(
                    isinstance(receipts.get(role), dict)
                    and receipts[role].get('event_id') == event_id
                    and receipts[role].get('role') == role
                    and bool(receipts[role].get('evidence_id'))
                    for role in ('verify', 'monitor', 'pickup', 'deliver', 'handover')),
                    'Completed event lacks its own full closure evidence: '+event_id)
    for job, task in p['tasks'].items():
        if task['kind'] in {'verify', 'monitor', 'pickup', 'deliver'}:
            require(job in referenced, 'Unindexed event task: '+job)
        require(job in p.get('allowed_robots', {}), 'Missing legal domain: '+job)
    active = p.get('active_bindings', {})
    for job, binding in active.items():
        require(job in p['tasks'], 'Active obligation omitted: '+job)
        if job not in p['tasks']:
            continue
        task = p['tasks'][job]
        require(binding.get('mode') == 'monitor_continuation' and task['kind'] == 'monitor',
                'Unsupported active-service continuation: '+job)
        require(binding.get('event_id') == task.get('event_id'),
                'Active event identity changed: '+job)
        require(binding.get('owner') in p['robots'], 'Unknown active owner: '+job)
        require(isinstance(binding.get('actual_started_at'), (float, int))
                and p['time'] >= binding['actual_started_at'],
                'Observed monitor start required: '+job)
        require(bool(binding.get('record_task_id')) and bool(binding.get('execution_target'))
                and binding.get('attempt') is not None
                and binding.get('execution_revision') is not None,
                'Active execution identity cannot be fabricated: '+job)
        require(job not in p['reference']['starts'],
                'A residual interval must not be charged as an accepted service-start shift: '+job)
        require(task.get('start_deadline') is None,
                'Original start deadline must be audited against actual start, not residual start: '+job)
        old_limit = binding.get('original_start_deadline')
        if old_limit is not None:
            require(old_limit >= binding['actual_started_at'],
                    'Actual monitor start violated its original deadline: '+job)
        owner = binding.get('owner')
        if owner in p['robots']:
            require(p['robots'][owner]['source_anchor'] == task['anchor'],
                    'Active service must start its residual interval at the actual service anchor: '+job)
            require(p['time'] >= p['robots'][owner]['ready'],
                    'Active monitor cannot be projected behind a future release: '+job)
    for event_id, event in events.items():
        if event.get('phase') == 'ACTIVE':
            require(event['tasks'].get('monitor') in active,
                    'Active event has no preserved monitor continuation: '+event_id)
    for job, binding in p.get('issued_bindings', {}).items():
        require(job in p['tasks'] and binding.get('owner') in p['robots'],
                'Issued action missing from the remaining graph: '+job)
        require(bool(binding.get('record_task_id')) and bool(binding.get('goal')),
                'Issued action identity/goal required: '+job)
        require(binding.get('state') not in {'SERVICE_RUNNING', 'BED_WAIT'},
                'Running non-monitor or unknown blocked navigation requires a separate state contract: '+job)
    for lease in p.get('resource_leases', []):
        require(lease.get('holder_task') in p['tasks'] and bool(lease.get('lease_id')),
                'An actual lease needs a represented holder interval and identity.')
    require(all(robot.get('move_rate') == robot.get('idle_rate') == 0.
                for robot in p['robots'].values())
            and all(task.get('energy_rate') == 0. for task in p['tasks'].values()),
            'Nonzero active-prefix battery accounting is not implemented.')
    for pair in p.get('required_monitor_overlap', []):
        require(len(pair) == 2 and all(
            event_id in events and events[event_id].get('phase') in {'CONFIRMED', 'ACTIVE'}
            for event_id in pair), 'Monitor-overlap test needs two represented positive events.')
    return dict(status='BLOCKED' if errors else 'READY',
                passed=not errors, errors=errors, execution_authorized=False)


def native_view(p):
    q = deepcopy(p)
    q['events'] = {}
    for event_id, event in p['event_index'].items():
        if event['phase'] in {'CONFIRMED', 'ACTIVE'}:
            q['events'][event_id] = dict(
                monitor=event['tasks']['monitor'], pickup=event['tasks']['pickup'],
                deliver=event['tasks']['deliver'], observed_at=event['candidate_at'])
    return q


def stage_response(p, plan):
    total = 0.
    for event in p['event_index'].values():
        roles, phase = event['tasks'], event['phase']
        if phase == 'CANDIDATE':
            total += plan['starts'][roles['verify']]-event['candidate_at']
        elif phase in {'CONFIRMED', 'ACTIVE'}:
            job = roles['monitor']
            start = (p.get('active_bindings', {}).get(job, {}).get('actual_started_at')
                     if job in p.get('active_bindings', {}) else plan['starts'][job])
            total += start-event['confirmed_at']
    return total


def objective_parts(p, plan):
    w, reference = p['assignment_weights'], p['reference']
    travel = 0.
    for robot, route in plan['routes'].items():
        for a, b in zip(['src']+route, route+['end']):
            travel += original_check.tau(p, robot, a, b)
    return dict(
        response=w['response']*stage_response(p, plan),
        completion=w['completion']*(max(plan['ends'].values())-p['time']),
        normal_wait=w['normal_wait']*sum(
            plan['starts'][j]-t['release'] for j, t in p['tasks'].items() if t['kind'] == 'normal'),
        owner=w['owner']*sum(plan['owners'][j] != r for j, r in reference['owners'].items()),
        shift=w['shift']*sum(abs(plan['starts'][j]-t) for j, t in reference['starts'].items()),
        travel=w['travel']*travel)


class EventIndexedModel(native.Model):
    def __init__(self, problem):
        gate = preflight(problem)
        if not gate['passed']:
            raise ValueError(json.dumps(gate, ensure_ascii=False))
        self.semantic = deepcopy(problem)
        core = native_view(problem)
        # The old builder rejects resource-sharing monitors because their
        # duration is variable. Restore every such constraint below using f_j.
        # The independent checker always receives the complete semantic input.
        for task in core['tasks'].values():
            if task['kind'] == 'monitor':
                task['resources'] = []
        super().__init__(core)

    def _build(self):
        super()._build()
        p, b = self.semantic, native.b
        w, big_m = p['assignment_weights'], 5*p['horizon']+20.
        self.var('allocation_cmax', p['time'], p['horizon'])
        for robot in p['robots']:
            self.row('allocation_end_'+robot, {'allocation_cmax':1., 'end_'+robot:-1.})
        self.add_cost('allocation_cmax', w['completion'])
        self.constant -= w['completion']*p['time']
        for event_id, event in p['event_index'].items():
            roles, phase = event['tasks'], event['phase']
            if phase == 'CANDIDATE':
                self.add_cost('s_'+roles['verify'], w['response'])
                self.constant -= w['response']*event['candidate_at']
            elif phase in {'CONFIRMED', 'ACTIVE'}:
                monitor, deliver = roles['monitor'], roles['deliver']
                if monitor in p.get('active_bindings', {}):
                    self.constant += w['response']*(
                        p['active_bindings'][monitor]['actual_started_at']-event['confirmed_at'])
                else:
                    self.add_cost('s_'+monitor, w['response'])
                    self.constant -= w['response']*event['confirmed_at']
                self.row('handover_'+event_id,
                         {'f_'+monitor:1., 's_'+deliver:-1.},
                         p['tasks'][deliver]['duration']+4.)
                clearance = event.get('clearance_task')
                if clearance:
                    self.eq('direct_monitor_clear_'+event_id,
                            {b.ak(r, monitor, clearance):1. for r in p['robots']}, 1.)
                    for robot in p['robots']:
                        self.eq('same_monitor_clear_'+event_id+'_'+robot,
                                {b.xk(robot, monitor):1., b.xk(robot, clearance):-1.})
                        finish, constant = self.finish(clearance)
                        for job, task in p['tasks'].items():
                            if task['kind'] != 'normal':
                                continue
                            coefficients = {
                                's_'+job:1.,
                                b.xk(robot, job):-big_m,
                                b.xk(robot, roles['pickup']):-big_m,
                                **{key:-value for key, value in finish.items()}}
                            self.row('courier_after_clear_'+event_id+'_'+robot+'_'+job,
                                     coefficients,
                                     constant+p['tasks'][clearance].get('egress', 0.)+
                                     event['clearance_margin']-2*big_m)
        owners = dict(p.get('hard_owners', {}))
        for bindings in (p.get('active_bindings', {}), p.get('issued_bindings', {})):
            for job, binding in bindings.items():
                if job in owners and owners[job] != binding['owner']:
                    raise ValueError('Conflicting immutable owner: '+job)
                owners[job] = binding['owner']
        for job, task in p['tasks'].items():
            for robot in p['robots']:
                if robot not in p['allowed_robots'][job] or (
                        job in owners and owners[job] != robot):
                    self.eq('qualified_'+robot+'_'+job, {b.xk(robot, job):1.})
        for job, binding in p.get('active_bindings', {}).items():
            self.eq('continuation_now_'+job, {'s_'+job:1.}, p['time'])
            self.eq('continuation_first_'+job,
                    {b.ak(binding['owner'], 'src', job):1.}, 1.)
        for job, binding in p.get('issued_bindings', {}).items():
            self.eq('issued_first_'+job,
                    {b.ak(binding['owner'], 'src', job):1.}, 1.)
        for n, policy in enumerate(p.get('third_role_policies', [])):
            event = p['event_index'][policy['event_id']]
            jobs = (policy['normal_task'], event['tasks']['monitor'], event['tasks']['pickup'])
            for robot in p['robots']:
                self.row('third_role_'+str(n)+'_'+robot,
                         {b.xk(robot, job):-1. for job in jobs}, -1.)
        for n, pair in enumerate(p.get('required_monitor_overlap', [])):
            left, right = (p['event_index'][event]['tasks']['monitor'] for event in pair)
            # A positive overlap is a structural concurrency test, not a new
            # emergency response limit or a changed objective weight.
            self.row('overlap_left_'+str(n), {'f_'+left:1., 's_'+right:-1.}, .001)
            self.row('overlap_right_'+str(n), {'f_'+right:1., 's_'+left:-1.}, .001)
        jobs = list(p['tasks'])
        for number, u in enumerate(jobs):
            for v in jobs[number+1:]:
                if not set(p['tasks'][u]['resources']).intersection(p['tasks'][v]['resources']):
                    continue
                key = self.var('semantic_resource_'+u+'_'+v, 0., 1., binary=True)
                uf, uc = self.finish(u)
                vf, vc = self.finish(v)
                self.ge('semantic_u_first_'+key,
                        {'s_'+v:1., **{k:-x for k, x in uf.items()}},
                        uc+p['tasks'][u].get('egress', 0.)+
                        p['tasks'][v].get('approach', 0.)+p['buffer'], key, big_m)
                self.row('semantic_v_first_'+key,
                         {'s_'+u:1., key:big_m, **{k:-x for k, x in vf.items()}},
                         vc+p['tasks'][v].get('egress', 0.)+
                         p['tasks'][u].get('approach', 0.)+p['buffer'])
        for n, lock in enumerate(p.get('fixed_resources', [])):
            for job, task in p['tasks'].items():
                if lock['resource'] in task['resources']:
                    self.row('semantic_fixed_'+str(n)+'_'+job,
                             {'s_'+job:1.},
                             lock['finish']+p['buffer']+task.get('approach', 0.))
        for n, lock in enumerate(p.get('blocked_resources', [])):
            for job, task in p['tasks'].items():
                if lock['resource'] not in task['resources']:
                    continue
                key = self.var('semantic_block_'+str(n)+'_'+job, 0., 1., binary=True)
                finish, constant = self.finish(job)
                self.ge(key+'_after', {'s_'+job:1.},
                        lock['finish']+p['buffer']+task.get('approach', 0.), key, big_m)
                self.row(key+'_before', {key:big_m, **{k:-v for k, v in finish.items()}},
                         constant+task.get('egress', 0.)+p['buffer']-lock['start'])
        for n, lease in enumerate(p.get('resource_leases', [])):
            holder = lease['holder_task']
            finish, constant = self.finish(holder)
            for job, task in p['tasks'].items():
                if job != holder and lease['resource'] in task['resources']:
                    self.row('lease_'+str(n)+'_'+job,
                             {'s_'+job:1., **{k:-v for k, v in finish.items()}},
                             constant+p['tasks'][holder].get('egress', 0.)+
                             task.get('approach', 0.)+p['buffer'])


def build_model(p):
    template = EventIndexedModel(p)
    b = native.b
    model, variables = template.pulp_model(dict(free=list(p['tasks']), freeze_time=False))
    outer = {key:b.pulp.LpVariable(key, *template.bounds[key]) for key in template.outer}
    all_variables = dict(variables, **outer)
    for row in template.rows:
        if any(key in outer for key in row.coefficients):
            model += sum(value*all_variables[key] for key, value in row.coefficients.items()) >= row.rhs, row.name
    model += template.constant+sum(value*all_variables[key] for key, value in template.cost.items())
    return template, model, all_variables


def validate(p, plan, claimed=None):
    gate = preflight(p)
    if not gate['passed']:
        return dict(passed=False, status='BLOCKED', checks=0, errors=gate['errors'])
    try:
        result = original_check.validate(
            native_view(p), plan, dict(free=list(p['tasks']), freeze_time=False))
    except (KeyError, ValueError, IndexError, TypeError) as error:
        return dict(passed=False, checks=1, errors=[
            dict(name='malformed_or_inconsistent_plan', detail=repr(error), residual=1.)])
    def check(name, condition):
        result['checks'] += 1
        if not condition:
            result['errors'].append(dict(name=name, residual=1.))
    check('all_tasks_preserved', set(plan['owners']) == set(p['tasks']))
    check('input_version_and_digest', plan.get('state_version') == p['state_version']
          and plan.get('input_sha256') == digest(p))
    check('active_identity_retained',
          plan.get('retained_active_bindings') == p.get('active_bindings', {}))
    check('issued_identity_retained',
          plan.get('retained_issued_bindings') == p.get('issued_bindings', {}))
    check('leases_retained', plan.get('retained_resource_leases') == p.get('resource_leases', []))
    for job, owner in plan['owners'].items():
        check('legal_domain_'+job, owner in p['allowed_robots'][job])
        if job in p.get('hard_owners', {}):
            check('hard_owner_'+job, owner == p['hard_owners'][job])
    for job, binding in p.get('active_bindings', {}).items():
        owner = binding['owner']
        check('active_owner_'+job, plan['owners'][job] == owner)
        check('residual_interval_origin_'+job, not abs(plan['starts'][job]-p['time']) > 1e-5)
        check('active_interval_first_'+job, plan['routes'][owner][0] == job)
    for job, binding in p.get('issued_bindings', {}).items():
        owner = binding['owner']
        check('issued_owner_'+job, plan['owners'][job] == owner)
        check('issued_action_first_'+job, plan['routes'][owner][0] == job)
    for event_id, event in p['event_index'].items():
        if event['phase'] in {'CONFIRMED', 'ACTIVE'}:
            roles = event['tasks']
            check('event_handover_'+event_id,
                  plan['finishes'][roles['monitor']]+1e-5 >= plan['finishes'][roles['deliver']]+4.)
            clearance = event.get('clearance_task')
            if clearance:
                monitor, courier = plan['owners'][roles['monitor']], plan['owners'][roles['pickup']]
                route = plan['routes'][monitor]
                check('same_monitor_clear_'+event_id, plan['owners'][clearance] == monitor)
                check('direct_monitor_clear_'+event_id,
                      clearance in route and roles['monitor'] in route
                      and route.index(clearance) == route.index(roles['monitor'])+1)
                area_clear = (plan['finishes'][clearance]+
                              p['tasks'][clearance].get('egress', 0.)+
                              event['clearance_margin'])
                for job in plan['routes'][courier]:
                    if p['tasks'][job]['kind'] == 'normal':
                        check('courier_after_clear_'+event_id+'_'+job,
                              plan['starts'][job]+1e-5 >= area_clear)
    for lease in p.get('resource_leases', []):
        holder = lease['holder_task']
        for job, task in p['tasks'].items():
            if job != holder and lease['resource'] in task['resources']:
                check('lease_occupation_'+lease['lease_id']+'_'+job,
                      plan['starts'][job]-task.get('approach', 0.)+1e-5 >=
                      plan['finishes'][holder]+p['tasks'][holder].get('egress', 0.)+p['buffer'])
    for lock in p.get('fixed_resources', []):
        for job, task in p['tasks'].items():
            if lock['resource'] in task['resources']:
                check('full_fixed_occupation_'+job,
                      plan['starts'][job]-task.get('approach', 0.)+1e-5 >=
                      lock['finish']+p['buffer'])
    for policy in p.get('third_role_policies', []):
        roles = p['event_index'][policy['event_id']]['tasks']
        check('third_role_'+policy['event_id'],
              plan['owners'][policy['normal_task']] not in
              (plan['owners'][roles['monitor']], plan['owners'][roles['pickup']]))
    for pair in p.get('required_monitor_overlap', []):
        left, right = (p['event_index'][event]['tasks']['monitor'] for event in pair)
        check('required_monitor_overlap_'+':'.join(pair),
              min(plan['finishes'][left], plan['finishes'][right])-
              max(plan['starts'][left], plan['starts'][right]) >= .001-1e-5)
    parts = objective_parts(p, plan)
    if claimed is not None:
        check('independent_event_indexed_objective', not abs(sum(parts.values())-claimed) > 1e-4)
    result.update(passed=not result['errors'], objective_parts=parts,
                  execution_authorized=False, predicted_closure_is_actual=False)
    return result
