#!/usr/bin/env python3
"""Explicit ideal-localization experimental condition, not an AMCL result."""
import math,json
from collections import deque
import rclpy
from rclpy.node import Node
from rclpy.parameter import Parameter
from rclpy.qos import qos_profile_sensor_data
from geometry_msgs.msg import TransformStamped
from tf2_msgs.msg import TFMessage
from nav_msgs.msg import Odometry
from std_msgs.msg import String
class Reference(Node):
 def __init__(self,rid):
  super().__init__('aligned_reference_localization',namespace=rid,parameter_overrides=[Parameter('use_sim_time',value=True)]);self.truth={r:deque(maxlen=200) for r in [rid]};self.counts={r:0 for r in self.truth};self.pubs={r:self.create_publisher(TFMessage,f'/{r}/tf',100) for r in self.truth};self.state=self.create_publisher(String,'/clinic_aligned/localization_condition',10)
  self.create_subscription(TFMessage,'/world/clinic_l1_three/dynamic_pose/info',self.pose,100)
  for rid in self.truth:self.create_subscription(Odometry,f'/{rid}/odom',lambda m,r=rid:self.odom(r,m),qos_profile_sensor_data)
 def yaw(self,q):return math.atan2(2*(q.w*q.z+q.x*q.y),1-2*(q.y*q.y+q.z*q.z))
 def stamp(self,s):return s.sec+s.nanosec*1e-9
 def pose(self,msg):
  for t in msg.transforms:
   if t.child_frame_id in self.truth:
    at=self.stamp(t.header.stamp) or self.get_clock().now().nanoseconds*1e-9;v=t.transform;self.truth[t.child_frame_id].append((at,v.translation.x,v.translation.y,self.yaw(v.rotation)))
 def odom(self,rid,msg):
  if not self.truth[rid]:return
  at=self.stamp(msg.header.stamp);v=min(self.truth[rid],key=lambda p:abs(p[0]-at))
  if abs(v[0]-at)>.10:return
  o=msg.pose.pose;angle=v[3]-self.yaw(o.orientation);c,s=math.cos(angle),math.sin(angle);t=TransformStamped();t.header.stamp=msg.header.stamp;t.header.frame_id='map';t.child_frame_id='odom';t.transform.translation.x=v[1]-c*o.position.x+s*o.position.y;t.transform.translation.y=v[2]-s*o.position.x-c*o.position.y;t.transform.rotation.z=math.sin(angle/2);t.transform.rotation.w=math.cos(angle/2);self.pubs[rid].publish(TFMessage(transforms=[t]));self.counts[rid]+=1
  if self.counts[rid]%100==0:self.state.publish(String(data=json.dumps(dict(condition='gazebo_reference_pose',robot=rid,messages=self.counts[rid],pair_time_difference=abs(v[0]-at),note='AMCL tf broadcast disabled; physics and live odometry remain active'))))
if __name__=='__main__':
 rclpy.init();nodes=[Reference(r) for r in ['r1','r2','r3']];executor=rclpy.executors.SingleThreadedExecutor()
 for n in nodes:executor.add_node(n)
 try:executor.spin()
 finally:
  for n in nodes:n.destroy_node()
  if rclpy.ok():rclpy.shutdown()
