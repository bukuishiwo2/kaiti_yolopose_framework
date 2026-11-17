#!/usr/bin/env python3
"""Reuse single-robot on-site worker; shared target additionally requires its lease."""
from pathlib import Path
import json
import math
import yaml
import rclpy
from std_msgs.msg import String
from shared_resource import STATE_QOS
from service_worker import Worker


class TB4Worker(Worker):
    def __init__(self):
        self.lease={}
        self.target=yaml.safe_load((Path(__file__).resolve().parents[1]/'config/three_tb4/scenario.yaml').read_text())['shared']
        super().__init__();self.rid=self.get_namespace().strip('/')
        self.create_subscription(String,'/clinic_three/resource_state',self.resource,STATE_QOS)
    def resource(self,msg):self.lease=json.loads(msg.data)
    def shared(self,task):return math.hypot(task['target']['x']-self.target['x'],task['target']['y']-self.target['y'])<.1
    def permitted(self,task):return not self.shared(task) or (self.lease.get('owner')==self.rid and self.lease.get('lease_id')==task.get('lease_id'))
    def request(self,msg):
        task=json.loads(msg.data)
        if task.get('command')!='cancel' and not self.permitted(task):self.emit(task,'rejected','shared_lease_missing');return
        super().request(msg)
    def tick(self):
        if self.active and not self.permitted(self.active):self.emit(self.active,'failed','shared_lease_lost');self.active=None
        super().tick()


if __name__=='__main__':
    rclpy.init();node=TB4Worker()
    try:rclpy.spin(node)
    finally:node.destroy_node();rclpy.shutdown()
