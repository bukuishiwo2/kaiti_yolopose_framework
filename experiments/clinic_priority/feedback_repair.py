"""Replay a captured pre-dispatch path rejection using the existing Clinic MILP."""
import argparse
from pathlib import Path

from factorial import Comparison, G1_HOLD, allocation, benchmark, READ, WRITE

BUDGET = 5.
SEED = 17


def route_arcs(plan):
    return [(robot, previous, job)
            for robot, route in plan['routes'].items()
            for previous, job in zip(['src', *route], [*route, 'end'])]


def path_checks(problem, plan, cross_job, robot='r2'):
    """Return the exact model arc alongside each existing cross-assignment query."""
    cross = problem['tasks'][cross_job]
    for rid, previous, job in route_arcs(plan):
        if rid != robot or job == 'end':
            continue
        source = (problem['robots'][rid]['source_anchor'] if previous == 'src'
                  else problem['tasks'][previous]['clear_anchor'])
        target = problem['tasks'][job]['entry_anchor']
        if source != target and (job == cross_job or source == cross['clear_anchor']):
            yield (rid, previous, job), (rid, source, target)


def revised_problem(problem, arc, witness):
    if witness['passed'] or witness['status'] != 6 or witness['length'] != 0:
        raise ValueError('Expected an aborted path query with no path')
    revised = dict(problem, rejected_transition=dict(arc=list(arc), witness=witness))
    rid, previous, job = arc
    source = (problem['robots'][rid]['source_anchor'] if previous == 'src'
              else problem['tasks'][previous]['clear_anchor'])
    if [rid, source, problem['tasks'][job]['entry_anchor']] != witness['edge']:
        raise ValueError('Rejection does not match the transition in this snapshot')
    return revised


class FeedbackComparison(Comparison):
    @staticmethod
    def model(problem, method):
        template, model, variables = Comparison.model(problem, method)
        if rejection := problem.get('rejected_transition'):
            backend = allocation.native()[0].b
            key = backend.ak(*rejection['arc'])
            model += variables[key] == 0, 'rejected_transition_' + key
        return template, model, variables

    @staticmethod
    def validate(problem, plan, method, claimed=None):
        result = Comparison.validate(problem, plan, method, claimed)
        if rejection := problem.get('rejected_transition'):
            result['checks'] += 1
            if tuple(rejection['arc']) in route_arcs(plan):
                result['errors'].append(dict(name='rejected_transition', residual=1.))
        result['passed'] = not result['errors']
        return result

    @staticmethod
    def greedy(problem, method, deadline):
        result = Comparison.greedy(problem, method, deadline)
        if result.get('plan') and not FeedbackComparison.validate(problem, result['plan'], method)['passed']:
            return dict(status='CONSTRUCTION_REUSES_REJECTED_TRANSITION')
        return result


def check_prefix(problem, plan, states, completed):
    """Check actual task identity and readiness immediately before a commit."""
    if set(completed).difference(problem['known_finishes']):
        raise ValueError('New completion outside the protected checkpoint')
    for job, end in problem['actual_known_finishes'].items():
        if job not in completed or completed[job]['end'] != end:
            raise ValueError(f'Completed fact changed: {job}')
    for robot, prefix in problem['prefixes'].items():
        state, source = states[robot], problem['robots'][robot]
        if state['cargo'] != problem['snapshot_states'][robot]['cargo']:
            raise ValueError(f'Cargo commitment changed: {robot}')
        old_job = prefix['actual_job']
        if old_job is None:
            if state['job'] is not None or state['anchor'] != source['source_anchor']:
                raise ValueError(f'Idle robot source changed: {robot}')
            continue
        record = (state['record'] if state['job'] == old_job else
                  completed.get(old_job) if state['job'] is None else None)
        if (old_job in plan['owners'] or any(old_job in route for route in plan['routes'].values())
                or not record or record['task_id'] != prefix['record_task_id']
                or record['robot'] != robot or record['job_id'] != old_job):
            raise ValueError(f'Issued prefix identity changed: {robot}/{old_job}')
        issued = problem['snapshot_states'][robot]['record']
        if any(record[k] != issued[k] for k in ('plan_revision', 'begin', 'anchor')):
            raise ValueError(f'Issued prefix dispatch facts changed: {robot}/{old_job}')
        if state['job'] is None and (record['end'] > source['ready']
                                    or state['anchor'] != source['source_anchor']):
            raise ValueError(f'Issued prefix cleared outside its projection: {robot}/{old_job}')


def summarize(problem, result):
    metrics = result.get('metrics', {})
    plan = result.get('plan') or {}
    timeline = []
    for job, robot in plan.get('owners', {}).items():
        task = problem['tasks'][job]
        timeline.append(dict(job=job, robot=robot, label=job, anchor=task['anchor'],
                             xy=task['location'], start=plan['starts'][job], finish=plan['finishes'][job]))
    return dict(status=result['status'], first=result['first_feasible_seconds'],
                wall=result['total_seconds'], objective=result.get('objective'),
                delivery=metrics.get('delivery_from_confirmed'), delay=metrics.get('positive_delay'),
                tardiness=metrics.get('tardiness'), offsets=metrics.get('completion_offset'),
                owners=plan.get('owners'), routes=plan.get('routes'),
                changes=metrics.get('accepted_owner_changes'), predicted=timeline)


def replay(run, out):
    source = run/'response/problem.json'
    initial_solve = run/'response/solve/result.json'
    recorded_result = run/'result.json'
    problem, initial, recorded = READ(source), READ(initial_solve), READ(recorded_result)
    if (recorded['commit'] is not None or len(recorded['path_witness']) != 1
            or initial['input_sha256'] != allocation.digest(problem)):
        raise ValueError('Expected a captured rejection before any response commit')
    witness, plan = recorded['path_witness'][0], initial['plan']
    arc, = (arc for arc, edge in path_checks(problem, plan, 'C0_r1_W3')
            if list(edge) == witness['edge'])
    changed = revised_problem(problem, arc, witness)
    # The original plan is valid in the base model and fails exactly the new row.
    old_validation = FeedbackComparison.validate(changed, plan, 'full', initial['objective'])
    if [e['name'] for e in old_validation['errors']] != ['rejected_transition']:
        raise ValueError(f'Unexpected change to original model validation: {old_validation}')
    reservation = recorded['reservation']
    if not any(q.get('request') == reservation and any(
            all(b[k] == reservation[k] for k in ('resource', 'start', 'finish', 'change_id'))
            for b in q['blocked']) for q in recorded['resource_events'] if q['phase'] == 'availability_changed'):
        raise ValueError('Missing resource-manager reservation acknowledgement')
    g1, = [q for q in problem['blocked_resources'] if q['resource'] == 'G1']
    if (abs(g1['finish'] - g1['start'] - G1_HOLD) > 1e-6 or any(
            abs(g1[k] - (reservation[k] - recorded['epoch'])) > 1e-6 for k in ('start', 'finish'))):
        raise ValueError('Reservation in model differs from acknowledged window')
    snapshot = problem['snapshot_states']
    completed = {j: recorded['completed'][j] for j in problem['actual_known_finishes']}
    check_prefix(problem, plan, snapshot, completed)
    WRITE(out/'problem.json', changed)
    WRITE(out/'rejected_plan_validation.json', old_validation)
    benchmark.ca = FeedbackComparison
    result = benchmark.solve_worker(changed, 'full', (out/'solve').resolve(), BUDGET, SEED)
    if result.get('plan'):
        check_prefix(changed, result['plan'], snapshot, completed)
    fixed = benchmark.solve_worker(changed, 'fixed', (out/'fixed').resolve(), BUDGET, SEED)
    if fixed.get('plan'):
        check_prefix(changed, fixed['plan'], snapshot, completed)
    outcome = ('MODEL_CANDIDATE' if result.get('plan') else
               'MODEL_INFEASIBLE' if result['status'] == 'INFEASIBLE' else 'BUDGET_UNKNOWN')
    return dict(run=run.name, witness=witness, arc=arc, outcome=outcome, execution_authorized=False,
                rejected=summarize(problem, initial), repaired=summarize(changed, result),
                fixed=summarize(changed, fixed),
                confirmed=problem['clocks']['confirmed_at'], reservation=[g1['start'], g1['finish']],
                prefixes=problem['prefixes'], preserved=dict(
                    snapshot=all(changed[k] == v for k, v in problem.items()), reservation_ack=True,
                    initial_rejected_by_new_constraint=True),
                source_sha256={str(f): benchmark.sha(f) for f in (source, initial_solve, recorded_result)})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--runs', type=Path, nargs='+', required=True)
    args = parser.parse_args()
    out = args.out.resolve()
    if len({run.name for run in args.runs}) != len(args.runs):
        parser.error('Run directory names must be unique')
    out.mkdir(parents=True, exist_ok=False)
    cases = [replay(run.resolve(), out/run.name) for run in args.runs]
    WRITE(out/'viewer.json', dict(budget=BUDGET, seed=SEED, cases=cases,
                                 code_sha256=benchmark.sha(Path(__file__))))
    for case in cases:
        print(case['run'], case['outcome'], case['repaired']['status'], case['repaired']['wall'])


if __name__ == '__main__':
    main()
