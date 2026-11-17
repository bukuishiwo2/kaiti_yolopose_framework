"""Pure checks shared by the independent worker, executor and offline auditor."""
from aligned_contract import validate as base_validate
def validate(p,plan,scope,claimed=None):
 v=base_validate(p,plan,scope,None);extra=p['weights']['response']*sum(plan['starts'][j]-p['time'] for j,t in p['tasks'].items() if t['kind']=='verify');v['objective_parts']['verify_response']=extra
 if claimed is not None:
  v['checks']+=1;residual=abs(sum(v['objective_parts'].values())-claimed)
  if residual>1e-5:v['errors'].append(dict(name='dense_objective',residual=residual))
 if p['stage']=='response':
  for j,t in p['tasks'].items():
   if t['kind']=='normal':
    v['checks']+=1
    if plan['owners'][j] in [plan['owners']['E1_monitor'],plan['owners']['E1_pickup']]:v['errors'].append(dict(name='third_'+j,residual=1.))
 v['passed']=not v['errors'];return v
