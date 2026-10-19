#!/usr/bin/env python3
"""Bounded TCP exchange of stamped RGB, inference JSON, and debug JPEG.

Robot stays in vendor ROS domain 8; workstation uses isolated domain 18.
Camera timestamps are copied exactly. There are no motion endpoints.
"""
import argparse
import json
import socket
import struct
import threading
import time

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import CompressedImage
from std_msgs.msg import String

LIMIT = 8 * 1024 * 1024


def read_exact(sock, count):
    chunks = bytearray()
    while len(chunks) < count:
        try:
            data = sock.recv(count - len(chunks))
        except socket.timeout:
            # One direction may be idle while inference initializes. Preserve
            # partial framing; sender shutdown closes the socket on termination.
            continue
        if not data:
            raise EOFError('TCP peer disconnected')
        chunks.extend(data)
    return bytes(chunks)


def send_packet(sock, meta, data=b''):
    header = json.dumps(meta, separators=(',', ':')).encode()
    size = 4 + len(header) + len(data)
    if len(header) > 65536 or size > LIMIT:
        raise ValueError('Packet exceeds display bridge limits')
    sock.sendall(struct.pack('!II', size, len(header)) + header + data)


def receive_packet(sock):
    size, header_size = struct.unpack('!II', read_exact(sock, 8))
    if not 2 <= header_size <= 65536 or not header_size + 4 <= size <= LIMIT:
        raise ValueError('Invalid TCP frame lengths')
    meta = json.loads(read_exact(sock, header_size))
    if not isinstance(meta, dict):
        raise ValueError('Invalid TCP metadata')
    return meta, read_exact(sock, size - 4 - header_size)


def image_meta(kind, header):
    return {'kind': kind, 'sec': int(header.stamp.sec),
            'nanosec': int(header.stamp.nanosec), 'frame_id': header.frame_id}


def image_message(meta, data):
    msg = CompressedImage()
    msg.header.stamp.sec = int(meta['sec'])
    msg.header.stamp.nanosec = int(meta['nanosec'])
    msg.header.frame_id = str(meta['frame_id'])
    msg.format, msg.data = 'jpeg', data
    return msg


class Bridge(Node):
    def __init__(self, args):
        super().__init__('pose3d_tcp_' + args.mode)
        self.args = args
        self.stop = threading.Event()
        self.lock = threading.Lock()
        self.latest = {}
        self.sequence = 0
        self.rx_count = self.tx_count = 0
        self.rx_bytes = self.tx_bytes = 0
        sensor = QoSProfile(depth=1, reliability=ReliabilityPolicy.BEST_EFFORT)
        self.publishers_by_kind = {}
        if args.mode == 'server':
            self.create_subscription(CompressedImage, '/camera/color/image_raw/compressed',
                                     self.on_rgb, sensor)
            for kind, topic in [('pose', '/perception/pose_observation_3d'),
                                ('semantic', '/perception/semantic_event_3d'),
                                ('goal_status', '/perception/human_approach_candidate_status')]:
                self.create_subscription(String, topic,
                    lambda msg, k=kind: self.store(k, {'kind': k, 'json': msg.data}), 1)
            self.publishers_by_kind['event'] = self.create_publisher(String, '/perception/events', 10)
            self.publishers_by_kind['debug'] = self.create_publisher(
                CompressedImage, '/perception/debug_image/compressed', sensor)
        else:
            self.create_subscription(String, '/perception/events',
                lambda msg: self.store('event', {'kind': 'event', 'json': msg.data}), 1)
            self.create_subscription(CompressedImage, '/perception/debug_image/compressed',
                                     self.on_debug, sensor)
            self.publishers_by_kind['rgb'] = self.create_publisher(
                CompressedImage, '/inference/color/image_raw/compressed', sensor)
            for kind, topic in [('pose', '/perception/pose_observation_3d'),
                                ('semantic', '/perception/semantic_event_3d'),
                                ('goal_status', '/perception/human_approach_candidate_status')]:
                self.publishers_by_kind[kind] = self.create_publisher(String, topic, 1)
        self.worker = threading.Thread(target=self.network, daemon=True)
        self.worker.start()
        self.create_timer(5, self.report)

    def store(self, key, meta, data=b''):
        with self.lock:
            self.sequence += 1
            self.latest[key] = (self.sequence, meta, bytes(data))

    def on_rgb(self, msg):
        self.store('rgb', image_meta('rgb', msg.header), msg.data)

    def on_debug(self, msg):
        self.store('debug', image_meta('debug', msg.header), msg.data)

    def report(self):
        self.get_logger().info(f'TCP frames rx={self.rx_count} tx={self.tx_count} '
                               f'bytes rx={self.rx_bytes} tx={self.tx_bytes}')

    def reader(self, connection, ended):
        try:
            while not self.stop.is_set() and not ended.is_set():
                meta, data = receive_packet(connection)
                kind = meta.get('kind')
                publisher = self.publishers_by_kind.get(kind)
                if publisher is None:
                    raise ValueError('Unsupported bridge direction or message kind')
                if kind in ('rgb', 'debug'):
                    publisher.publish(image_message(meta, data))
                else:
                    publisher.publish(String(data=str(meta['json'])))
                self.rx_count += 1
                self.rx_bytes += len(data)
        except (OSError, EOFError, ValueError, KeyError) as error:
            if not self.stop.is_set():
                self.get_logger().info(f'TCP reader reconnecting: {error}')
        finally:
            ended.set()

    def exchange(self, connection):
        connection.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        connection.settimeout(3)
        ended = threading.Event()
        reader = threading.Thread(target=self.reader, args=(connection, ended), daemon=True)
        reader.start()
        sent = {}
        rgb_due = 0.0
        try:
            while not self.stop.is_set() and not ended.is_set():
                with self.lock:
                    packets = list(self.latest.items())
                # Debug precedes its event so the robot can annotate the exact frame.
                packets.sort(key=lambda item: item[0] != 'debug')
                for key, (sequence, meta, data) in packets:
                    if sent.get(key) == sequence:
                        continue
                    if key == 'rgb' and time.monotonic() < rgb_due:
                        continue
                    send_packet(connection, meta, data)
                    sent[key] = sequence
                    self.tx_count += 1
                    self.tx_bytes += len(data)
                    if key == 'rgb':
                        rgb_due = time.monotonic() + 1 / self.args.fps
                ended.wait(0.01)
        finally:
            ended.set()
            try:
                connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            reader.join(timeout=3.5)

    def network(self):
        listener = None
        try:
            if self.args.mode == 'server':
                listener = socket.socket()
                listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                listener.bind((self.args.host, self.args.port))
                listener.listen(1)
                listener.settimeout(1)
            while not self.stop.is_set():
                try:
                    if listener:
                        connection, peer = listener.accept()
                        self.get_logger().info(f'TCP client {peer[0]}')
                    else:
                        connection = socket.create_connection((self.args.host, self.args.port), timeout=3)
                    with connection:
                        self.exchange(connection)
                except (OSError, EOFError, ValueError) as error:
                    if not isinstance(error, socket.timeout):
                        self.get_logger().info(f'TCP reconnect: {error}')
                    self.stop.wait(0.5)
        finally:
            if listener:
                listener.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['server', 'client'])
    parser.add_argument('--host', default='192.168.31.191')
    parser.add_argument('--port', type=int, default=8560)
    parser.add_argument('--fps', type=float, default=5)
    args = parser.parse_args()
    if args.fps <= 0:
        parser.error('fps must be positive')
    rclpy.init()
    node = Bridge(args)
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.stop.set()
        node.worker.join(timeout=5)
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
