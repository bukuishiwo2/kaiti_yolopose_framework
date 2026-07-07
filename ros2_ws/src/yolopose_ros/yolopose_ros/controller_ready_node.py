from __future__ import annotations

import sys
import time

import rclpy
from builtin_interfaces.msg import Duration
from controller_manager_msgs.srv import (
    ConfigureController,
    ListControllers,
    LoadController,
    SwitchController,
)
from rcl_interfaces.msg import ParameterDescriptor
from rclpy.node import Node


class ControllerReadyNode(Node):
    """Ensure required ros2_control controllers reach the active state."""

    def __init__(self) -> None:
        super().__init__("controller_ready_node")

        dynamic_number = ParameterDescriptor(dynamic_typing=True)

        self.declare_parameter("controller_manager", "/controller_manager")
        self.declare_parameter(
            "controllers",
            ["joint_state_broadcaster", "diffdrive_controller"],
        )
        self.declare_parameter("wait_timeout_sec", 90.0, dynamic_number)
        self.declare_parameter("command_timeout_sec", 20.0, dynamic_number)
        self.declare_parameter("poll_period_sec", 1.0, dynamic_number)
        self.declare_parameter("activation_settle_sec", 2.0, dynamic_number)

        self._controller_manager = str(self.get_parameter("controller_manager").value).strip()
        if not self._controller_manager:
            self._controller_manager = "/controller_manager"
        self._controllers = [
            str(name).strip()
            for name in self.get_parameter("controllers").value
            if str(name).strip()
        ]
        self._wait_timeout_sec = max(1.0, float(self.get_parameter("wait_timeout_sec").value))
        self._command_timeout_sec = max(
            1.0, float(self.get_parameter("command_timeout_sec").value)
        )
        self._poll_period_sec = max(0.2, float(self.get_parameter("poll_period_sec").value))
        self._activation_settle_sec = max(
            0.0, float(self.get_parameter("activation_settle_sec").value)
        )

        self._list_client = self.create_client(ListControllers, self._list_service_name())
        self._load_client = self.create_client(LoadController, self._service_name("load_controller"))
        self._configure_client = self.create_client(
            ConfigureController, self._service_name("configure_controller")
        )
        self._switch_client = self.create_client(
            SwitchController, self._service_name("switch_controller")
        )

    def _list_service_name(self) -> str:
        manager = self._controller_manager.rstrip("/")
        return manager + "/list_controllers"

    def _service_name(self, suffix: str) -> str:
        manager = self._controller_manager.rstrip("/")
        return manager + "/" + suffix

    def _fetch_states(self) -> dict[str, str]:
        request = ListControllers.Request()
        future = self._list_client.call_async(request)
        rclpy.spin_until_future_complete(self, future, timeout_sec=self._command_timeout_sec)
        if not future.done():
            raise TimeoutError("list_controllers timed out")
        result = future.result()
        if result is None:
            raise RuntimeError("list_controllers returned no result")
        return {controller.name: controller.state for controller in result.controller}

    def _call_service(self, client, request, service_name: str):
        if not client.wait_for_service(timeout_sec=self._command_timeout_sec):
            raise TimeoutError("Timed out waiting for %s" % service_name)
        future = client.call_async(request)
        rclpy.spin_until_future_complete(self, future, timeout_sec=self._command_timeout_sec)
        if not future.done():
            raise TimeoutError("%s timed out" % service_name)
        result = future.result()
        if result is None:
            raise RuntimeError("%s returned no result" % service_name)
        return result

    def _load_controller(self, name: str) -> bool:
        request = LoadController.Request()
        request.name = name
        response = self._call_service(
            self._load_client,
            request,
            self._service_name("load_controller"),
        )
        if not response.ok:
            self.get_logger().warning("load_controller returned ok=false for %s" % name)
            return False
        return True

    def _configure_controller(self, name: str) -> bool:
        request = ConfigureController.Request()
        request.name = name
        response = self._call_service(
            self._configure_client,
            request,
            self._service_name("configure_controller"),
        )
        if not response.ok:
            self.get_logger().warning("configure_controller returned ok=false for %s" % name)
            return False
        return True

    def _activate_controller(self, name: str) -> bool:
        request = SwitchController.Request()
        request.activate_controllers = [name]
        request.strictness = SwitchController.Request.STRICT
        request.activate_asap = True
        request.timeout = Duration(sec=int(self._command_timeout_sec), nanosec=0)
        response = self._call_service(
            self._switch_client,
            request,
            self._service_name("switch_controller"),
        )
        if not response.ok:
            self.get_logger().warning("switch_controller returned ok=false for %s" % name)
            return False
        return True

    def _ensure_controller(self, name: str, state: str | None) -> None:
        if state == "active":
            return
        if state is None:
            self.get_logger().info("Loading controller %s" % name)
            if not self._load_controller(name):
                return
            return
        if state == "unconfigured":
            self.get_logger().info("Configuring controller %s" % name)
            if not self._configure_controller(name):
                return
            return
        if state in {"inactive", "configured"}:
            self.get_logger().info("Activating controller %s" % name)
            self._activate_controller(name)

    def run(self) -> int:
        deadline = time.monotonic() + self._wait_timeout_sec
        self.get_logger().info(
            "Waiting for controllers %s under %s"
            % (self._controllers, self._controller_manager)
        )

        while time.monotonic() < deadline:
            if self._list_client.wait_for_service(timeout_sec=self._poll_period_sec):
                break
        else:
            self.get_logger().error(
                "Timed out waiting for %s" % self._list_service_name()
            )
            return 1

        last_states: dict[str, str] = {}
        while time.monotonic() < deadline:
            try:
                states = self._fetch_states()
            except Exception as exc:  # pragma: no cover - runtime defensive logging
                self.get_logger().warning("Failed to query controller states: %s" % exc)
                time.sleep(self._poll_period_sec)
                continue

            last_states = states
            inactive = [name for name in self._controllers if states.get(name) != "active"]
            if not inactive:
                self.get_logger().info(
                    "Controllers active: %s"
                    % {name: states.get(name, "missing") for name in self._controllers}
                )
                return 0

            for controller_name in inactive:
                try:
                    self._ensure_controller(controller_name, states.get(controller_name))
                except Exception as exc:  # pragma: no cover - runtime defensive logging
                    self.get_logger().warning(
                        "Failed to activate %s: %s" % (controller_name, exc)
                    )

            if self._activation_settle_sec > 0.0:
                time.sleep(self._activation_settle_sec)
            else:
                time.sleep(self._poll_period_sec)

        self.get_logger().error(
            "Controllers failed to reach active state before timeout: %s"
            % {name: last_states.get(name, "missing") for name in self._controllers}
        )
        return 1


def main() -> None:
    rclpy.init(args=sys.argv)
    node = ControllerReadyNode()
    try:
        exit_code = node.run()
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
    raise SystemExit(exit_code)
