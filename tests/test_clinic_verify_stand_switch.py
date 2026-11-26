"""Check that occupancy selection revises the existing verification task."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'experiments/clinic_priority'))
from verify_stand_switch import TASK, observation, select
from kaiti_task_sim.clinic_visual import compile_tasks, execution_fence, execution_tokens
from kaiti_task_sim.event_protocol import EventTaskProtocol


def test_selection_revises_target_and_keeps_task_pending_when_no_site_qualifies():
    original = dict(id='V1',pose=[14.5,-13.7,1.27],passed=True,occupied=False)
    south = dict(id='south',pose=[14.5,-14.3,1.27],passed=True,occupied=False)
    assert select([original,south]) is original
    blocked_original = dict(original,occupied=True)
    chosen = select([blocked_original,south])
    assert chosen is south
    protocol = EventTaskProtocol()
    observation(protocol,0.,[15.4,-10.8],original,'initial')
    previous_token = execution_tokens(protocol,[TASK])
    observation(protocol,1.,[15.45,-13.1],chosen,'switch')
    task = protocol.tasks[TASK]
    assert task['revision']==2 and task['target']['xy']==south['pose'][:2]
    assert not execution_fence(protocol,previous_token)['passed']
    config = dict(anchors={'V1':original['pose'],'south':south['pose']},event={'center':[15.4,-10.8]},
                  resource_phases={})
    def phases(item, config):
        return dict(item,location=config['anchors'][item['anchor']][:2])
    compiled = compile_tasks(protocol.planning_view(),1.,config,'A',phases,verify_anchor='south')
    assert compiled['E1_verify']['protocol_revision']==2
    assert compiled['E1_verify']['location']==south['pose'][:2]
    chosen = select([blocked_original,dict(south,passed=False)])
    assert chosen is None
    observation(protocol,2.,[15.45,-13.95],chosen,'blocked')
    assert list(protocol.tasks)==[TASK]
    assert protocol.tasks[TASK]['state']=='PENDING'
    assert protocol.tasks[TASK]['blockers']==['service_point_missing']
    assert protocol.planning_view()['tasks']==[]
