#!/usr/bin/env python3
"""Reuse physical/protocol guards; require correct hospital station lease."""
import json
import rclpy
from fall_service_worker import FallWorker
class HospitalWorker(FallWorker):
 def permitted(self,task):
  resource=task.get('resource')
  if not resource:return True
  lease=self.lease.get('owners',{}).get(resource,{})
  return lease.get('robot')==self.rid and lease.get('lease_id')==task.get('lease_id')
if __name__=='__main__':
 rclpy.init();n=HospitalWorker()
 try:rclpy.spin(n)
 finally:n.destroy_node();rclpy.shutdown()
