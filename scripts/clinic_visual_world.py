"""Opt-in launch supervisor reusing native identity-checked cleanup helpers."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import subprocess
import psutil


@contextmanager
def visual_world(out,domain,prepared):
    from support.clinic_runtime.__main__ import cleanup_owned_group,write
    root=Path('/home/yhc/clinic_planning_ws');partition='clinic_runtime_'+out.name
    for p in psutil.process_iter(['pid']):
        try:
            if p.pid!=os.getpid() and p.environ().get('ROS_DOMAIN_ID')==str(domain) and any(s in ' '.join(p.cmdline()) for s in ['ros2','gazebo','rclpy','clinic_runtime','nav2','parameter_bridge']):
                raise RuntimeError(f'domain {domain} in use by {p.pid}')
        except (psutil.NoSuchProcess,psutil.AccessDenied):pass
    env=os.environ.copy();env.update(ROS_DOMAIN_ID=str(domain),IGN_PARTITION=partition,
        CLINIC_DENSE_DOMAIN=str(domain),CLINIC_DENSE_PARTITION=partition,CLINIC_RUNTIME_PREPARED=str(prepared))
    os.environ.update({k:env[k] for k in ['ROS_DOMAIN_ID','IGN_PARTITION','CLINIC_DENSE_DOMAIN','CLINIC_DENSE_PARTITION','CLINIC_RUNTIME_PREPARED']})
    log=(out/'startup.log').open('w')
    p=subprocess.Popen(['ros2','launch',str(Path(__file__).with_name('clinic_visual_launch.py')),'headless:=true'],cwd=root,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
    created=psutil.Process(p.pid).create_time()
    write(out/'owned_world.json',dict(pid=p.pid,created=created,partition=partition,domain=domain,launch='opt-in visual keepout; original Clinic unchanged'))
    try:yield p
    finally:
        try:write(out/'cleanup.json',cleanup_owned_group(p.pid,partition,created))
        finally:log.close()
