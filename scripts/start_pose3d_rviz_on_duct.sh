#!/usr/bin/env bash
# Run on the robot's NoMachine desktop. No navigation or motion publishers.
set -eo pipefail
source /opt/ros/humble/setup.bash
source /data/ductcleanrob/install/setup.bash
export ROS_DOMAIN_ID=8 ROS_LOCALHOST_ONLY=0 RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
export CYCLONEDDS_URI=file:///data/ductcleanrob/scripts/cyclonedds.xml
exec rviz2 -d /home/duct/duct_pose_3d_robot.rviz
