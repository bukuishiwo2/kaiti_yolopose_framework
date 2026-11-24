"""Run the event-indexed model with explicit capability-test status and audit.

This is an independent offline entry. PASS means a complete returned schedule
passed the original physical constraint checker and the event-indexed checks.
It does not mean actual navigation, event closure, optimality or a timing
advantage. The legacy comparison below is limited to a pending single-event
fixture; it does not claim that the old model accepted active monitoring.
"""
import argparse
from copy import deepcopy
import importlib.util
import json
import os
from pathlib import Path
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
import event_model as indexed


def read(path):
    return json.loads(path.read_text())


def write(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write(chr(10))


def annotate_plan(p, plan):
    q = deepcopy(plan)
    q.update(
        state_version=p['state_version'], input_sha256=indexed.digest(p),
        retained_active_bindings=deepcopy(p.get('active_bindings', {})),
        retained_issued_bindings=deepcopy(p.get('issued_bindings', {})),
        retained_resource_leases=deepcopy(p.get('resource_leases', [])),
        execution_authorized=False, actual_event_closures_generated=False)
    return q


def solve(p, output, budget=25., builder=None, legacy_validator=None):
    output.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    gate = indexed.preflight(p)
    result = dict(
        status='BLOCKED' if not gate['passed'] else 'UNKNOWN',
        input_sha256=indexed.digest(p), preflight=gate,
        budget_seconds=budget, solver_seed=17, solver_threads=1,
        execution_authorized=False, actual_execution_validation='NOT_RUN')
    if not gate['passed']:
        write(output/'result.json', result)
        return result
    if hasattr(os, 'sched_getaffinity'):
        os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})
    template, model, variables = (builder or indexed.build_model)(p)
    result['model_size'] = dict(
        variables=len(model.variables()), constraints=len(model.constraints))
    b = indexed.native.b
    log = (output/'cbc.log').resolve()
    solver = b.pulp.PULP_CBC_CMD(
        msg=False, threads=1, timeLimit=budget, gapRel=0., gapAbs=0.,
        keepFiles=True, options=['randomSeed 17', 'randomCbcSeed 17'],
        logPath=str(log))
    previous = Path.cwd()
    try:
        os.chdir(output.resolve())
        model.solve(solver)
    finally:
        os.chdir(previous)
    raw = log.read_text() if log.exists() else ''
    result['raw_status'] = dict(
        model_status=int(model.status), solution_status=int(model.sol_status))
    values = {key:variable.value() for key, variable in variables.items()}
    if all(value is not None for value in values.values()):
        try:
            plan = annotate_plan(p, b.reconstruct(indexed.native_view(p), values))
            objective = float(b.pulp.value(model.objective))
            audit = indexed.validate(p, plan, objective)
            result['independent_validation'] = audit
            if legacy_validator is not None:
                old_audit = legacy_validator(p, plan, objective)
                result['legacy_validation'] = old_audit
                accepted = audit['passed'] and old_audit['passed']
            else:
                accepted = audit['passed']
            if accepted:
                optimal = ('Result - Optimal solution found' in raw
                           and model.sol_status == b.pulp.LpSolutionOptimal)
                result.update(
                    status='PASS', proof_status='OPTIMAL' if optimal else 'FEASIBLE_WITHIN_BUDGET',
                    plan=plan, objective=objective,
                    objective_parts=indexed.objective_parts(p, plan))
        except (KeyError, RuntimeError, ValueError, StopIteration) as error:
            result['reconstruction_or_audit_error'] = repr(error)
    if result['status'] != 'PASS':
        if model.status == b.pulp.LpStatusInfeasible and 'infeasible' in raw.lower():
            result['status'] = 'INFEASIBLE'
            result['proof_status'] = 'CBC_REPORTED_INFEASIBLE'
        else:
            result['status'] = 'UNKNOWN'
            result['proof_status'] = 'NO_INDEPENDENTLY_VALIDATED_COMPLETE_INCUMBENT'
    result['elapsed_wall_seconds'] = time.perf_counter()-started
    result['input_unchanged'] = indexed.digest(p) == result['input_sha256']
    if not result['input_unchanged']:
        raise RuntimeError('Solver path mutated the frozen input.')
    write(output/'result.json', result)
    return result


def pending_single_input(source):
    """Attach event indexing to an unchanged, labelled historical model fixture."""
    p = read(source)
    for task in p['tasks'].values():
        if task['kind'] in {'verify', 'monitor', 'pickup', 'deliver'}:
            task['event_id'] = 'E1'
    p['event_index'] = dict(E1=dict(
        event_id='E1', phase='CONFIRMED',
        tasks=dict(verify='E1_verify', monitor='E1_monitor',
                   pickup='E1_pickup', deliver='E1_deliver'),
        candidate_at=p['clocks']['candidate_at'],
        confirmed_at=p['clocks']['confirmed_at'],
        verification_source=dict(
            kind='INHERITED_OFFLINE_COUNTERFACTUAL_FIXTURE',
            source_problem=str(source),
            qualification='No new actual fall verdict or execution evidence is claimed.'),
        position_valid=True, position_source='video_source_registered',
        handover_required=True))
    p['state_version'] = 1
    p['active_bindings'] = {}
    p['issued_bindings'] = {}
    p['resource_leases'] = []
    p['third_role_policies'] = [
        dict(event_id='E1', normal_task=p['necessary_normal'])
    ] if p.get('necessary_normal') else []
    p['test_scope'] = dict(
        kind='PENDING_SINGLE_EVENT_MODEL_SMOKE',
        original_source=str(source),
        original_source_sha256=__import__('hashlib').sha256(source.read_bytes()).hexdigest(),
        actual_active_monitor_case=False, actual_new_event_observation=False)
    return p


def single_smoke(source, output, budget):
    output.mkdir(parents=True, exist_ok=False)
    p = pending_single_input(source)
    write(output/'problem.json', p)
    sources = [
        HERE/'event_model.py', Path(__file__),
        ROOT/'experiments/clinic_coupling_necessity/coupling_adapter.py',
        ROOT/'src/kaiti_task_sim/clinic_assignment.py'
    ] + [indexed.WORKSPACE/'tools'/name for name in (
        'aligned_solver.py', 'aligned_contract.py',
        'clinic_milp_backend.py', 'clinic_plan_check.py')]
    write(output/'protocol.json', dict(
        frozen_before_solves=True, input_sha256=indexed.digest(p),
        source_manifest={
            str(path):__import__('hashlib').sha256(path.read_bytes()).hexdigest()
            for path in sources},
        budget_seconds=budget, comparison='Pending single-event equivalence probe only.',
        qualification='Not an active-monitor capability result, algorithm ranking or physical execution result.'))
    spec = importlib.util.spec_from_file_location(
        'unchanged_coupling_baseline_isolated',
        ROOT/'experiments/clinic_coupling_necessity/coupling_adapter.py')
    old = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(old)
    legacy_builder = lambda problem:old.model(problem, 'B3')
    legacy_check = lambda problem, plan, value:old.validate(problem, plan, 'B3', value)
    current = solve(p, output/'indexed', budget, legacy_validator=legacy_check)
    previous = solve(p, output/'legacy', budget,
                     builder=legacy_builder, legacy_validator=legacy_check)
    both = current['status'] == previous['status'] == 'PASS'
    optimal = both and current['proof_status'] == previous['proof_status'] == 'OPTIMAL'
    same_value = both and not abs(current['objective']-previous['objective']) > 1e-4
    conclusion = (
        'PASS_OPTIMAL_VALUE_AND_CROSS_VALIDATED_WITNESSES_FOR_THIS_FIXTURE'
        if optimal and same_value else
        'UNKNOWN_OPTIMALITY_OR_DIFFERENT_INCUMBENTS')
    comparison = dict(
        status=conclusion, indexed_status=current['status'],
        legacy_status=previous['status'],
        both_returned_plans_pass_both_checkers=both,
        both_proved_optimal=optimal, equal_objective=same_value,
        objective_delta=None if not both else current['objective']-previous['objective'],
        general_semantic_equivalence_proved=False,
        active_monitor_equivalence_proved=False,
        new_multievent_execution_proved=False)
    write(output/'comparison.json', comparison)
    print(json.dumps(comparison, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['solve', 'single-smoke'])
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--budget', type=float, default=25.)
    args = parser.parse_args()
    if args.mode == 'single-smoke':
        single_smoke(args.source, args.output, args.budget)
    else:
        result = solve(read(args.source), args.output, args.budget)
        print(json.dumps(dict(status=result['status'],
                              objective=result.get('objective')), ensure_ascii=False))
