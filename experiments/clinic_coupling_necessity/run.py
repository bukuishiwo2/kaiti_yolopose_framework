"""Prespecified coupling scenarios, existing-policy paired runs, no dispatch."""
import argparse
from copy import deepcopy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
import coupling_adapter as ca

spec = importlib.util.spec_from_file_location('previous_assignment_worker', ROOT/'scripts/benchmark_clinic_assignment.py')
worker_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker_module)
read, write, sha = worker_module.read, worker_module.write, worker_module.sha
SOURCE = Path('/home/yhc/clinic_planning_ws/verification/assignment_insert_2026-11-18_h1/formal_01')
RUNS = ('dense_loop_a13', 'unified_bed_local_r1')


def build(run, family, level, due_mode='NONE'):
    stage = '01_verify' if family == 'S1' else '02_response'
    source = SOURCE/'cases'/f'{run}__{stage}__observed'/'problem.json'
    p = read(source)
    p['parent_problem'] = str(source)
    p['parent_problem_sha256'] = sha(source)
    p['scenario'] = dict(family=family, level=level, historical_run=run,
                         sample_type='DEPENDENT_OFFLINE_COUNTERFACTUAL', independent_trial=False)
    p['due_mode'] = due_mode
    p['routine_due_at'] = {}
    p['new_normal_pairs'] = []
    parameters = {}
    if family == 'S1':
        _, contract = ca.native()
        nearest = min(p['robots'], key=lambda r:(contract.tau(p, r, 'src', 'E1_verify'), r))
        hold = (0., 60., 180.)[level]
        p['robots'][nearest]['ready'] += hold
        parameters = dict(nearest_by_projected_source=nearest, additional_uninterruptible_service_seconds=hold,
                          assumption='Counterfactual noninterruptible service occupancy at the immutable projected source; not an observed new service or actual-pose nearest claim')
    elif family == 'S3':
        for j, role, template in [('ND_pickup', 'pickup', 'E1_pickup'), ('ND_deliver', 'deliver', 'C0_r1_W3')]:
            t = deepcopy(p['tasks'][template])
            t.update(kind='normal', duration=8. if role == 'pickup' else 6., release=p['time'],
                     deadline=2200., capabilities=['move', 'carry'], energy_rate=0.,
                     dependencies=[] if role == 'pickup' else ['ND_pickup'],
                     nominal_owner='r2', service_role='ordinary_supply_'+role,
                     execution_authorized=False)
            t.pop('start_deadline', None)
            for key in ('protocol_task_id', 'protocol_revision', 'protocol_attempt'):
                t.pop(key, None)
            t.update(cargo_group='ND', cargo_role=role)
            p['tasks'][j] = t
            p['nominal_owners'][j] = p['original_nominal_owners'][j] = p['static_owners'][j] = 'r2'
            p['allowed_robots'][j] = list(p['robots'])
        p['cargo_pairs'].append(['ND_pickup', 'ND_deliver'])
        p['new_normal_pairs'] = [['ND_pickup', 'ND_deliver']]
        lock = (0., 120., 300.)[level]
        if lock:
            p['blocked_resources'].append(dict(resource='G1', start=p['time'], finish=p['time']+lock,
                                               source='HYPOTHETICAL_EXISTING_STATION_RESERVATION'))
        parameters = dict(ordinary_supply_order='NEW_NOT_PREVIOUSLY_ACCEPTED', nominal_carrier='r2',
                          pickup_point='G1', drop_point='DL', station_reservation_seconds=lock,
                          assumption='Generic non-emergency supply order at existing anchors; same-car adjacent transport and full occupancy retained; no corridor path-coordination claim')
    elif family == 'S5':
        slack = (0., 90., 240.)[level]
        p['routine_due_at'] = {j:p['accepted_reference']['finishes'][j]+slack
                               for j, t in p['tasks'].items() if t['kind'] == 'normal'}
        if due_mode == 'HARD':
            for j, due in p['routine_due_at'].items():
                p['tasks'][j]['deadline'] = min(p['tasks'][j]['deadline'], due)
        elif due_mode != 'EVALUATION_ONLY':
            raise ValueError(due_mode)
        parameters = dict(accepted_finish_plus_slack_seconds=slack, due_mode=due_mode,
                          assumption='Hypothetical service agreement, not historical due dates; evaluation-only tardiness is not a new objective penalty; HARD never allows late service')
    else:
        raise ValueError(family)
    p['scenario']['parameters'] = parameters
    p['case_id'] = f'{family}__{run}__l{level}__{due_mode}'
    p['methods'] = list(ca.METHODS)
    p['physical_execution_authorized'] = False
    return p


def context(p):
    """No-new-emergency matched background: isolates pre-existing SLA failures."""
    q = deepcopy(p)
    removed = {j for j, t in q['tasks'].items() if t['kind'] != 'normal'}
    for j in removed:
        q['tasks'].pop(j)
        q['allowed_robots'].pop(j)
        q['static_owners'].pop(j)
    q['events'] = {}
    q['cargo_pairs'] = []
    q.pop('necessary_normal', None)
    q['scenario']['family'] = 'S5_BACKGROUND'
    q['scenario']['paired_event_case'] = p['case_id']
    q['case_id'] = p['case_id']+'__NO_NEW_EMERGENCY'
    q['methods'] = ['B0']
    return q


def blocked_specs():
    active = Path('/home/yhc/clinic_planning_ws/verification/visual_bed_2026-11-18_d1/bed_before_pickup_04/repair_01/problem.json')
    loaded = Path('/home/yhc/clinic_planning_ws/verification/visual_bed_2026-11-18_d1/bed_before_pickup_01/repair_03/problem.json')
    return [dict(family='S2', status='BLOCKED_MODEL_CONTRACT', source=str(active), source_sha256=sha(active),
                 requirements=dict(first_event='E1 active monitor retains owner/resource until its own delivery/handover',
                                   second_event='distinct E2 ID, candidate/confirmation clocks, verify and response lifecycle',
                                   shared_station='G1', no_dropping=True, no_cross_event_ACK=True),
                 controlled_levels=dict(second_event_offset_seconds=[0, 60, 180]),
                 reason='Native suffix backend rejects events whose active monitor is outside tasks; current allocation objective/greedy is E1-specific. No certified two-region concurrent execution or multiple-event protocol integration.',
                 forbidden_shortcuts=['rename E1 into E2', 'erase active monitor', 'pretend predicted E1 release is guaranteed', 'delete third-role business rule'],
                 next_gate='Independent multi-event obligation/active-interval representation and validator, before any ranking'),
            dict(family='S4', status='BLOCKED_UNBOUNDED_RECOVERY', source=str(loaded), source_sha256=sha(loaded),
                 requirements=dict(cargo_owner='r2 retains E1 cargo', monitor_obligation='held until actual delivery/handover',
                                   unissued_normal_suffix='may reassign if legal', obstruction='actual observed obstruction required for physical validation'),
                 controlled_levels=dict(obstruction_end=['FINITE_60_SECONDS', 'FINITE_180_SECONDS', 'UNKNOWN']),
                 reason='Stored prefix carries forecasts, not a guaranteed release under unknown-duration obstruction. Loading metadata differs between normalized snapshot and active commitment; retain both. Cannot release monitor/cargo or substitute fixed ready to claim recovery.',
                 forbidden_shortcuts=['cargo transfer without ACK', 'fixed future release under unknown obstruction', 'fake Nav2 failure', 'call suffix-only feasibility full emergency recovery'],
                 next_gate='Validate cargo/ACK provenance and block-conditioned prefix release, then compare suffix repair; no new physical run in this round')]


def probe_blocked(specification):
    p = read(Path(specification['source']))
    summary = dict(specification=specification,
                   observed_commitments=p.get('active_commitments', {}),
                   observed_prefixes=p.get('prefixes', {}),
                   snapshot_cargo={r:s.get('cargo') for r, s in p.get('snapshot_states', {}).items()},
                   execution_authorized=False, attempted_performance_solves=0)
    if specification['family'] == 'S2':
        probe = deepcopy(p)
        probe['events']['E1'] = dict(monitor='E1_monitor', pickup='E1_pickup', deliver='E1_deliver', observed_at=p['time'])
        try:
            ca.native()[0].Model(probe)
            summary['native_active_event_probe'] = 'UNEXPECTEDLY_ACCEPTED_REQUIRES_DIAGNOSIS'
        except ValueError as exc:
            summary['native_active_event_probe'] = repr(exc)
    else:
        summary['cargo_evidence_disagreement'] = {
            r:dict(normalized_snapshot=p.get('snapshot_states', {}).get(r, {}).get('cargo'),
                   projected_commitment=c.get('cargo_at_snapshot'), record_task_id=c.get('record_task_id'))
            for r, c in p.get('active_commitments', {}).items() if c.get('cargo_at_snapshot') is not None}
    return summary


def generate(out):
    out.mkdir(parents=True, exist_ok=False)
    cases = []
    for run in RUNS:
        for family in ('S1', 'S3', 'S5'):
            for level in range(3):
                for due_mode in (('EVALUATION_ONLY', 'HARD') if family == 'S5' else ('NONE',)):
                    p = build(run, family, level, due_mode)
                    cases.append(p)
                    if family == 'S5':
                        cases.append(context(p))
    for p in cases:
        write(out/'cases'/p['case_id']/'problem.json', p)
    specs = blocked_specs()
    for s in specs:
        write(out/'capability_gates'/s['family']/'result.json', probe_blocked(s))
    sources = [HERE/n for n in ('coupling_adapter.py', 'run.py', 'audit.py', 'test_scenarios.py')]
    sources += [ROOT/'src/kaiti_task_sim/clinic_assignment.py', ROOT/'scripts/benchmark_clinic_assignment.py', ROOT/'scripts/audit_clinic_assignment.py']
    sources += [ca.base.WORKSPACE/'tools'/n for n in ('aligned_solver.py', 'aligned_contract.py', 'clinic_milp_backend.py', 'clinic_plan_check.py')]
    protocol = dict(schema='clinic-coupling-necessity/v1', date='2026-11-23', frozen_before_solves=True,
                    algorithms_changed=False, objective_weights=ca.WEIGHTS, budget_seconds=5., seed=17,
                    methods=list(ca.METHODS), supported=['S1', 'S3', 'S5'], blocked=['S2', 'S4'],
                    selection='Two fixed historical runs x three preset levels; all cases retained. No result-based instance selection.',
                    controls='S1 zero extra hold; S3 no extra station reservation; S5 generous and strict due margins; S5 paired no-emergency B0 contexts',
                    fairness='Same input, objective, hard business third-role, immutable prefix, resources and five-second algorithm wall budget. Policy owner freedom differs explicitly.',
                    qualification='All changed role/timing/new transport cases MODEL_ONLY_NOT_PHYSICALLY_QUALIFIED; no dispatch',
                    population='Dependent historical-state counterfactuals, not IID trials. Due dates and extra reservations are explicit hypotheses, not observed clinical SLAs.',
                    source_manifest={str(f):sha(f) for f in sources},
                    cases={p['case_id']:ca.digest(p) for p in cases})
    write(out/'protocol.json', protocol)
    print('Frozen', len(cases), 'inputs,', sum(len(p['methods']) for p in cases), 'calls; S2/S4 blocked')


def worker(inp, out, method):
    p = read(inp)
    worker_module.ca = ca
    q = worker_module.solve_worker(p, method, out, 5., 17)
    q['physical_execution_authorized'] = False
    write(out/'result.json', q)


def run(out):
    protocol = read(out/'protocol.json')
    for path, expected in protocol['source_manifest'].items():
        assert sha(Path(path)) == expected, ('source drift', path)
    for index, (name, expected) in enumerate(protocol['cases'].items()):
        folder = out/'cases'/name
        p = read(folder/'problem.json')
        assert ca.digest(p) == expected
        methods = p['methods']
        order = methods[index % len(methods):]+methods[:index % len(methods)]
        for method in order:
            target = folder/method
            assert not target.exists(), target
            env = dict(os.environ, OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1', MKL_NUM_THREADS='1')
            child = subprocess.run([sys.executable, str(HERE/'run.py'), 'worker', '--input', str(folder/'problem.json'),
                                    '--output', str(target), '--method', method],
                                   capture_output=True, text=True, env=env, timeout=20., start_new_session=True)
            target.mkdir(exist_ok=True)
            (target/'worker.log').write_text(child.stdout+child.stderr)
            if child.returncode:
                raise RuntimeError(child.stderr[-2500:])
        print(name, [(m, read(folder/m/'result.json')['status']) for m in methods], flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['generate', 'run', 'worker'])
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--input', type=Path)
    parser.add_argument('--method', choices=ca.METHODS)
    args = parser.parse_args()
    if args.mode == 'generate':
        generate(args.output)
    elif args.mode == 'run':
        run(args.output)
    else:
        worker(args.input, args.output, args.method)
