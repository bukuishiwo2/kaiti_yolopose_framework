#!/usr/bin/env python3
"""Hospital service guards with explicit protocol-reception acknowledgment."""
import json
import rclpy
from std_msgs.msg import String
from hospital_service_worker import HospitalWorker
from shared_resource import STATE_QOS
class AlignedWorker(HospitalWorker):
 def __init__(self):
  super().__init__();self.ack_pub=self.create_publisher(String,'experiment/protocol_ack',STATE_QOS)
 def protocol_cb(self,msg):
  super().protocol_cb(msg);p=self.protocol
  tasks={tid:dict(state=t['state'],revision=t['revision'],attempt=t['attempt'],owner=p.get('planned_owners',{}).get(tid)) for tid,t in p.get('tasks',{}).items()}
  self.ack_pub.publish(String(data=json.dumps(dict(run_id=p.get('run_id'),received_at=self.now(),tasks=tasks))))
if __name__=='__main__':
 rclpy.init();n=AlignedWorker()
 try:rclpy.spin(n)
 finally:n.destroy_node();rclpy.shutdown()
