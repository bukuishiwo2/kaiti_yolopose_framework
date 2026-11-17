"""Sequence upstream ros_gz_sim create and controller_manager spawner.

Only readiness/ordering is project-specific. Robot geometry and controller
implementations are installed TurtleBot4/ros2_control components.
"""
import subprocess
import time
import rclpy
from rclpy.node import Node
from rcl_interfaces.srv import GetParameters
from controller_manager_msgs.srv import ListControllers
from rosgraph_msgs.msg import Clock
from .config import ROOT, scenario

def main():
    rclpy.init();node=Node('clinic_runtime_bootstrap');clock=[None]
    node.create_subscription(Clock,'/clock',lambda m:clock.__setitem__(0,m.clock.sec+m.clock.nanosec*1e-9),10)
    def wait(predicate, seconds, reason):
        deadline=time.monotonic()+seconds
        while time.monotonic()<deadline:
            if predicate():return
            rclpy.spin_once(node,timeout_sec=.05)
        raise TimeoutError(reason)
    try:
        wait(lambda:clock[0] is not None,60.,'Gazebo clock unavailable')
        for rid,robot in scenario()['robots'].items():
            client=node.create_client(GetParameters,f'/{rid}/robot_state_publisher/get_parameters')
            wait(client.service_is_ready,60.,rid+' description service')
            req=GetParameters.Request();req.names=['robot_description'];f=client.call_async(req)
            wait(f.done,10.,rid+' description roundtrip')
            if not f.result().values or len(f.result().values[0].string_value)<1000:raise RuntimeError(rid+' incomplete robot description')
            x,y,yaw=robot['start']
            command=['/opt/ros/humble/lib/ros_gz_sim/create','-world','clinic_l1_three','-file',str(ROOT/'config/three_tb4'/f'{rid}.urdf'),'-name',rid,'-allow_renaming','false','-x',str(x),'-y',str(y),'-z','0.01','-Y',str(yaw)]
            subprocess.run(command,check=True,timeout=25.)
            manager=node.create_client(ListControllers,f'/{rid}/controller_manager/list_controllers')
            wait(manager.service_is_ready,60.,rid+' controller manager')
            before=clock[0];wait(lambda:clock[0]-before>=.3,30.,rid+' physics progress')
            subprocess.run(['/opt/ros/humble/lib/controller_manager/spawner','joint_state_broadcaster','diffdrive_controller','-c',f'/{rid}/controller_manager','-n',f'/{rid}','--controller-manager-timeout','60','--switch-timeout','30','--service-call-timeout','45'],check=True,timeout=100.)
            f=manager.call_async(ListControllers.Request());wait(f.done,10.,rid+' controller status')
            active={c.name for c in f.result().controller if c.state=='active'}
            if not {'joint_state_broadcaster','diffdrive_controller'}<=active:raise RuntimeError(rid+' official controllers not active')
            print(rid,'upstream create + ros2_control confirmed',flush=True)
    finally:node.destroy_node();rclpy.try_shutdown()

if __name__=='__main__':main()
