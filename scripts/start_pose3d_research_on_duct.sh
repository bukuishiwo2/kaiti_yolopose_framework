#!/usr/bin/env bash
set -eo pipefail
source /opt/ros/humble/setup.bash
source /data/ductcleanrob/install/setup.bash
export ROS_DOMAIN_ID=8 ROS_LOCALHOST_ONLY=0 RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
export CYCLONEDDS_URI=file:///data/ductcleanrob/scripts/cyclonedds.xml
export PYTHONPATH="/home/duct/pose3d_fusion:${PYTHONPATH:-}"
case "${1:-}" in
  tcp) exec python3 /home/duct/pose3d_tcp_bridge.py server --host 0.0.0.0 ;;
  visualization) exec python3 -c 'from yolopose_ros.pose_3d_visualization_node import main; main()' ;;
  goal) exec python3 /home/duct/preview_duct_human_goal.py ;;
  cloud) exec python3 /home/duct/pose3d_cloud_display.py ;;
  motion-shadow) exec python3 /home/duct/duct_motion_guard_shadow.py ;;
  *) echo 'Expected tcp, visualization, goal, cloud, or motion-shadow' >&2; exit 2 ;;
esac
