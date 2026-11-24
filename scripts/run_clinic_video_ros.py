#!/usr/bin/env python3
"""Actual RGB ROS replay -> existing PoseStreamNode -> event-task -> Clinic MILP.

No Gazebo, no executor-injected event, no fabricated verification ACK. The
publisher waits for each inference receipt (explicit paced replay, not a live
camera throughput benchmark). A separate process can consume the trace later.
"""
from __future__ import annotations
import argparse
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import sys
import time

PROJECT = Path(__file__).resolve().parents[1]
WORKSPACE = Path('/home/yhc/clinic_planning_ws')
sys.path[:0] = [str(PROJECT/'src'), str(PROJECT/'ros2_ws/src/yolopose_ros'), str(WORKSPACE/'tools')]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--videos', nargs='+', default=['fall-01-cam0', 'adl-01-cam0'])
    p.add_argument('--regions', nargs='+', choices=['A', 'B'], default=['A', 'B'])
    p.add_argument('--repeats', type=int, default=1)
    p.add_argument('--gap-at-frame', type=int, default=-1)
    p.add_argument('--gap-seconds', type=float, default=0.)
    p.add_argument('--silence-seconds', type=float, default=11.)
    p.add_argument('--solve', action='store_true')
    p.add_argument('--perception-only', action='store_true',
        help='Publish RGB/model/metadata for an external unique protocol owner')
    p.add_argument('--out', type=Path, required=True)
    args = p.parse_args()
    if args.repeats < 1 or args.gap_seconds < 0 or args.silence_seconds < 0:
        p.error('repeats must be positive and durations nonnegative')
    if int(os.environ.get('ROS_DOMAIN_ID', '0')) not in range(90, 102):
        p.error('set isolated ROS_DOMAIN_ID 90..101')
    args.out.mkdir(parents=True, exist_ok=False)
    import cv2
    import numpy as np
    import rclpy
    from rclpy.node import Node
    from rclpy.executors import SingleThreadedExecutor
    from sensor_msgs.msg import Image
    from std_msgs.msg import String
    from yolopose_ros.pose_stream_node import PoseStreamNode
    from kaiti_task_sim.clinic_visual import VisualEventBridge, compile_tasks, sensor_position_contract
    import dense_tasks as dt
    import bed_contract
    cfg = bed_contract.config()
    class IsolatedPoseStream(PoseStreamNode):
        def _load_runner(self, source):
            # Reuse native ROS decode/inference/publish, isolating output paths.
            import yaml
            from yolopose.pipeline.runner import PoseRunner
            settings = yaml.safe_load((PROJECT/'configs/infer_pose_stream.yaml').read_text())
            settings.update(model=str(PROJECT/settings['model']), source=source,
                device='0', save_visualization=False, save_jsonl=None)
            settings['sequence_fall_detector']['device'] = '0'
            return PoseRunner(settings, PROJECT)
    (args.out/'spatial_sensor_interface.json').write_text(json.dumps(sensor_position_contract(), indent=2))
    npz = np.load(PROJECT/'data/processed/urfall_pose_sequences.npz', allow_pickle=False)
    split_key = 'video_ids' if 'video_ids' in npz else 'video_id'
    manifest = {}
    for v in args.videos:
        path = PROJECT/'data/urfall/cam0_mp4'/f'{v}.mp4'
        vid = v.removesuffix('-cam0')
        selected = npz[split_key].astype(str) == vid
        splits = sorted(set(npz['split'][selected].astype(str)))
        manifest[v] = dict(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            dataset_splits=splits, independent_test=False,
            usage='integration_development_sample; historical URFall evaluation/tuning domain')
    (args.out/'input_manifest.json').write_text(json.dumps(manifest, indent=2))
    npz.close()
    rclpy.init(args=['--ros-args', '-p', 'input_mode:=ros_image', '-p',
        'ros_image_topic:=/clinic_visual/rgb', '-p', 'event_topic:=/clinic_visual/model',
        '-p', f'project_root:={PROJECT}'])
    ex = SingleThreadedExecutor()
    replay = Node('clinic_visual_replay')
    pub = replay.create_publisher(Image, '/clinic_visual/rgb', 10)
    metadata_pub = replay.create_publisher(String, '/clinic_visual/replay_metadata', 100)
    ex.add_node(replay)
    stream, current, received = None, {}, {}
    trace = (args.out/'causal.jsonl').open('w')
    summaries = []

    def log(kind, **data):
        trace.write(json.dumps(dict(kind=kind, wall_monotonic=time.monotonic(), **data), allow_nan=False)+'\n')
        trace.flush()

    def on_model(msg):
        record = json.loads(msg.data)
        stamp = record.get('source_ros_stamp_ns')
        if stamp not in current or stamp in received:
            return  # heartbeat is never a fresh observation
        meta = current[stamp]
        sample = dict(sample_id=meta['sample_id'], source_id=meta['source_id'],
            source_at=meta['published_monotonic']-meta['origin'],
            score=record['seq_fall_score'], stable=record['seq_stable_fall_detected'],
            window_ready=record['seq_window_ready'], video_time=meta['video_time'],
            ros_stamp_ns=stamp, replay=meta['repeat'])
        now = time.monotonic()-meta['origin']
        transition = meta['bridge'].observe(sample, now) if meta['bridge'] else None
        compiled = compile_tasks(meta['bridge'].protocol.planning_view(), now, cfg, meta['region'], dt.phases) if meta['bridge'] else {}
        item = dict(sample=sample, model=record, transition=transition,
            compiled=compiled, latency_seconds=time.monotonic()-meta['published_monotonic'])
        received[stamp] = item
        log('image_model_event_tasks', **item)

    sub = replay.create_subscription(String, '/clinic_visual/model', on_model, 100)

    def spin_for(seconds, bridge=None, origin=None):
        until = time.monotonic()+seconds
        while time.monotonic() < until:
            ex.spin_once(timeout_sec=min(.05, max(0., until-time.monotonic())))
            if bridge:
                bridge.tick(time.monotonic()-origin)

    try:
        for video in args.videos:
            for region in args.regions:
                origin = time.monotonic()
                bridge = VisualEventBridge(cfg, region, source_id=video) if not args.perception_only else None
                scores, positives, max_tasks, counts, solves = [], [], set(), [], []
                first_candidate = None
                for repeat in range(args.repeats):
                    if stream:
                        ex.remove_node(stream); stream.destroy_node(); stream = None
                    stream = IsolatedPoseStream()  # resets 32-frame buffer between playbacks
                    if stream._runner is None:
                        raise RuntimeError('real model failed to load')
                    ex.add_node(stream)
                    subscription_deadline=time.monotonic()+20.
                    while pub.get_subscription_count() == 0:
                        if time.monotonic()>subscription_deadline:
                            raise TimeoutError('ROS image subscriber discovery timeout')
                        spin_for(.1)
                    capture = cv2.VideoCapture(manifest[video]['path'])
                    fps = capture.get(cv2.CAP_PROP_FPS)
                    if fps <= 0:
                        raise RuntimeError('invalid source FPS')
                    index = 0
                    try:
                        while True:
                            ok, frame = capture.read()
                            if not ok:
                                break
                            if index == args.gap_at_frame and args.gap_seconds:
                                before = bridge.protocol.snapshot() if bridge else None
                                spin_for(args.gap_seconds, bridge, origin)
                                # Do not join two separated sequences into one temporal window.
                                stream._runner = stream._load_runner('/clinic_visual/rgb')
                                log('image_interruption', seconds=args.gap_seconds, before=before,
                                    after=bridge.protocol.snapshot() if bridge else None, model_buffer_reset=True)
                            tick = time.monotonic()
                            stamp = replay.get_clock().now().nanoseconds
                            msg = Image()
                            msg.header.stamp.sec, msg.header.stamp.nanosec = divmod(stamp, 10**9)
                            msg.header.frame_id = 'registered_video_optical'
                            msg.height, msg.width = frame.shape[:2]
                            msg.encoding, msg.step, msg.data = 'bgr8', frame.shape[1]*3, frame.tobytes()
                            current[stamp] = dict(sample_id=f'{video}:{region}:{repeat}:{index}',
                                source_id=video, video_time=index/fps, published_monotonic=tick,
                                repeat=repeat, region=region, origin=origin, bridge=bridge)
                            metadata_pub.publish(String(data=json.dumps({k:v for k,v in current[stamp].items() if k!='bridge'} | dict(ros_stamp_ns=stamp, registration_mode='video_source_registered'))))
                            pub.publish(msg)
                            deadline = tick+20.
                            while stamp not in received and time.monotonic() < deadline:
                                ex.spin_once(timeout_sec=.01)
                            if stamp not in received:
                                raise RuntimeError(f'inference receipt timeout {video}:{index}')
                            item = received.pop(stamp)
                            current.pop(stamp)
                            scores.append(item['sample']['score'])
                            if item['sample']['stable']:
                                positives.append(dict(repeat=repeat, video_time=index/fps))
                            max_tasks.update(item['compiled'])
                            if item['compiled'] and first_candidate is None:
                                first_candidate = deepcopy(item)
                            index += 1
                            spin_for(max(0., 1/fps-(time.monotonic()-tick)))
                    finally:
                        capture.release()
                    counts.append(index)
                    log('replay_completed', video=video, region=region, repeat=repeat,
                        decoded_and_inferred=index, source_fps=fps, buffer_reset_on_next_replay=True)
                if args.solve and first_candidate:
                    import dense_solver as ds
                    import dense_validate as dv
                    normal, _ = dt.normal_tasks()
                    normal = {j:t for j,t in normal.items() if t['waypoint'] == 1}
                    tasks = {**normal, **first_candidate['compiled']}
                    states = {r:dict(job=None, state='IDLE', anchor=cfg['starts'][r], cargo=None,
                        record={}, pose=dict(zip(('x','y','yaw'), cfg['anchors'][cfg['starts'][r]])), leg='service')
                        for r in cfg['robots']}
                    now = first_candidate['transition']['snapshot']['time']
                    problem = dt.problem(cfg, tasks, list(tasks), {}, states, dict(starts={}), now, now, 'visual_verify')
                    folder = args.out/f'{video}_{region}_milp'; folder.mkdir()
                    # Existing solver and full independent validator.
                    scope = dict(free=list(problem['tasks']), freeze_time=False)
                    result = ds.a.ScopedSolver(folder/'solver').solve(problem, scope, 'monolithic', time.perf_counter()+5.)
                    check = (dv.validate(problem, result['plan'], scope, result['objective'])
                        if result['status'] in {'OPTIMAL','FEASIBLE_BUDGET'} else dict(passed=False))
                    (folder/'problem.json').write_text(json.dumps(problem, indent=2))
                    (folder/'result.json').write_text(json.dumps(result, indent=2))
                    (folder/'validation.json').write_text(json.dumps(check, indent=2))
                    solves.append(dict(passed=check['passed'], status=result['status']))
                before_silence = bridge.protocol.snapshot() if bridge else None
                spin_for(args.silence_seconds, bridge, origin)
                summary = dict(video=video, region=region, frames_per_replay=counts,
                    stable_positive_frames=len(positives), positives=positives,
                    max_score=max(scores), generated_tasks=sorted(max_tasks),
                    event_id=((bridge.protocol.event or {}).get('event_id') if bridge else None),
                    before_silence=before_silence, after_silence=bridge.protocol.snapshot() if bridge else None,
                    milp=solves, verification_verdict_source=None,
                    navigation_executed=False, source_kind='video_source_registered')
                summaries.append(summary)
                log('case_completed', **summary)
        (args.out/'summary.json').write_text(json.dumps(dict(status='PASS', cases=summaries,
            scope='ROS RGB -> actual models -> candidate/verify tasks; no service ACK or navigation'), indent=2))
        print(json.dumps(dict(status='PASS', cases=len(summaries))))
    finally:
        trace.close()
        if stream:
            ex.remove_node(stream); stream.destroy_node()
        replay.destroy_node(); ex.shutdown(); rclpy.try_shutdown()


if __name__ == '__main__':
    main()
