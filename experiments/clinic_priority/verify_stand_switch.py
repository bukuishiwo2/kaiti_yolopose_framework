"""Trace a controlled A-area placement through site selection, MILP and verify ACK."""
import argparse
from copy import deepcopy
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time

from factorial import READ, WRITE, WORKSPACE, benchmark
from qualify_spatial_stand import ORIGIN, ROBOT, SOURCE, execution_checks, points, screen_passed
from kaiti_task_sim.clinic_visual import compile_tasks, execution_fence, execution_tokens, registered_space
from kaiti_task_sim.event_protocol import EventTaskProtocol


JOB = 'E1_verify'
TASK = 'E1:verify'
CONDITIONS = ('original', 'switch', 'blocked')


def select(rows):
    return next((row for row in rows if not row['occupied'] and row['passed']), None)


def observation(protocol, at, center, selected, label, response_points=None):
    service_points = dict(response_points or {})
    if selected:
        service_points['verify'] = selected['pose'][:2]
    msg = dict(schema='event-task/v1', kind='observation', event_id='E1',
               message_id=label, at=at, source_at=at, status='confirmed',
               space=dict(valid=True, frame='map', event_xy=center,
                          provenance='controlled_gazebo_body_mask',
                          service_points=service_points))
    protocol.apply(msg)
    return msg


def run(out, domain, response=False, via_v3=False, after_patrol=False):
    sys.path[:0] = [str(WORKSPACE), str(WORKSPACE/'tools')]
    import dense_tasks as dt
    from dense_validate import validate
    from clinic_visual_world import visual_world
    from nav2_msgs.action import ComputePathToPose
    from nav_msgs.msg import OccupancyGrid
    import rclpy
    from rclpy.executors import SingleThreadedExecutor
    from std_msgs.msg import String
    from support.clinic_runtime import episode as bed
    from support.clinic_runtime.__main__ import require_static, runtime_gate
    from support.clinic_runtime.config import prepare
    from bed_keepout import QOS
    import yaml

    bed.configure_research_backend()
    cfg = dt.config()
    candidates = points(cfg['anchors'])[:2]
    baseline, alternative = candidates
    history = READ(SOURCE/'result.json')['completed']
    centers = dict(original=cfg['event']['center'], switch=[15.45,-13.10], blocked=[15.45,-13.95])
    expected_masks = dict(original=[False,False], switch=[True,False], blocked=[True,True])
    poses = {r:[history[j]['ground_truth'][k] for k in ('x','y','yaw')]
             for r,j in (('r1','C0_r1_W2'),('r2','C0_r2_W2'),('r3','C0_r3_W1'))}
    anchors = {'r1':ORIGIN,'r2':'CPW2','r3':'CTLR3'}
    if response:
        from stand_switch_response import fixture
        prior = fixture(cfg)
        poses.update(prior['poses'])
        anchors.update(prior['anchors'])
    out.mkdir(parents=True,exist_ok=False)
    WRITE(out/'poses.json',poses)
    WRITE(out/'fixture.json',dict(centers=centers,candidates=candidates,poses=poses,
        mask_expectations=expected_masks, source=SOURCE.name, source_sha256=benchmark.sha(SOURCE/'result.json'),
        eligible={'E1_verify':[ROBOT]}, verdict='controlled positive after actual verify worker ACK',
        representative='switch', method='ordered unoccupied Nav2-screened candidates from prior execution evidence',
        response=prior if response else None, monitor_approach='V3' if via_v3 else 'direct',
        monitor_after_patrol=after_patrol))
    require_static(out)
    for robot,path in prepare(out/'prepared').items():
        path = Path(path)
        params = yaml.safe_load(path.read_text())
        x,y,yaw = poses[robot]
        params['amcl']['ros__parameters']['initial_pose'] = dict(x=x,y=y,z=0.,yaw=yaw)
        path.write_text(yaml.safe_dump(params,sort_keys=False))
    os.environ.update(CLINIC_PROBE_POSES=str(out/'poses.json'), CLINIC_CONTROLLED_BODY='1')
    result = dict(conditions=[], execution=None, failure=None, candidates=candidates, origin=poses[ROBOT])
    with visual_world(out,domain,out/'prepared'):
        try:
            runtime_gate(out,120.)
        except RuntimeError:
            checks=READ(out/'runtime_preflight.json')['robots']
            failed=[k for entries in checks.values() for k,v in entries.items() if not v]
            if not failed or any(not k.startswith('live:') for k in failed):
                raise
            retry=out/'runtime_recheck'
            retry.mkdir()
            runtime_gate(retry,60.)
        rclpy.init()

        class Episode(bed.Episode):
            def publish(self):
                msg = self.protocol.snapshot()
                msg.update(controlled_body_fixture=True, planned_owners=self.planned_owners,
                           published_ros_time=self.now(), run_id=self.run_id)
                self.proto_pub.publish(String(data=json.dumps(msg)))

        opts = argparse.Namespace(reference=None,arrival='pose_handoff',parking='dense_cycle',
               localization='reference',mode='event',policy='fixed',changes='none')
        c = Episode(out,opts)
        executor = SingleThreadedExecutor()
        executor.add_node(c)
        for rid, anchor in anchors.items():
            peer = bed.Bot(rid,c)
            peer.anchor=anchor
            c.peers[rid]=peer
            executor.add_node(peer)
        b = c.peers[ROBOT]
        masks = []
        c.create_subscription(OccupancyGrid,'/r1/experiment/keepout_mask',lambda msg:masks.append(msg),QOS)
        last = -1.

        def wait(predicate, seconds, move=False):
            nonlocal last
            deadline=time.monotonic()+seconds
            while not predicate():
                if c.failed:
                    raise RuntimeError(c.failed)
                if time.monotonic()>deadline:
                    raise TimeoutError('Station switch wait exceeded')
                executor.spin_once(timeout_sec=.02)
                if c.epoch is None or c.elapsed()-last<.05:
                    continue
                last=c.elapsed()
                c.update_motion()
                c.update_neck()
                if move:
                    for peer in c.peers.values():
                        peer.step()
                    c.publish()

        def mask_values(msg, positions):
            info=msg.info
            return [msg.data[math.floor((y-info.origin.position.y)/info.resolution)*info.width
                             +math.floor((x-info.origin.position.x)/info.resolution)] for x,y in positions]

        def apply_mask(label):
            before=len(masks)
            observation(c.protocol, c.elapsed(),centers[label],None,f'mask:{label}:{before}')
            c.publish()
            coords=[p['pose'][:2] for p in candidates]
            wait(lambda:len(masks)>before and
                 [v==100 for v in mask_values(masks[-1],coords)]==expected_masks[label] and
                 mask_values(masks[-1],[centers[label]])==[100], 15.)
            measured=mask_values(masks[-1],coords)
            end=c.elapsed()+2.
            wait(lambda:c.elapsed()>=end,12.)
            return measured

        def query(candidate, occupied, peer=b, source=None):
            goal=ComputePathToPose.Goal()
            goal.use_start=source is not None
            goal.planner_id='GridBased'
            goal.goal.header.frame_id='map'
            goal.goal.header.stamp=peer.get_clock().now().to_msg()
            if source:
                x0,y0,yaw0=source
                goal.start.header=goal.goal.header
                goal.start.pose.position.x,goal.start.pose.position.y=x0,y0
                goal.start.pose.orientation.z,goal.start.pose.orientation.w=math.sin(yaw0/2),math.cos(yaw0/2)
            x,y,yaw=candidate['pose']
            goal.goal.pose.position.x,goal.goal.pose.position.y=x,y
            goal.goal.pose.orientation.z,goal.goal.pose.orientation.w=math.sin(yaw/2),math.cos(yaw/2)
            future=peer.path_action.send_goal_async(goal)
            wait(future.done,10.,move=response and c.peers['r3'].job is not None)
            action=future.result()
            status,path=None,[]
            if action.accepted:
                future=action.get_result_async()
                wait(future.done,15.,move=response and c.peers['r3'].job is not None)
                reply=future.result()
                status=reply.status
                path=[(p.pose.position.x,p.pose.position.y) for p in reply.result.path.poses]
            length=sum(math.dist(u,v) for u,v in zip(path,path[1:]))
            endpoint=math.dist(path[-1],(x,y)) if path else None
            passed=screen_passed(status,len(path),endpoint,length)
            reason='occupied_by_body_mask' if occupied else 'eligible' if passed else 'nav2_path_rejected'
            return dict(candidate, occupied=occupied, passed=passed, reason=reason, status=status,
                        length=length, endpoint=endpoint, points=len(path))

        def plan(folder, chosen, protocol):
            config=deepcopy(cfg)
            anchor=chosen['id']
            config['anchors'][anchor]=chosen['pose']
            measured_prior = 12.+chosen['length']/.22
            config['tables']['event'].setdefault(anchor,{})[anchor]=0.
            config['tables']['event'][ORIGIN][anchor]=measured_prior
            tasks=compile_tasks(protocol.planning_view(),c.elapsed(),config,'A',dt.phases,verify_anchor=anchor)
            task=tasks[JOB]
            task['spatial_source']='controlled_gazebo_body_mask'
            task['capabilities']=[*task['capabilities'],'qualified_verify_approach']
            config['capabilities'][ROBOT]=[*config['capabilities'][ROBOT],'qualified_verify_approach']
            p=dt.problem(config,tasks,[JOB],{},c.states(),{},c.elapsed(),c.elapsed(),'verify')
            # Native model defines arcs even for ineligible robots. Only R1 has a measured travel row.
            for rid in tuple(p['robots']):
                if rid!=ROBOT:
                    del p['robots'][rid]
                    del p['reference']['routes'][rid]
                    del p['prefixes'][rid]
            p['travel_times'][anchor]['END_'+ROBOT]=0.
            WRITE(folder/'request.json',dict(variants=[p]))
            with (folder/'worker.log').open('w') as log:
                subprocess.run([sys.executable,str(WORKSPACE/'tools/dense_solver.py'),
                    str(folder/'request.json'),str(folder/'result.json')],stdout=log,stderr=subprocess.STDOUT,
                    timeout=20.,check=True)
            q=READ(folder/'result.json')
            if not q.get('plan') or not validate(p,q['plan'],q['scope'],q['objective'])['passed']:
                raise ValueError(f"Native verify plan failed: {q['status']}")
            return config,tasks,q['plan'],dict(status=q['status'],owner=q['plan']['owners'][JOB],
                start=q['plan']['starts'][JOB],finish=q['plan']['finishes'][JOB],
                modelTarget=q['selected_problem']['tasks'][JOB]['location'],
                anchor=q['selected_problem']['tasks'][JOB]['anchor'],
                travelPrior=measured_prior, travelLength=chosen['length'])

        try:
            wait(lambda:len(c.truth)==3 and all(peer.ready() for peer in c.peers.values()),60.)
            if any(math.dist((v['x'],v['y']),poses[r][:2])>.15 for r,v in c.truth.items()):
                raise ValueError('Gazebo spawn does not match the shared fixture')
            c.epoch=c.now()
            c.ledger={}
            for label in CONDITIONS:
                c.protocol=EventTaskProtocol(position_ttl=180.,supply=cfg['anchors']['G1'][:2])
                mask=apply_mask(label)
                rows=[query(site,value==100) for site,value in zip(candidates,mask)]
                chosen=select(rows)
                protocol=EventTaskProtocol(position_ttl=180.,supply=cfg['anchors']['G1'][:2])
                # Identical prior target for all three snapshots. The current mask/result revises this task.
                observation(protocol,0.,centers['original'],baseline,'reference')
                msg=observation(protocol,c.elapsed(),centers[label],chosen,'current')
                task=deepcopy(protocol.tasks[TASK])
                case=dict(condition=label,center=centers[label],queries=rows,observation=msg,task=task,
                          selected=chosen['id'] if chosen else None,plan=None)
                result['conditions'].append(case)
                if chosen:
                    _,_,_,case['plan']=plan(out/label,chosen,protocol)
                elif task['state']!='PENDING' or protocol.planning_view()['tasks']:
                    raise ValueError('Blocked verification must stay pending outside MILP')
            if [case['selected'] for case in result['conditions']] != [baseline['id'],alternative['id'],None]:
                raise ValueError('Declared spatial contrast did not materialize')
            c.protocol=EventTaskProtocol(position_ttl=180.,supply=cfg['anchors']['G1'][:2])
            mask=apply_mask('switch')
            chosen=select([query(site,value==100) for site,value in zip(candidates,mask)])
            if not chosen or chosen['id']!=alternative['id']:
                raise ValueError('Fresh runtime gate did not select the same alternative')
            protocol=EventTaskProtocol(position_ttl=700. if response else 180.,supply=cfg['anchors']['G1'][:2])
            response_points=None
            if response:
                response_points=registered_space(cfg,'A')['service_points']
                del response_points['verify']
            observation(protocol,0.,centers['original'],baseline,'reference',response_points)
            observation(protocol,c.elapsed(),centers['switch'],chosen,'current',response_points)
            c.protocol=protocol
            tokens=execution_tokens(protocol,[TASK])
            cfg_exec,c.tasks,c.plan,model=plan(out/'execution',chosen,protocol)
            if not execution_fence(protocol,tokens)['passed']:
                raise ValueError('Formal verify task changed after solve')
            c.cfg=cfg_exec
            c.plan_revision=1
            c.queues={r:([JOB] if r==ROBOT else []) for r in c.peers}
            c.planned_owners={TASK:model['owner']}
            recorded_goals=[]
            send=b.path_action.send_goal_async

            def record_goal(goal,*args,**kwargs):
                pose=goal.goal.pose
                yaw=math.atan2(2*pose.orientation.w*pose.orientation.z,1-2*pose.orientation.z**2)
                row=dict(at=c.elapsed(), frame=goal.goal.header.frame_id,
                         pose=[pose.position.x,pose.position.y,yaw])
                recorded_goals.append(row)
                c.log('formal_verify_nav2_goal',**{k:v for k,v in row.items() if k!='at'})
                return send(goal,*args,**kwargs)

            b.path_action.send_goal_async=record_goal
            result['execution']=dict(target=chosen['id'],model=model,task=deepcopy(protocol.tasks[TASK]),
                                     goals=recorded_goals, passed=False)
            c.log('formal_verify_plan_committed',task=protocol.tasks[TASK],model=model)
            if response:
                from stand_switch_response import issue_routine
                issue_routine(c,prior,wait)
            wait(lambda:(c.dispatch_dense(b) or b.job==JOB),90.,move=True)
            wait(lambda:JOB in c.completed,120.,move=True)
            rec=c.completed[JOB]
            ack=[v for (task_id,_),v in b.phases.items() if task_id==rec['task_id']]
            checks=execution_checks(rec,ack,chosen['pose'])
            checks.update(nav2_goal=bool(recorded_goals) and all(g['frame']=='map' and
                          math.dist(g['pose'],chosen['pose'])<1e-6 for g in recorded_goals),
                          model_target=model['modelTarget']==chosen['pose'][:2]==tokens[TASK]['target']['xy'],
                          protocol_tokens=protocol.tasks[TASK]['state']=='SUCCEEDED'
                          and all(v['protocol_task_id']==TASK and v['task_revision']==tokens[TASK]['revision'] for v in ack))
            result['execution'].update(record=rec,feedback=ack,checks=checks,passed=all(checks.values()))
            if response:
                from stand_switch_response import continue_response
                if not result['execution']['passed']:
                    raise ValueError('Formal verification did not pass independent execution checks')
                b.path_action.send_goal_async=send
                result['response']={}
                continue_response(c,out,query,wait,result['response'],
                                  via_v3=via_v3,after_patrol=after_patrol)
        except Exception as error:
            result['failure']=repr(error)
        finally:
            if result['execution'] is not None and c.records and 'record' not in result['execution']:
                result['execution']['record']=c.records[-1]
            result['protocol_final']=c.protocol.snapshot()
            if response:
                result['runtime_records']=c.records
                result['runtime_completed']=c.completed
                result['resource_events']=c.resource_events
            c.file.close()
            for node in (*c.peers.values(),c):
                if getattr(node,'nav_handle',None) and node.state!='IDLE':
                    node.nav_handle.cancel_goal_async()
                executor.remove_node(node)
                node.destroy_node()
            executor.shutdown()
            rclpy.try_shutdown()
    result['cleanup']=READ(out/'cleanup.json')['passed']
    WRITE(out/'summary.json',benchmark.json_finite(result))
    viewer=READ(out/'summary.json')
    viewer.update(run=out.name,evidence={name:benchmark.sha(out/name) for name in
                  ('fixture.json','summary.json','trace.jsonl','cleanup.json')})
    WRITE(out/'viewer.json',viewer)
    passed = result['cleanup'] and result['failure'] is None and bool((result['execution'] or {}).get('passed'))
    if response:
        passed = passed and result.get('response',{}).get('passed',False)
    print(out, result['failure'], passed,flush=True)
    return passed


if __name__=='__main__':
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--out',required=True,type=Path)
    cli.add_argument('--domain',default=96,type=int)
    cli.add_argument('--response',action='store_true',help='Continue the verified alternate stand through the A-area response')
    cli.add_argument('--via-v3',action='store_true',help='Use a V3 stop before the monitor approach')
    cli.add_argument('--after-patrol',action='store_true',help='Require the committed patrol to clear before dispatching monitor')
    args=cli.parse_args()
    if (args.via_v3 or args.after_patrol) and not args.response:
        cli.error('Monitor approach options require --response')
    raise SystemExit(0 if run(args.out.resolve(),args.domain,args.response,args.via_v3,args.after_patrol) else 1)
