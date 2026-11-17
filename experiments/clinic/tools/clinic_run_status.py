"""Bounded log summary: no trajectory/history arrays are printed or loaded."""
import argparse,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--name',required=True);a=p.parse_args()
if not a.name.replace('_','').replace('-','').isalnum():p.error('Invalid name')
state=ROOT/'verification/clinic_runtime'/a.name/'status.json';result={'name':a.name}
if state.exists():
 s=json.loads(state.read_text());result.update(status=s['status'],error=s.get('error'))
f=ROOT/'runs'/a.name/'trace.jsonl'
if f.exists():
 with f.open('rb') as h:
  h.seek(max(0,f.stat().st_size-65536));lines=h.read().splitlines()
 for line in reversed(lines):
  try:
   row=json.loads(line);result.update(last_sim_seconds=row.get('episode_time'),last_phase=row.get('phase'));break
  except (ValueError,UnicodeError):continue
print(json.dumps(result,ensure_ascii=False))
