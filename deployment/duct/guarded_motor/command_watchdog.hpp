#pragma once
#include <cmath>

// Clock arguments are seconds: steady for expiry, ROS for source age.
// Pure helper tested without opening a serial device.
namespace duct_experiment {
class CommandWatchdog {
  bool valid_ = false;
  double received_ = 0.0;
  double last_stamp_ = -1.0;
public:
  bool accept(double steady, double ros_now, double stamp,
              double vx, double vy, double wz, bool base_frame) {
    valid_ = false;
    if (!std::isfinite(steady) || !std::isfinite(ros_now) || !std::isfinite(stamp) ||
        !std::isfinite(vx) || !std::isfinite(vy) || !std::isfinite(wz) ||
        !base_frame || stamp <= last_stamp_ || ros_now < stamp ||
        ros_now - stamp > 0.25 || vx < 0.0 || vx > 0.05 || vy != 0.0 || wz != 0.0) {
      return false;
    }
    last_stamp_ = stamp;
    received_ = steady;
    valid_ = true;
    return true;
  }
  bool fresh(double steady) const {
    return valid_ && std::isfinite(steady) && steady >= received_ && steady - received_ < 0.25;
  }
};
}
