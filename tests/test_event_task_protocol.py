"""Semantic lifecycle regressions independent of ROS, solver, and transition rows."""
from copy import deepcopy
from pathlib import Path
import sys
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from kaiti_task_sim.event_protocol import EventTaskProtocol,ProtocolError,canonical
from kaiti_task_sim.event_replay_cases import cases,observation,feedback,SPACE
from kaiti_task_sim.event_replay_validation import audit,check_expected


@pytest.mark.parametrize('case',cases(),ids=lambda c:c['name'])
def test_hand_authored_replays_and_determinism(case):
    outputs=[]
    for _ in range(2):
        p=EventTaskProtocol();previous=None;trace=[]
        for entry in case['steps']:
            result=p.apply(entry['message']);view=p.planning_view()
            assert audit(result['snapshot'],view,previous)['passed']
            assert check_expected(result,view,entry['expect'],previous)['passed']
            previous=result['snapshot'];trace.append(result)
        outputs.append(canonical(trace))
    assert outputs[0]==outputs[1]


def verified():
    p=EventTaskProtocol()
    p.apply(observation('o0',0))
    p.apply(feedback('f1',1,'verify','started'))
    p.apply(feedback('f2',2,'verify','succeeded',result='fall'))
    return p


def watched():
    p=verified();p.apply(feedback('f3',3,'monitor','started'));return p


def cargo():
    p=watched();p.apply(feedback('f4',4,'pickup','started','R1'))
    p.apply(feedback('f5',5,'pickup','succeeded','R1'));return p


@pytest.mark.parametrize('factory,bad',[
    (verified,feedback('bad',3,'pickup','started','R1')),
    (watched,feedback('bad',4,'deliver','started','R1')),
    (watched,feedback('bad',4,'monitor','succeeded')),
    (watched,feedback('bad',4,'pickup','started','R0')),
    (cargo,feedback('bad',6,'deliver','started','R2',revision=2)),
    (cargo,feedback('bad',6,'deliver','started','R1',revision=1)),
    (cargo,feedback('bad',6,'deliver','started','R1',revision=2,attempt=2)),
])
def test_invalid_execution_order_identity_and_tokens_are_atomic(factory,bad):
    p=factory();before=canonical(p.snapshot())
    with pytest.raises(ProtocolError):p.apply(bad)
    assert canonical(p.snapshot())==before


def test_false_verdict_closes_without_generating_response():
    p=EventTaskProtocol();p.apply(observation('o0',0));p.apply(feedback('f1',1,'verify','started'))
    r=p.apply(feedback('f2',2,'verify','succeeded',result='no_fall'))
    assert r['snapshot']['event']['lifecycle']=='CLOSED'
    assert set(p.tasks)=={'E1:verify'} and not p.planning_view()['tasks']
    p.apply(observation('o3',3))
    assert set(p.tasks)=={'E1:verify'}  # Same episode cannot be resurrected.


def test_short_occlusion_does_not_require_replanning_but_expiry_stops_service():
    p=watched()
    r=p.apply(observation('o4',4,'occluded'))
    assert not r['planning_changed'] and p.tasks['E1:monitor']['state']=='RUNNING'
    p.apply(dict(schema='event-task/v1',kind='tick',message_id='tick',at=10.01))
    assert p.event['lifecycle']=='OPEN' and not p.event['position_valid']
    assert p.tasks['E1:monitor']['state']=='CANCEL_REQUESTED'
    assert len(p.planning_view()['active_commitments'])==1 and not p.planning_view()['tasks']


def test_position_loss_during_pickup_requires_both_cancel_acknowledgements():
    p=watched();p.apply(feedback('p4',4,'pickup','started','R1'))
    r=p.apply(observation('lost',5,space={'valid':False}))
    assert p.tasks['E1:monitor']['state']==p.tasks['E1:pickup']['state']=='CANCEL_REQUESTED'
    assert len(p.planning_view()['active_commitments'])==2
    before=canonical(p.snapshot())
    with pytest.raises(ProtocolError):p.apply(feedback('late',6,'pickup','succeeded','R1'))
    assert canonical(p.snapshot())==before
    assert audit(r['snapshot'],p.planning_view())['passed']


def test_closed_event_preserves_cargo_followup_requirement():
    p=cargo()
    p.apply(dict(schema='event-task/v1',kind='resolution',message_id='r6',event_id='E1',at=6,result='resolved'))
    assert p.event['cargo_disposition']=='REQUIRES_FOLLOWUP'
    assert p.tasks['E1:deliver']['state']=='CANCELLED'
    assert p.tasks['E1:monitor']['state']=='CANCEL_REQUESTED'
    assert p.event['lifecycle']=='CLOSED'


def test_stale_observation_cannot_retarget_and_id_collision_is_rejected():
    p=verified();old=deepcopy(p.event['space'])
    p.apply(observation('new',3))
    r=p.apply(observation('stale',4,space={'valid':False},source_at=1))
    assert r['decision']=='STALE_OBSERVATION' and p.event['space']==old and not r['planning_changed']
    before=canonical(p.snapshot())
    with pytest.raises(ProtocolError):p.apply(observation('new',5,space={'valid':False},source_at=3))
    assert canonical(p.snapshot())==before


@pytest.mark.parametrize('space',[
    dict(valid=True,frame='odom',event_xy=[2,1],service_points={}),
    dict(valid=True,frame='map',event_xy=[float('nan'),1],service_points={}),
    dict(valid=True,frame='map',event_xy=[2,1],service_points={'verify':[float('inf'),0]}),
])
def test_bad_geometry_is_rejected(space):
    p=EventTaskProtocol()
    with pytest.raises((ProtocolError,ValueError)):p.apply(observation('bad',0,space=space))
    assert p.event is None and not p.tasks


def test_missing_service_point_does_not_invent_navigation_goal():
    p=EventTaskProtocol();space=deepcopy(SPACE);space['service_points']={}
    r=p.apply(observation('o0',0,space=space))
    assert p.tasks['E1:verify']['state']=='PENDING' and p.tasks['E1:verify']['target'] is None
    assert not p.planning_view()['tasks'] and audit(r['snapshot'],p.planning_view())['passed']


def test_independent_audit_catches_premature_release_and_invented_completion():
    p=watched();p.apply(observation('lost',4,space={'valid':False}))
    s=p.snapshot();view=p.planning_view();view['active_commitments']=[]
    assert 'cancel request retains commitment' in audit(s,view)['errors']
    s['tasks']['E1:monitor']['state']='SUCCEEDED'
    assert 'monitor end after delivery' in audit(s,p.planning_view())['errors']
