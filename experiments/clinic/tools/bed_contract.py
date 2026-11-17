"""Active monitor/custody commitment projection; forecasts never become actual ACKs.
Reuse dense normal-prefix projection and original prefix validation/impact propagation.
"""
from copy import deepcopy
import math
import dense_tasks as dt
from prefix_contract import trim,validate,impact_scope
ROOT=dt.ROOT

def config():
 import json
 return json.loads((ROOT/'config/hospital_bed/scenario.json').read_text())
def project(cfg,tasks,plan,completed,states,now,blocked=False):
 proxy=deepcopy(states);commitments={};forecast={};drop=states[next(r for r,s in states.items() if s.get('cargo')=='E1')];courier=next(r for r,s in states.items() if s.get('cargo')=='E1');monitor=next(r for r,s in states.items() if s['job']=='E1_monitor');assert drop['job']=='E1_deliver' and states[monitor]['record'].get('service_started') is not None
 target=cfg['anchors']['H1'];pose=drop['pose'];remaining=math.hypot(target[0]-pose['x'],target[1]-pose['y'])/.22+12.
 # Receding observation horizon, not the driver's hidden removal schedule.
 finish=math.ceil((now+(cfg['bed_experiment']['rolling_unavailability_seconds'] if blocked else 0.)+remaining+tasks['E1_deliver']['duration']+1.)*100)/100.;handover=finish+4.
 assert finish<=tasks['E1_deliver']['deadline'] and handover<=tasks['E1_monitor']['deadline'],'Projected hard event deadline infeasible; cannot repair by breaking custody/monitor promises'
 for rid,j,anchor,release in [(courier,'E1_deliver','H1',finish),(monitor,'E1_monitor','M1',handover)]:
  s=states[rid];rec=s['record'];assert rec['job_id']==j
  commitments[rid]=dict(jobs=[j],schedule=[dict(job=j,owner=rid,clear_forecast=release,service_finish_forecast=release,clear_anchor=anchor)],record_task_id=rec['task_id'],source_anchor=anchor,ready=release,actual_service_started=rec.get('service_started'),goal=deepcopy(rec['target']),cargo_at_snapshot=s.get('cargo'),protocol_revision=rec.get('sent_revision'))
  proxy[rid].update(job=None,cargo=None,anchor=anchor);forecast[j]=release
 selected=[j for j,t in tasks.items() if t['kind']=='normal' and j not in completed]
 p=dt.problem(cfg,tasks,selected,completed,proxy,plan,now,None,'active_repair');p['reference']=trim(plan,p['tasks']);p['start_tolerance']=2.;p['active_commitments']=commitments;p['actual_snapshot']=deepcopy(states);p['actual_known_finishes']={j:q['end'] for j,q in completed.items()};p['committed_finishes']=forecast;p['known_finishes'].update(forecast)
 for rid,v in commitments.items():p['robots'][rid].update(source_anchor=v['source_anchor'],position=cfg['anchors'][v['source_anchor']][:2],ready=max(now+35.,v['ready']));p['prefixes'][rid]=v
 p['coverage_projection']=dict(monitor=monitor,courier=courier,delivery_finish=finish,monitor_release=handover,actual_pickup=completed['E1_pickup']['service_started'],observation_horizon=cfg['bed_experiment']['rolling_unavailability_seconds'] if blocked else 0.)
 p['projection_note']='Hard issued goals/owners/custody; revocable future release only. Active monitoring remains until real delivery+handover ACK.'
 return p

def commitment_check(p,completed,states):
 errors=[]
 for rid,pre in p['active_commitments'].items():
  j=pre['jobs'][0]
  if j in completed:
   if completed[j]['robot']!=rid or completed[j]['task_id']!=pre['record_task_id']:errors.append(j+'_identity')
  else:
   s=states[rid]
   if s['job']!=j or s['record']['task_id']!=pre['record_task_id'] or s['record']['target']!=pre['goal']:errors.append(j+'_issued_goal_changed')
   if j=='E1_deliver' and s['cargo']!='E1':errors.append('custody_changed')
   if j=='E1_monitor' and s['record'].get('service_started')!=pre['actual_service_started']:errors.append('monitor_restarted')
 return dict(passed=not errors,errors=errors)
