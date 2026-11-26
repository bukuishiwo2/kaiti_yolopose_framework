"""Reuse installed Clinic launch, replace only opt-in visual keepout action."""
from pathlib import Path
import importlib.util
import os
from launch import LaunchDescription
from launch.actions import ExecuteProcess


def generate_launch_description():
    path='/home/yhc/clinic_planning_ws/launch/clinic_experiment.launch.py'
    spec=importlib.util.spec_from_file_location('clinic_base_launch',path)
    base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
    original=base.generate_launch_description();actions=[];replaced=0
    for action in original.entities:
        if isinstance(action,ExecuteProcess):
            cmd=[''.join(getattr(s,'text',str(s)) for s in token) for token in action.cmd]
            if any(str(s).endswith('/tools/bed_keepout.py') for s in cmd):
                actions.append(ExecuteProcess(cmd=['/usr/bin/python3','-u',str(Path(__file__).with_name('clinic_visual_keepout.py')),
                    '--ros-args','-p','use_sim_time:=true'],output='screen'))
                replaced+=1;continue
            if 'support.clinic_runtime.bootstrap' in cmd and os.getenv('CLINIC_PROBE_POSES'):
                actions.append(ExecuteProcess(cmd=['/usr/bin/python3','-u',
                    str(Path(__file__).with_name('clinic_probe_bootstrap.py')),
                    os.environ['CLINIC_PROBE_POSES']],output='screen'))
                continue
        actions.append(action)
    if replaced!=1:raise RuntimeError('expected exactly one original keepout action')
    return LaunchDescription(actions)
