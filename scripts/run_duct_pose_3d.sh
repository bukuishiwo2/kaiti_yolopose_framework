#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ROS_SETUP="/opt/ros/humble/setup.bash"
WORKSPACE_SETUP="$PROJECT_ROOT/ros2_ws/install/setup.bash"
CYCLONE_CONFIG="${DUCT_CYCLONE_CONFIG:-$PROJECT_ROOT/configs/cyclonedds_pose3d_local.xml}"
# Workstation ROS is local. The stamped RGB/JSON bridge uses TCP over Wi-Fi.

if [[ ! -f "$ROS_SETUP" ]]; then
  echo "ROS2 Humble setup not found: $ROS_SETUP" >&2
  exit 2
fi
if [[ ! -f "$WORKSPACE_SETUP" ]]; then
  echo "Workspace is not built. Run:" >&2
  echo "  cd $PROJECT_ROOT/ros2_ws && colcon build --packages-select yolopose_ros --symlink-install" >&2
  exit 2
fi
set +u
# shellcheck disable=SC1090
source "$ROS_SETUP"
# shellcheck disable=SC1090
source "$WORKSPACE_SETUP"
set -u
export KAITI_PROJECT_ROOT="$PROJECT_ROOT"
export ROS_DOMAIN_ID="${DUCT_ROS_DOMAIN_ID:-18}"
export ROS_LOCALHOST_ONLY=0
export RMW_IMPLEMENTATION="${DUCT_RMW_IMPLEMENTATION:-rmw_cyclonedds_cpp}"
if [[ "$RMW_IMPLEMENTATION" == "rmw_cyclonedds_cpp" ]]; then
  if ! find /opt/ros/humble -name librmw_cyclonedds_cpp.so -print -quit | grep -q .; then
    echo "Cyclone DDS was selected but ros-humble-rmw-cyclonedds-cpp is missing." >&2
    exit 3
  fi
  export CYCLONEDDS_URI="file://$CYCLONE_CONFIG"
else
  unset CYCLONEDDS_URI || true
fi

exec ros2 launch yolopose_ros duct_pose_3d_event.launch.py "$@"
