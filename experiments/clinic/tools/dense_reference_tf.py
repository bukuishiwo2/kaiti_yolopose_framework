#!/usr/bin/env python3
"""Ideal-localization reference, reference truth receipt paired with original odometry stamps."""
import math,json
from collections import deque
import rclpy
from rclpy.node import Node
from rclpy.parameter import Parameter
from rclpy.qos import QoSProfile,ReliabilityPolicy,qos_profile_sensor_data
from geometry_msgs.msg import TransformStamped
from tf2_msgs.msg import TFMessage
from nav_msgs.msg import Odometry
from std_msgs.msg import String
class Reference(Node):
 def __init__(self):
  super().__init__('dense_reference_localization',parameter_overrides=[Parameter('use_sim_time',value=True)])
  self.ids=['r1','r2','r3'];self.truth={r:deque(maxlen=100) for r in self.ids};self.odometry={r:deque(maxlen=100) for r in self.ids};self.last={r:-1. for r in self.ids};self.count={r:0 for r in self.ids};self.outputs={r:Node('dense_reference_output',namespace=r) for r in self.ids};self.pubs={r:self.outputs[r].create_publisher(TFMessage,'tf',10) for r in self.ids};self.state=self.create_publisher(String,'/clinic_aligned/localization_condition',10)
  self.create_subscription(TFMessage,'/world/clinic_l1_three/dynamic_pose/info',self.pose,QoSProfile(depth=5,reliability=ReliabilityPolicy.BEST_EFFORT))
  for r in self.ids:self.create_subscription(Odometry,f'/{r}/odom',lambda m,r=r:self.odom(r,m),qos_profile_sensor_data)
 @staticmethod
 def stamp(s):return s.sec+s.nanosec*1e-9
 @staticmethod
 def yaw(q):return math.atan2(2*(q.w*q.z+q.x*q.y),1-2*(q.y*q.y+q.z*q.z))
 def pose(self,msg):
  for t in msg.transforms:
   if t.child_frame_id in self.truth:
    v=t.transform;self.truth[t.child_frame_id].append((self.stamp(t.header.stamp) or self.get_clock().now().nanoseconds*1e-9,v.translation.x,v.translation.y,self.yaw(v.rotation)))
  for r in self.ids:self.pair(r)
 def odom(self,r,m):self.odometry[r].append(m);self.pair(r)
 def pair(self,r):
  if not self.truth[r] or not self.odometry[r]:return
  # Newest mutually available measurement; tolerate callback ordering, never time travel.
  newest=self.truth[r][-1][0];eligible=[m for m in self.odometry[r] if self.last[r]<self.stamp(m.header.stamp)<=newest+.02]
  if not eligible:return
  m=eligible[-1];at=self.stamp(m.header.stamp);v=min(self.truth[r],key=lambda p:abs(p[0]-at))
  if abs(v[0]-at)>.10:return
  o=m.pose.pose;angle=v[3]-self.yaw(o.orientation);c,s=math.cos(angle),math.sin(angle);t=TransformStamped();t.header.stamp=m.header.stamp;t.header.frame_id='map';t.child_frame_id='odom';t.transform.translation.x=v[1]-c*o.position.x+s*o.position.y;t.transform.translation.y=v[2]-s*o.position.x-c*o.position.y;t.transform.rotation.z=math.sin(angle/2);t.transform.rotation.w=math.cos(angle/2);self.pubs[r].publish(TFMessage(transforms=[t]));self.last[r]=at;self.count[r]+=1
  if self.count[r]%50==0:self.state.publish(String(data=json.dumps(dict(condition='gazebo_reference_pose',robot=r,pair_time_difference=abs(v[0]-at),measurement_age=self.get_clock().now().nanoseconds*1e-9-at,note='bridge truth stamps zero: truth receipt time fallback; output keeps original odom stamp; one shared truth subscription; no AMCL claim'))))
if __name__=='__main__':
 rclpy.init();n=Reference()
 try:rclpy.spin(n)
 finally:
  for output in n.outputs.values():output.destroy_node()
  n.destroy_node();rclpy.shutdown()
