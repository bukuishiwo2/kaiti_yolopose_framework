#!/usr/bin/env bash
set -u

# Read-only audit for the delivered KYBOT/Lab Robot computer.
# Run locally on the robot, or remotely with:
#   ssh kybot@ROBOT_IP 'bash -s' < scripts/audit_lab_robot_sensors.sh

section() {
  printf '\n===== %s =====\n' "$1"
}

run() {
  printf '\n$ %s\n' "$*"
  "$@" 2>&1 || true
}

run_shell() {
  printf '\n$ %s\n' "$1"
  bash -lc "$1" 2>&1 || true
}

section "identity and operating system"
run hostnamectl
run uname -a
run_shell "sed -n '1,80p' /etc/os-release"
run timedatectl status
run_shell "ip -brief address"

section "ROS installation and environment"
run_shell "env | grep -E '^(ROS|CMAKE_PREFIX_PATH|CATKIN|AMENT)=' | sort"
run_shell "command -v roscore; command -v rostopic; command -v ros2; command -v rospack"
run_shell "rosversion -d 2>/dev/null"
run_shell "find /home -maxdepth 4 -type f \\( -name setup.bash -o -name package.xml \\) 2>/dev/null | head -200"

section "USB, video, serial, and stable device names"
run lsusb
run_shell "command -v v4l2-ctl >/dev/null && v4l2-ctl --list-devices"
run_shell "ls -l /dev/video* /dev/ttyUSB* /dev/ttyACM* 2>/dev/null"
run_shell "find /dev/v4l/by-id /dev/v4l/by-path /dev/serial/by-id /dev/serial/by-path -maxdepth 1 -type l -printf '%p -> %l\n' 2>/dev/null"

section "relevant ROS packages"
for package in astra_camera astra_launch usb_cam lslidar_x10_driver rtabmap_ros robot_state_publisher tf tf2_ros; do
  run_shell "rospack find $package 2>/dev/null"
done

section "running sensor and ROS processes"
run_shell "ps -ef | grep -E 'roscore|rosmaster|roslaunch|astra|orbbec|openni|usb_cam|lslidar|rtabmap|robot_state|static_transform|camera' | grep -v grep"
run_shell "ss -lntup | sed -n '1,200p'"
run_shell "systemctl status ssh --no-pager 2>/dev/null | sed -n '1,80p'"

section "camera calibration and robot geometry files"
run_shell "find /home /etc/ros -maxdepth 7 -type f \\( -iname '*camera*.yaml' -o -iname '*calib*.yaml' -o -iname '*.urdf' -o -iname '*.xacro' -o -iname '*astra*.launch' -o -iname '*rtabmap*.launch' \\) 2>/dev/null | head -400"
run_shell "find /home -maxdepth 7 -type f \\( -iname '*.launch' -o -iname '*.urdf' -o -iname '*.xacro' \\) -print0 2>/dev/null | xargs -0 grep -nE 'static_transform_publisher|camera_link|camera_(rgb|depth|color)_optical_frame|depth_registered|depth_align|camera_info|lslidar|frame_id.*laser' 2>/dev/null | head -500"
run_shell "find /home -path '*/.ros/camera_info/*' -type f -maxdepth 7 -print -exec sed -n '1,100p' {} \; 2>/dev/null"

if command -v rostopic >/dev/null 2>&1 && timeout 3 rostopic list >/tmp/kybot_rostopic_list.$$ 2>/dev/null; then
  section "live ROS1 graph"
  sed -n '1,300p' /tmp/kybot_rostopic_list.$$
  rm -f /tmp/kybot_rostopic_list.$$

  for topic in \
    /camera/rgb/camera_info \
    /camera/color/camera_info \
    /camera/depth/camera_info \
    /camera/depth_registered/camera_info \
    /camera/rgb/image_raw \
    /camera/color/image_raw \
    /camera/depth/image_raw \
    /camera/depth_registered/image_raw \
    /camera/depth/points \
    /scan \
    /imu/data \
    /odom \
    /tf \
    /tf_static; do
    if rostopic list 2>/dev/null | grep -Fxq "$topic"; then
      run_shell "rostopic type '$topic'"
      run_shell "timeout 4 rostopic echo -n 1 '$topic' | sed -n '1,140p'"
      run_shell "timeout 6 rostopic hz '$topic' | sed -n '1,40p'"
    fi
  done

  section "live parameters and TF hints"
  run_shell "rosparam list | grep -Ei 'camera|astra|depth|rgb|laser|robot_description|use_sim_time' | head -300"
  run_shell "rosparam get /use_sim_time 2>/dev/null"
  run_shell "rosparam get /robot_description 2>/dev/null | grep -E 'camera|optical|laser|joint|origin' | head -300"
else
  section "live ROS1 graph"
  echo "ROS master is not reachable; no live topic, rate, calibration-message, or TF audit was possible."
fi

section "audit end"
date --iso-8601=seconds

