TOL = 1e-6

def tau(p, i, u, v):
    """Clinic fixed-map path prior; used by model, objective and validation alike."""
    a = p['robots'][i]['source_anchor'] if u == 'src' else p['tasks'][u]['anchor']
    b = p['robots'][i]['home_anchor'] if v == 'end' else p['tasks'][v]['anchor']
    return float(p['travel_times'][a][b])

def objective(p, plan):
    w = p['weights']
    ref = p['reference']
    travel_sum = wait = draw = adj = 0.0
    for (i, route) in plan['routes'].items():
        r = p['robots'][i]
        previous = 'src'
        finish = r['ready']
        pairs = set(zip(route, route[1:]))
        old = [j for j in ref['routes'].get(i, []) if j in p['tasks']]
        adj += sum((pair not in pairs for pair in zip(old, old[1:])))
        for j in route + ['end']:
            start = plan['ends'][i] if j == 'end' else plan['starts'][j]
            dt = tau(p, i, previous, j)
            idle = start - finish - dt
            travel_sum += dt
            wait += idle
            draw += r['move_rate'] * dt + r['idle_rate'] * idle
            if j != 'end':
                t = p['tasks'][j]
                draw += t['energy_rate'] * (plan['finishes'][j] - start)
            finish = start if j == 'end' else plan['finishes'][j]
            previous = j
    response = sum((plan['starts'][e['monitor']] + plan['finishes'][e['deliver']] - 2 * e['observed_at'] for e in p['events'].values()))
    parts = {'travel': w['travel'] * travel_sum, 'wait': w['wait'] * wait, 'energy': w['energy'] * draw, 'response': w['response'] * response, 'normal_delay': w['normal_delay'] * sum((plan['starts'][j] - t['release'] for (j, t) in p['tasks'].items() if t['kind'] == 'normal')), 'owner': w['owner'] * sum((plan['owners'][j] != i for (j, i) in ref['owners'].items() if j in p['tasks'])), 'shift': w['shift'] * sum((abs(plan['starts'][j] - ref['starts'][j]) for j in ref['owners'] if j in p['tasks'])), 'adjacency': w['adjacency'] * adj, 'return': w['return'] * sum((plan['ends'][i] - p['robots'][i]['ready'] for i in p['robots']))}
    return parts

def validate(p, plan, scope, claimed=None):
    errors = []
    checks = 0
    maximum = 0.0

    def check(name, left, right, equal=False):
        nonlocal checks, maximum
        residual = abs(left - right) if equal else max(0, right - left)
        maximum = max(maximum, residual)
        checks += 1
        if residual > TOL:
            errors.append({'name': name, 'residual': residual})
    counts = {j: 0 for j in p['tasks']}
    for (i, route) in plan['routes'].items():
        robot = p['robots'][i]
        energy = robot['energy']
        previous = 'src'
        finish = robot['ready']
        for j in route + ['end']:
            s = plan['ends'][i] if j == 'end' else plan['starts'][j]
            dt = tau(p, i, previous, j)
            gap = s - finish - dt
            check(i + j + '_travel', gap, 0)
            energy -= robot['move_rate'] * dt + robot['idle_rate'] * gap
            check(i + j + '_arrival_energy', energy, robot['minimum'])
            if j != 'end':
                counts[j] += 1
                t = p['tasks'][j]
                f = plan['finishes'][j]
                check(j + '_ability', int(set(t['capabilities']).issubset(robot['capabilities'])), 1, True)
                check(j + '_owner', int(plan['owners'][j] == i), 1, True)
                check(j + '_release', s, max(p['time'], t['release']))
                if t.get('start_deadline') is not None:
                    check(j + '_start_deadline', t['start_deadline'], s)
                if t['kind'] == 'monitor':
                    check(j + '_min', f - s, t['minimum_duration'])
                else:
                    check(j + '_duration', f - s, t['duration'], True)
                    check(j + '_deadline', t['deadline'], f)
                for dep in t.get('dependencies', []):
                    check(j + '_dependency', s, plan['finishes'].get(dep, p['known_finishes'].get(dep, 0)))
                energy -= t['energy_rate'] * (f - s)
                finish = f
            else:
                finish = s
            check(i + j + '_energy', energy, robot['minimum'])
            check(i + j + '_capacity', robot['capacity'], energy)
            if j != 'end':
                check(j + '_horizon', p['horizon'], plan['finishes'][j])
            previous = j
        check(i + '_return', p['horizon'], plan['ends'][i])
        check(i + '_energy_trace', plan['energy_end'][i], energy, True)
    for (j, n) in counts.items():
        check(j + '_unique', n, 1, True)
    for event in p['events'].values():
        (m, a, b) = (event[k] for k in ('monitor', 'pickup', 'deliver'))
        check('monitor_before_pickup', plan['starts'][a], plan['starts'][m])
        check('monitor_until_delivery', plan['finishes'][m], plan['finishes'][b])
        check('cargo', int(plan['owners'][a] == plan['owners'][b]), 1, True)
        check('distinct_roles', int(plan['owners'][m] != plan['owners'][a]), 1, True)
    jobs = list(p['tasks'])
    for (n, u) in enumerate(jobs):
        for v in jobs[n + 1:]:
            if set(p['tasks'][u]['resources']) & set(p['tasks'][v]['resources']):
                check('resource_' + u + v, max(plan['starts'][v] - plan['finishes'][u], plan['starts'][u] - plan['finishes'][v]), p['buffer'])
    for lock in p['fixed_resources']:
        for (j, t) in p['tasks'].items():
            if lock['resource'] in t['resources']:
                check('active_resource_' + j, plan['starts'][j], lock['finish'] + p['buffer'])
    for (i, old) in p['reference']['routes'].items():
        fixed = [j for j in old if j in p['tasks'] and j not in scope['free']]
        actual = [j for j in plan['routes'][i] if j in fixed]
        check('external_sequence', int(actual == fixed), 1, True)
        for j in fixed:
            check(j + '_frozen_owner', int(plan['owners'][j] == i), 1, True)
            if scope['freeze_time']:
                check(j + '_frozen_time', plan['starts'][j], p['reference']['starts'][j], True)
    parts = objective(p, plan)
    if claimed is not None:
        check('objective', sum(parts.values()), claimed, True)
    return {'passed': not errors, 'checks': checks, 'max_residual': maximum, 'errors': errors, 'objective_parts': parts}
