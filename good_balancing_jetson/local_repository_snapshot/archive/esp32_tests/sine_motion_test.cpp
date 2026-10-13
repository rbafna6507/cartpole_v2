#include "../cart_sine/SineMotion.h"
#include <cassert>
#include <cstdio>
#include <initializer_list>
#include <limits>

namespace sm = sine_motion;
int main() {
  const sm::Config c = {25, 0.5};
  assert(sm::valid(c));
  assert(!sm::valid({0, 0.5}));
  assert(!sm::valid({136, 0.5}));
  assert(!sm::valid({25, 0}));
  assert(!sm::valid({25, 6}));
  assert(!sm::valid({135, 5}));
  assert(!sm::valid({std::numeric_limits<double>::quiet_NaN(), 0.5}));
  assert(!sm::valid({25, std::numeric_limits<double>::infinity()}));
  const sm::Limits raised = {1250, 7500};
  assert(!sm::valid({25, 2.2}));
  assert(sm::valid({25, 2.2}, raised));
  assert(!sm::valid({135, 5}, raised));
  const double ceiling = sm::pulseSpeedLimit(100);
  assert(fabs(ceiling - 3712.5) < 1e-9);
  assert(sm::validLimits({ceiling, 100000}, ceiling));
  assert(!sm::validLimits({ceiling + 0.01, 100000}, ceiling));
  assert(!sm::validLimits({1000, 0}, ceiling));
  assert(!sm::validLimits({1000, std::numeric_limits<double>::infinity()}, ceiling));
  assert(!sm::validLimits({0, 5000}, ceiling));
  assert(sm::pulseSpeedLimit(1) == 0);
  // Rounded neighboring samples must fit the existing 100-pulse guard even
  // when the configurable mechanical caps admit faster trajectories.
  for (double amp : {25.0, 100.0, 135.0}) {
    for (double hz : {1.0, 2.2, 3.0, 4.0, 5.0}) {
      const sm::Config cfg = {amp, hz};
      if (!sm::valid(cfg, {ceiling, 200000})) continue;
      int32_t previous = 0;
      for (int i = 1; i <= 8000; ++i) {
        const int32_t target = sm::positionSteps(cfg, i*0.001, 6.0);
        assert(abs(target-previous) <= sm::MAX_STEPS_PER_SEGMENT);
        previous = target;
      }
      assert(previous == 0);
    }
  }
  assert(sm::positionSteps(c, 0) == 0);
  assert(fabs(sm::positionMm(c, 2.5) - 25) < 1e-9);
  assert(fabs(sm::positionMm(c, 3.5) + 25) < 1e-9);

  // Independent finite differences check the startup/finish derivative bounds
  // and half-microstep quantization over the full range of allowed inputs.
  const double h = 0.0001;
  for (double amp : {0.5, 25.0, 135.0}) {
    for (double hz : {0.02, 0.5, 1.0, 5.0}) {
      const sm::Config cfg = {amp, hz};
      if (!sm::valid(cfg)) continue;
      const double finish = 3.237;
      for (int i = 1; i < 60000; ++i) {
        const double t = i*h;
        const double x = sm::positionMm(cfg, t, finish);
        const double before = sm::positionMm(cfg, t-h, finish);
        const double after = sm::positionMm(cfg, t+h, finish);
        assert(fabs(x) <= amp + 1e-9);
        assert(fabs((after-before)/(2*h)) <= sm::speedBound(cfg) + 1e-5);
        assert(fabs((after-2*x+before)/(h*h)) <= sm::accelerationBound(cfg) + 0.01);
        assert(fabs(sm::positionSteps(cfg,t,finish)/sm::STEPS_PER_MM-x) <=
               0.5/sm::STEPS_PER_MM + 1e-9);
      }
      assert(sm::positionSteps(cfg, finish+sm::RAMP_SECONDS, finish) == 0);
    }
  }
  // Long runs return to the same absolute step target, without integration drift.
  for (int cycle = 2; cycle <= 10000; ++cycle)
    assert(sm::positionSteps(c, cycle / c.frequencyHz) == 0);
  puts("Sine waveform, bounds, quantization and long-run position checks passed.");
}
