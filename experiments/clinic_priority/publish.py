"""Audit saved factorial results and publish a compact read-only view."""
import argparse
from pathlib import Path

from factorial import Comparison, METHODS, MARGINS, WORKSPACE, allocation, benchmark, READ, WRITE

ROLES = {'monitor': '现场监护', 'pickup': '领取物资', 'deliver': '送达物资'}
PLACES = {'DL': '常态服务点', 'G1': '物资站', 'PW2': '巡检点二', 'PW1': '巡检点一',
          'M1': '监护站位', 'H1': '物资交付点'}


def publish(out, workspace):
    protocol = READ(out/'protocol.json')
    certificate_path = (workspace/'verification/visual_positive_2026-11-18_c1'
                        /'a_qualification_audit/A.json')
    certificate = READ(certificate_path)
    audit_path = Path(certificate['evidence'])
    certificate_valid = (certificate['passed'] and certificate['concurrent_resource_qualification']
                         and READ(audit_path)['passed']
                         and benchmark.sha(audit_path) == certificate['evidence_sha256'])
    snapshots = {}
    for name, digest in protocol['case_hashes'].items():
        run, cell = name.split('__')
        p = READ(out/name/'problem.json')
        assert allocation.digest(p) == digest and benchmark.sha(Path(p['fixture'])) == p['fixture_sha256']
        ref = p['reference']
        targets = {j: dict(label=ROLES.get(t['kind'], PLACES.get(t['anchor'], '常态任务')),
                           anchor=t['anchor'], xy=t['location'], kind=t['kind'],
                           resources=t['resources'], referenceOwner=ref['owners'].get(j))
                   for j,t in p['tasks'].items()}
        result = {}
        for method in METHODS:
            q = READ(out/name/method/'result.json')
            assert q['input_sha256'] == digest
            data = dict(status=q['status'], first=q['first_feasible_seconds'], seconds=q['total_seconds'])
            if 'plan' in q:
                plan = q['plan']
                check = Comparison.validate(p, plan, method, q['objective'])
                assert check['passed'] and q['first_feasible_seconds'] <= protocol['budget_seconds'], check
                metrics = Comparison.metrics(p, plan)
                gaps = []
                for j,r in plan['owners'].items():
                    if j in ref['owners'] and r != ref['owners'][j]:
                        gaps.append(f'{j} → {r.upper()} 缺改派后的路径、资源与服务资格')
                    if j not in ref['owners'] and r not in certificate['qualified_robots'].get(p['tasks'][j]['kind'], []):
                        gaps.append(f'{ROLES[p["tasks"][j]["kind"]]} → {r.upper()} 缺现有角色证书')
                bars = [dict(id=j, robot=r, start=plan['starts'][j]-p['time'],
                             finish=plan['finishes'][j]-p['time'])
                        for r,route in plan['routes'].items() for j in route]
                data.update(metrics=metrics, bars=bars, qualificationGaps=gaps,
                            checks=check['checks'], owners=plan['owners'])
            result[method] = data
        snapshots.setdefault(run,{})[cell] = dict(factors=p['factors'], results=result, targets=targets,
                                                  targeted=p['targeted_jobs'], closure=p['closure_jobs'],
                                                  issued=[dict(robot=r, job=j) for r,v in p['prefixes'].items()
                                                          for j in v['jobs']])
    execution = READ(out/'execution.json') if (out/'execution.json').is_file() else {}
    quality = READ(out/'observations.json') if (out/'observations.json').is_file() else []
    WRITE(out/'viewer.json', dict(schema='clinic-factorial/v1', snapshots=snapshots, methods=METHODS,
                                  margins=MARGINS, g1Seconds=protocol['g1_hold_seconds'],
                                  budget=protocol['budget_seconds'], certificateValid=certificate_valid,
                                  execution=execution, observations=quality))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('out', type=Path)
    args = parser.parse_args()
    publish(args.out.resolve(), WORKSPACE)
