"""Independent evidence-source safety cases, ACKs here explicitly fixtures."""
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
sys.path.insert(0,str(TOOLS))
import bed_contract
from kaiti_task_sim.clinic_visual import VisualEventBridge,registered_space
from kaiti_task_sim.clinic_visual_repair import RegisteredVideoProtocol,resource_fence,before_pickup_scope,monitor_clearance_task,project_before_pickup,project_initial_clearance


def setup():
    cfg=bed_contract.config();b=VisualEventBridge(cfg,source_id='v',protocol_type=RegisteredVideoProtocol)
    s=registered_space(cfg,'A')
    reg=dict(schema='video-region-registration/v1',id='A:v1',source='qualified_scenario_registration',
        config_sha256='fixture-config',region='A',valid=True,issued_at=0.,valid_until=500.,
        event_xy=s['event_xy'],service_points=s['service_points'])
    b.protocol.set_registration(reg,0.)
    b.observe(dict(sample_id='real-model-fixture',source_id='v',source_at=1.,score=.9,stable=True,window_ready=True),1.)
    def fb(role,phase,t,verdict=None):
        task=b.protocol.tasks['E1:'+role]
        return b.feedback(dict(schema='event-task/v1',kind='feedback',message_id=f'{role}:{phase}:{t}',event_id='E1',
            task_id='E1:'+role,task_revision=task['revision'],attempt=task['attempt'],robot_id='r1',phase=phase,at=t),verdict)
    fb('verify','started',1.1)
    fb('verify','succeeded',1.2,dict(result='fall',event_id='E1',source='controlled_visual_review',evidence_id='OFFLINE_FIXTURE'))
    fb('monitor','started',1.3)
    return b,reg


def test_inference_stops_behavior_expires_registration_persists_no_new_samples():
    b,reg=setup();count=len(b.evidence);source=b.protocol.event['position_source_at']
    b.tick(40.)
    e=b.protocol.evidence_state()
    assert not e['behavior_valid'] and e['position_valid'] and e['verified']
    assert b.protocol.tasks['E1:monitor']['state']=='RUNNING'
    assert b.protocol.tasks['E1:monitor']['owner']=='r1'
    assert len(b.evidence)==count and b.protocol.event['position_source_at']==source


def test_registration_revoked_does_not_release_active_commitment():
    b,reg=setup();reg.update(id='A:revoke:v2',valid=False)
    b.protocol.set_registration(reg,2.)
    task=b.protocol.tasks['E1:monitor'];assert task['state']=='CANCEL_REQUESTED' and task['owner']=='r1'
    assert b.protocol.evidence_state()['recovery']=='AWAIT_REVALIDATION_OR_QUALIFIED_HANDOVER'
    assert b.protocol.planning_view()['active_commitments'][0]['task_id']=='E1:monitor'
    reg.update(id='A:restore:v3',valid=True);b.protocol.set_registration(reg,3.)
    assert b.protocol.tasks['E1:monitor']['state']=='CANCEL_REQUESTED' # cannot erase pending cancel


def test_registration_expiry_and_geometry_mismatch_fail_closed():
    b,reg=setup();b.tick(501.)
    assert not b.protocol.event['position_valid']
    assert b.protocol.tasks['E1:monitor']['owner']=='r1'
    b,reg=setup();reg['event_xy']=[0.,0.];reg['id']='A:wrong'
    b.protocol.set_registration(reg,2.)
    assert not b.protocol.event['position_valid']


def test_resource_lease_fence():
    old=dict(owners=dict(G1=dict(lease_id='run:E1_pickup:r2',robot='r2')))
    assert resource_fence(old,deepcopy(old),['E1_pickup'])['passed']
    assert not resource_fence(old,dict(owners={}),['E1_pickup'])['passed']
    assert resource_fence(old,dict(owners={}),[])['passed']


def test_before_pickup_instance_does_not_activate_postpickup_experiment():
    assert before_pickup_scope('E1_pickup',None,None)
    assert not before_pickup_scope('E1_pickup','E1',None)
    assert not before_pickup_scope('E1_pickup',None,20.)
    assert not before_pickup_scope('E1_deliver','E1',None)
    assert not before_pickup_scope('E1_monitor',None,10.)


def test_raw_bed_region_counts_cannot_classify_an_unarmed_delivery_scenario():
    # Actual previous no-bed positive_02 and failed bed_before_pickup_01
    # both had 35 hits near the named bed ROI from CG1. Retain the evidence;
    # do not promote these counts to a second, unrequested bed experiment.
    raw=dict(hits=35,global_new=52,local_new=0)
    assert raw['hits']>=4 and raw['global_new']>=4
    assert not before_pickup_scope('E1_deliver','E1',None)


def test_clearance_is_after_real_monitor_completion_with_original_resource_phases():
    cfg=bed_contract.config();task=monitor_clearance_task(cfg)
    assert task['dependencies']==['E1_monitor'] and task['resources']==['TL']
    assert (task['entry_anchor'],task['clear_anchor'])==('ETL','V3')
    assert task['approach']==22 and task['egress']==22
    assert task['service_role']=='monitor_area_clearance' and 'protocol_task_id' not in task


def test_initial_clearance_keeps_running_r3_dependency_without_inventing_ACK():
    import dense_tasks as dt
    cfg=bed_contract.config();tasks,routes=dt.normal_tasks()
    for role,anchor,owner in [('monitor','M1','r1'),('pickup','G1','r2'),('deliver','H1','r2')]:
        tasks['E1_'+role]=dt.phases(dict(kind=role,anchor=anchor,duration=8.,capabilities=['move'],
            release=100.,deadline=1800.,resources=['G1'] if role=='pickup' else [],dependencies=[]),cfg)
    plan=dict(owners={j:t['nominal_owner'] for j,t in tasks.items() if t['kind']=='normal'},
        starts={j:200.+i*40 for i,j in enumerate(tasks)},finishes={j:210.+i*40 for i,j in enumerate(tasks)},
        routes=routes,ends={r:900. for r in cfg['robots']})
    plan['owners'].update(E1_monitor='r1',E1_pickup='r2',E1_deliver='r2')
    states={r:dict(job=None,cargo=None,state='IDLE',anchor='V1',record={},pose=dict(x=0.,y=0.)) for r in cfg['robots']}
    states['r3'].update(job='C0_r3_W1',state='NAVIGATING',leg='clear',record=dict(
        job_id='C0_r3_W1',task_id='running-prefix-token',target=dict(x=20.,y=-10.),service_started=100.,service_finished=104.))
    completed={j:dict(end=90.) for j in ['C0_r1_W1','C0_r2_W1','E1_verify']}
    original=deepcopy((tasks,plan,completed,states))
    p=project_initial_clearance(cfg,tasks,plan,completed,states,120.)
    assert len(p['tasks'])==5 and 'C0_r3_W2' not in p['tasks']
    assert p['prefixes']['r3']['issued_prefix']['record_task_id']=='running-prefix-token'
    assert 'C0_r3_W2' in p['known_finishes'] and 'C0_r3_W2' not in p['actual_known_finishes']
    assert 'E1_monitor_clear' not in p['actual_known_finishes'] and not p['active_commitments']
    assert p['robots']['r2']['ready']>=p['coverage_projection']['area_clear']
    assert original==(tasks,plan,completed,states)
