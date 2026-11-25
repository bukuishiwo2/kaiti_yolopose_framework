"""Offline paired Clinic experiments using saved execution and perception evidence."""
import argparse
import csv
from copy import deepcopy
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'experiments/clinic_assignment_insert')]
import benchmark_clinic_assignment as benchmark
import adapter as insert
from kaiti_task_sim import clinic_assignment as allocation
from kaiti_task_sim.clinic_visual import VisualEventBridge

WORKSPACE = allocation.WORKSPACE
VERIFY = WORKSPACE / 'verification'
INSERT = VERIFY / 'assignment_insert_2026-11-18_h1/formal_01'
VISUAL = VERIFY / 'visual_positive_2026-11-18_c1/positive_02/video/causal.jsonl'
RUNS = ('dense_loop_a13', 'unified_bed_local_r1')
METHODS = ('B1', 'retime', 'fixed_owner', 'local_owner', 'impact_closure', 'full')
BUDGET = 5.
WRITE = benchmark.write
READ = benchmark.read


def owner_locks(problem, method):
    reference = problem['accepted_reference']
    if method in ('retime', 'fixed_owner'):
        return problem['static_owners']
    if method == 'local_owner':
        return {job: r for job, r in reference['owners'].items()
                if job not in problem['local_owner_free']}
    if method == 'impact_closure':
        return {job: reference['owners'][job] for job in problem['impact']['preserved']}
    return {}


def scope_check(problem, plan, method):
    checks = {
        'owner_scope': all(plan['owners'][j] == r
                           for j, r in owner_locks(problem, method).items()),
    }
    reference = problem['accepted_reference']
    if method == 'retime':
        checks['routine_order'] = all(
            [j for j in plan['routes'][r] if j in reference['owners']] == jobs
            for r, jobs in reference['routes'].items())
    if method == 'impact_closure':
        checks['unaffected_times'] = all(abs(plan['starts'][j] - reference['starts'][j]) < 1e-5
                                         for j in problem['impact']['preserved'])
    return checks


class Comparison:
    digest = staticmethod(allocation.digest)
    native = staticmethod(allocation.native)
    warm_values = staticmethod(allocation.warm_values)

    @staticmethod
    def model(problem, method):
        template, model, variables = insert.model(problem, 'F11')
        backend = allocation.native()[0].b
        for job, robot in owner_locks(problem, method).items():
            model += variables[backend.xk(robot, job)] == 1, 'comparison_owner_' + job
        reference = problem['accepted_reference']
        if method == 'retime':
            ranks = model.variablesDict()
            for robot, jobs in reference['routes'].items():
                for a, b in zip(jobs, jobs[1:]):
                    model += (ranks[f'rank_{robot}_{b}'] >= ranks[f'rank_{robot}_{a}'] + 1,
                              f'comparison_order_{robot}_{a}_{b}')
        if method == 'impact_closure':
            for job in problem['impact']['preserved']:
                model += variables['s_' + job] == reference['starts'][job]
        return template, model, variables

    @staticmethod
    def greedy(problem, method, deadline):
        if not problem.get('necessary_normal'):
            return allocation.greedy(problem, 'B1', deadline)
        result = insert.greedy(problem, 'B1', deadline)
        if result.get('plan') and not all(scope_check(problem, result['plan'], method).values()):
            return dict(status='CONSTRUCTION_OUTSIDE_SCOPE')
        return result

    @staticmethod
    def validate(problem, plan, method, claimed=None):
        result = insert.validate(problem, plan, 'F11', claimed)
        for name, passed in scope_check(problem, plan, method).items():
            result['checks'] += 1
            if not passed:
                result['errors'].append(dict(name=name, residual=1.))
        result['passed'] = not result['errors']
        return result

    @staticmethod
    def metrics(problem, plan):
        metrics = insert.metrics(problem, plan)
        late = {j: max(0., plan['finishes'][j] - due)
                for j, due in problem['evaluation_due'].items()}
        metrics.update(routine_tardiness_sum=sum(late.values()),
                       routine_tardy_jobs=sum(v > 1e-5 for v in late.values()),
                       routine_tardiness_by_job=late)
        return metrics


def planning_cases():
    _, contract = allocation.native()
    for run in RUNS:
        # Every variant shares the accepted plan and issued prefix of its own episode.
        for variant in ('observed', 'g1_reservation', 'routine_qualification'):
            source_variant = variant if variant != 'routine_qualification' else 'observed'
            source = INSERT / 'cases' / f'{run}__02_response__{source_variant}' / 'problem.json'
            problem = READ(source)
            name = f'{run}__{variant}'
            problem.update(case_id=name, fixture_sha256=benchmark.sha(source))
            problem['evaluation_due'] = {j: finish + 90.
                                         for j, finish in problem['accepted_reference']['finishes'].items()}
            if variant == 'routine_qualification':
                job = 'C0_r1_W3'
                incumbent = problem['accepted_reference']['owners'][job]
                problem['allowed_robots'][job].remove(incumbent)
                problem['scenario_parameters']['qualification_withdrawal'] = dict(job=job, robot=incumbent)
            impact = contract.impact_scope(problem)
            domains = allocation.domains(problem, 'B3')
            # Spatial/role eligibility is a seed too, even when capabilities are unchanged.
            for job, robot in problem['accepted_reference']['owners'].items():
                if robot not in domains[job]:
                    impact['seeds'].setdefault(job, []).append('owner_outside_legal_domain')
            queue = list(impact['seeds'])
            affected = set(queue)
            for job in queue:
                for successor in impact['edges'].get(job, []):
                    if successor not in affected:
                        affected.add(successor)
                        queue.append(successor)
            impact.update(free=sorted(affected), preserved=sorted(problem['tasks'].keys() - affected))
            problem['local_owner_free'] = sorted(
                j for j, reasons in impact['seeds'].items()
                if 'new_task' in reasons or 'owner_outside_legal_domain' in reasons)
            problem['impact'] = impact
            yield name, problem


def solve(problem, method, out):
    benchmark.ca = Comparison
    result = benchmark.solve_worker(problem, method, out.resolve(), BUDGET, 17)
    if result.get('plan'):
        audit = Comparison.validate(problem, result['plan'], method, result['objective'])
        if not audit['passed']:
            raise RuntimeError(audit)
    return result


def pose_rows(path):
    with path.open() as stream:
        for line in stream:
            row = json.loads(line)
            if row['kind'] == 'image_model_event_tasks':
                yield row


def verify_feedback(bridge, phase, at, verdict=None):
    task = bridge.protocol.tasks['E1:verify']
    msg = dict(schema='event-task/v1', kind='feedback', message_id='fixture-' + phase,
               event_id='E1', task_id=task['task_id'], task_revision=task['revision'],
               attempt=task['attempt'], robot_id='r1', phase=phase, at=at)
    review = None if verdict is None else dict(result=verdict, source='operator_review',
                                               event_id='E1', evidence_id='OFFLINE_FIXTURE')
    bridge.feedback(msg, review)


def semantic_cases(config, seed):
    import dense_tasks
    source = INSERT / 'cases' / f'{RUNS[0]}__01_verify__observed/problem.json'
    original = READ(source)
    original.pop('necessary_normal', None)
    old_verify = original['tasks'].pop('E1_verify')
    t = original['time']
    rows = {}
    for name, verdict in (('pending', None), ('excluded', 'no_fall'), ('confirmed', 'fall')):
        b = VisualEventBridge(config, source_id=seed['source_id'])
        b.observe(dict(seed, source_at=t - 2.), t - 2.)
        if verdict is not None:
            verify_feedback(b, 'started', t - 1.)
            verify_feedback(b, 'succeeded', t, verdict)
        else:
            b.tick(t)
        view = b.protocol.planning_view()
        p = deepcopy(original)
        p['fixture_sha256'] = benchmark.sha(source)
        clocks = dict(candidate_at=t-2., confirmed_at=t if verdict == 'fall' else None,
                      actual_verify_started_at=None,
                      task_planning_release={task['task_id']: task['generated_at'] for task in view['tasks']})
        compiled = allocation.compile_frozen(view, t, config, 'A', dense_tasks.phases, clocks)
        p['tasks'].update(compiled)
        p['allowed_robots'].pop('E1_verify', None)
        p['static_owners'].pop('E1_verify', None)
        p['allowed_robots'].update({j: list(p['robots']) for j in compiled})
        # Same recorded projection even after the synthetic ACK. This isolates
        # branch semantics, and cannot be used as actual post-service telemetry.
        if verdict is not None:
            p['known_finishes']['E1_verify'] = t
            p['fixture_completed_verify_at'] = t
        if verdict == 'fall':
            p['events'] = dict(E1=dict(monitor='E1_monitor', pickup='E1_pickup',
                                      deliver='E1_deliver', observed_at=t-2.))
            p['cargo_pairs'] = [['E1_pickup', 'E1_deliver']]
        p['clocks'] = clocks
        p['evaluation_due'] = {}
        assert old_verify['anchor'] == 'V1'
        rows[name] = dict(problem=p, compiled=compiled, view=view, snapshot=b.protocol.snapshot())
    assert set(rows['pending']['compiled']) == {'E1_verify'}
    assert not rows['excluded']['compiled']
    assert set(rows['confirmed']['compiled']) == {'E1_monitor','E1_pickup','E1_deliver'}
    assert rows['excluded']['snapshot']['event']['lifecycle'] == 'CLOSED'
    return rows


def replay_quality(config, samples):
    # Only the replay adapter applies this working threshold. Production source
    # registration expiry and any live execution rules are unchanged.
    seed = next(row for row in samples if row['sample']['stable'] and row['sample']['window_ready']
                and row['model']['seq_feature_valid'] and row['model']['seq_visible_keypoint_count'] >= 6)
    start = seed['sample']['source_at']
    later = next(row for row in samples if row['sample']['source_at'] > start + 11
                 and row['sample']['stable'] and row['sample']['window_ready']
                 and row['model']['seq_feature_valid'] and row['model']['seq_visible_keypoint_count'] >= 6)
    cases = {}
    for name, drops, degraded in (('control', (), None), ('short_missing', (2.,), 0),
                                  ('sustained_low_quality', (2., 5., 8., 11.), 3)):
        bridge = VisualEventBridge(config, source_id=seed['sample']['source_id'], ttl=10.)
        trace = []

        def step(label, row, at, visible):
            sample = dict(row['sample'], sample_id=label, source_at=at)
            accepted = visible >= 6 and row['model']['seq_feature_valid'] and sample['window_ready']
            sent = sample if accepted else dict(sample, window_ready=False)
            result = bridge.observe(sent, at)
            event = bridge.protocol.event
            trace.append(dict(step=label, at=at, source_sample=row['sample']['sample_id'],
                              source_log_at=row['sample']['source_at'], visible_keypoints=visible,
                              original_stable=sample['stable'], score=sample['score'],
                              window_ready_for_event=sent['window_ready'], decision=result['decision'],
                              evidence_status='SUFFICIENT' if accepted else 'INSUFFICIENT',
                              reobserve_required=not event['position_valid'],
                              snapshot=result['snapshot'], view=bridge.protocol.planning_view()))

        step('candidate', seed, start, seed['model']['seq_visible_keypoint_count'])
        for offset in drops:
            step(f'degraded_{offset:g}', seed, start + offset, degraded)
        if name == 'control':
            for offset in (5., 10.):
                row = next(r for r in samples if r['sample']['source_at'] > start + offset
                           and r['sample']['stable'] and r['sample']['window_ready']
                           and r['model']['seq_feature_valid'] and r['model']['seq_visible_keypoint_count'] >= 6)
                step(f'fresh_{offset:g}', row, start + offset, row['model']['seq_visible_keypoint_count'])
        if name == 'short_missing':
            row = next(r for r in samples if r['sample']['source_at'] > start + 3.
                       and r['sample']['stable'] and r['sample']['window_ready']
                       and r['model']['seq_feature_valid'] and r['model']['seq_visible_keypoint_count'] >= 6)
            step('short_recovery', row, start + 3., row['model']['seq_visible_keypoint_count'])
        step('recovered', later, later['sample']['source_at'], later['model']['seq_visible_keypoint_count'])
        for step_record in trace:
            assert set(step_record['snapshot']['tasks']) == {'E1:verify'}
            assert step_record['snapshot']['event']['event_id'] == 'E1'
        assert trace[-1]['view']['tasks'][0]['state'] == 'READY'
        assert trace[1]['reobserve_required'] is False
        if name == 'sustained_low_quality':
            stale = trace[-2]
            assert stale['reobserve_required'] and not stale['view']['tasks']
            assert stale['snapshot']['tasks']['E1:verify']['target'] is None
            assert stale['snapshot']['event']['position_source_at'] == start
        cases[name] = trace
    return cases


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    solver, _ = allocation.native()
    import bed_contract
    config = bed_contract.config()
    samples = list(pose_rows(VISUAL))
    seed = next(row['sample'] for row in samples if row['sample']['stable'] and row['sample']['window_ready'])
    cases = dict(planning_cases())
    semantic = semantic_cases(config, seed)
    quality = replay_quality(config, samples)
    frozen = dict(methods=METHODS, budget=BUDGET, seed=17, input_log_sha256=benchmark.sha(VISUAL),
                  implementation_sha256={str(path): benchmark.sha(path) for path in (
                      Path(__file__), Path(benchmark.__file__), Path(insert.__file__),
                      Path(allocation.__file__), Path(solver.__file__),
                      *(Path(solver.__file__).with_name(name) for name in
                        ('aligned_contract.py', 'clinic_milp_backend.py', 'clinic_plan_check.py',
                         'dense_tasks.py', 'bed_contract.py')),
                      WORKSPACE/'config/hospital_bed/scenario.json',
                      ROOT/'src/kaiti_task_sim/clinic_visual.py',
                      ROOT/'src/kaiti_task_sim/event_protocol.py')},
                  problems={k: allocation.digest(v) for k,v in cases.items()},
                  semantic={k: allocation.digest(v['problem']) for k,v in semantic.items()},
                  execution_authorized=False)
    WRITE(out/'protocol.json', frozen)
    WRITE(out/'quality.json', quality)
    comparison = []
    for index, (name, problem) in enumerate(cases.items()):
        WRITE(out/name/'problem.json', problem)
        order = METHODS[index % len(METHODS):] + METHODS[:index % len(METHODS)]
        for method in order:
            result = solve(problem, method, out/name/method)
            metrics = result.get('metrics', {})
            row = dict(case=name, method=method, status=result['status'],
                       local_owner_free=len(problem['local_owner_free']),
                       closure_free=len(problem['impact']['free']), suffix=len(problem['tasks']),
                       monitor=metrics.get('monitor_response'), delivery=metrics.get('delivery_from_confirmed'),
                       tardiness=metrics.get('routine_tardiness_sum'),
                       owner_changes=metrics.get('accepted_owner_changes'),
                       first_feasible=result['first_feasible_seconds'], seconds=result['total_seconds'])
            comparison.append(row)
            print(row, flush=True)
    with (out/'planning.csv').open('w') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(comparison[0]))
        writer.writeheader()
        writer.writerows(comparison)
    for name, case in semantic.items():
        WRITE(out/'semantic'/name/'input.json', case)
        result = solve(case['problem'], 'full', out/'semantic'/name/'full')
        if not result.get('plan'):
            raise RuntimeError(f'Semantic branch {name} has no validated plan: {result["status"]}')
        planned = {j for j in result['plan']['owners'] if j.startswith('E1_')}
        assert planned == set(case['compiled'])
    print('Wrote', out, flush=True)


if __name__ == '__main__':
    main()
