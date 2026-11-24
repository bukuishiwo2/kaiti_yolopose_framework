"""Read-back audit: original full constraints, independent J and SLA evaluation."""
import argparse
from collections import Counter, defaultdict
import csv
import importlib.util
import json
from pathlib import Path
import statistics
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import coupling_adapter as ca
spec = importlib.util.spec_from_file_location('coupling_cost_audit', HERE.parents[1]/'scripts/audit_clinic_assignment.py')
independent = importlib.util.module_from_spec(spec)
spec.loader.exec_module(independent)
read, sha, write = independent.read, independent.sha, independent.write


def csvwrite(path, rows):
    fields = list(dict.fromkeys(k for r in rows for k in r))
    with path.open('w') as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows({k:json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v for k, v in r.items()} for r in rows)


def audit(source, out):
    out.mkdir(parents=True, exist_ok=False)
    protocol = read(source/'protocol.json')
    errors, checks, rows, saved, before_after = [], 0, [], {}, {}
    def check(name, ok):
        nonlocal checks
        checks += 1
        if not ok:
            errors.append(name)
    for f, h in protocol['source_manifest'].items():
        check('frozen_source:'+f, sha(Path(f)) == h)
    for name, expected in protocol['cases'].items():
        folder = source/'cases'/name
        p = read(folder/'problem.json')
        parent = read(Path(p['parent_problem']))
        check(name+':input', ca.digest(p) == expected)
        check(name+':parent', sha(Path(p['parent_problem'])) == p['parent_problem_sha256'])
        for key in ('prefixes', 'snapshot_states', 'accepted_reference', 'immutable_projection'):
            check(name+':preserve_'+key, p[key] == parent[key])
        for r in p['robots']:
            check(name+':source_'+r, p['robots'][r]['source_anchor'] == parent['robots'][r]['source_anchor'])
            check(name+':ready_'+r, p['robots'][r]['ready'] >= parent['robots'][r]['ready'])
        for j in ('ND_pickup', 'ND_deliver'):
            if j in p['tasks']:
                check(name+':not_accepted_'+j, j not in p['accepted_reference']['owners'])
        if len(p['methods']) > 1:
            check(name+':same_common_model', len({ca.common_signature(p, m) for m in p['methods']}) == 1)
        for method in p['methods']:
            q = read(folder/method/'result.json')
            check(name+method+':same_input', q['input_sha256'] == expected)
            check(name+method+':budget', q['budget_seconds'] == 5. and q['total_seconds'] <= 5.15)
            check(name+method+':no_dispatch', q['physical_execution_authorized'] is False)
            row = dict(case_id=name, family=p['scenario']['family'], source_run=p['scenario']['historical_run'],
                       level=p['scenario']['level'], due_mode=p['due_mode'], method=method,
                       feasible=bool(q.get('plan')), status=q['status'], total_seconds=q['total_seconds'],
                       first_feasible_seconds=q.get('first_feasible_seconds'), objective=None,
                       monitor_response=None, verify_response=None, delivery_from_confirmed=None,
                       normal_wait=None, total_routine_tardiness=None, routine_late_count=None,
                       minimum_due_slack=None, accepted_owner_changes=None, accepted_time_shift=None,
                       verify_service_lower_bound_gap=None, actual_nav2_completion=None,
                       hard_violations=None, execution_authorized=False)
            if q.get('plan'):
                plan = q['plan']
                native = independent.contract.validate(p, plan, dict(free=list(p['tasks']), freeze_time=False))
                policy = ca.validate(p, plan, method, q['objective'])
                check(name+method+':original_full_constraints', native['passed'])
                check(name+method+':policy', policy['passed'])
                objective = sum(independent.independent_cost(p, plan).values())
                check(name+method+':independent_J', abs(objective-q['objective']) < 1e-4)
                tardy = sum(max(0., plan['finishes'][j]-due) for j, due in p['routine_due_at'].items())
                check(name+method+':independent_tardiness', abs(tardy-q['metrics']['total_routine_tardiness']) < 1e-5)
                check(name+method+':all_tasks', set(plan['owners']) == set(p['tasks']))
                for j, r in p['accepted_reference']['owners'].items():
                    check(name+method+':accepted_reference_'+j, parent['accepted_reference']['owners'][j] == r)
                for pair in p['cargo_pairs']:
                    pick, drop = pair
                    owner = plan['owners'][pick]
                    check(name+method+':cargo_'+pick, owner == plan['owners'][drop] and plan['routes'][owner].index(drop) == plan['routes'][owner].index(pick)+1)
                row.update({k:q['metrics'][k] for k in row if k in q['metrics']})
                row.update(objective=objective, hard_violations=len(native['errors'])+len(policy['errors']),
                           owners=plan['owners'], routes=plan['routes'], objective_parts=independent.independent_cost(p, plan))
                before_after[name+'|'+method] = dict(accepted=p['accepted_reference'], nominal=p['nominal_owners'],
                                                   immutable_prefix=p['prefixes'], after=plan)
            else:
                row['failure_reasons'] = q.get('construction', {}).get('reasons', {})
                check(name+method+':no_fake_metrics', 'metrics' not in q)
            rows.append(row)
            saved[name, method] = row
    pairs, contexts = [], []
    for name in protocol['cases']:
        p = read(source/'cases'/name/'problem.json')
        if p['scenario']['family'] == 'S5_BACKGROUND':
            target = p['scenario']['paired_event_case']
            back = saved[name, 'B0']
            for method in ca.METHODS:
                event = saved[target, method]
                contexts.append(dict(case_id=target, method=method, due_mode=p['due_mode'],
                                     background_status=back['status'], background_feasible=back['feasible'],
                                     event_status=event['status'], event_feasible=event['feasible'],
                                     background_tardiness=back['total_routine_tardiness'], event_tardiness=event['total_routine_tardiness'],
                                     attribution='BACKGROUND_ALREADY_FAILS_NO_INSERTION_CAUSE_CLAIM' if not back['feasible'] else 'PAIRED_BACKGROUND_FEASIBLE'))
            continue
        joint = saved[name, 'B3']
        for baseline in ('B0', 'B1', 'B2'):
            b = saved[name, baseline]
            pair = dict(case_id=name, family=joint['family'], due_mode=joint['due_mode'], baseline=baseline,
                        base_feasible=b['feasible'], joint_feasible=joint['feasible'],
                        base_status=b['status'], joint_status=joint['status'], both_feasible=b['feasible'] and joint['feasible'])
            if pair['both_feasible']:
                for key in ('objective', 'monitor_response', 'verify_response', 'delivery_from_confirmed', 'normal_wait',
                            'total_routine_tardiness', 'routine_late_count', 'accepted_owner_changes', 'accepted_time_shift', 'total_seconds'):
                    if joint.get(key) is not None and b.get(key) is not None:
                        pair['delta_'+key] = joint[key]-b[key]
                pair['changed_owners'] = [j for j, r in b['owners'].items() if joint['owners'][j] != r]
            pairs.append(pair)
    grouped = defaultdict(list)
    for row in rows:
        grouped[row['family'], row['due_mode'], row['method']].append(row)
    aggregates = []
    for (family, mode, method), values in grouped.items():
        x = dict(family=family, due_mode=mode, method=method, inputs=len(values), feasible=sum(v['feasible'] for v in values),
                 statuses=dict(Counter(v['status'] for v in values)), median_total_seconds=statistics.median(v['total_seconds'] for v in values))
        aggregates.append(x)
    pair_summary = []
    for family, mode, baseline in sorted({(p['family'], p['due_mode'], p['baseline']) for p in pairs}):
        subset = [p for p in pairs if (p['family'], p['due_mode'], p['baseline']) == (family, mode, baseline)]
        costs = [p['delta_objective'] for p in subset if p['both_feasible']]
        pair_summary.append(dict(family=family, due_mode=mode, baseline=baseline, conditions=len(subset),
                                 both_feasible=len(costs), joint_J_wins=sum(v < -1e-4 for v in costs),
                                 joint_J_ties=sum(abs(v) <= 1e-4 for v in costs), joint_J_losses=sum(v > 1e-4 for v in costs),
                                 joint_only_found=sum(p['joint_feasible'] and not p['base_feasible'] for p in subset),
                                 baseline_only_found=sum(p['base_feasible'] and not p['joint_feasible'] for p in subset)))
    gates = {s:read(source/'capability_gates'/s/'result.json')['specification']['status'] for s in ('S2', 'S4')}
    summary = dict(passed=not errors, checks=checks, errors=errors, inputs=len(protocol['cases']), calls=len(rows),
                   feasible=sum(r['feasible'] for r in rows), returned_plan_hard_violations=sum(r['hard_violations'] or 0 for r in rows),
                   blocked=gates, aggregates=aggregates, paired_summary=pair_summary,
                   physical_trials=0, innovation='NOT_ESTABLISHED',
                   interpretation='Fixed-input offline diagnostic; J improvements, emergency service, routine lateness and feasibility are separate. Unknown-budget is not proof of infeasibility.')
    write(out/'summary.json', summary)
    write(out/'per_instance.json', rows)
    write(out/'before_after.json', before_after)
    write(out/'paired.json', pairs)
    write(out/'background_attribution.json', contexts)
    csvwrite(out/'per_instance.csv', rows)
    csvwrite(out/'paired.csv', pairs)
    csvwrite(out/'background_attribution.csv', contexts)
    csvwrite(out/'aggregates.csv', aggregates)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('source', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    sys.exit(0 if audit(args.source, args.output)['passed'] else 1)
