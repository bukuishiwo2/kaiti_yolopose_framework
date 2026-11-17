"""Same independent phase-aware monolithic MILP with a third-robot routine job."""
from pathlib import Path
from time import perf_counter
import json,argparse
import aligned_solver as a
from aligned_contract import validate as base_validate
class DenseModel(a.Model):
 def _build(self):
  super()._build()
  for j,t in self.p['tasks'].items():
   if t['kind']=='verify':self.add_cost('s_'+j,self.p['weights']['response']);self.constant-=self.p['weights']['response']*self.p['time']
  if self.p['stage']=='response':
   for j,t in self.p['tasks'].items():
    if t['kind']=='normal':
     for r in self.p['robots']:self.row('third_'+r+j,{a.b.xk(r,j):-1,a.b.xk(r,'E1_monitor'):-1,a.b.xk(r,'E1_pickup'):-1},-1.)
from dense_validate import validate
a.b.Model=DenseModel;a.validate=validate;a.b.validate=validate
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('request',type=Path);p.add_argument('output',type=Path);z=p.parse_args();request=json.loads(z.request.read_text());deadline=perf_counter()+25.;results=[]
 for k,problem in enumerate(request['variants']):
  folder=z.output.parent/f'candidate_{k:02d}';folder.mkdir();(folder/'problem.json').write_text(json.dumps(problem,indent=2));scope=dict(free=list(problem['tasks']) if problem['stage'] in ['verify','response'] else [],freeze_time=False);r=a.ScopedSolver(folder/'solver').solve(problem,scope,'monolithic',deadline);(folder/'result.json').write_text(json.dumps(r,indent=2));results.append(dict(problem=problem,result=r,candidate=k))
  if perf_counter()>=deadline:break
 feasible=[r for r in results if r['result']['status'] in ['OPTIMAL','FEASIBLE_BUDGET']]
 if feasible:
  best=min(feasible,key=lambda r:r['result']['objective']);result=best['result'];result.update(selected_problem=best['problem'],selected_candidate=best['candidate'],candidate_summaries=[dict(candidate=r['candidate'],status=r['result']['status'],objective=r['result'].get('objective')) for r in results],selection_proven=all(r['result']['status'] in ['OPTIMAL','INFEASIBLE'] for r in results) and len(results)==len(request['variants']))
 else:result=dict(status='NO_FEASIBLE_INCUMBENT',candidates=results)
 z.output.write_text(json.dumps(result,indent=2));print(result['status'],result.get('objective'))
