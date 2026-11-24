#!/usr/bin/env python3
"""Read-only native ROS mask/protocol witness; never publishes observations."""
import argparse
import json
from pathlib import Path
import time


def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--timeout',type=float,default=260.)
    a=p.parse_args();a.out.mkdir(parents=True,exist_ok=False)
    import rclpy
    from rclpy.node import Node
    from rclpy.qos import QoSProfile,DurabilityPolicy,ReliabilityPolicy
    from nav_msgs.msg import OccupancyGrid
    from std_msgs.msg import String
    rclpy.init();n=Node('visual_mask_readonly_audit');state={};mask=[None];rows=[]
    qos=QoSProfile(depth=1,durability=DurabilityPolicy.TRANSIENT_LOCAL,reliability=ReliabilityPolicy.RELIABLE)
    def protocol(m):
        nonlocal state
        state=json.loads(m.data)
    def grid(m):mask[0]=m
    subs=[n.create_subscription(String,'/clinic_fall/protocol_state',protocol,qos),n.create_subscription(OccupancyGrid,'/r1/experiment/keepout_mask',grid,qos)]
    begin=time.monotonic();last=None
    try:
        while time.monotonic()-begin<a.timeout:
            rclpy.spin_once(n,timeout_sec=.05)
            e=state.get('event');m=mask[0]
            if not e or m is None:continue
            xy=(e.get('space') or {}).get('event_xy')
            if not xy:continue
            i=int((xy[0]-m.info.origin.position.x)/m.info.resolution);j=int((xy[1]-m.info.origin.position.y)/m.info.resolution)
            if not (0<=i<m.info.width and 0<=j<m.info.height):continue
            item=dict(event_id=e['event_id'],lifecycle=e['lifecycle'],verified=e['verified'],event_xy=xy,
                mask_center_value=int(m.data[j*m.info.width+i]),mask_stamp=m.header.stamp.sec+m.header.stamp.nanosec*1e-9,
                protocol_published_ros_time=state.get('published_ros_time'))
            key=(item['lifecycle'],item['verified'],item['mask_center_value'])
            if key!=last:rows.append(item);last=key
            if e['lifecycle']=='CLOSED':break
        passed=bool(rows) and any(r['lifecycle']=='CLOSED' for r in rows) and all(r['mask_center_value']==0 for r in rows if not r['verified'])
        (a.out/'summary.json').write_text(json.dumps(dict(passed=passed,samples=rows,scope='actual mask cell at registered event center; no claim about all collision constraints'),indent=2))
        print(json.dumps(dict(passed=passed,samples=len(rows))))
        return 0 if passed else 1
    finally:n.destroy_node();rclpy.try_shutdown()


if __name__=='__main__':raise SystemExit(main())
