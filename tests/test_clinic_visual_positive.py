"""Positive extension safety; no mocked ACK is claimed as physical evidence."""
from copy import deepcopy
import os
from pathlib import Path
import sys
import pytest
REPO = Path(__file__).resolve().parents[1]
TOOLS = Path(os.environ.get('CLINIC_TOOLS', '/home/yhc/clinic_planning_ws/tools'))
if not TOOLS.is_dir():
    TOOLS = REPO/'experiments/clinic/tools'
if not TOOLS.is_dir():
    pytest.skip('Clinic tools are neither installed nor present in the source snapshot', allow_module_level=True)
sys.path.insert(0, str(TOOLS))
import bed_contract
from kaiti_task_sim.clinic_visual import (VisualEventBridge,execution_fence,
    execution_tokens,transfer_guard,compile_tasks)
import dense_tasks


def bridge():
    b=VisualEventBridge(bed_contract.config(),source_id='v')
    b.observe(dict(sample_id='s1',source_id='v',source_at=1.,score=.9,stable=True,window_ready=True),1.)
    return b


def feedback(b,role,phase,t,result=None,robot='r1'):
    task=b.protocol.tasks['E1:'+role]
    m=dict(schema='event-task/v1',kind='feedback',message_id=f'{role}:{phase}:{t}',
        event_id='E1',task_id='E1:'+role,task_revision=task['revision'],attempt=task['attempt'],
        robot_id=robot,phase=phase,at=t)
    return b.feedback(m,dict(result=result,event_id='E1',source='controlled_visual_review',
        evidence_id='saved-image',reviewer='assistant_visual_review',human_review=False) if result else None)


def test_task_fence_rejects_stale_revision_and_expiry():
    b=bridge();tokens=execution_tokens(b.protocol,['E1:verify'])
    assert execution_fence(b.protocol,tokens)['passed']
    stale=deepcopy(tokens);stale['E1:verify']['revision']+=1
    assert not execution_fence(b.protocol,stale)['passed']
    b.tick(12.)
    assert not execution_fence(b.protocol,tokens)['passed']


def test_review_is_explicit_and_has_honest_nonhuman_source():
    b=bridge();feedback(b,'verify','started',1.1)
    feedback(b,'verify','succeeded',1.2,'fall')
    assert b.protocol.event['verified']
    assert set(b.protocol.tasks)=={'E1:verify','E1:monitor','E1:pickup','E1:deliver'}


def test_no_monitor_release_even_with_cancel_ack_before_handover():
    b=bridge();feedback(b,'verify','started',1.1);feedback(b,'verify','succeeded',1.2,'fall')
    feedback(b,'monitor','started',1.3)
    before=b.protocol.snapshot()
    q=transfer_guard(before,'monitor',cancel_ack=True,handover_ack=False)
    assert not q['allowed'] and b.protocol.snapshot()==before
    b.tick(12.)
    assert b.protocol.tasks['E1:monitor']['state']=='CANCEL_REQUESTED'
    assert not transfer_guard(b.protocol.snapshot(),'monitor',cancel_ack=True)['allowed']
    assert b.protocol.tasks['E1:monitor']['owner']=='r1'


def test_cargo_owner_protected_before_delivery():
    b=bridge();feedback(b,'verify','started',1.1);feedback(b,'verify','succeeded',1.2,'fall')
    feedback(b,'monitor','started',1.3)
    feedback(b,'pickup','started',1.4,robot='r2');feedback(b,'pickup','succeeded',1.5,robot='r2')
    assert not transfer_guard(b.protocol.snapshot(),'deliver',proposed_owner='r3',cancel_ack=True)['allowed']
    assert transfer_guard(b.protocol.snapshot(),'deliver',proposed_owner='r2')['allowed']
    tasks=compile_tasks(b.protocol.planning_view(),1.5,b.config,'A',dense_tasks.phases)
    assert tasks['E1_deliver']['cargo_role']=='drop'
    assert tasks['E1_deliver']['protocol_revision']==b.protocol.tasks['E1:deliver']['revision']


def test_a_structural_gate():
    import importlib.util
    from pathlib import Path
    spec=importlib.util.spec_from_file_location('qa',Path(__file__).resolve().parents[1]/'scripts/qualify_clinic_visual_a.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    assert module.offline_check(bed_contract.config())['passed']
    cfg=bed_contract.config();cfg['anchors']['H1']=cfg['anchors']['M1'][:]
    assert not module.offline_check(cfg)['passed']


def test_ros_numpy_uuid_can_be_saved_and_matched():
    import json
    import numpy as np
    from kaiti_task_sim.clinic_visual import action_uuid_bytes
    raw=np.arange(16,dtype=np.uint8)
    assert json.loads(json.dumps(action_uuid_bytes(raw)))==list(range(16))
    assert action_uuid_bytes(raw)==action_uuid_bytes(bytes(range(16)))
