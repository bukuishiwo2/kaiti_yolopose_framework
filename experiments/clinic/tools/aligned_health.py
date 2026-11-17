#!/usr/bin/env python3
"""Independent execution hold acknowledgment/odometry feedback, a controlled delay."""
import json,math
import rclpy
from rclpy.node import Node
from std_msgs.msg import String
from nav_msgs.msg import Odometry
from rclpy.qos import qos_profile_sensor_data
from shared_resource import STATE_QOS
class Health(Node):
 def __init__(self):
  super().__init__('aligned_execution_health');self.holds={};self.odom={};self.pub=self.create_publisher(String,'/clinic_aligned/health',STATE_QOS);self.create_subscription(String,'/clinic_aligned/hold_request',self.request,10)
  for rid in ['r1','r2','r3']:self.create_subscription(Odometry,f'/{rid}/odom',lambda m,r=rid:self.odom.update({r:m}),qos_profile_sensor_data)
  self.create_timer(.1,self.tick)
 def request(self,m):
  p=json.loads(m.data);self.holds[p['robot']]=p;self.tick()
 def tick(self):
  now=self.get_clock().now().nanoseconds*1e-9;states={}
  for rid,p in self.holds.items():
   v=self.odom.get(rid);speed=math.hypot(v.twist.twist.linear.x,v.twist.twist.linear.y) if v else None;states[rid]=dict(change_id=p['change_id'],until=p['until'],active=now<p['until'],speed=speed,stopped=speed is not None and speed<.04 and abs(v.twist.twist.angular.z)<.06)
  self.pub.publish(String(data=json.dumps(dict(at=now,robots=states))))
if __name__=='__main__':
 rclpy.init();n=Health()
 try:rclpy.spin(n)
 finally:n.destroy_node();rclpy.shutdown()
