#!/usr/bin/env python3
"""Namespaced I/O adapters, not a custom robot controller or ground-truth localizer."""
import json
import math
import rclpy
from rclpy.node import Node
from rclpy.time import Time
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import LaserScan
from nav_msgs.msg import Odometry
from geometry_msgs.msg import Twist
from std_msgs.msg import String
from tf2_ros import Buffer, TransformListener, TransformException


class IO(Node):
    def __init__(self):
        super().__init__('experiment_io')
        self.rid=self.get_namespace().strip('/')
        self.scan_pub=self.create_publisher(LaserScan,'scan',qos_profile_sensor_data)
        self.cmd_pub=self.create_publisher(Twist,'diffdrive_controller/cmd_vel_unstamped',10)
        self.state_pub=self.create_publisher(String,'experiment/robot_state',10)
        self.create_subscription(LaserScan,'scan_raw',self.scan,qos_profile_sensor_data)
        self.create_subscription(Twist,'cmd_vel',self.cmd_pub.publish,10)
        self.create_subscription(Odometry,'odom',self.odom_cb,qos_profile_sensor_data)
        self.buffer=Buffer();self.listener=TransformListener(self.buffer,self)
        self.odom=None;self.odom_at=None;self.create_timer(.1,self.state)
    def now(self):return self.get_clock().now().nanoseconds*1e-9
    def scan(self,msg):msg.header.frame_id='rplidar_link';self.scan_pub.publish(msg)
    def odom_cb(self,msg):self.odom=msg;self.odom_at=self.now()
    def state(self):
        if self.odom is None:return
        try:t=self.buffer.lookup_transform('map','base_link',Time())
        except TransformException:return
        q=t.transform.rotation
        self.state_pub.publish(String(data=json.dumps(dict(robot=self.rid,at=self.now(),x=t.transform.translation.x,y=t.transform.translation.y,yaw=math.atan2(2*(q.w*q.z+q.x*q.y),1-2*(q.y*q.y+q.z*q.z)),speed=math.hypot(self.odom.twist.twist.linear.x,self.odom.twist.twist.linear.y),angular_speed=abs(self.odom.twist.twist.angular.z),tf_age=self.now()-(t.header.stamp.sec+t.header.stamp.nanosec*1e-9),odom_age=self.now()-self.odom_at))))


if __name__=='__main__':
    rclpy.init();node=IO()
    try:rclpy.spin(node)
    finally:node.destroy_node();rclpy.shutdown()
