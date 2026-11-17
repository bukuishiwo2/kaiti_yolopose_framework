"""Initial active-event schedule: reuse MILP, add whole known normal backlog."""
import argparse,json
from pathlib import Path
from time import perf_counter
import aligned_solver as a
from dense_validate import validate as base_validate
class Model(a.Model):
 def _build(self):
  super()._build();j=self.p['necessary_normal']
  for r in self.p['robots']:self.row('third_'+r,{a.b.xk(r,j):-1,a.b.xk(r,'E1_monitor'):-1,a.b.xk(r,'E1_pickup'):-1},-1.)
  self.row('actual_handover_margin',{'f_E1_monitor':1,'s_E1_deliver':-1},self.p['tasks']['E1_deliver']['duration']+4.)
from bed_validate import validate
a.b.Model=Model;a.b.validate=validate;a.validate=validate
if __name__=='__main__':
 z=argparse.ArgumentParser();z.add_argument('input',type=Path);z.add_argument('output',type=Path);args=z.parse_args();req=json.loads(args.input.read_text());results=[];deadline=perf_counter()+25.
 for i,p in enumerate(req['variants']):
  q=a.ScopedSolver(args.output.parent/f'candidate_{i}').solve(p,dict(free=['E1_monitor','E1_pickup','E1_deliver',p['necessary_normal']],freeze_time=False),'monolithic',deadline);results.append((p,q))
  if perf_counter()>deadline:break
 feasible=[(p,q) for p,q in results if q['status'] in ['OPTIMAL','FEASIBLE_BUDGET']]
 if feasible:
  p,q=min(feasible,key=lambda x:x[1]['objective']);q.update(selected_problem=p,candidate_summaries=[dict(job=p['necessary_normal'],status=q['status'],objective=q.get('objective')) for p,q in results]);args.output.write_text(json.dumps(q,indent=2))
 else:args.output.write_text(json.dumps(dict(status='NO_FEASIBLE_INCUMBENT',attempts=results),indent=2))
