"""Predefined event × G1-reservation comparisons on saved Clinic prefixes."""
import argparse
from copy import deepcopy
from itertools import product
from pathlib import Path
import time

from run import RUNS, INSERT, ROOT, WORKSPACE, allocation, benchmark, insert, READ, WRITE

METHODS = ('fixed', 'targeted', 'full', 'closure')
MARGINS = (0, 60, 90, 120)
BUDGET = 5.
G1_HOLD = 240.


def cases():
    _, contract = allocation.native()
    for run in RUNS:
        source = INSERT / 'cases' / f'{run}__02_response__observed/problem.json'
        original = READ(source)
        for name, event, disturbance, withdrawal in (
            *((f'e{int(e)}_g{int(g)}', e, g, False) for e, g in product((False, True), repeat=2)),
            ('qualification', False, False, True),
        ):
            p = deepcopy(original)
            if not event:
                p['tasks'] = {j: t for j, t in p['tasks'].items() if t['kind'] == 'normal'}
                p['events'] = {}
                p['cargo_pairs'] = []
                p['clocks'].update(confirmed_at=None, actual_verify_started_at=None,
                                   task_planning_release={})
                p.pop('necessary_normal', None)
                # E1_verify is prior history/part of the recorded projection.
                # Hold it constant in every cell; the factor is response insertion.
            p['allowed_robots'] = {j: p['allowed_robots'][j] for j in p['tasks']}
            if withdrawal:
                p['allowed_robots']['C0_r1_W3'].remove(p['reference']['owners']['C0_r1_W3'])
            if disturbance:
                p['blocked_resources'].append(dict(resource='G1', start=p['time'],
                                                   finish=p['time'] + G1_HOLD))
            domain = allocation.domains(p, 'B3')
            illegal = sorted(j for j, r in p['reference']['owners'].items() if r not in domain[j])
            assert bool(illegal) == withdrawal
            # Directly coupled routine work only: event and reservation both
            # touch G1, or an incumbent has lost its eligibility.
            p['targeted_jobs'] = sorted(set(illegal) | {
                j for j, task in p['tasks'].items()
                if (event or disturbance) and task['kind'] == 'normal' and 'G1' in task['resources']
            })
            impact = contract.impact_scope(p)
            p['closure_jobs'] = sorted(set(impact['free']) | set(illegal))
            p['factors'] = dict(event=event, disturbance=disturbance, withdrawal=withdrawal)
            p['case_id'] = f'{run}__{name}'
            p['fixture_sha256'] = benchmark.sha(source)
            p['fixture'] = str(source)
            yield p


def locks(p, method):
    owners = p['reference']['owners']
    free = {'fixed': (), 'targeted': p['targeted_jobs'], 'full': owners,
            'closure': p['closure_jobs']}[method]
    return {j: r for j, r in owners.items() if j not in free}


class Comparison:
    digest = staticmethod(allocation.digest)
    native = staticmethod(allocation.native)
    warm_values = staticmethod(allocation.warm_values)

    @staticmethod
    def model(p, method):
        template, model, variables = insert.model(p, 'F11')
        backend = allocation.native()[0].b
        for job, robot in locks(p, method).items():
            model += variables[backend.xk(robot, job)] == 1, f'factorial_owner_{job}'
            if method == 'closure':
                model += variables['s_' + job] == p['reference']['starts'][job], f'factorial_time_{job}'
        return template, model, variables

    @staticmethod
    def validate(p, plan, method, claimed=None):
        result = insert.validate(p, plan, 'F11', claimed)
        for job, robot in locks(p, method).items():
            result['checks'] += 1
            if plan['owners'][job] != robot:
                result['errors'].append(dict(name=f'factorial_owner_{job}', residual=1.))
            if method == 'closure':
                result['checks'] += 1
                if abs(plan['starts'][job] - p['reference']['starts'][job]) > 1e-5:
                    result['errors'].append(dict(name=f'factorial_time_{job}', residual=1.))
        result['passed'] = not result['errors']
        return result

    @staticmethod
    def greedy(p, method, deadline):
        # The same deterministic accepted-route construction for every arm.
        # Closure may reject that incumbent due to its additional time locks.
        if p['events']:
            result = insert.greedy(p, 'B1', deadline)
        else:
            plan, reason = allocation.schedule_routes(p, p['reference']['routes'])
            result = (dict(status='FEASIBLE_CONSTRUCTIVE', plan=plan,
                           objective=sum(allocation.parts(p, plan).values())) if plan else
                      dict(status='CONSTRUCTION_FAILED', reason=reason))
        if result.get('plan') and not Comparison.validate(p, result['plan'], method)['passed']:
            return dict(status='COMMON_CONSTRUCTION_OUTSIDE_SCOPE')
        return result

    @staticmethod
    def metrics(p, plan):
        metrics = allocation.metrics(p, plan)
        offsets = {j: plan['finishes'][j] - finish for j, finish in p['reference']['finishes'].items()}
        metrics.update(completion_offset=offsets, positive_delay=sum(max(0., x) for x in offsets.values()),
                       net_offset=sum(offsets.values()), tardiness={str(m): sum(max(0., x-m) for x in offsets.values())
                                                                    for m in MARGINS})
        return metrics


def run(out):
    out.mkdir(parents=True, exist_ok=False)
    problems = list(cases())
    native = Path(allocation.native()[0].__file__).parent
    files = [Path(__file__), Path(benchmark.__file__), Path(insert.__file__), Path(allocation.__file__),
             *(native / name for name in ('aligned_solver.py', 'aligned_contract.py',
                                          'clinic_milp_backend.py', 'clinic_plan_check.py'))]
    manifest = dict(budget_seconds=BUDGET, seed=17, margins=MARGINS, g1_hold_seconds=G1_HOLD,
                    methods=METHODS, case_hashes={p['case_id']: allocation.digest(p) for p in problems},
                    sources={str(f): benchmark.sha(f) for f in files})
    WRITE(out/'protocol.json', manifest)
    for p in problems:
        WRITE(out/p['case_id']/'problem.json', p)
    benchmark.ca = Comparison
    for i, p in enumerate(problems):
        shift = i % len(METHODS)
        for method in METHODS[shift:] + METHODS[:shift]:
            start = time.monotonic()
            result = benchmark.solve_worker(p, method, out/p['case_id']/method, BUDGET, 17)
            print(p['case_id'], method, result['status'], round(time.monotonic()-start, 2), flush=True)
    from publish import publish
    publish(out, WORKSPACE)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True, type=Path)
    run(parser.parse_args().out.resolve())
