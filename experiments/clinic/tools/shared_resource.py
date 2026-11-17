#!/usr/bin/env python3
"""FIFO exclusive service-area lease, held through physical exit acknowledgement."""
from pathlib import Path
import json
import math
import yaml
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile,DurabilityPolicy,ReliabilityPolicy
from std_msgs.msg import String

STATE_QOS=QoSProfile(depth=100,durability=DurabilityPolicy.TRANSIENT_LOCAL,reliability=ReliabilityPolicy.RELIABLE)


class Resource(Node):
    def __init__(self):
        super().__init__('clinic_shared_resource')
        self.cfg=yaml.safe_load((Path(__file__).resolve().parents[1]/'config/three_tb4/scenario.yaml').read_text())
        self.states={};self.owner=None;self.queue=[];self.seen={};self.seq=0
        self.pub=self.create_publisher(String,'/clinic_three/resource_state',STATE_QOS)
        self.create_subscription(String,'/clinic_three/resource_request',self.request,10)
        for rid in self.cfg['robots']:
            self.create_subscription(String,f'/{rid}/experiment/robot_state',lambda m,r=rid:self.robot(r,m),10)
        self.emit('idle')
    def now(self):return self.get_clock().now().nanoseconds*1e-9
    def robot(self,rid,msg):self.states[rid]=json.loads(msg.data)
    def emit(self,phase,request=None,reason=None):
        self.seq+=1
        data=dict(seq=self.seq,at=self.now(),phase=phase,resource='shared_service',owner=self.owner['robot'] if self.owner else None,lease_id=self.owner['lease_id'] if self.owner else None,queue=[q['robot'] for q in self.queue],request=request,reason=reason)
        self.pub.publish(String(data=json.dumps(data)));self.get_logger().info(json.dumps(data))
    def grant(self):
        if self.owner is None and self.queue:self.owner=self.queue.pop(0);self.emit('granted',self.owner)
    def request(self,msg):
        req=json.loads(msg.data);rid=req.get('robot');lease=req.get('lease_id');action=req.get('action')
        if rid not in self.cfg['robots'] or not isinstance(lease,str) or not lease:return
        if action=='acquire':
            if lease in self.seen:self.emit('duplicate_request',req);return
            self.seen[lease]=rid;self.queue.append(req);self.emit('queued',req);self.grant()
        elif action=='release':
            if not self.owner or self.owner['lease_id']!=lease or self.owner['robot']!=rid:self.emit('release_denied',req,'not_current_owner');return
            state=self.states.get(rid);target=self.cfg['shared']
            if state is None or self.now()-state['at']>.5 or state['tf_age']>.5 or math.hypot(state['x']-target['x'],state['y']-target['y'])<1.2:
                self.emit('release_denied',req,'owner_not_confirmed_clear');return
            old=self.owner;self.owner=None;self.emit('released',old);self.grant()


if __name__=='__main__':
    rclpy.init();n=Resource()
    try:rclpy.spin(n)
    finally:n.destroy_node();rclpy.shutdown()
