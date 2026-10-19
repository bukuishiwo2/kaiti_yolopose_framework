#!/usr/bin/env bash
set -eo pipefail
source /opt/ros/humble/setup.bash
source /data/ductcleanrob/install/setup.bash
export ROS_DOMAIN_ID=8 ROS_LOCALHOST_ONLY=0 RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
export CYCLONEDDS_URI=file:///data/ductcleanrob/scripts/cyclonedds.xml
export PYTHONPATH="/home/duct/pose3d_fusion:${PYTHONPATH:-}"
exec python3 -c 'from yolopose_ros.pose_3d_fusion_node import main; main()' \
  --ros-args --params-file /home/duct/duct_pose3d_fusion_robot.yaml
