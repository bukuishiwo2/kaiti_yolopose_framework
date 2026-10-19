#!/usr/bin/env python3
"""Robot-local immutable baseline and recovery verification. Never drives motors.

No live experiment switch is implemented here: original files remain untouched.
Restore refuses if something else changed them, instead of overwriting user work.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

BASE = Path('/home/duct/pose3d_motion_experiment/baseline_20261019')
TARGETS = [
    '/etc/systemd/system/robot-start.service',
    '/data/ductcleanrob/scripts/start-robot.sh',
    '/data/ductcleanrob/install/motor_driver/lib/motor_driver/M0601C_Motor',
    '/data/ductcleanrob/install/motor_driver/share/motor_driver/param/ductcleanrob.yaml',
    '/data/ductcleanrob/install/motor_driver/share/motor_driver/launch/base_robot.launch.py',
    '/data/ductcleanrob/install/motor_driver/share/motor_driver/launch/motor_driver.launch.py',
    '/data/ductcleanrob/src/motor_driver/src/M0601C_Motor/wheelmotor.cpp',
    '/data/ductcleanrob/src/motor_driver/include/motor_driver/M0601C/wheelmotor.h',
]


def digest(path):
    result = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(chunk)
    return result.hexdigest()


def command(*args):
    return subprocess.run(args, capture_output=True, text=True, check=True).stdout


def snapshot():
    # Never silently replace an earlier baseline with experimental state.
    if BASE.exists():
        raise RuntimeError(f'Baseline already exists: {BASE}; run verify')
    contents = command('systemctl', 'cat', 'robot-start.service')
    if 'pose3d-motion' in contents or 'motion_experiment' in contents:
        raise RuntimeError('Refusing experimental state as original baseline')
    for name in TARGETS:
        if not Path(name).is_file():
            raise RuntimeError(f'Missing baseline input: {name}')
    BASE.mkdir(parents=True)
    records = {}
    for index, name in enumerate(TARGETS):
        path = Path(name)
        saved = BASE / f'{index:02d}_{path.name}'
        shutil.copy2(path, saved)
        records[name] = {'sha256': digest(path), 'copy': saved.name}
    (BASE / 'robot-start.systemctl.txt').write_text(contents, encoding='utf-8')
    record = {'files': records, 'effective_service_sha256': hashlib.sha256(contents.encode()).hexdigest(),
              'hardware_mode_changed': False, 'commands_sent': 0}
    (BASE / 'manifest.json').write_text(json.dumps(record, indent=2), encoding='utf-8')
    return verify()


def verify():
    manifest = json.loads((BASE / 'manifest.json').read_text(encoding='utf-8'))
    differences = []
    for name, record in manifest['files'].items():
        if digest(BASE / record['copy']) != record['sha256']:
            differences.append('backup_corrupt:' + name)
        if not Path(name).is_file() or digest(Path(name)) != record['sha256']:
            differences.append('original_changed:' + name)
    service = command('systemctl', 'cat', 'robot-start.service')
    if hashlib.sha256(service.encode()).hexdigest() != manifest['effective_service_sha256']:
        differences.append('effective_robot_start_changed')
    result = {'baseline': str(BASE), 'original_unchanged': not differences,
              'differences': differences, 'checked_files': len(manifest['files'])}
    if differences:
        raise RuntimeError(json.dumps(result))
    return result


def restore():
    # Shadow-only version: no motor switch exists. Stop only its own observer.
    subprocess.run(['systemctl', '--user', 'stop', 'pose3d-motion-shadow.service'], check=True)
    return {'shadow_stopped': True, 'motor_service_restarted': False, **verify()}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['snapshot', 'verify', 'restore'])
    args = parser.parse_args()
    print(json.dumps(globals()[args.action](), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
