#!/usr/bin/env python3
"""Independent latest-frame RTSP display; never changes the vendor 8554 server."""
import argparse
import signal
import sys
import threading
import time

import cv2
import numpy as np
import gi

gi.require_version('Gst', '1.0')
gi.require_version('GstRtspServer', '1.0')
from gi.repository import GLib, Gst, GstRtspServer
import rclpy
from rclpy.qos import QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import CompressedImage


class Frames:
    def __init__(self, width, height):
        self.lock = threading.Lock()
        self.width, self.height = width, height
        self.frame = None
        self.received_at = 0.0
        self.received = 0
        self.source_stamp_ns = 0

    def receive(self, msg):
        frame = cv2.imdecode(np.frombuffer(msg.data, np.uint8), cv2.IMREAD_COLOR)
        if frame is None:
            return
        if frame.shape[:2] != (self.height, self.width):
            frame = cv2.resize(frame, (self.width, self.height))
        with self.lock:
            self.frame = frame
            self.received_at = time.monotonic()
            self.received += 1
            self.source_stamp_ns = msg.header.stamp.sec * 10**9 + msg.header.stamp.nanosec

    def snapshot(self):
        with self.lock:
            frame = self.frame
            age = time.monotonic() - self.received_at
            source_age = (time.time_ns() - self.source_stamp_ns) / 1e9
        if frame is None or age > 1.0 or not -0.15 <= source_age <= 1.5:
            frame = np.zeros((self.height, self.width, 3), np.uint8)
            text = 'Waiting for live 3D image' if self.frame is None else '3D image stale'
            cv2.putText(frame, text, (30, 60), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 180, 255), 2)
        else:
            frame = frame.copy()
        # This live server clock reveals player buffering separately from source age.
        now = time.time()
        label = f"RTSP {time.strftime('%H:%M:%S', time.localtime(now))}.{int(now % 1 * 1000):03d} source-age={source_age:.2f}s"
        cv2.putText(frame, label, (12, self.height - 42), cv2.FONT_HERSHEY_SIMPLEX,
                    0.5, (0, 0, 0), 3, cv2.LINE_AA)
        cv2.putText(frame, label, (12, self.height - 42), cv2.FONT_HERSHEY_SIMPLEX,
                    0.5, (50, 255, 255), 1, cv2.LINE_AA)
        return frame.tobytes()


class Factory(GstRtspServer.RTSPMediaFactory):
    def __init__(self, frames, args):
        super().__init__()
        self.frames, self.args = frames, args
        self.set_shared(True)
        self.set_latency(0)

    def do_create_element(self, url):
        args = self.args
        return Gst.parse_launch(
            '( appsrc name=imagesrc is-live=true do-timestamp=true format=time '
            'block=false max-bytes=0 max-buffers=1 leaky-type=downstream '
            f'caps=video/x-raw,format=BGR,width={args.width},height={args.height},framerate={args.fps}/1 '
            '! queue max-size-buffers=1 max-size-bytes=0 max-size-time=0 leaky=downstream '
            '! videoconvert ! video/x-raw,format=I420 '
            f'! x264enc tune=zerolatency speed-preset=ultrafast bitrate={args.bitrate} '
            f'key-int-max={args.fps} bframes=0 threads=2 '
            '! video/x-h264,profile=baseline ! h264parse config-interval=1 '
            '! rtph264pay name=pay0 pt=96 config-interval=1 mtu=1400 )'
        )

    def do_configure(self, media):
        source = media.get_element().get_by_name('imagesrc')
        state = {'alive': True}
        media.connect('unprepared', lambda *_: state.update(alive=False))

        def push():
            if not state['alive']:
                return False
            raw = self.frames.snapshot()
            buf = Gst.Buffer.new_allocate(None, len(raw), None)
            buf.fill(0, raw)
            buf.duration = Gst.SECOND // self.args.fps
            result = source.emit('push-buffer', buf)
            return result in (Gst.FlowReturn.OK, Gst.FlowReturn.FLUSHING)

        GLib.timeout_add(max(1, 1000 // self.args.fps), push)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config')
    parser.add_argument('--port', default='8555')
    parser.add_argument('--topic', default='/perception/pose_3d_debug_image/compressed')
    parser.add_argument('--fps', type=int, default=5)
    parser.add_argument('--bitrate', type=int, default=1800)
    parser.add_argument('--width', type=int, default=1280)
    parser.add_argument('--height', type=int, default=720)
    args = parser.parse_args()
    if args.config:
        import yaml
        with open(args.config, encoding='utf-8') as config_file:
            params = yaml.safe_load(config_file)['/pose3d_image2rtsp']['ros__parameters']
        for name, key in [('port', 'port'), ('topic', 'streams.pose3d.topic'),
                          ('fps', 'streams.pose3d.framerate'),
                          ('bitrate', 'streams.pose3d.bitrate'),
                          ('width', 'streams.pose3d.width'), ('height', 'streams.pose3d.height')]:
            explicit = any(arg == '--' + name or arg.startswith('--' + name + '=')
                           for arg in sys.argv[1:])
            if not explicit and key in params:
                setattr(args, name, str(params[key]) if name in ('port', 'topic') else int(params[key]))
    if args.fps < 1 or args.width < 1 or args.height < 1:
        parser.error('fps and dimensions must be positive')
    Gst.init(None)
    rclpy.init()
    node = rclpy.create_node('pose3d_rtsp_latest_frame')
    frames = Frames(args.width, args.height)
    qos = QoSProfile(depth=1, reliability=ReliabilityPolicy.BEST_EFFORT)
    node.create_subscription(CompressedImage, args.topic, frames.receive, qos)
    worker = threading.Thread(target=rclpy.spin, args=(node,), daemon=True)
    worker.start()
    server = GstRtspServer.RTSPServer()
    server.set_service(args.port)
    factory = Factory(frames, args)
    server.get_mount_points().add_factory('/pose3d', factory)
    if not server.attach(None):
        raise RuntimeError(f'Cannot bind RTSP port {args.port}')
    print(f'Latest-frame RTSP :{args.port}/pose3d fps={args.fps}', flush=True)
    loop = GLib.MainLoop()
    signal.signal(signal.SIGTERM, lambda *_: loop.quit())
    signal.signal(signal.SIGINT, lambda *_: loop.quit())
    try:
        loop.run()
    except KeyboardInterrupt:
        pass
    finally:
        rclpy.try_shutdown()
        worker.join(timeout=2)
        node.destroy_node()


if __name__ == '__main__':
    main()
