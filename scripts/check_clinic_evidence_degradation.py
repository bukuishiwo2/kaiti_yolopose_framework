#!/usr/bin/env python3
"""Separate, explicitly offline safety forks of one saved live monitor state.

No ROS/world control, simulated ACK, new model sample or runtime state mutation.
Revocation recovery is deliberately reported BLOCKED pending a service workflow.
"""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys

P=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(P/'src'))
from kaiti_task_sim.clinic_visual_repair import RegisteredVideoProtocol


def run(source,out):
    out.mkdir(parents=True,exist_ok=False)
    actual=json.loads(source.read_text());saved=actual['protocol']
    reg=actual['evidence']['registration'];tasks=saved['tasks']
    if tasks.get('E1:monitor',{}).get('state')!='RUNNING':raise ValueError('requires actual live monitor snapshot')
    def fork():
        p=RegisteredVideoProtocol()
        p.event=deepcopy(saved['event']);p.tasks=deepcopy(tasks);p.now=saved['time'];p.world_revision=saved['world_revision'];p.registration=deepcopy(reg)
        return p
    logs=[];checks={}
    def log(case,p):
        logs.append(dict(case=case,evidence=p.evidence_state(),protocol=p.snapshot(),view=p.planning_view(),
            scope='offline fork from saved real monitor; no worker command or fabricated ACK'))
    p=fork();now=p.now+20
    p.apply(dict(schema='event-task/v1',kind='tick',message_id='independent:eof',at=now));log('EOF_valid_registration',p)
    checks['EOF_no_new_observation']=p.event['last_seen_at']==saved['event']['last_seen_at'] and p.event['position_source_at']==saved['event']['position_source_at']
    checks['behavior_expired_space_still_registered']=not p.evidence_state()['behavior_valid'] and p.event['position_valid']
    checks['confirmed_monitor_not_released']=p.event['verified'] and p.tasks['E1:monitor']==tasks['E1:monitor']
    p=fork();revoked=deepcopy(reg);revoked.update(id=reg['id']+':independent-revoke',valid=False)
    p.set_registration(revoked,p.now+1);log('registration_revoked',p)
    monitor=p.tasks['E1:monitor'];original=tasks['E1:monitor']
    checks['revocation_requests_cancel_not_ACK']=monitor['state']=='CANCEL_REQUESTED' and monitor['owner']==original['owner'] and all(monitor[k]==original[k] for k in ['attempt','execution_revision','execution_target','started_at'])
    checks['hard_commitment_retained']=any(t['task_id']=='E1:monitor' for t in p.planning_view()['active_commitments'])
    checks['recovery_explicitly_blocked']=p.evidence_state()['recovery']=='AWAIT_REVALIDATION_OR_QUALIFIED_HANDOVER'
    restored=deepcopy(reg);restored['id']=reg['id']+':independent-restore'
    p.set_registration(restored,p.now+1);log('restored_with_cancel_still_pending',p)
    checks['restore_does_not_erase_pending_cancel']=p.tasks['E1:monitor']['state']=='CANCEL_REQUESTED' and p.tasks['E1:monitor']['owner']==original['owner']
    p=fork();p.apply(dict(schema='event-task/v1',kind='tick',message_id='independent:registration-expired',at=reg['valid_until']+1));log('registration_expired',p)
    checks['expiry_preserves_owner_pending_ACK']=not p.event['position_valid'] and p.tasks['E1:monitor']['state']=='CANCEL_REQUESTED' and p.tasks['E1:monitor']['owner']==original['owner']
    (out/'cases.jsonl').write_text(''.join(json.dumps(x)+'\n' for x in logs))
    result=dict(passed=all(checks.values()),checks=checks,source=str(source),source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        protocol_tests='PASS' if all(checks.values()) else 'FAIL',actual_active_service_revocation_recovery='BLOCKED',
        reason='Native running worker requires a qualified cancellation/handover workflow; this instance never invokes it. No ACK or release synthesized.',
        physical_EOF_with_valid_registration='see separate actual execution audit',new_model_samples=0,physical_execution=False)
    (out/'summary.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--source',type=Path,required=True);ap.add_argument('--out',type=Path,required=True)
    a=ap.parse_args();run(a.source,a.out)
