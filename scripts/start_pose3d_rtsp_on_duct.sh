#!/usr/bin/env bash
set -eo pipefail

CONFIG_PATH="${1:-/home/duct/duct_pose3d_rtsp.yaml}"
if [[ ! -f "$CONFIG_PATH" ]]; then
  echo "RTSP config not found: $CONFIG_PATH" >&2
  exit 2
fi

set +u
# shellcheck disable=SC1091
source /opt/ros/humble/setup.bash
# shellcheck disable=SC1091
source /data/ductcleanrob/install/setup.bash
set -u

export ROS_DOMAIN_ID=8
export ROS_LOCALHOST_ONLY=0
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
export CYCLONEDDS_URI=file:///data/ductcleanrob/scripts/cyclonedds.xml

# Independent display process; source timestamps stay in ROS observations.
# GStreamer timestamps video frames against the current playback clock.
exec /usr/bin/python3 /home/duct/pose3d_rtsp_server.py --config "$CONFIG_PATH"
