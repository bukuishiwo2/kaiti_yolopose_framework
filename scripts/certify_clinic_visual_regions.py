#!/usr/bin/env python3
"""Issue narrow VERIFY certificates from actually passed docking/ACK evidence."""
import argparse
import hashlib
import json
from pathlib import Path


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--qualification',type=Path,required=True);ap.add_argument('--out',type=Path,required=True)
    ap.add_argument('--allow-partial-verify',action='store_true',help='retain overall qualification failure, certify only individually proven VERIFY roles')
    a=ap.parse_args();s=json.loads((a.qualification/'summary.json').read_text())
    if not a.allow_partial_verify and not (s.get('passed') is True and s.get('arrival_audit',{}).get('passed') is True):
        raise RuntimeError('actual docking, original arrival guards and service ACK must pass')
    a.out.mkdir(parents=True,exist_ok=False)
    cfg_path=Path('/home/yhc/clinic_planning_ws/config/hospital_bed/scenario.json')
    static=json.loads((a.qualification/'static_preflight.json').read_text())
    if hashlib.sha256(cfg_path.read_bytes()).hexdigest()!=static['source_hashes'][str(cfg_path)]:
        raise RuntimeError('configuration changed after physical qualification')
    import sys
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
    from kaiti_task_sim.event_protocol import canonical
    cfg=json.loads(cfg_path.read_text());issued=[]
    for region,anchor in [('A','V1'),('B','DL')]:
        record=next(r for r in s['records'] if r['anchor']==anchor and r['status']=='SUCCEEDED')
        arrival=record['arrival']
        valid=(arrival['position_error']<=.20 and arrival['yaw_error']<=.30 and
            record['stable_at']-record['stable_since']>=.7-1e-6 and
            all(0<=arrival[k]<=.5 for k in ['tf_age','scan_age','odom_age']) and
            record['service_started']>=record['stable_at'] and
            record['service_finished']>=record['service_started'])
        if not valid:raise RuntimeError('role-level arrival/service audit failed')
        anchors={anchor}
        if anchor in cfg['resource_phases']:
            if not record.get('lease_released_at') or not record.get('clear_at'):
                raise RuntimeError('VERIFY shared resource phase not completed')
            anchors.update([cfg['resource_phases'][anchor]['entry'],cfg['resource_phases'][anchor]['clear']])
        c=dict(passed=True,region=region,config_sha256=hashlib.sha256(canonical(cfg).encode()).hexdigest(),
            validated_anchors=sorted(anchors),qualified_roles=['verify'],
            concurrent_resource_qualification=False,
            overall_qualification_passed=s.get('passed',False),
            evidence=str(a.qualification/'summary.json'),
            evidence_sha256=hashlib.sha256((a.qualification/'summary.json').read_bytes()).hexdigest(),
            actual_record=record,scope='VERIFY only; no concurrent monitor/courier authorization')
        (a.out/(region+'.json')).write_text(json.dumps(c,indent=2))
        issued.append(region)
    (a.out/'scope.json').write_text(json.dumps(dict(issued=issued,overall_qualification_passed=s.get('passed',False),concurrent_resource_qualification=False),indent=2))
    print('PASS narrow VERIFY certificates A/B; overall qualification status retained')


if __name__=='__main__':main()
