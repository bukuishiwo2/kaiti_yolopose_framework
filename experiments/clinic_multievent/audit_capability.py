"""Re-read frozen model cases, preserve failure statuses and audit mutations."""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import event_model as indexed
from solve_model import read, write
from prepare_active import sha


def audit(source, output):
    output.mkdir(parents=True, exist_ok=False)
    protocol = read(source/'protocol.json')
    errors, checks, rows, mutations = [], 0, [], []
    def check(label, condition):
        nonlocal checks
        checks += 1
        if not condition:
            errors.append(label)
    for path, expected in protocol['source_manifest'].items():
        check('source:'+path, sha(Path(path)) == expected)
    for name, metadata in protocol['cases'].items():
        p = read(source/name/'problem.json')
        q = read(source/name/'solve/result.json')
        check(name+':input', indexed.digest(p) == metadata['input_sha256'] == q['input_sha256'])
        check(name+':expected_status', q['status'] == metadata['expected_status'])
        check(name+':not_execution', q['execution_authorized'] is False
              and q['actual_execution_validation'] == 'NOT_RUN')
        row = dict(case_id=name, status=q['status'],
                   proof_status=q.get('proof_status'), audit=None,
                   execution_authorized=False)
        if q['status'] == 'PASS':
            plan = q['plan']
            result = indexed.validate(p, plan, q['objective'])
            check(name+':complete_independent_check', result['passed'])
            row['audit'] = result
            row['event_intervals'] = {
                event_id:dict(
                    phase=event['phase'],
                    monitor_owner=plan['owners'].get(event['tasks'].get('monitor')),
                    monitor_actual_start=p.get('active_bindings', {}).get(event['tasks'].get('monitor'), {}).get('actual_started_at'),
                    monitor_residual_start=plan['starts'].get(event['tasks'].get('monitor')),
                    monitor_forecast_finish=plan['finishes'].get(event['tasks'].get('monitor')),
                    pickup_forecast_start=plan['starts'].get(event['tasks'].get('pickup')),
                    delivery_forecast_finish=plan['finishes'].get(event['tasks'].get('deliver')),
                    lifecycle_mutated_by_plan=False)
                for event_id, event in p['event_index'].items()}
            if 'E2_pickup' in p['tasks'] and 'E1_pickup' in p['tasks']:
                bad = deepcopy(plan)
                bad['starts']['E2_pickup'] = bad['starts']['E1_pickup']
                bad['finishes']['E2_pickup'] = (
                    bad['starts']['E2_pickup']+p['tasks']['E2_pickup']['duration'])
                rejected = indexed.validate(p, bad)
                check(name+':G1_overlap_rejected', not rejected['passed'])
                mutations.append(dict(
                    case_id=name, mutation='CROSS_EVENT_G1_OVERLAP',
                    rejected=not rejected['passed'], errors=rejected['errors']))
            wrong = deepcopy(p)
            first = next(iter(wrong['event_index']))
            wrong['event_index'][first]['event_id'] = 'OTHER_EVENT'
            gate = indexed.preflight(wrong)
            check(name+':identity_swap_blocked', gate['status'] == 'BLOCKED')
            mutations.append(dict(
                case_id=name, mutation='EVENT_IDENTITY_SWAP',
                status=gate['status'], errors=gate['errors']))
        else:
            check(name+':no_fabricated_plan', 'plan' not in q)
        rows.append(row)
    summary = dict(
        status='PASS' if not errors else 'FAIL', checks=checks, errors=errors,
        cases=len(rows), counts={status:sum(row['status'] == status for row in rows)
                                for status in ('PASS', 'INFEASIBLE', 'UNKNOWN', 'BLOCKED')},
        validation_checks=sum((row['audit'] or {}).get('checks', 0) for row in rows),
        physical_trials=0, baselines_B0_B1_B2_B3='BLOCKED_NOT_ALL_MULTIEVENT_ADAPTED',
        scope='Complete returned schedules checked; expected infeasible/unsupported boundaries retained. No algorithm speed comparison or actual E2 execution.')
    write(output/'summary.json', summary)
    write(output/'case_audits.json', rows)
    write(output/'negative_mutation_audits.json', mutations)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('source', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    sys.exit(0 if audit(args.source, args.output)['status'] == 'PASS' else 1)
