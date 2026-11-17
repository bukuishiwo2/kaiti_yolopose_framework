#!/usr/bin/env python3
"""Shared hospital execution masks: station leases and scripted event body."""
import json,math
from pathlib import Path
import numpy as np
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile,DurabilityPolicy,ReliabilityPolicy
from std_msgs.msg import String
from nav_msgs.msg import OccupancyGrid
from nav2_msgs.msg import CostmapFilterInfo
ROOT=Path(__file__).resolve().parents[1];QOS=QoSProfile(depth=1,durability=DurabilityPolicy.TRANSIENT_LOCAL,reliability=ReliabilityPolicy.RELIABLE)
class Masks(Node):
 def __init__(self):
  super().__init__('hospital_keepout');self.cfg=json.loads((ROOT/'config/hospital_dense/scenario.json').read_text());self.peers={};self.owners={};self.blocks=[];self.body=False;self.signature=None;self.pubs={};yy,xx=np.indices((1000,1200));self.x=(xx+.5)*.05;self.y=(yy+.5)*.05-50.
  for rid in self.cfg['robots']:self.pubs[rid]=(self.create_publisher(CostmapFilterInfo,f'/{rid}/experiment/keepout_info',QOS),self.create_publisher(OccupancyGrid,f'/{rid}/experiment/keepout_mask',QOS))
  self.create_subscription(String,'/clinic_dense/execution_state',self.execution,QOS);self.create_subscription(String,'/clinic_three/resource_state',self.resource,10);self.create_subscription(String,'/clinic_fall/protocol_state',self.protocol,QOS);self.create_timer(.2,self.publish);self.publish()
 def execution(self,m):self.peers=json.loads(m.data);self.publish()
 def resource(self,m):p=json.loads(m.data);self.owners=p['owners'];self.blocks=p.get('blocked',[]);self.publish()
 def protocol(self,m):
  p=json.loads(m.data);e=p.get('event');self.body=bool(e and e.get('lifecycle')!='COMPLETED');self.publish()
 def publish(self):
  active=[b['resource'] for b in self.blocks if b['start']<=self.get_clock().now().nanoseconds*1e-9<b['finish']]
  signature=json.dumps([active,self.body,{k:v['robot'] for k,v in self.owners.items()},{r:p for r,p in self.peers.items() if p['stationary']}],sort_keys=True)
  if signature==self.signature:return
  self.signature=signature
  body=np.zeros((1000,1200),dtype=bool)
  if self.body:
   e=self.cfg['event'];cx,cy=e['center'];a=e['body_yaw'];u=(self.x-cx)*math.cos(a)+(self.y-cy)*math.sin(a);v=-(self.x-cx)*math.sin(a)+(self.y-cy)*math.cos(a);body=(abs(u)<=e['body_length']/2+.55)&(abs(v)<=e['body_width']/2+.55)
  for rid,(ip,mp) in self.pubs.items():
   lo,hi,bottom,top=self.cfg['execution_roi'];inset=self.cfg['roi_center_inset_m'];blocked=body | (self.x<lo+inset) | (self.x>hi-inset) | (self.y<bottom+inset) | (self.y>top-inset)
   for res in active:
    x,y,_=self.cfg['anchors'][res];blocked |= np.hypot(self.x-x,self.y-y)<.80
   for res,lease in self.owners.items():
    if lease['robot']!=rid:
     x,y,_=self.cfg['anchors'][res];blocked |= np.hypot(self.x-x,self.y-y)<.80
   for peer,p in self.peers.items():
    if peer!=rid and p['stationary']:blocked |= np.hypot(self.x-p['x'],self.y-p['y'])<.5
   m=OccupancyGrid();m.header.frame_id='map';m.header.stamp=self.get_clock().now().to_msg();m.info.resolution=.05;m.info.width=1200;m.info.height=1000;m.info.origin.position.y=-50.;m.info.origin.orientation.w=1.;m.data=(blocked.astype(np.int8)*100).ravel().tolist();i=CostmapFilterInfo();i.header=m.header;i.type=0;i.base=0.;i.multiplier=1.;i.filter_mask_topic=f'/{rid}/experiment/keepout_mask';mp.publish(m);ip.publish(i)
  self.get_logger().info('HOSPITAL_MASK '+signature)
if __name__=='__main__':
 rclpy.init();n=Masks()
 try:rclpy.spin(n)
 finally:n.destroy_node();rclpy.shutdown()
