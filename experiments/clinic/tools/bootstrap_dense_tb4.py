#!/usr/bin/env python3
"""Parameter roundtrip, model spawn, physics progress and control, one robot at a time."""
from pathlib import Path
import subprocess
import time
import rclpy
from rclpy.node import Node
from rcl_interfaces.srv import GetParameters
from controller_manager_msgs.srv import ListControllers
from rosgraph_msgs.msg import Clock

root=Path(__file__).resolve().parents[1]
rclpy.init();node=Node('three_tb4_bootstrap');stamp=[None]
def on_clock(msg):stamp[0]=msg.clock.sec+msg.clock.nanosec*1e-9
node.create_subscription(Clock,'/clock',on_clock,10)
def wait(condition,seconds):
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        if condition():return True
        rclpy.spin_once(node,timeout_sec=.05)
    return False
try:
    for rid in ['r1','r2','r3']:
        client=node.create_client(GetParameters,f'/{rid}/robot_state_publisher/get_parameters')
        if not wait(client.service_is_ready,120):raise RuntimeError(rid+' description service unavailable')
        req=GetParameters.Request();req.names=['robot_description'];f=client.call_async(req)
        if not wait(f.done,20) or not f.result().values or len(f.result().values[0].string_value)<1000:raise RuntimeError(rid+' full URDF parameter roundtrip failed')
        print(rid,'URDF parameter roundtrip confirmed',flush=True)
        subprocess.run(['/usr/bin/python3',str(root/'tools/spawn_dense_tb4.py'),rid],check=True,timeout=220)
        manager=node.create_client(ListControllers,f'/{rid}/controller_manager/list_controllers')
        if not wait(manager.service_is_ready,90):raise RuntimeError(rid+' controller manager unavailable')
        # Process pending clock callbacks before selecting the baseline.
        wait(lambda:stamp[0] is not None,10);before=stamp[0]
        if not wait(lambda:stamp[0] is not None and before is not None and stamp[0]-before>=.3,90):raise RuntimeError(rid+' physics not advancing after model configuration')
        cmd=['/opt/ros/humble/lib/controller_manager/spawner','joint_state_broadcaster','diffdrive_controller','-c',f'/{rid}/controller_manager','-n',f'/{rid}','--controller-manager-timeout','90','--switch-timeout','60','--service-call-timeout','75']
        subprocess.run(cmd,check=True,timeout=220)
        print(rid,'spawn and official controllers confirmed active',flush=True)
    print('All three official TurtleBot4 pipelines ready.',flush=True)
finally:node.destroy_node();rclpy.shutdown()
