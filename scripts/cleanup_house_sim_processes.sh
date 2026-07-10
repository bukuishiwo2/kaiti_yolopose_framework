#!/usr/bin/env bash
#
# 主要功能:
# - 清理 house 仿真相关残留进程，避免重复 launch 导致 /clock、controller_manager、
#   RTAB-Map、Nav2 等链路互相冲突。
# - 重置 ROS 2 daemon，降低旧图信息残留带来的假故障。
# - 作为所有 house 仿真/预检查 launch 前的推荐第一步。
#
# 典型用途:
# - 上一次 Gazebo / RTAB-Map / precheck 没有正常退出。
# - 准备从头重新启动 kaiti_house_* launch。
#
set -euo pipefail

patterns=(
  "ign gazebo"
  "rtabmap"
  "controller_ready_node"
  "robot_ready_gate_node"
  "ros_gz_bridge parameter_bridge"
  "irobot_create_nodes"
  "turtlebot4_node"
)

echo "[cleanup_house_sim] stopping stale house sim processes if present"
for pattern in "${patterns[@]}"; do
  if pgrep -fa "$pattern" >/dev/null 2>&1; then
    echo "[cleanup_house_sim] pkill -f $pattern"
    pkill -f "$pattern" || true
  fi
done

sleep 2

echo "[cleanup_house_sim] resetting ROS 2 daemon"
ros2 daemon stop >/dev/null 2>&1 || true
sleep 1
ros2 daemon start >/dev/null 2>&1 || true

echo "[cleanup_house_sim] remaining matches:"
for pattern in "${patterns[@]}"; do
  pgrep -fa "$pattern" || true
done
