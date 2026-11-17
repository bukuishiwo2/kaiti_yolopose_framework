"""Refactor safety: namespace regressions, fail-closed launch, real-frame replay."""
import ast
import json
import math
from pathlib import Path
import sys
from types import SimpleNamespace as N
import numpy as np
import pytest
import yaml
from support.clinic_runtime import config, preflight

ROOT=config.ROOT

def test_resolved_template_matches_all_accepted_nav2_parameters():
    for rid in config.scenario()['robots']:
        accepted=yaml.safe_load((ROOT/'config/hospital_bed'/f'{rid}_nav2.yaml').read_text())
        assert config.nav2_parameters(rid,resolve=True)==accepted

def test_relative_costmap_scan_is_rejected_before_launch(monkeypatch):
    original=preflight.nav2_parameters
    def broken(rid,resolve=False):
        p=original(rid,resolve=resolve)
        p['local_costmap']['local_costmap']['ros__parameters']['obstacle_layer']['scan']['topic']='scan'
        return p
    monkeypatch.setattr(preflight,'nav2_parameters',broken)
    r=preflight.static_check()
    assert not r['passed']
    assert any(not c['passed'] and c['name'].endswith(':scan') for c in r['checks'])

def test_failed_static_gate_does_not_start_world(monkeypatch,tmp_path):
    from support.clinic_runtime import __main__ as cli
    monkeypatch.setattr(cli,'BASE',tmp_path)
    monkeypatch.setattr(cli,'require_static',lambda _:(_ for _ in ()).throw(RuntimeError('deliberate bad config')))
    touched=[]
    monkeypatch.setattr(cli,'world',lambda *a:touched.append(a))
    monkeypatch.setattr(sys,'argv',['runtime','run','--name','negative_gate','--policy','local_impact'])
    with pytest.raises(RuntimeError,match='bad config'):cli.main()
    assert not touched
    assert json.loads((tmp_path/'negative_gate/status.json').read_text())['status']=='FAILED'

def test_episode_rejects_missing_passed_gate(monkeypatch,tmp_path):
    from support.clinic_runtime import __main__ as cli
    monkeypatch.setenv('CLINIC_PREFLIGHT_REPORT',str(tmp_path/'absent.json'))
    monkeypatch.setattr(sys,'argv',['runtime','_episode','--out',str(tmp_path/'never_started')])
    with pytest.raises(RuntimeError,match='mandatory'):cli.main()
    assert not (tmp_path/'never_started').exists()

def test_episode_rejects_sources_changed_after_gate(monkeypatch,tmp_path):
    from support.clinic_runtime import __main__ as cli
    gate=tmp_path/'runtime_preflight.json';gate.write_text(json.dumps(dict(passed=True)))
    (tmp_path/'static_preflight.json').write_text(json.dumps(dict(source_hashes={})))
    monkeypatch.setenv('CLINIC_PREFLIGHT_REPORT',str(gate))
    monkeypatch.setattr(sys,'argv',['runtime','_episode','--out',str(tmp_path/'never_started')])
    with pytest.raises(RuntimeError,match='Sources changed'):cli.main()
    assert not (tmp_path/'never_started').exists()

def test_research_methods_are_unchanged_ast_not_runtime_rewritten():
    old=ast.parse((ROOT/'runs/bed_local_a13/source/tools/run_bed_episode.py').read_text())
    new=ast.parse((ROOT/'support/clinic_runtime/episode.py').read_text())
    def methods(tree,cls):
        c=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name==cls)
        return {n.name:n for n in c.body if isinstance(n,ast.FunctionDef)}
    for cls,names in [('Episode',['__init__','physical_truth','sensor_graph','submit_dense','poll_dense','request_repair','dispatch_dense']),('Bot',['corridor_ahead','blocked'])]:
        a,b=methods(old,cls),methods(new,cls)
        for name in names:assert ast.dump(a[name])==ast.dump(b[name]),name
    previous=methods(old,'Episode')['tick'];merged=ast.parse(ast.unparse(methods(new,'Episode')['tick'])).body[0];merged.body=merged.body[1:-1]
    assert ast.dump(previous)==ast.dump(merged)
    a={n.name:n for n in old.body if isinstance(n,ast.FunctionDef)};b={n.name:n for n in new.body if isinstance(n,ast.FunctionDef)}
    for name in ['cycle','event','witness']:assert ast.dump(a[name])==ast.dump(b[name])

def test_merged_local_evidence_replays_all_121_real_frames():
    from support.clinic_runtime.episode import Bot
    reference=json.loads((ROOT/'verification/active_bed_2026-11-16/static_local_evidence_regression.json').read_text())
    for r in reference['rows']:
        z=np.load(r['file']);m=json.loads(str(z['metadata']));tx,ty,yaw=m['map_from_frame']
        t=N(transform=N(translation=N(x=tx,y=ty),rotation=N(x=0.,y=0.,z=math.sin(yaw/2),w=math.cos(yaw/2))))
        b=N(rid='r2',buffer=N(lookup_transform=lambda *a:t),c=N(cfg=config.scenario()))
        msg=N(header=N(frame_id=m['frame']),metadata=N(size_y=z['costmap'].shape[0],size_x=z['costmap'].shape[1],resolution=m['resolution'],origin=N(position=N(x=m['origin'][0],y=m['origin'][1]))),data=z['costmap'].ravel())
        Bot.grid_counts(b,msg,True)
        assert b.local_raw_counts['short']==r['raw']
        assert b.local_counts['short']==r['new']

def test_new_lethal_cell_holds_wait_then_zero_stable_resumes():
    from support.clinic_runtime.episode import Bot
    b=Bot.__new__(Bot);now=[100.];events=[]
    b.c=N(elapsed=lambda:now[0],cfg=config.scenario(),log=lambda *a,**kw:None);b.state='BED_WAIT';b.rid='r2';b.job='E1_deliver';b.local_counts={'short':1,'long':1};b.hits={'short':0,'long':0};b.global_counts={'short':0,'long':0};b.baseline={};b.clear_since=None;b.laser_clear_since=None;b.last_global_clear=0.;b.bed_wait_at=99.;b.clear_global=N(service_is_ready=lambda:False);b.clear_local=b.clear_global;b.send_navigation=lambda:events.append('resume');b.fail=lambda reason:events.append(reason)
    b.step();now[0]=101.2;b.step();assert not events
    b.local_counts={'short':0,'long':0};b.step();assert not events
    now[0]=102.3;b.step();assert events==['resume']


def test_ros_preflight_nodes_construct_without_gazebo():
    # This checks installed ROS API integration before any physical world launch.
    result=preflight.runtime_check(timeout=0.)
    assert result['passed'] is False


def test_cleanup_finds_children_after_launcher_exits():
    import os,subprocess,time
    from support.clinic_runtime.__main__ import cleanup_owned_group
    env=os.environ.copy();env['IGN_PARTITION']='clinic_unit_cleanup_orphan'
    p=subprocess.Popen([sys.executable,'-c','import subprocess,time;subprocess.Popen(["sleep","30"]);time.sleep(.2)'],env=env,start_new_session=True)
    import psutil
    created=psutil.Process(p.pid).create_time();p.wait(timeout=3.)
    report=cleanup_owned_group(p.pid,env['IGN_PARTITION'],created)
    assert report['passed'] and report['remaining']==[]


def test_cleanup_refuses_another_partition():
    import os,subprocess,signal
    import psutil
    from support.clinic_runtime.__main__ import cleanup_owned_group
    env=os.environ.copy();env['IGN_PARTITION']='clinic_unit_other_partition'
    p=subprocess.Popen(['sleep','30'],env=env,start_new_session=True)
    created=psutil.Process(p.pid).create_time()
    try:
        with pytest.raises(RuntimeError,match='identity mismatch'):
            cleanup_owned_group(p.pid,'clinic_unit_wrong_partition',created)
        assert p.poll() is None
    finally:os.killpg(p.pid,signal.SIGKILL);p.wait()


def test_installed_humble_qos_result_and_incompatible_profiles():
    from rclpy.qos import QoSProfile, ReliabilityPolicy, qos_check_compatible, QoSCompatibility
    pub=QoSProfile(depth=10,reliability=ReliabilityPolicy.BEST_EFFORT)
    reliable_sub=QoSProfile(depth=10,reliability=ReliabilityPolicy.RELIABLE)
    assert qos_check_compatible(pub,reliable_sub)[0]==QoSCompatibility.ERROR
    assert qos_check_compatible(pub,pub)[0]!=QoSCompatibility.ERROR


def test_explicit_auditor_reproduces_both_accepted_audits(tmp_path):
    from support.clinic_runtime.audits import audit
    for name in ['bed_local_a13','bed_full_a13']:
        run=ROOT/'runs'/name;previous=json.loads((run/'independent_audit.json').read_text())
        result=audit(run,tmp_path/name)
        for key in ['passed','checks','failed','services','resource_intervals','repair_metrics','bed_wait_drift_m','short_historical_clear_sensor_times']:
            assert result[key]==previous[key],(name,key)


def test_current_runtime_never_executes_or_rewrites_source_at_runtime():
    for path in (ROOT/'support/clinic_runtime').glob('*.py'):
        tree=ast.parse(path.read_text())
        assert not any(isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id in ['exec','eval','compile'] for n in ast.walk(tree)),path


def test_full_run_cannot_skip_current_smoke_qualification(monkeypatch,tmp_path):
    from support.clinic_runtime import __main__ as cli
    monkeypatch.setattr(cli,'BASE',tmp_path)
    with pytest.raises(RuntimeError,match='No passed sensor'):cli.require_qualified_smoke()


def test_stop_rejects_a_different_named_supervisor(monkeypatch,tmp_path):
    from support.clinic_runtime import __main__ as cli
    monkeypatch.setattr(cli,'BASE',tmp_path);out=tmp_path/'expected';out.mkdir()
    (out/'status.json').write_text(json.dumps(dict(status='EXECUTING',supervisor_pid=123,supervisor_created=1.)))
    sent=[]
    fake=N(create_time=lambda:1.,cmdline=lambda:['python','-m','support.clinic_runtime','run','--name','different'],send_signal=lambda sig:sent.append(sig))
    monkeypatch.setattr(cli.psutil,'Process',lambda _:fake)
    monkeypatch.setattr(sys,'argv',['runtime','stop','--name','expected'])
    with pytest.raises(RuntimeError,match='identity mismatch'):cli.main()
    assert not sent


def test_legacy_episode_modules_are_flat_aliases_not_patch_layers():
    import run_bed_episode,run_bed_episode_recovery,run_bed_episode_static_delta
    from support.clinic_runtime.episode import Bot,Episode
    for module in [run_bed_episode,run_bed_episode_recovery,run_bed_episode_static_delta]:
        assert module.Bot is Bot and module.Episode is Episode
