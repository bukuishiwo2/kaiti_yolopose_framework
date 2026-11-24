"""Finite visual mode gates; these fixtures are not image recognition evidence."""
from copy import deepcopy
import json
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
from kaiti_task_sim.clinic_visual import VisualEventBridge, compile_tasks, registered_space, sensor_position_contract
from kaiti_task_sim.event_protocol import ProtocolError
import bed_contract
import dense_tasks


@pytest.fixture
def cfg():
    return bed_contract.config()


def sample(i='s1', t=1., stable=True):
    return dict(sample_id=i, source_id='video', source_at=t, score=.9,
                stable=stable, window_ready=True)


def fb(task, phase, t, revision=1, robot='r3', attempt=1):
    return dict(schema='event-task/v1', kind='feedback', message_id=f'{task}:{phase}:{t}',
        event_id='E1', task_id='E1:'+task, task_revision=revision, attempt=attempt,
        robot_id=robot, phase=phase, at=t)


def verdict(result):
    return dict(result=result, event_id='E1', source='operator_review', evidence_id='reviewed-frame')


def test_no_input_and_negative_no_task(cfg):
    b=VisualEventBridge(cfg, source_id='video')
    b.tick(1.)
    assert not b.protocol.tasks
    b.observe(sample(t=2., stable=False), 2.)
    assert not b.protocol.tasks


def test_positive_verify_only_and_duplicate_occlusion(cfg):
    b=VisualEventBridge(cfg, source_id='video')
    b.observe(sample(), 1.)
    rev=b.protocol.world_revision
    assert set(b.protocol.tasks)=={'E1:verify'}
    assert b.observe(sample(), 1.1)['decision']=='DUPLICATE_MODEL_SAMPLE'
    b.observe(sample('s2', 2., False), 2.)
    assert set(b.protocol.tasks)=={'E1:verify'}
    assert b.protocol.tasks['E1:verify']['state']=='READY'


def test_invalid_and_stale_fail_closed(cfg):
    b=VisualEventBridge(cfg, source_id='video')
    b.observe(sample(), 1., space_valid=False)
    assert not b.protocol.planning_view()['tasks']
    b2=VisualEventBridge(cfg, source_id='video')
    assert b2.observe(sample(), 3.)['decision']=='STALE_OR_FUTURE_MODEL_EVIDENCE'
    assert not b2.protocol.tasks


@pytest.mark.parametrize('result', ['fall','no_fall'])
def test_explicit_verdict_and_false_alarm_lifecycle(cfg,result):
    b=VisualEventBridge(cfg, source_id='video')
    b.observe(sample(),1.)
    b.feedback(fb('verify','started',1.1))
    with pytest.raises(ProtocolError):
        b.feedback(fb('verify','succeeded',1.2))
    b.feedback(fb('verify','succeeded',1.2),verdict(result))
    if result=='no_fall':
        assert b.protocol.event['lifecycle']=='CLOSED'
        assert not b.protocol.planning_view()['tasks']
    else:
        assert {t['role'] for t in b.protocol.planning_view()['tasks']}=={'monitor','pickup','deliver'}


def test_cancel_requires_ack_and_protects_execution(cfg):
    b=VisualEventBridge(cfg, source_id='video')
    b.observe(sample(),1.)
    b.feedback(fb('verify','started',1.1))
    b.tick(12.)
    task=b.protocol.tasks['E1:verify']
    assert task['state']=='CANCEL_REQUESTED' and task['owner']=='r3'
    assert b.protocol.planning_view()['active_commitments'][0]['owner']=='r3'
    with pytest.raises(ProtocolError):
        b.feedback(fb('verify','succeeded',12.1),verdict('fall'))
    b.feedback(fb('verify','cancelled',12.1))
    assert task['owner']=='r3'  # old detached snapshot does not mutate
    assert b.protocol.tasks['E1:verify']['owner'] is None
    assert b.protocol.tasks['E1:verify']['attempt']==2


def test_dual_region_spatial_compile_and_resource(cfg):
    tasks={}
    for region in ['A','B']:
        b=VisualEventBridge(cfg,region,source_id='video')
        b.observe(sample(),1.)
        tasks[region]=compile_tasks(b.protocol.planning_view(),1.,cfg,region,dense_tasks.phases)
    a,b=tasks['A']['E1_verify'],tasks['B']['E1_verify']
    assert a['anchor']=='V1' and b['anchor']=='DL'
    assert a['location']!=b['location']
    assert b['resources']==['DL'] and b['entry_anchor']!=a['entry_anchor']
    assert not a['execution_authorized'] and not b['execution_authorized']
    assert cfg['tables']['event']['G1'][a['entry_anchor']]!=cfg['tables']['event']['G1'][b['entry_anchor']]


def test_move_revision_keeps_execution_target_until_ack(cfg):
    b=VisualEventBridge(cfg,source_id='video')
    b.observe(sample(),1.)
    b.feedback(fb('verify','started',1.1))
    old=deepcopy(b.protocol.tasks['E1:verify']['execution_target'])
    b.region='B'
    b.observe(sample('s2',2.),2.)
    task=b.protocol.tasks['E1:verify']
    assert task['state']=='CANCEL_REQUESTED'
    assert task['execution_target']==old and task['target']!=old
    assert task['revision']>task['execution_revision']


def test_arbitrary_target_no_v1_fallback(cfg):
    b=VisualEventBridge(cfg,source_id='video');b.observe(sample(),1.)
    view=b.protocol.planning_view();view['tasks'][0]['target']['xy'][0]+=1
    with pytest.raises(ValueError):
        compile_tasks(view,1.,cfg,'A',dense_tasks.phases)


def test_no_identity_fusion_and_position_sources(cfg):
    b=VisualEventBridge(cfg,source_id='video');s=sample();s['source_id']='other-camera'
    with pytest.raises(ValueError):b.observe(s,1.)
    assert registered_space(cfg,'A')['provenance']=='video_source_registered'
    assert sensor_position_contract()['provenance']=='sensor_estimated'
    assert not sensor_position_contract()['valid']


def test_only_qualified_verify_may_execute_without_concurrent_certificate(cfg):
    import hashlib
    from kaiti_task_sim.event_protocol import canonical
    b=VisualEventBridge(cfg,source_id='video');b.observe(sample(),1.)
    cert=dict(passed=True,region='A',config_sha256=hashlib.sha256(canonical(cfg).encode()).hexdigest(),
        qualified_roles=['verify'],validated_anchors=['V1'],concurrent_resource_qualification=False)
    t=compile_tasks(b.protocol.planning_view(),1.,cfg,'A',dense_tasks.phases,cert)
    assert t['E1_verify']['execution_authorized']
    b.feedback(fb('verify','started',1.1));b.feedback(fb('verify','succeeded',1.2),verdict('fall'))
    t=compile_tasks(b.protocol.planning_view(),1.2,cfg,'A',dense_tasks.phases,cert)
    assert not any(v['execution_authorized'] for v in t.values())
    cert['config_sha256']='different-config'
    b2=VisualEventBridge(cfg,source_id='video');b2.observe(sample(),1.)
    assert not compile_tasks(b2.protocol.planning_view(),1.,cfg,'A',dense_tasks.phases,cert)['E1_verify']['execution_authorized']


def test_visual_keepout_candidate_and_explicit_closure(cfg):
    from kaiti_task_sim.clinic_visual import visual_obstacle
    b=VisualEventBridge(cfg,source_id='video');b.observe(sample(),1.)
    assert visual_obstacle(b.protocol.snapshot(),[0.,0.])[0] is False
    b.feedback(fb('verify','started',1.1));b.feedback(fb('verify','succeeded',1.2),verdict('fall'))
    active,xy=visual_obstacle(b.protocol.snapshot(),[0.,0.]);assert active and xy==cfg['event']['center']
    snap=b.protocol.snapshot();snap['event']['lifecycle']='CLOSED'
    assert visual_obstacle(snap,xy)[0] is False
    snap['event']['lifecycle']='OPEN';snap['event']['space']['valid']=False
    assert visual_obstacle(snap,xy)==(True,xy)
