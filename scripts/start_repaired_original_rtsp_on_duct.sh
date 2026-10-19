#!/usr/bin/env bash
# Isolated build of the original server. Keeps its 8554 URLs and config.
set -eo pipefail
# Cyclone explicitly binds this interface. A network-online target alone does
# not guarantee this particular NIC has an address during a cold boot.
bash /home/duct/wait_duct_research_network.sh
source /opt/ros/humble/setup.bash
source /data/ductcleanrob/install/setup.bash
source /home/duct/rtsp_repair_ws/install/setup.bash
export ROS_DOMAIN_ID=8 ROS_LOCALHOST_ONLY=0
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
export CYCLONEDDS_URI=file:///data/ductcleanrob/scripts/cyclonedds.xml
export DUCT_RTSP_STARTUP_PREROLL=1
# Keep the vendor parameter file, not the copied build's potentially old config.
exec ros2 launch image2rtsp image2rtsp.launch.py \
  params_file_dir:=/data/ductcleanrob/install/image2rtsp/share/image2rtsp/config/parameters.yaml
