"""Hand-authored expectations; no imports from the transition implementation."""
from copy import deepcopy

SCHEMA = 'event-task/v1'
SPACE = dict(valid=True,frame='map',event_xy=[2,1],
             service_points=dict(verify=[2,0],monitor=[2,0],deliver=[3,1]))


def observation(mid,at,status='confirmed',space=None,source_at=None):
    m=dict(schema=SCHEMA,message_id=mid,kind='observation',at=at,event_id='E1',
           source_at=at if source_at is None else source_at,status=status)
    if status=='confirmed':m['space']=deepcopy(SPACE if space is None else space)
    return m


def feedback(mid,at,role,phase,robot='R0',revision=1,attempt=1,result=None):
    m=dict(schema=SCHEMA,message_id=mid,kind='feedback',at=at,event_id='E1',
           task_id='E1:'+role,phase=phase,robot_id=robot,task_revision=revision,attempt=attempt)
    if result is not None:m['result']=result
    return m


def step(message,states,generated=(),**expect):
    return dict(message=message,expect=dict(states=states,generated=list(generated),**expect))


def cases():
    v={'verify':'READY'}
    vr={'verify':'RUNNING'}
    checked={'verify':'SUCCEEDED','monitor':'READY','pickup':'PENDING','deliver':'PENDING'}
    watched={**checked,'monitor':'RUNNING','pickup':'READY'}
    carried={**watched,'pickup':'SUCCEEDED','deliver':'READY'}
    moved=deepcopy(SPACE);moved['event_xy']=[3,1]
    moved['service_points']=dict(verify=[3,0],monitor=[3,0],deliver=[4,1])
    confirmed=[
        step(observation('a0',0),v,['verify'],lifecycle='OPEN',verified=False,position_valid=True),
        step(feedback('a1',1,'verify','started'),vr),
        step(feedback('a2',2,'verify','succeeded',result='fall'),checked,['monitor','pickup','deliver'],verified=True),
        step(observation('a3',2.5,space=moved),checked,targets={'monitor':[3,0],'deliver':[4,1]},revisions={'monitor':2,'deliver':2},same_ids=True),
        step(feedback('a4',3,'monitor','started',revision=2),watched),
        step(feedback('a5',4,'pickup','started','R1',revision=2),{**watched,'pickup':'RUNNING'}),
        step(feedback('a6',5,'pickup','succeeded','R1',revision=2),carried,required_owner={'deliver':'R1'}),
        step(feedback('a7',6,'deliver','started','R1',revision=3),{**carried,'deliver':'RUNNING'}),
        step(feedback('a8',7,'deliver','succeeded','R1',revision=3),{**carried,'deliver':'SUCCEEDED'}),
        step(feedback('a9',8,'monitor','succeeded',revision=2),{**carried,'monitor':'SUCCEEDED','deliver':'SUCCEEDED'},lifecycle='COMPLETED',cargo_disposition='DELIVERED'),
    ]
    occlusion=[
        step(observation('b0',0),v,['verify']),
        step(feedback('b1',1,'verify','started'),vr),
        step(feedback('b2',2,'verify','succeeded',result='fall'),checked,['monitor','pickup','deliver']),
        step(feedback('b3',3,'monitor','started'),watched),
        step(observation('b4',4,'occluded'),watched,lifecycle='OPEN',position_valid=True,same_ids=True),
        step(observation('b5',5,'occluded'),watched,changed=False,same_ids=True),
        step(observation('b6',6),watched,same_ids=True),
        step(dict(schema=SCHEMA,message_id='b7',kind='resolution',event_id='E1',at=7,result='resolved'),
             {'verify':'SUCCEEDED','monitor':'CANCEL_REQUESTED','pickup':'CANCELLED','deliver':'CANCELLED'},lifecycle='CLOSED',active_commitments=1),
        step(feedback('b8',8,'monitor','cancelled'),{'verify':'SUCCEEDED','monitor':'CANCELLED','pickup':'CANCELLED','deliver':'CANCELLED'},lifecycle='CLOSED',active_commitments=0),
    ]
    duplicate=[
        step(observation('c0',0),v,['verify']),
        step(observation('c0',1,source_at=0),v,changed=False,decision='DUPLICATE_MESSAGE',same_ids=True),
        step(observation('c1',2,source_at=0),v,changed=False,same_ids=True),
        step(feedback('c2',3,'verify','started'),vr),
        step(feedback('c2',4,'verify','started'),vr,changed=False,decision='DUPLICATE_MESSAGE'),
        step(feedback('c3',5,'verify','succeeded',result='fall'),checked,['monitor','pickup','deliver']),
        step(feedback('c4',6,'verify','succeeded',result='fall'),checked,changed=False,decision='DUPLICATE_FEEDBACK'),
        step(observation('c5',7),checked,changed=False,same_ids=True),
    ]
    invalid=[
        step(observation('d0',0,space={'valid':False}),{},position_valid=False,verified=False),
        step(observation('d1',1),v,['verify'],position_valid=True),
        step(feedback('d2',2,'verify','started'),vr),
        step(observation('d3',3,space={'valid':False}),{'verify':'CANCEL_REQUESTED'},position_valid=False,targets={'verify':None},active_commitments=1),
        step(observation('d4',4),{'verify':'CANCEL_REQUESTED'},position_valid=True,active_commitments=1),
        step(feedback('d5',5,'verify','cancelled'),v,attempts={'verify':2},revisions={'verify':3},same_ids=True,active_commitments=0),
        step(feedback('d6',6,'verify','started',revision=3,attempt=2),vr),
        step(feedback('d7',7,'verify','succeeded',revision=3,attempt=2,result='fall'),checked,['monitor','pickup','deliver']),
        step(observation('d8',8,space={'valid':False}),{'verify':'SUCCEEDED','monitor':'PENDING','pickup':'PENDING','deliver':'PENDING'},position_valid=False,planning_tasks=0),
        step(observation('d9',9),checked,position_valid=True,same_ids=True),
    ]
    return [dict(name='confirmed_fall',steps=confirmed),dict(name='short_occlusion',steps=occlusion),
            dict(name='duplicate_observation',steps=duplicate),dict(name='invalid_position',steps=invalid)]
