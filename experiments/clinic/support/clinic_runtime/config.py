"""One profile, one scenario JSON and one Nav2 template for all robot namespaces."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[2]
PROFILE = ROOT / 'config/clinic_runtime/profile.json'

def profile():
    return json.loads(PROFILE.read_text())

def scenario():
    return json.loads((ROOT / profile()['scenario']).read_text())

def nav2_parameters(robot, *, resolve=False):
    """Keep Nav2's upstream <robot_namespace>/RewrittenYaml mechanism."""
    cfg = scenario()
    if robot not in cfg['robots']:
        raise ValueError('Unknown robot namespace: ' + robot)
    text = (ROOT / profile()['nav2_template']).read_text()
    if resolve:
        text = text.replace('<robot_namespace>', '/' + robot)
    params = yaml.safe_load(text)
    x, y, yaw = cfg['robots'][robot]['start']
    params['amcl']['ros__parameters']['initial_pose'] = dict(x=x, y=y, z=0.0, yaw=yaw)
    return params

def prepare(directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    files = {}
    for robot in scenario()['robots']:
        path = directory / (robot + '_nav2.yaml')
        path.write_text(yaml.safe_dump(nav2_parameters(robot), sort_keys=False))
        files[robot] = str(path)
    return files

def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def source_manifest():
    # Runtime helpers and borrowed research modules are snapshotted without edits.
    paths = [PROFILE, ROOT / profile()['nav2_template'], ROOT / profile()['scenario'],
             ROOT / 'clinic_experiment.sh', ROOT / 'launch/clinic_experiment.launch.py']
    paths += list((ROOT / 'support/clinic_runtime').glob('*.py'))
    paths += [ROOT / 'support/clinic_runtime/environment.sh']
    paths += list((ROOT / 'config/clinic_modes').glob('*.json'))
    paths += list((ROOT / 'config/hospital_bed').glob('*'))
    for key in ['static_map','collision_map']:
        info=ROOT/profile()[key];paths.append(info.parent/yaml.safe_load(info.read_text())['image'])
    paths += [ROOT / profile()[key] for key in ['static_map', 'collision_map', 'world']]
    paths += [ROOT / 'tools' / n for n in ['dense_tasks.py', 'dense_solver.py', 'dense_validate.py',
        'run_dense_episode.py', 'run_aligned_episode.py', 'aligned_solver.py', 'aligned_contract.py',
        'clinic_milp_backend.py', 'prefix_solver.py', 'prefix_contract.py', 'bed_contract.py',
        'bed_solver.py', 'bed_initial_solver.py', 'bed_validate.py', 'bed_local_evidence.py',
        'aligned_service_worker.py', 'bed_resources.py', 'bed_keepout.py', 'bed_driver.py',
        'tb4_io.py', 'dense_reference_tf.py',
        'aligned_reference_tf.py', 'aligned_health.py', 'dense_resources.py', 'dense_keepout.py',
        'aligned_resources.py', 'aligned_keepout.py', 'shared_resource.py']]
    paths.append(Path('/home/yhc/kaiti_yolopose_framework/src/kaiti_task_sim/event_protocol.py'))
    return {str(p): sha256(p) for p in sorted(set(paths)) if p.is_file()}
