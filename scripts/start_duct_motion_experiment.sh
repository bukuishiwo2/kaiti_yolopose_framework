#!/usr/bin/env bash
set -eo pipefail
source /opt/ros/humble/setup.bash
source /data/ductcleanrob/install/setup.bash
export ROS_DOMAIN_ID=8 ROS_LOCALHOST_ONLY=0 RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
export CYCLONEDDS_URI=file:///data/ductcleanrob/scripts/cyclonedds.xml
export PYTHONPATH="/home/duct/pose3d_fusion:${PYTHONPATH:-}"
# Root transient system services may have no HOME; use a scoped ROS log path.
export ROS_LOG_DIR=/home/duct/pose3d_motion_experiment/ros_logs-${EUID}
mkdir -p "$ROS_LOG_DIR"
case "${1:-}" in
  base) exec ros2 launch /home/duct/pose3d_motion_experiment/guarded_base.launch.py ;;
  jog) shift; exec python3 /home/duct/duct_guarded_jog.py "$@" ;;
  mode) shift; exec python3 /home/duct/duct_motion_mode.py "$@" ;;
  *) exit 2 ;;
esac
