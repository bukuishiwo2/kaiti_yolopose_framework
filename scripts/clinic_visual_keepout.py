#!/usr/bin/env python3
"""Opt-in original keepout with event-space geometry and explicit closure.

The legacy worker remains unchanged. No model classification or event is
generated here. Unknown/temporarily stale position retains the last obstacle.
"""
import json
from pathlib import Path
import sys
sys.path.insert(0,'/home/yhc/clinic_planning_ws/tools')
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
import rclpy
from bed_keepout import Masks
from kaiti_task_sim.clinic_visual import visual_obstacle


class VisualKeepout(Masks):
    def protocol(self,msg):
        p=json.loads(msg.data)
        self.body,xy=visual_obstacle(p,self.cfg['event']['center'])
        if xy!=self.cfg['event']['center']:
            self.cfg['event']['center']=xy
            self.signature=None  # geometry changes invalidate mask cache
        self.publish()


if __name__=='__main__':
    rclpy.init();n=VisualKeepout()
    try:rclpy.spin(n)
    finally:n.destroy_node();rclpy.try_shutdown()
