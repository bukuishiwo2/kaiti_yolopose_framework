"""Release/dispatch tests target premature next-cycle execution, no fake Nav2."""
from pathlib import Path
import sys,json
from types import SimpleNamespace
sys.path[:0]=[str(Path(__file__).resolve().parents[1]),str(Path(__file__).resolve().parents[1]/'tools')]
from support.clinic_runtime.experiment_modes import load_spec,select_cycle,release_time,install
import dense_tasks as dt

def test_benchmark_release_is_unchanged():
 s=load_spec('benchmark');assert release_time(s,None)==900.;assert s['expected_normal_services']==18

def test_compressed_release_requires_observed_closure():
 for name in ['fast','standard']:
  s=load_spec(name);assert release_time(s,None)==float('inf');assert release_time(s,710.)==725.
 assert release_time(load_spec('fast'),300.)==315.
 assert release_time(load_spec('standard'),300.)==650.

def test_mode_task_set_and_dependencies(monkeypatch):
 from support.clinic_runtime.config import ROOT
 cfg=json.loads((ROOT/'config/hospital_bed/scenario.json').read_text());monkeypatch.setattr(dt,'config',lambda:cfg)
 for name in ['benchmark','standard','fast']:
  s=load_spec(name);tasks={}
  for k in [0,1]:
   t,r=select_cycle(*dt.cycle_tasks(k),k,s);tasks.update(t)
   assert all(set(q)<=set(t) for q in r.values())
  assert len(tasks)==s['expected_normal_services']
  assert all(dep in tasks for t in tasks.values() for dep in t['dependencies'])

def test_future_task_is_not_dispatched_by_early_optimization(monkeypatch,tmp_path):
 monkeypatch.setenv('CLINIC_EXPERIMENT_MODE','fast')
 class Base:
  def __init__(self,out,args):pass
  def dispatch_dense(self,b):self.dispatched=True
  def tick(self):self.parent_seen_period=self.cfg['period_seconds']
 ep=SimpleNamespace(bc=SimpleNamespace(config=lambda:{}),dt=SimpleNamespace(cycle_tasks=lambda k:({},{})),old=SimpleNamespace(),Episode=Base)
 install(ep);e=ep.Episode(tmp_path,None);e.queues={'r1':['C1_r1_W1']};e.completed={};e.tasks={'C1_r1_W1':{'cycle_id':1}};e.released_cycles={0};e.dispatched=False
 e.dispatch_dense(SimpleNamespace(rid='r1'));assert not e.dispatched
 e.released_cycles.add(1);e.dispatch_dense(SimpleNamespace(rid='r1'));assert e.dispatched
 e.cfg={};e.incident_closed_at=None;e.tick();assert e.parent_seen_period==float('inf')
 e.incident_closed_at=400.;e.tick();assert e.parent_seen_period==415.

def test_controller_false_result_cannot_be_labelled_passed(monkeypatch,tmp_path):
 import pytest
 from contextlib import contextmanager
 from support.clinic_runtime import __main__ as cli
 @contextmanager
 def no_world(*args,**kw):yield None
 monkeypatch.setattr(cli,'ROOT',tmp_path);monkeypatch.setattr(cli,'BASE',tmp_path/'verification')
 monkeypatch.setattr(cli,'require_static',lambda out:{})
 monkeypatch.setattr(cli,'require_qualified_smoke',lambda:'test-only')
 monkeypatch.setattr(cli,'prepare',lambda out:None)
 monkeypatch.setattr(cli,'world',no_world)
 monkeypatch.setattr(cli,'runtime_gate',lambda *a,**kw:tmp_path/'test_gate.json')
 monkeypatch.setattr(cli,'episode',lambda *a,**kw:{'passed':False,'failure':'INJECTED_CONTROLLER_FAILURE'})
 monkeypatch.setattr(sys,'argv',['clinic_experiment','run','--name','failed_mock','--domain','79','--policy','local_impact'])
 with pytest.raises(RuntimeError,match='Controller did not complete'):cli.main()
 state=json.loads((tmp_path/'verification/failed_mock/status.json').read_text());assert state['status']=='FAILED'
