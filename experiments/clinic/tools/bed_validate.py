"""Pure initial active-event checks; no ROS or solver dependency."""
from dense_validate import validate as base_validate
def validate(p,plan,scope,claimed=None):
 v=base_validate(p,plan,scope,claimed);j=p['necessary_normal'];v['checks']+=2
 if plan['owners'][j] in [plan['owners']['E1_monitor'],plan['owners']['E1_pickup']]:v['errors'].append(dict(name='third_role',residual=1))
 if plan['finishes']['E1_monitor']<plan['finishes']['E1_deliver']+4.-1e-6:v['errors'].append(dict(name='handover_margin',residual=1))
 v['passed']=not v['errors'];return v
