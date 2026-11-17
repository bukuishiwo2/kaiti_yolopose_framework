"""Versioned task/release profiles; the Benchmark branch preserves prior behavior.
No physics, navigation, ACK, service, obstacle or optimization-model changes.
"""
from copy import deepcopy
import hashlib,json,os
from pathlib import Path
from .config import ROOT

def load_spec(name=None):
 name=name or os.environ.get('CLINIC_EXPERIMENT_MODE','benchmark')
 if name not in ['benchmark','standard','fast']:raise ValueError(name)
 spec=json.loads((ROOT/f'config/clinic_modes/{name}.json').read_text())
 assert hashlib.sha256((ROOT/spec['base_scenario']).read_bytes()).hexdigest()==spec['base_scenario_sha256']
 return spec

def select_cycle(tasks,routes,cycle,spec):
 tasks=deepcopy(tasks);routes=deepcopy(routes)
 if cycle==1:
  keep={j for route in routes.values() for j in route[:spec['next_cycle_waypoints']]}
  tasks={j:t for j,t in tasks.items() if j in keep};routes={r:[j for j in q if j in keep] for r,q in routes.items()}
 return tasks,routes

def release_time(spec,closed):
 if spec['name']=='benchmark':return spec['nominal_next_release']
 return float('inf') if closed is None else max(spec['nominal_next_release'],closed+15.)

def install(ep,probe=None):
 spec=load_spec()
 if spec['name']=='benchmark' or probe:return
 original_config=ep.bc.config;original_cycle=ep.dt.cycle_tasks
 def config():
  c=original_config();c['period_seconds']=spec['nominal_next_release'];return c
 def cycle(k):return select_cycle(*original_cycle(k),k,spec)
 ep.dt.config=config;ep.old.config=config;ep.dt.cycle_tasks=cycle
 class ModeEpisode(ep.Episode):
  def __init__(self,out,args):
   super().__init__(out,args);(out/'experiment_mode.json').write_text(json.dumps(spec,indent=2))
  def tick(self):
   # The event time is never supplied in advance. Release uses observed closure.
   self.cfg['period_seconds']=release_time(spec,self.incident_closed_at)
   super().tick()
  def dispatch_dense(self,b):
   q=[j for j in self.queues.get(b.rid,[]) if j not in self.completed]
   if q and self.tasks[q[0]].get('cycle_id')==1 and 1 not in self.released_cycles:return
   super().dispatch_dense(b)
 ep.Episode=ModeEpisode
