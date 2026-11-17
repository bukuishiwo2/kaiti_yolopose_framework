#!/usr/bin/env python3
import os
import time
import rclpy
from rclpy.node import Node
from controller_manager_msgs.srv import ListControllers
rclpy.init();node=Node('three_gui_readiness');deadline=time.monotonic()+240
clients={r:node.create_client(ListControllers,f'/{r}/controller_manager/list_controllers') for r in ['r1','r2','r3']}
active=set();futures={}
while time.monotonic()<deadline:
    rclpy.spin_once(node,timeout_sec=.1)
    for rid,client in clients.items():
        if rid in active:continue
        if rid in futures and futures[rid].done():
            result=futures.pop(rid).result()
            states={c.name:c.state for c in result.controller} if result else {}
            if all(states.get(k)=='active' for k in ['joint_state_broadcaster','diffdrive_controller']):active.add(rid)
        elif rid not in futures and client.service_is_ready():futures[rid]=client.call_async(ListControllers.Request())
    if len(active)==3:
        node.destroy_node();rclpy.shutdown();os.execvp('ign',['ign','gazebo','--force-version','6','-g','-v','3'])
raise SystemExit('Three complete control pipelines not ready within 240 s; GUI not started')
