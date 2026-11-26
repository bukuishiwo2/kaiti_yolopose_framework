"""Apply saved Gazebo spawn poses to the existing Clinic bootstrap."""
import json
from pathlib import Path
import sys

from support.clinic_runtime import bootstrap


if __name__ == '__main__':
    poses = json.loads(Path(sys.argv[1]).read_text())
    scenario = bootstrap.scenario()
    if poses.keys() != scenario['robots'].keys():
        raise ValueError('Probe pose namespaces must match Clinic')
    for robot, pose in poses.items():
        scenario['robots'][robot]['start'] = pose
    bootstrap.scenario = lambda: scenario
    bootstrap.main()
