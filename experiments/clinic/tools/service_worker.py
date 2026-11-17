#!/usr/bin/env python3
"""Explicit simulated on-site service acknowledgements; no real manipulation."""
import json
import math
import rclpy
from rclpy.node import Node
from rclpy.time import Time
from rclpy.qos import qos_profile_sensor_data
from std_msgs.msg import String
from nav_msgs.msg import Odometry
from tf2_ros import Buffer, TransformListener, TransformException


class Worker(Node):
    def __init__(self):
        super().__init__('clinic_service_worker')
        self.buffer=Buffer();self.listener=TransformListener(self.buffer,self)
        self.pub=self.create_publisher(String,'/clinic_experiment/service_feedback',10)
        self.create_subscription(String,'/clinic_experiment/service_request',self.request,10)
        self.create_subscription(Odometry,'/odom',self.odom_cb,qos_profile_sensor_data)
        self.odom=None;self.odom_at=None;self.active=None;self.requests={};self.responses={}
        self.create_timer(.05,self.tick)

    def now(self):return self.get_clock().now().nanoseconds*1e-9

    def odom_cb(self,msg):self.odom=msg;self.odom_at=self.now()

    def emit(self,task,phase,reason=None):
        data=dict(task_id=task['task_id'],attempt=task['attempt'],phase=phase,at=self.now(),reason=reason)
        self.responses[task['task_id'],task['attempt']]=data
        self.pub.publish(String(data=json.dumps(data)))

    def ready(self,task):
        try:t=self.buffer.lookup_transform('map','base_link',Time())
        except TransformException:return False
        yaw=2*math.atan2(t.transform.rotation.z,t.transform.rotation.w)
        dyaw=math.atan2(math.sin(yaw-task['target']['yaw']),math.cos(yaw-task['target']['yaw']))
        return self.odom is not None and self.now()-self.odom_at<.5 and math.hypot(self.odom.twist.twist.linear.x,self.odom.twist.twist.linear.y)<.04 and abs(self.odom.twist.twist.angular.z)<.06 and math.hypot(t.transform.translation.x-task['target']['x'],t.transform.translation.y-task['target']['y'])<=.20 and abs(dyaw)<=.30 and self.now()-(t.header.stamp.sec+t.header.stamp.nanosec*1e-9)<.5

    def request(self,msg):
        task=json.loads(msg.data);key=task['task_id'],task['attempt']
        if task.get('command')=='cancel':
            if self.active and (self.active['task_id'],self.active['attempt'])==key:self.active=None
            self.emit(task,'cancelled');return
        if key in self.requests:
            if key in self.responses:self.pub.publish(String(data=json.dumps(self.responses[key])))
            return
        self.requests[key]=task
        if self.active:self.emit(task,'rejected','worker_busy');return
        if task.get('fault')=='drop_start_ack':
            self.emit(task,'fault_injected','drop_start_ack_no_service_execution');return
        if not self.ready(task):self.emit(task,'rejected','arrival_guard_failed');return
        self.active=dict(task,requested=self.now(),started=None)

    def tick(self):
        a=self.active
        if not a:return
        if not self.ready(a):self.emit(a,'failed','service_guard_lost');self.active=None;return
        if a['started'] is None and self.now()-a['requested']>=.25:
            a['started']=self.now();self.emit(a,'started')
        elif a['started'] is not None and self.now()-a['started']>=a['duration']:
            self.emit(a,'succeeded');self.active=None


if __name__=='__main__':
    rclpy.init();node=Worker()
    try:rclpy.spin(node)
    finally:node.destroy_node();rclpy.shutdown()
