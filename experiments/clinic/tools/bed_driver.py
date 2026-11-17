"""Scenario-only Gazebo NormalBed insertion/rotation/removal. No planner ETA API."""
import json,subprocess,math
from pathlib import Path
import rclpy
from rclpy.node import Node
from std_msgs.msg import String
from bed_contract import config,ROOT
from shared_resource import STATE_QOS
class Driver(Node):
 def __init__(self):
  super().__init__('physical_bed_driver');self.cfg=config()['bed_experiment'];self.active=None;self.seen=set();self.pub=self.create_publisher(String,'/clinic_bed/physical_truth',STATE_QOS);self.create_subscription(String,'/clinic_bed/scenario_trigger',self.trigger,10);self.create_timer(.1,self.tick)
 def now(self):return self.get_clock().now().nanoseconds*1e-9
 def service(self,name,typ,request):
  # set_pose is idempotent: a timed-out acknowledgement can be retried safely.
  for attempt in range(3 if name=='set_pose' else 1):
   try:r=subprocess.run(['ign','service','-s','/world/clinic_l1_three/'+name,'--reqtype',typ,'--reptype','ignition.msgs.Boolean','--timeout','5000','--req',request],capture_output=True,text=True,timeout=7)
   except subprocess.TimeoutExpired:
    self.get_logger().warning(f'{name} client timeout attempt={attempt+1}');continue
   if r.returncode==0 and 'true' in r.stdout:return
   self.get_logger().warning(f'{name} not acknowledged attempt={attempt+1}: {r.stderr}')
  raise RuntimeError(f'Gazebo {name} acknowledgement failed; physical scenario invalid')
 def emit(self,event,**kw):
  kw['phase_id']=kw.pop('phase',kw.get('phase_id'));self.pub.publish(String(data=json.dumps(dict(at=self.now(),action=event,**kw))))
 def trigger(self,msg):
  phase=json.loads(msg.data)['phase']
  if phase in self.seen:return
  assert self.active is None;self.seen.add(phase);x,y=self.cfg[phase+'_center'];name='experiment_bed_'+phase
  self.service('create','ignition.msgs.EntityFactory',f'sdf_filename: "{ROOT}/config/hospital_bed/bed.sdf" name: "{name}" allow_renaming: false pose: {{position: {{x: {x} y: {y}}} orientation: {{z: 0.70710678118 w: 0.70710678118}}}}')
  self.active=dict(phase=phase,name=name,x=x,y=y,begin=self.now(),hold=self.cfg[phase+'_hold'],last_pose=-10.,last_yaw=math.pi/2);self.emit('inserted',**self.active)
 def tick(self):
  a=self.active
  if not a:return
  age=self.now()-a['begin']
  if age>a['hold']+2.:
   self.service('remove','ignition.msgs.Entity',f'name: "{a["name"]}" type: MODEL');self.emit('removed',**a);self.active=None;return
  if self.now()-a['last_pose']<.2:return
  a['last_pose']=self.now();angle=(math.pi/2)*(max(0.,1-age) if age<1 else min(1.,max(0.,age-a['hold']-1.)))
  if abs(angle-a['last_yaw'])<.01:return # Hold is static: do not flood Gazebo transport.
  self.service('set_pose','ignition.msgs.Pose',f'name: "{a["name"]}" position: {{x: {a["x"]} y: {a["y"]}}} orientation: {{z: {math.sin(angle/2)} w: {math.cos(angle/2)}}}')
  a['last_yaw']=angle
  self.emit('pose',phase_id=a['phase'],name=a['name'],x=a['x'],y=a['y'],yaw=angle)
rclpy.init();n=Driver()
try:rclpy.spin(n)
finally:n.destroy_node();rclpy.shutdown()
