"""Frozen existing B0/B1/B2/B3 policies; no new allocation algorithm.

B1 extends the previous exhaustive bundle insertion only to accept one newly
released ordinary transport pair. Its nominal owner is not an accepted owner.
All methods keep the same third-role business constraint and native validator.
"""
from copy import deepcopy
import itertools
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'src'))
from kaiti_task_sim import clinic_assignment as base

native, digest, warm_values, WEIGHTS = base.native, base.digest, base.warm_values, base.WEIGHTS
METHODS = ('B0', 'B1', 'B2', 'B3')


def domains(p, method):
    eligible = base.domains(p, 'B3')
    for j, t in p['tasks'].items():
        lock = None
        if method == 'B0':
            lock = p['static_owners'][j]
        elif t['kind'] == 'normal' and (method == 'B1' or method == 'B2' and j != p.get('necessary_normal')):
            lock = p['accepted_reference']['owners'].get(j, p['nominal_owners'][j])
        if lock is not None:
            eligible[j] = [r for r in eligible[j] if r == lock]
    return eligible


def business_check(p, plan):
    j = p.get('necessary_normal')
    return j is None or plan['owners'][j] not in (plan['owners']['E1_monitor'], plan['owners']['E1_pickup'])


def validate(p, plan, method, claimed=None):
    q = base.validate(p, plan, 'B3', claimed)
    eligible = domains(p, method)
    for j, r in plan['owners'].items():
        q['checks'] += 1
        if r not in eligible[j]:
            q['errors'].append(dict(name='policy_domain_'+j, residual=1.))
    q['checks'] += 1
    if not business_check(p, plan):
        q['errors'].append(dict(name='required_third_role', residual=1.))
    q.update(passed=not q['errors'], execution_authorized=False)
    return q


def model(p, method):
    tpl, m, v = base.model(p, 'B3')
    a, _ = native()
    eligible = domains(p, method)
    for j in p['tasks']:
        for r in p['robots']:
            if r not in eligible[j]:
                m += v[a.b.xk(r, j)] == 0., 'policy_owner_'+r+'_'+j
    if p.get('necessary_normal'):
        for r in p['robots']:
            m += sum(v[a.b.xk(r, j)] for j in (p['necessary_normal'], 'E1_monitor', 'E1_pickup')) <= 1., 'policy_third_'+r
    return tpl, m, v


def common_signature(p, method):
    _, m, _ = model(p, method)
    return digest(dict(
        rows={n:dict(sense=c.sense, constant=c.constant,
                     coefficients=sorted((v.name, x) for v, x in c.items()))
              for n, c in m.constraints.items() if not n.startswith('policy_owner_')},
        objective=dict(constant=m.objective.constant, coefficients=sorted((v.name, x) for v, x in m.objective.items())),
        variables={v.name:[v.lowBound, v.upBound, v.cat] for v in m.variables()}))


def greedy(p, method='B1', deadline=float('inf')):
    eligible = domains(p, method)
    initial = deepcopy(p['accepted_reference']['routes'])
    new_pairs = p.get('new_normal_pairs', [])
    if len(new_pairs) > 1:
        raise ValueError('Only the predeclared one-new-transport scenario is supported')
    ordinary_queues = [initial]
    for pick, drop in new_pairs:
        ordinary_queues = []
        # Ordinary order is a nominal initial allocation, never an accepted one.
        for r in eligible[pick]:
            if r not in eligible[drop]:
                continue
            for slot in range(len(initial[r])+1):
                q = deepcopy(initial)
                q[r][slot:slot] = [pick, drop]
                ordinary_queues.append(q)
    candidates, reasons, evaluations = [], {}, 0

    def consider(routes):
        nonlocal evaluations
        if time.perf_counter() >= deadline:
            return
        evaluations += 1
        plan, reason = base.schedule_routes(p, routes)
        if plan:
            check = validate(p, plan, method)
            if not check['passed']:
                reason = ','.join(e['name'] for e in check['errors'][:4])
                plan = None
        if not plan:
            reasons[reason] = reasons.get(reason, 0)+1
            return
        first = plan['starts'].get('E1_verify', plan['starts'].get('E1_monitor', p['time']))
        finish = plan['finishes'].get('E1_deliver', max(plan['ends'].values()))
        candidates.append(((first, finish, sum(base.parts(p, plan).values()), json.dumps(routes, sort_keys=True)), plan))

    for routes in ordinary_queues:
        if 'E1_verify' in p['tasks']:
            for r in eligible['E1_verify']:
                for slot in range(len(routes[r])+1):
                    q = deepcopy(routes)
                    q[r].insert(slot, 'E1_verify')
                    consider(q)
        elif 'E1_monitor' in p['tasks']:
            for monitor, courier in itertools.product(eligible['E1_monitor'], eligible['E1_pickup']):
                if monitor == courier or courier not in eligible['E1_deliver']:
                    continue
                for i, j in itertools.product(range(len(routes[monitor])+1), range(len(routes[courier])+1)):
                    q = deepcopy(routes)
                    q[monitor].insert(i, 'E1_monitor')
                    q[courier][j:j] = ['E1_pickup', 'E1_deliver']
                    consider(q)
        else:
            consider(routes)
    if not candidates:
        return dict(status='GREEDY_NO_FEASIBLE_INSERTION', evaluations=evaluations, reasons=reasons)
    _, plan = min(candidates, key=lambda q:q[0])
    value = sum(base.parts(p, plan).values())
    return dict(status='FEASIBLE_CONSTRUCTIVE', plan=plan, objective=value,
                validation=validate(p, plan, method, value), evaluations=evaluations, reasons=reasons)


def metrics(p, plan):
    q = base.metrics(p, plan)
    due = p.get('routine_due_at', {})
    tardiness = {j:max(0., plan['finishes'][j]-d) for j, d in due.items()}
    q.update(routine_tardiness=tardiness, total_routine_tardiness=sum(tardiness.values()),
             routine_late_count=sum(v > 1e-5 for v in tardiness.values()),
             minimum_due_slack=min((d-plan['finishes'][j] for j, d in due.items()), default=None),
             due_mode=p.get('due_mode', 'NONE'),
             due_provenance='PRESPECIFIED_HYPOTHETICAL_SLA_NOT_HISTORICAL_HOSPITAL_OBSERVATION',
             execution_authorized=False, new_physical_trial=False)
    if p['scenario']['family'] == 'S1':
        _, contract = native()
        arrival = {r:p['robots'][r]['ready']+contract.tau(p, r, 'src', 'E1_verify')
                   for r in domains(p, 'B3')['E1_verify']}
        owner = plan['owners']['E1_verify']
        q.update(verify_owner=owner, earliest_service_lower_bound=min(arrival.values()),
                 verify_service_lower_bound_gap=plan['starts']['E1_verify']-min(arrival.values()),
                 earliest_robot_arrivals=arrival)
    return q
