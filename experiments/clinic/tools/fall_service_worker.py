#!/usr/bin/env python3
"""Existing physical service worker plus protocol/owner guards and explicit monitor finish."""
import json
import rclpy
from std_msgs.msg import String
from tb4_service_worker import TB4Worker
from shared_resource import STATE_QOS


class FallWorker(TB4Worker):
    def __init__(self):
        self.protocol={};super().__init__()
        self.create_subscription(String,'/clinic_fall/protocol_state',self.protocol_cb,STATE_QOS)
    def protocol_cb(self,msg):self.protocol=json.loads(msg.data)
    def emit(self,task,phase,reason=None):
        data=dict(task_id=task['task_id'],attempt=task['attempt'],phase=phase,at=self.now(),reason=reason,robot=self.get_namespace().strip('/'),protocol_task_id=task.get('protocol_task_id'),task_revision=task.get('task_revision'),role=task.get('role'),plan_revision=task.get('plan_revision'))
        self.responses[task['task_id'],task['attempt']]=data;self.pub.publish(String(data=json.dumps(data)))
    def protocol_ready(self,task,running=False):
        tid=task.get('protocol_task_id')
        if not tid:return True
        if self.now()-self.protocol.get('published_ros_time',-100.)>5.:return False
        t=self.protocol.get('tasks',{}).get(tid)
        if not t or not t['target_valid'] or t['state'] not in (['RUNNING'] if running else ['READY']):return False
        if self.protocol.get('planned_owners',{}).get(tid)!=self.rid:return False
        if t['revision']!=task['task_revision'] or t['attempt']!=task['attempt'] or t['target']['xy']!=[task['target']['x'],task['target']['y']]:return False
        return not t.get('required_owner') or t['required_owner']==self.rid
    def request(self,msg):
        task=json.loads(msg.data)
        if task.get('command')=='finish_monitor':
            if self.active and self.active['task_id']==task['task_id'] and self.active.get('role')=='monitor':self.active['finish_requested']=True
            else:self.emit(task,'rejected','no_matching_monitor')
            return
        if task.get('command')!='cancel' and not self.protocol_ready(task):self.emit(task,'rejected','protocol_guard_not_ready');return
        if task.get('role')=='monitor':task['duration']=10000.;msg=String(data=json.dumps(task))
        super().request(msg)
    def tick(self):
        a=self.active
        if a and a.get('protocol_task_id') and a['started'] is not None:
            # A short transport interval can precede the root's RUNNING update;
            # thereafter physical/protocol health must remain valid.
            if self.now()-a['started']>.5 and not self.protocol_ready(a,True):self.emit(a,'failed','protocol_running_guard_lost');self.active=None;return
        if a and a.get('role')=='monitor' and a.get('finish_requested'):
            deliver=self.protocol.get('tasks',{}).get('E1:deliver',{})
            if deliver.get('state')=='SUCCEEDED' and self.ready(a):self.emit(a,'succeeded');self.active=None;return
        super().tick()


if __name__=='__main__':
    rclpy.init();n=FallWorker()
    try:rclpy.spin(n)
    finally:n.destroy_node();rclpy.shutdown()
