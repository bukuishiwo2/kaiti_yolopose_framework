"""Opt-in registered-video evidence policy and before-pickup commitments.

No synthetic model observations, verdicts or failures. Registration evidence is
an explicit configuration-bound administrative source, not a sensor estimate.
Original MILP/impact/validation code remains in the actual Clinic workspace.
"""
from copy import deepcopy
import math
from .event_protocol import EventTaskProtocol, ProtocolError


def before_pickup_scope(job, cargo, service_started):
    """This opt-in instance does not activate the old post-pickup bed scenario.

    False means the dedicated bed experiment is inapplicable, not that a path
    is safe. Unchanged Nav2 path/collision/arrival/resource guards still apply.
    """
    return job == 'E1_pickup' and cargo is None and service_started is None


def monitor_clearance_task(cfg):
    """Existing qualified TL entry/service/V3-clear sequence after monitoring."""
    import dense_tasks as dt
    return dt.phases(dict(kind='clearance',anchor='TL',duration=1.,capabilities=['move'],
        release=0.,deadline=2200.,resources=['TL'],dependencies=['E1_monitor'],
        service_role='monitor_area_clearance',nominal_owner='r1',cycle_id=0,waypoint=9,energy_rate=0.),cfg)


def project_initial_clearance(cfg,tasks,plan,completed,states,now):
    """Initial scheduling policy, before any bed: identical clearance promises.

    Fixed future emergency assignments come from the validated original MILP;
    no observation, action result or actual completion is invented here.
    """
    import dense_tasks as dt
    import bed_contract as bc
    assert plan['owners']['E1_monitor']=='r1' and plan['owners']['E1_pickup']==plan['owners']['E1_deliver']=='r2'
    clear_task=monitor_clearance_task(cfg)
    drop=plan['finishes']['E1_deliver'];release=plan['finishes']['E1_monitor']
    start=release+cfg['tables']['event']['M1'][clear_task['entry_anchor']]+clear_task['approach']
    finish=start+clear_task['duration'];area=finish+clear_task['egress']+8.
    pickup_clear=plan['finishes']['E1_pickup']+tasks['E1_pickup']['egress']+8.
    w2='C0_r3_W2';w2clear=plan['finishes'][w2]+tasks[w2]['egress']+8.
    selected=[j for j,t in tasks.items() if t['kind']=='normal' and j not in completed and j!=w2 and t['waypoint']>1]
    proxy=deepcopy(states)
    for rid,a in [('r1','V3'),('r2','H1')]:proxy[rid].update(job=None,cargo=None,anchor=a)
    # Include the future W2 while checking the native dependency graph, then
    # project it as a fixed future promise (never an actual completion record).
    p=dt.problem(cfg,tasks,selected+[w2],completed,proxy,plan,now,None,'active_repair')
    p['tasks'].pop(w2)
    p.update(reference=bc.trim(plan,p['tasks']),start_tolerance=2.,active_commitments={},actual_snapshot=deepcopy(states),
        actual_known_finishes={j:r['end'] for j,r in completed.items()},
        committed_finishes={'E1_pickup':pickup_clear,'E1_deliver':drop,'E1_monitor':release,'E1_monitor_clear':area,w2:w2clear},
        committed_future=dict(E1_monitor_clear=dict(owner='r1',task=clear_task,finish=area)))
    p['known_finishes'].update(p['committed_finishes'])
    for rid,ready in [('r1',area),('r2',area),('r3',w2clear)]:
        anchor={'r1':'V3','r2':'H1','r3':tasks[w2]['clear_anchor']}[rid]
        p['robots'][rid].update(ready=max(now+35.,ready),source_anchor=anchor,position=cfg['anchors'][anchor][:2])
        p['prefixes'][rid]=dict(jobs=[],schedule=[],issued_prefix=deepcopy(p['prefixes'][rid]),source_anchor=anchor,ready=ready,
            basis='fixed future original-response plan, not actual execution ACK')
    p['blocked_resources'] += [
        dict(resource='TL',start=release,finish=area,job='E1_monitor_clear',owner='r1',kind='mandatory_post_monitor_area_clearance'),
        dict(resource='G1',start=plan['starts']['E1_pickup']-tasks['E1_pickup']['approach'],finish=pickup_clear,job='E1_pickup',owner='r2',kind='fixed_response_pickup'),
        dict(resource=tasks[w2]['resources'][0],start=plan['starts'][w2]-tasks[w2]['approach'],finish=w2clear,job=w2,owner='r3',kind='fixed_response_routine')]
    p['coverage_projection']=dict(monitor='r1',courier='r2',delivery_finish=drop,monitor_release=release,
        pickup_start=plan['starts']['E1_pickup'],pickup_finish=plan['finishes']['E1_pickup'],pickup_clear=pickup_clear,
        delivery_start=plan['starts']['E1_deliver'],observation_horizon=0.,clearance_start=start,clearance_finish=finish,
        area_clear=area,courier_normal_ready=area)
    p['projection_note']='INITIAL policy before disturbance: fixed original emergency/r3-W2 promises + qualified TL/V3 clearance. Same clearance constraints will be present in old plan and both repair policies.'
    return p


class RegisteredVideoProtocol(EventTaskProtocol):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.registration = None

    def position_evidence_valid(self, event):
        space = event.get('space') or {}
        if space.get('provenance') != 'video_source_registered':
            return super().position_evidence_valid(event)
        r = self.registration or {}
        return bool(space.get('valid') and r.get('valid') and
            r.get('region') == space.get('registration_id') and
            r.get('service_points') == space.get('service_points') and
            r.get('event_xy') == space.get('event_xy') and
            r.get('issued_at',math.inf) <= self.now <= r.get('valid_until',-math.inf))

    def set_registration(self, registration, now):
        r=deepcopy(registration)
        if not (r.get('schema')=='video-region-registration/v1' and
                r.get('source')=='qualified_scenario_registration' and r.get('config_sha256') and
                isinstance(r.get('valid'),bool) and math.isfinite(r.get('valid_until',math.inf))):
            raise ProtocolError('explicit finite configuration-bound registration required')
        previous=self.registration
        self.registration=r
        try:
            return self.apply(dict(schema='event-task/v1',kind='tick',
                message_id='registration:'+r['id'],at=now))
        except Exception:
            self.registration=previous
            raise

    def evidence_state(self):
        e=self.event or {};last=e.get('last_seen_at')
        return dict(behavior_last_observation=last,
            behavior_age=None if last is None else self.now-last,
            behavior_valid=last is not None and 0<=self.now-last<=self.position_ttl,
            registration=deepcopy(self.registration),position_valid=e.get('position_valid',False),
            verified=e.get('verified',False),lifecycle=e.get('lifecycle'),
            recovery='AWAIT_REVALIDATION_OR_QUALIFIED_HANDOVER' if any(
                t['state']=='CANCEL_REQUESTED' for t in self.tasks.values()) else None)


def project_before_pickup(cfg,tasks,plan,completed,states,now,observation):
    """Project immutable monitor + issued pickup/coupled delivery, free suffix.

    Forecasts use observed blockage plus the existing 30s rolling horizon,
    never the hidden bed removal schedule. They are not completion ACKs.
    """
    import dense_tasks as dt
    import bed_contract as bc
    monitor=next(r for r,s in states.items() if s['job']=='E1_monitor')
    courier=next(r for r,s in states.items() if s['job']=='E1_pickup')
    mon,cur=states[monitor],states[courier]
    assert mon['record'].get('service_started') is not None
    assert cur.get('cargo') is None and cur['record'].get('service_started') is None
    assert cur['state']=='BED_WAIT', 'issued navigation must stop with real cancel ACK before projection'
    pickup=tasks['E1_pickup'];deliver=tasks['E1_deliver']
    point=cfg['anchors'][pickup['entry_anchor']];pose=cur['pose']
    remaining=math.hypot(point[0]-pose['x'],point[1]-pose['y'])/.22+12.
    horizon=cfg['bed_experiment']['rolling_unavailability_seconds'] if observation['blocked'] else 0.
    start=math.ceil((now+horizon+remaining+pickup['approach'])*100)/100
    finish=start+pickup['duration'];clear=finish+pickup['egress']+8.
    drop_start=clear+cfg['tables']['event'][pickup['clear_anchor']][deliver['entry_anchor']]+deliver['approach']
    drop_finish=drop_start+deliver['duration']+1.;release=drop_finish+4.
    # The completed monitor still occupies M1 physically. Its qualified
    # TL/V3 departure is a future hard prefix, not a fabricated service ACK.
    clearance=monitor_clearance_task(cfg)
    clearance_start=release+cfg['tables']['event']['M1'][clearance['entry_anchor']]+clearance['approach']
    clearance_finish=clearance_start+clearance['duration']
    area_clear=clearance_finish+clearance['egress']+8.
    assert release<=tasks['E1_monitor']['deadline'] and drop_finish<=deliver['deadline']
    commitments={}
    for rid,j,a,t in [(monitor,'E1_monitor','V3',area_clear),(courier,'E1_pickup','H1',area_clear)]:
        rec=states[rid]['record']
        commitments[rid]=dict(jobs=[j],schedule=[dict(job=j,owner=rid,clear_forecast=t,
            service_finish_forecast=release if rid==monitor else finish,clear_anchor=a)],record_task_id=rec['task_id'],
            source_anchor=a,ready=t,actual_service_started=rec.get('service_started'),
            goal=deepcopy(rec['target']),cargo_at_snapshot=states[rid].get('cargo'),
            protocol_revision=rec.get('sent_revision'))
    commitments[monitor]['jobs'].append('E1_monitor_clear')
    commitments[monitor]['schedule']=[
        dict(job='E1_monitor',owner=monitor,service_finish_forecast=release,clear_forecast=release,clear_anchor='M1'),
        dict(job='E1_monitor_clear',owner=monitor,service_finish_forecast=clearance_finish,clear_forecast=area_clear,clear_anchor='V3')]
    commitments[courier]['jobs'].append('E1_deliver')
    commitments[courier]['schedule']=[
        dict(job='E1_pickup',owner=courier,service_finish_forecast=finish,clear_forecast=clear,clear_anchor=pickup['clear_anchor']),
        dict(job='E1_deliver',owner=courier,service_finish_forecast=drop_finish,clear_forecast=drop_finish,clear_anchor='H1')]
    commitments[courier]['waiting_for_clearance']='E1_monitor_clear'
    proxy=deepcopy(states)
    proxy[monitor].update(job=None,cargo=None,anchor='V3')
    proxy[courier].update(job=None,cargo=None,anchor='H1')
    selected=[j for j,t in tasks.items() if t['kind']=='normal' and j not in completed]
    p=dt.problem(cfg,tasks,selected,completed,proxy,plan,now,None,'active_repair')
    p.update(reference=bc.trim(plan,p['tasks']),start_tolerance=2.,active_commitments=commitments,
        actual_snapshot=deepcopy(states),actual_known_finishes={j:r['end'] for j,r in completed.items()},
        committed_finishes=dict(E1_pickup=clear,E1_deliver=drop_finish,E1_monitor=release,E1_monitor_clear=area_clear),
        committed_future=dict(E1_deliver=dict(owner=courier,anchor='H1',cargo_group='E1'),
            E1_monitor_clear=dict(owner=monitor,task=clearance,finish=area_clear)))
    p['known_finishes'].update(p['committed_finishes'])
    p['blocked_resources'].append(dict(resource='G1',start=now,finish=clear,job='E1_pickup',owner=courier,kind='issued_pickup_coupled_reservation'))
    p['blocked_resources'].append(dict(resource='TL',start=release,finish=area_clear,job='E1_monitor_clear',owner=monitor,kind='mandatory_post_monitor_area_clearance'))
    for rid,c in commitments.items():
        p['robots'][rid].update(source_anchor=c['source_anchor'],position=cfg['anchors'][c['source_anchor']][:2],ready=max(now+35.,c['ready']))
        p['prefixes'][rid]=c
    p['coverage_projection']=dict(monitor=monitor,courier=courier,delivery_finish=drop_finish,
        monitor_release=release,pickup_start=start,pickup_finish=finish,pickup_clear=clear,
        delivery_start=drop_start,observation_horizon=horizon,
        clearance_start=clearance_start,clearance_finish=clearance_finish,area_clear=area_clear,
        courier_normal_ready=area_clear)
    p['projection_note']='BEFORE pickup: preserve issued pickup owner/goal/token, continuous monitor, coupled same-courier delivery; only normal suffix may change. Forecasts are revocable, not ACKs.'
    return p


def resource_fence(old,current,issued_jobs):
    """Allow unrelated transactions, reject loss/change of an issued lease."""
    errors=[]
    for resource,owner in old.get('owners',{}).items():
        if any(j in owner.get('lease_id','') for j in issued_jobs):
            if current.get('owners',{}).get(resource)!=owner: errors.append(resource)
    return dict(passed=not errors,errors=errors)
