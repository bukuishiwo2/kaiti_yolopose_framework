#!/usr/bin/env bash
# Workstation entrypoint. Robot research services must already be running.
set -eo pipefail
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
set +u
source /opt/ros/humble/setup.bash
set -u
export ROS_DOMAIN_ID=18 ROS_LOCALHOST_ONLY=0 RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
export CYCLONEDDS_URI="file://$PROJECT_ROOT/configs/cyclonedds_pose3d_local.xml"
python3 "$PROJECT_ROOT/scripts/pose3d_tcp_bridge.py" client \
  --host "${DUCT_ROBOT_HOST:-192.168.31.191}" &
bridge_pid=$!
cleanup() {
  if [[ -n "${launch_pid:-}" ]]; then
    kill -INT "$launch_pid" 2>/dev/null || true
    wait "$launch_pid" 2>/dev/null || true
  fi
  kill -TERM "$bridge_pid" 2>/dev/null || true
  wait "$bridge_pid" 2>/dev/null || true
}
trap cleanup EXIT
trap 'exit 130' INT TERM
bash "$PROJECT_ROOT/scripts/run_duct_pose_3d.sh" rviz:=false "$@" &
launch_pid=$!
wait "$launch_pid"
