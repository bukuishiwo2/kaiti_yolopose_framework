from __future__ import annotations

import time

import cv2
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image


class CameraStreamNode(Node):
    """Minimal USB camera publisher for ROS2 image-stream validation."""

    def __init__(self) -> None:
        super().__init__("camera_stream_node")

        self.declare_parameter("image_topic", "/camera/image_raw")
        self.declare_parameter("camera_device", "")
        self.declare_parameter("camera_index", 0)
        self.declare_parameter("camera_width", 640)
        self.declare_parameter("camera_height", 480)
        self.declare_parameter("camera_fps", 10.0)
        self.declare_parameter("camera_frame_id", "kaiti_camera_optical_frame")

        self._image_topic = str(self.get_parameter("image_topic").value)
        self._camera_device = str(self.get_parameter("camera_device").value).strip()
        self._camera_index = int(self.get_parameter("camera_index").value)
        self._camera_width = int(self.get_parameter("camera_width").value)
        self._camera_height = int(self.get_parameter("camera_height").value)
        self._camera_fps = float(self.get_parameter("camera_fps").value)
        self._camera_frame_id = str(self.get_parameter("camera_frame_id").value)

        self._publisher = self.create_publisher(Image, self._image_topic, 10)
        self._capture = cv2.VideoCapture(self._resolve_source())
        if not self._capture.isOpened() and not self._camera_device:
            fallback_device = f"/dev/video{self._camera_index}"
            self.get_logger().warning(
                "Camera index open failed, fallback to device path=%s" % fallback_device
            )
            self._capture = cv2.VideoCapture(fallback_device)
        if not self._capture.isOpened():
            raise RuntimeError("camera_stream_open_failed")

        if self._camera_width > 0:
            self._capture.set(cv2.CAP_PROP_FRAME_WIDTH, self._camera_width)
        if self._camera_height > 0:
            self._capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self._camera_height)
        if self._camera_fps > 0:
            self._capture.set(cv2.CAP_PROP_FPS, self._camera_fps)

        publish_period = 1.0 / self._camera_fps if self._camera_fps > 0 else 0.1
        self._read_fail_count = 0
        self._timer = self.create_timer(publish_period, self._publish_frame)

        self.get_logger().info(
            "Camera stream ready: source=%s image_topic=%s"
            % (self._camera_device or self._camera_index, self._image_topic)
        )

    def _resolve_source(self) -> str | int:
        if self._camera_device:
            return self._camera_device
        return self._camera_index

    def _publish_frame(self) -> None:
        ok, frame = self._capture.read()
        if not ok or frame is None:
            self._read_fail_count += 1
            if self._read_fail_count in {1, 10, 30}:
                self.get_logger().warning(
                    "Camera read failed: source=%s fail_count=%d"
                    % (self._camera_device or self._camera_index, self._read_fail_count)
                )
            return

        self._read_fail_count = 0
        msg = Image()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = self._camera_frame_id
        msg.height = int(frame.shape[0])
        msg.width = int(frame.shape[1])
        msg.encoding = "bgr8"
        msg.is_bigendian = 0
        msg.step = int(frame.shape[1] * frame.shape[2])
        msg.data = frame.tobytes()
        self._publisher.publish(msg)

    def destroy_node(self) -> bool:
        if hasattr(self, "_capture") and self._capture is not None:
            self._capture.release()
        return super().destroy_node()


def main(args=None) -> None:
    rclpy.init(args=args)
    node: CameraStreamNode | None = None
    try:
        node = CameraStreamNode()
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        if node is not None:
            node.destroy_node()
        time.sleep(0.05)
        if rclpy.ok():
            rclpy.shutdown()
