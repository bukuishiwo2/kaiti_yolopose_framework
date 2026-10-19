#!/usr/bin/env python3
"""Build-copy preparation only. Does not launch, stop or configure a motor.

Copy three vendor source files, transform only the copies, then build separately.
Fail on unknown source layout instead of patching unexpected vendor code.
"""
import argparse
from pathlib import Path
import shutil
import subprocess


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise RuntimeError(f'Unknown vendor source layout at: {old[:70]}')
    return text.replace(old, new, 1)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--assets', required=True)
    args = parser.parse_args()
    target = Path('/home/duct/pose3d_motion_experiment/guarded_motor_source')
    if target.exists():
        raise RuntimeError('Refusing to overwrite existing experimental source')
    vendor = Path('/data/ductcleanrob/src/motor_driver')
    header = (vendor / 'include/motor_driver/M0601C/wheelmotor.h').read_text()
    source = (vendor / 'src/M0601C_Motor/wheelmotor.cpp').read_text()
    main_source = (vendor / 'src/M0601C_Motor/Wheel_Motor_Driver.cpp').read_text()
    header = '#include <chrono>\n#include "command_watchdog.hpp"\n#include <geometry_msgs/msg/twist_stamped.hpp>\n' + header
    header = replace_once(header, 'private:', 'private:\n    duct_experiment::CommandWatchdog command_watchdog_;')
    header = header.replace('geometry_msgs::msg::Twist', 'geometry_msgs::msg::TwistStamped')
    source = source.replace('geometry_msgs::msg::Twist', 'geometry_msgs::msg::TwistStamped')
    source = replace_once(source, '    init_Serial();', '''    if (!declare_parameter<bool>("guarded_mode", false)) {
      throw std::runtime_error("Experimental driver disabled: serial port NOT opened");
    }
    init_Serial();''')
    source = replace_once(source, '      cmd_vel_topic_, qos,',
                          '      "/research/motion/motor_request", rclcpp::QoS(1),')
    zero = 'wheel_left_vel_=wheel_right_vel_=mWheel_motor1_=mWheel_motor2_=mWheel_motor3_=mWheel_motor4_=0;'
    steady = 'std::chrono::duration<double>(std::chrono::steady_clock::now().time_since_epoch()).count()'
    source = replace_once(source, 'void Wheel_Motor::joint_state_pub_callback(){',
        'void Wheel_Motor::joint_state_pub_callback(){\n  if (!command_watchdog_.fresh(' + steady + ')) { ' + zero + ' }')
    source = replace_once(source, '  double linear_x = msg->linear.x;', '''  const double stamp = rclcpp::Time(msg->header.stamp).seconds();
  if (!command_watchdog_.accept(''' + steady + ''', this->now().seconds(), stamp,
      msg->twist.linear.x, msg->twist.linear.y, msg->twist.angular.z,
      msg->header.frame_id == "base_link")) { ''' + zero + ''' return; }
  double linear_x = msg->twist.linear.x;''')
    source = source.replace('msg->linear.y', 'msg->twist.linear.y').replace('msg->angular.z', 'msg->twist.angular.z')
    (target / 'include/motor_driver/M0601C').mkdir(parents=True)
    (target / 'include/motor_driver/M0601C/wheelmotor.h').write_text(header)
    (target / 'wheelmotor.cpp').write_text(source)
    (target / 'Wheel_Motor_Driver.cpp').write_text(main_source)
    assets = Path(args.assets)
    for name in ('CMakeLists.txt', 'command_watchdog.hpp', 'watchdog_test.cpp'):
        shutil.copy2(assets / name, target / name)
    subprocess.run(['cmake', '-S', str(target), '-B', str(target / 'build')], check=True)
    subprocess.run(['cmake', '--build', str(target / 'build'), '-j1'], check=True)
    print('Built ONLY; guarded_mode defaults false; original driver untouched')


if __name__ == '__main__':
    main()
