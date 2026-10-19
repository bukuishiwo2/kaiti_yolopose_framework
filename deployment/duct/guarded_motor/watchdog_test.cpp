#include "command_watchdog.hpp"
#include <cassert>
#include <limits>
using duct_experiment::CommandWatchdog;
int main() {
  CommandWatchdog gate;
  assert(!gate.fresh(1));
  assert(gate.accept(1, 100, 99.99, .02, 0, 0, true));
  assert(gate.fresh(1.249));
  assert(!gate.fresh(1.25));
  assert(!gate.fresh(.99));
  assert(!gate.accept(2, 100, 99.99, .02, 0, 0, true)); // replay
  assert(!gate.fresh(2));
  assert(!gate.accept(2, 101, 100, .02, 0, 0, true)); // stale source
  assert(!gate.accept(2, 101, 102, .02, 0, 0, true)); // future
  assert(!gate.accept(2, 101, 100.99, .06, 0, 0, true));
  assert(!gate.accept(2, 101, 100.99, -.01, 0, 0, true));
  assert(!gate.accept(2, 101, 100.99, .01, .01, 0, true));
  assert(!gate.accept(2, 101, 100.99, .01, 0, .01, true));
  assert(!gate.accept(2, 101, 100.99, .01, 0, 0, false));
  assert(!gate.accept(2, 101, 100.99, std::numeric_limits<double>::quiet_NaN(), 0, 0, true));
  assert(gate.accept(2, 101, 100.99, 0, 0, 0, true));
  assert(gate.fresh(2.1));
  assert(gate.accept(3, 102, 101.99, .05, 0, 0, true));
  assert(!gate.fresh(3.25));
}
