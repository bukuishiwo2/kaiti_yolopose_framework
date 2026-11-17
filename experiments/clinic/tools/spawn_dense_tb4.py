#!/usr/bin/env python3
"""Wait for the actual world, then use a bounded EntityFactory request once."""
import math
import subprocess
import sys
import time
from pathlib import Path
import yaml

root=Path(__file__).resolve().parents[1];rid=sys.argv[1]
cfg=yaml.safe_load((root/'config/hospital_dense/scenario.yaml').read_text())['robots'][rid]
deadline=time.monotonic()+150
while time.monotonic()<deadline:
    try:
        p=subprocess.run(['ign','service','-s','/gazebo/worlds','--reqtype','ignition.msgs.Empty','--reptype','ignition.msgs.StringMsg_V','--timeout','1000','--req',''],capture_output=True,text=True,timeout=3)
        if p.returncode==0 and 'data: "clinic_l1_three"' in p.stdout:break
    except subprocess.TimeoutExpired:pass
    time.sleep(.5)
else:raise SystemExit(f'{rid}: world readiness timed out, no spawn requested')
x,y,yaw=cfg['start']
req=f'sdf_filename: "{root}/config/three_tb4/{rid}.urdf" name: "{rid}" allow_renaming: false pose: {{ position: {{x: {x} y: {y} z: 0.01}} orientation: {{z: {math.sin(yaw/2)} w: {math.cos(yaw/2)}}} }}'
p=subprocess.run(['ign','service','-s','/world/clinic_l1_three/create','--reqtype','ignition.msgs.EntityFactory','--reptype','ignition.msgs.Boolean','--timeout','60000','--req',req],capture_output=True,text=True,timeout=65)
print(rid,'spawn response',p.returncode,p.stdout,p.stderr,flush=True)
if p.returncode or 'data: true' not in p.stdout:raise SystemExit('No confirmed creation; do not blindly retry an unknown request')
