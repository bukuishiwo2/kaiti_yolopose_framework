# Shared environment for every current Clinic command; no process is stopped here.
CLINIC_RUNTIME_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
export PYTHONNOUSERSITE=1 ROS_LOCALHOST_ONLY=1
export ROS_DOMAIN_ID="${CLINIC_DENSE_DOMAIN:-${ROS_DOMAIN_ID:-79}}"
export IGN_PARTITION="${CLINIC_DENSE_PARTITION:-${IGN_PARTITION:-clinic_runtime_default}}"
export RMW_IMPLEMENTATION="${RMW_IMPLEMENTATION:-rmw_cyclonedds_cpp}"
export CYCLONEDDS_URI="file://$CLINIC_RUNTIME_ROOT/config/three_tb4/cyclonedds.xml"
source /opt/ros/humble/setup.bash
source /home/yhc/rmf_clinic_ws/install/setup.bash
export PYTHONPATH="$CLINIC_RUNTIME_ROOT:$CLINIC_RUNTIME_ROOT/tools:${PYTHONPATH:-}"
export IGN_GAZEBO_RESOURCE_PATH="/opt/ros/humble/share:/home/yhc/rmf_clinic_ws/clinic_models:/home/yhc/rmf_clinic_ws/install/rmf_demos_maps/share/rmf_demos_maps/maps/clinic_ign/models:/home/yhc/rmf_clinic_ws/install/rmf_demos_assets/share/rmf_demos_assets/models:${IGN_GAZEBO_RESOURCE_PATH:-}"
export IGN_GAZEBO_SYSTEM_PLUGIN_PATH="/opt/ros/humble/lib:${IGN_GAZEBO_SYSTEM_PLUGIN_PATH:-}"
