#!/usr/bin/env python3
"""FIFO on-site resource leases, release only after associated job and physical exit."""
import json,math
from pathlib import Path
import rclpy
from rclpy.node import Node
from std_msgs.msg import String
from shared_resource import STATE_QOS
ROOT=Path(__file__).resolve().parents[1]
class Resources(Node):
 def __init__(self):
  super().__init__('hospital_resource_manager');self.cfg=json.loads((ROOT/'config/hospital_aligned/scenario.json').read_text());self.blocks=[];self.states={};self.owners={};self.queues={s:[] for s in self.cfg['station_points']};self.seen=set();self.seq=0;self.pub=self.create_publisher(String,'/clinic_three/resource_state',STATE_QOS);self.create_subscription(String,'/clinic_three/resource_request',self.request,10)
  for rid in self.cfg['robots']:self.create_subscription(String,f'/{rid}/experiment/robot_state',lambda m,r=rid:self.robot(r,m),10)
  self.create_timer(.1,self.grant);self.emit('idle')
 def now(self):return self.get_clock().now().nanoseconds*1e-9
 def robot(self,rid,msg):self.states[rid]=json.loads(msg.data)
 def emit(self,phase,request=None,reason=None):
  self.seq+=1;data=dict(seq=self.seq,at=self.now(),phase=phase,owners=self.owners,queue=self.queues,request=request,reason=reason,blocked=self.blocks);self.pub.publish(String(data=json.dumps(data)))
 def clear(self,resource,excluded,distance):
  target=self.cfg['anchors'][resource]
  for rid in self.cfg['robots']:
   if rid==excluded:continue
   s=self.states.get(rid)
   if not s or self.now()-s['at']>.5 or s['tf_age']>.5 or math.hypot(s['x']-target[0],s['y']-target[1])<distance:return False
  return True
 def grant(self):
  for res,q in self.queues.items():
   if res not in self.owners and q and not any(b['resource']==res and self.now()<b['finish'] and max(self.now(),b['start'])<self.now()+q[0].get('expected_hold',0.) for b in self.blocks) and self.clear(res,q[0]['robot'],1.05):self.owners[res]=q.pop(0);self.emit('granted',self.owners[res])
 def request(self,msg):
  req=json.loads(msg.data);res=req.get('resource');rid=req.get('robot');lease=req.get('lease_id')
  if req.get('action')=='block':
   self.blocks.append(dict(resource=res,start=req['start'],finish=req['finish'],change_id=req['change_id']));self.emit('availability_changed',req);return
  if res not in self.queues or rid not in self.cfg['robots'] or not lease:return
  if req['action']=='acquire':
   state=self.states.get(rid);anchor=req.get('entry_anchor');target=self.cfg['anchors'].get(anchor)
   if not state or self.now()-state['at']>.5 or not target or math.hypot(state['x']-target[0],state['y']-target[1])>.25:self.emit('acquire_denied',req,'not_at_entry_gate');return
   if lease in self.seen:return
   self.seen.add(lease);self.queues[res].append(req);self.emit('queued',req);self.grant()
  elif req['action']=='release':
   owner=self.owners.get(res);state=self.states.get(rid);target=self.cfg['anchors'][res]
   if not owner or owner['lease_id']!=lease or owner['robot']!=rid:self.emit('release_denied',req,'owner_mismatch');return
   if not state or self.now()-state['at']>.5 or state['tf_age']>.5 or math.hypot(state['x']-target[0],state['y']-target[1])<1.5:self.emit('release_denied',req,'owner_not_clear');return
   target=self.cfg['anchors'][self.cfg['resource_phases'][res]['clear']]
   if math.hypot(state['x']-target[0],state['y']-target[1])>.25:self.emit('release_denied',req,'not_at_clear_gate');return
   del self.owners[res];self.emit('released',req);self.grant()
if __name__=='__main__':
 rclpy.init();n=Resources()
 try:rclpy.spin(n)
 finally:n.destroy_node();rclpy.shutdown()
