"""Single CLI for checks, short integration smoke and the research episode."""
import argparse
from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time
import traceback
import psutil
from .config import ROOT, profile, prepare, source_manifest, sha256
from .preflight import static_check

BASE=ROOT/'verification/clinic_runtime'

def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2))

def require_static(out):
    result=static_check();write(out/'static_preflight.json', result)
    if not result['passed']:
        raise RuntimeError('Static preflight failed: '+str([c['name'] for c in result['checks'] if not c['passed']]))
    return result

def runtime_gate(out, timeout, pulse=False):
    path=out/'runtime_preflight.json'
    code=subprocess.run([sys.executable,'-m','support.clinic_runtime','_check-runtime','--out',str(path),'--timeout',str(timeout)]+(['--pulse'] if pulse else []),cwd=ROOT).returncode
    if code or not path.exists() or not json.loads(path.read_text())['passed']:
        raise RuntimeError('Runtime preflight failed; episode was NOT started. Inspect '+str(path))
    return path

def cleanup_owned_group(pgid, partition, created):
    """Handle launch-startup races and orphaned children, never other partitions."""
    verified={}
    def members():
        found=[]
        for candidate in psutil.process_iter():
            try:
                if candidate.status()==psutil.STATUS_ZOMBIE or os.getpgid(candidate.pid)!=pgid:continue
                birth=candidate.create_time()
                try:owned=candidate.environ().get('IGN_PARTITION')==partition
                except psutil.AccessDenied:owned=verified.get(candidate.pid)==birth
                if birth<created-.05 or not owned:raise RuntimeError('Process group identity mismatch; cleanup refused')
                verified[candidate.pid]=birth;found.append(candidate)
            except (psutil.NoSuchProcess,ProcessLookupError):pass
        return found
    signals=[]
    for sig,grace in [(signal.SIGINT,5.),(signal.SIGTERM,3.),(signal.SIGKILL,2.)]:
        targets=members()
        if not targets:break
        os.killpg(pgid,sig);signals.append(dict(signal=int(sig),pids=[p.pid for p in targets]));until=time.monotonic()+grace
        while time.monotonic()<until and members():time.sleep(.1)
    remaining=members()
    if remaining:raise RuntimeError('Owned process cleanup incomplete')
    return dict(passed=True,partition=partition,pgid=pgid,signals=signals,remaining=[])

def physics_signature(manifest):
    excluded={str(ROOT/'support/clinic_runtime'/name) for name in ['__main__.py','audits.py','rendering.py']}
    return {path:sha for path,sha in manifest.items() if path not in excluded}

def require_qualified_smoke():
    current=physics_signature(source_manifest())
    for folder in sorted(BASE.glob('*'),reverse=True):
        try:
            status=json.loads((folder/'status.json').read_text())
            static=json.loads((folder/'static_preflight.json').read_text())
            runtime=json.loads((folder/'runtime_preflight.json').read_text())
            motion=json.loads((folder/'smoke_audit.json').read_text())
            cleanup=json.loads((folder/'cleanup.json').read_text())
            if status['mode']=='smoke' and status['status']=='PASSED' and physics_signature(static['source_hashes'])==current and runtime['passed'] and runtime['sensor_pulse']['passed'] and motion['passed'] and cleanup['passed']:
                return str(folder)
        except (FileNotFoundError,KeyError,json.JSONDecodeError):continue
    raise RuntimeError('No passed sensor+motion smoke for current execution/configuration sources. Run clinic_experiment.sh smoke with a NEW name first; full experiment was NOT launched.')

@contextmanager
def world(out, domain, prepared):
    partition='clinic_runtime_'+out.name
    for p in psutil.process_iter(['pid']):
        try:
            if p.pid!=os.getpid() and p.environ().get('ROS_DOMAIN_ID')==str(domain) and any(s in ' '.join(p.cmdline()) for s in ['ros2','gazebo','rclpy','clinic_runtime','nav2','parameter_bridge']):
                raise RuntimeError(f'ROS domain {domain} already has process {p.pid}; choose a free domain.')
        except (psutil.NoSuchProcess,psutil.AccessDenied):pass
    env=os.environ.copy();env.update(ROS_DOMAIN_ID=str(domain),IGN_PARTITION=partition,CLINIC_DENSE_DOMAIN=str(domain),CLINIC_DENSE_PARTITION=partition,CLINIC_RUNTIME_PREPARED=str(prepared))
    # Child processes inherit one explicit domain/partition; never touch native Clinic.
    os.environ.update({k:env[k] for k in ['ROS_DOMAIN_ID','IGN_PARTITION','CLINIC_DENSE_DOMAIN','CLINIC_DENSE_PARTITION','CLINIC_RUNTIME_PREPARED']})
    log=(out/'startup.log').open('w');p=subprocess.Popen(['ros2','launch',str(ROOT/'launch/clinic_experiment.launch.py'),'headless:=true'],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
    proc=psutil.Process(p.pid);created=proc.create_time();write(out/'owned_world.json',dict(pid=p.pid,created=created,partition=partition,domain=domain))
    try:yield p
    finally:
        try:
            try:
                owner=psutil.Process(p.pid)
                if abs(owner.create_time()-created)>.01 or owner.environ().get('IGN_PARTITION')!=partition:
                    raise RuntimeError('World identity mismatch; refusing unrelated cleanup')
            except psutil.NoSuchProcess:pass
            write(out/'cleanup.json',cleanup_owned_group(p.pid,partition,created))
        finally:log.close()

def episode(out, gate, policy, probe=None):
    os.environ['CLINIC_BED_POLICY']=policy;os.environ['CLINIC_PREFLIGHT_REPORT']=str(gate)
    args=[sys.executable,'-m','support.clinic_runtime','_episode','--out',str(out)]
    if probe:args+=['--probe',probe]
    with (gate.parent/'episode.log').open('w') as log:
        p=subprocess.Popen(args,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        try:code=p.wait(timeout=3700 if not probe else 1000)
        finally:
            if p.poll() is None:
                p.send_signal(signal.SIGINT)
                try:p.wait(timeout=10)
                except subprocess.TimeoutExpired:p.kill();p.wait()
    if code:raise RuntimeError('Episode failed; inspect '+str(gate.parent/'episode.log'))
    return json.loads((out/'result.json').read_text())

def validate_smoke(result):
    checks=[]
    for q in result['records']:
        a=q.get('arrival',{})
        checks.append(dict(job=q['job_id'],passed=q['status']=='SUCCEEDED' and a.get('position_error',999)<=.20 and a.get('yaw_error',999)<=.30 and q['stable_at']-q['stable_since']>=.7-1e-6 and all(0<=a.get(k,999)<=.5 for k in ['tf_age','scan_age','odom_age']) and q['service_started']>=q['stable_at'] and q['end']>=q['service_finished']))
    return dict(passed=result['passed'] and bool(checks) and all(c['passed'] for c in checks),checks=checks,scope='Quick real Nav2 motion and original stable-arrival/service guards; no full-loop MILP performance claim.')

def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    q=sub.add_parser('stop',help='SIGINT only the verified supervisor of a named run');q.add_argument('--name',required=True);q.add_argument('--legacy-layout',action='store_true',help=argparse.SUPPRESS)
    sub.add_parser('test',help='Run the bounded convergence regression suite (no Gazebo)')
    c=sub.add_parser('check',help='Static checks only, does not start Gazebo');c.add_argument('--out',type=Path,required=True)
    for name in ['smoke','run']:
        q=sub.add_parser(name);q.add_argument('--name',required=True);q.add_argument('--domain',type=int,default=profile()['default_domain']);q.add_argument('--timeout',type=float,default=120.)
        if name=='run':q.add_argument('--experiment-mode',choices=['benchmark','standard','fast'],default='benchmark');q.add_argument('--policy',choices=['local_impact','full_warm'],required=True);q.add_argument('--probe',choices=['quick','corridor','sensor','source','clearance']);q.add_argument('--legacy-layout',action='store_true',help=argparse.SUPPRESS)
    q=sub.add_parser('report',help='Audit/replay an existing full episode into a NEW directory');q.add_argument('run',type=Path);q.add_argument('--out',type=Path,required=True);q.add_argument('--no-render',action='store_true')
    q=sub.add_parser('episode',help='Compatibility: gated connection to an already launched world');q.add_argument('--out',type=Path,required=True);q.add_argument('--probe',choices=['quick','corridor','sensor','source','clearance'])
    q=sub.add_parser('_check-runtime',help='Internal worker (requires preflight)');q.add_argument('--out',type=Path,required=True);q.add_argument('--timeout',type=float,default=120.);q.add_argument('--pulse',action='store_true')
    q=sub.add_parser('_episode',help='Internal worker (requires preflight)');q.add_argument('--out',type=Path,required=True);q.add_argument('--probe',choices=['quick','corridor','sensor','source','clearance'])
    a=p.parse_args()
    if a.command=='run':os.environ['CLINIC_EXPERIMENT_MODE']=a.experiment_mode
    if a.command=='test':
        env=os.environ.copy();env['PYTEST_DISABLE_PLUGIN_AUTOLOAD']='1'
        return subprocess.run(['/home/yhc/kaiti_yolopose_framework/.venv/bin/python','-m','pytest','-q',str(ROOT/'tests/test_runtime_convergence.py')],cwd=ROOT,env=env).returncode
    if a.command=='stop':
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,70}',a.name):p.error('Invalid run name')
        folder=(ROOT/'verification/active_bed_2026-11-16' if a.legacy_layout else BASE)/a.name
        status=json.loads((folder/'status.json').read_text())
        if status['status'] in ['PASSED','EXECUTED','FAILED','STOPPED']:
            print('Already finished:',a.name);return 0
        supervisor=psutil.Process(status['supervisor_pid']);cmd=supervisor.cmdline()
        if abs(supervisor.create_time()-status['supervisor_created'])>.01 or 'support.clinic_runtime' not in cmd or '--name' not in cmd or cmd[cmd.index('--name')+1]!=a.name:
            raise RuntimeError('Supervisor identity mismatch; refusing stop')
        supervisor.send_signal(signal.SIGINT);print('SIGINT sent to verified supervisor:',a.name);return 0
    if a.command=='_check-runtime':
        from .preflight import runtime_check
        try:r=runtime_check(a.timeout,a.pulse)
        except Exception as e:r=dict(passed=False,error=repr(e))
        write(a.out,r);print('RUNTIME_PREFLIGHT',r['passed'],str(a.out));return 0 if r['passed'] else 1
    if a.command=='_episode':
        gate=Path(os.environ.get('CLINIC_PREFLIGHT_REPORT','/nonexistent'))
        if not gate.is_file() or not json.loads(gate.read_text())['passed']:raise RuntimeError('A passed runtime gate is mandatory')
        static=json.loads((gate.parent/'static_preflight.json').read_text())
        if static['source_hashes']!=source_manifest():raise RuntimeError('Sources changed after static preflight; rerun checks')
        evidence=json.loads(gate.read_text())
        if evidence.get('environment')!=dict(domain=os.environ.get('ROS_DOMAIN_ID'),partition=os.environ.get('IGN_PARTITION')) or time.time()-evidence.get('checked_wall',0)>30.:raise RuntimeError('Runtime gate is stale or belongs to another domain/partition')
        from . import episode as runner
        sys.argv=[sys.argv[0],'--out',str(a.out)]+(['--probe',a.probe] if a.probe else [])
        return runner.main()
    if a.command=='check':
        a.out.mkdir(parents=True,exist_ok=False);r=require_static(a.out);print('STATIC_PREFLIGHT',r['passed'],len(r['checks']),str(a.out));return 0
    if a.command=='report':
        from .audits import audit
        a.out.mkdir(parents=True,exist_ok=False);r=audit(a.run.resolve(),a.out)
        if r['passed'] and not a.no_render:
            from .rendering import render
            render(a.run.resolve(),a.out,r)
        print('AUDIT',r['passed'],r['checks'],str(a.out));return 0 if r['passed'] else 1
    if a.command=='episode':
        out=Path(str(a.out)+'.preflight');out.mkdir(parents=True,exist_ok=False);require_static(out)
        if not a.probe:require_qualified_smoke()
        gate=runtime_gate(out,120.)
        r=episode(a.out,gate,os.environ.get('CLINIC_BED_POLICY','local_impact'),a.probe);return 0 if r['passed'] else 1
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,70}',a.name):p.error('Name must be a new simple identifier')
    if not 0<=a.domain<=101:p.error('Use a free ROS domain in 0..101 for this local runtime')
    out=(ROOT/'verification/active_bed_2026-11-16' if getattr(a,'legacy_layout',False) else BASE)/a.name;out.mkdir(parents=True,exist_ok=False);result_out=ROOT/'runs'/a.name
    if result_out.exists():raise FileExistsError(result_out)
    status=dict(status='PREFLIGHT',mode=a.command,name=a.name,started_wall=time.time(),supervisor_pid=os.getpid(),supervisor_created=psutil.Process(os.getpid()).create_time());write(out/'status.json',status)
    try:
        require_static(out)
        if a.command=='run' and a.experiment_mode!='benchmark':
            candidates=sorted((ROOT/'verification').glob('*/mode_offline_gate*/summary.json'),reverse=True)
            qualified=[]
            for candidate in candidates:
                evidence=json.loads(candidate.read_text())
                if evidence.get('passed') and evidence.get('source_hashes') and all(Path(f).is_file() and sha256(f)==h for f,h in evidence['source_hashes'].items()):qualified.append(str(candidate))
            if not qualified:raise RuntimeError('No matching offline mode state/MILP gate; run tools/verify_experiment_modes.py first')
            status['offline_mode_gate']=qualified[0]
        if a.command=='run' and not a.probe:status['qualified_smoke']=require_qualified_smoke()
        prepare(out/'parameters');status['status']='RUNTIME_PREFLIGHT';write(out/'status.json',status)
        with world(out,a.domain,out/'parameters'):
            gate=runtime_gate(out,a.timeout,pulse=a.command=='smoke');status['status']='EXECUTING';write(out/'status.json',status)
            r=episode(result_out,gate,getattr(a,'policy','local_impact'),'quick' if a.command=='smoke' else a.probe)
            if not r.get('passed') or r.get('failure'):raise RuntimeError('Controller did not complete: '+str(r.get('failure'))+'; inspect '+str(result_out/'result.json'))
            if a.command=='smoke':
                audit=validate_smoke(r);write(out/'smoke_audit.json',audit)
                if not audit['passed']:raise RuntimeError('Physical smoke guard audit failed')
            status.update(status='EXECUTED' if getattr(a,'legacy_layout',False) else 'PASSED',result=str(result_out/'result.json'))
    except BaseException as e:
        status.update(status='FAILED',error=repr(e));(out/'failure_traceback.txt').write_text(traceback.format_exc());raise
    finally:
        status['finished_wall']=time.time();write(out/'status.json',status)
    print(json.dumps(status));return 0

if __name__=='__main__':
    try:raise SystemExit(main())
    except KeyboardInterrupt:
        print('Interrupted; owned processes were cleaned up.',file=sys.stderr);raise SystemExit(130)
    except Exception as error:
        print('ERROR:',str(error),file=sys.stderr);raise SystemExit(2)
