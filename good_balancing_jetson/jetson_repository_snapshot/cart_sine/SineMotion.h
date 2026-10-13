#pragma once
#include <math.h>
#include <stdint.h>

namespace sine_motion {
constexpr double PI_ = 3.14159265358979323846;
constexpr double STEPS_PER_MM = 200.0 * 16.0 / (60.0 * 2.0);
constexpr double RAMP_SECONDS = 2.0;
constexpr double MAX_AMPLITUDE_MM = 135.0; // 300 mm rail, 15 mm margin per end
constexpr double MAX_SPEED_MM_S = 1000.0;
constexpr double MAX_ACCEL_MM_S2 = 5000.0;
constexpr double SEGMENT_SECONDS = 0.001;
constexpr int MAX_STEPS_PER_SEGMENT = 100;
// Software limits, not measured motor torque/acceleration capabilities.
struct Config { double amplitudeMm, frequencyHz; };
struct Limits { double speedMmS, accelerationMmS2; };
// Reserve one pulse for rounding absolute positions to integer microsteps.
inline double pulseSpeedLimit(int stepsPerSegment) {
  return stepsPerSegment > 1 ?
    (stepsPerSegment - 1) / (SEGMENT_SECONDS * STEPS_PER_MM) : 0;
}
inline bool validLimits(Limits limits, double pulseSpeedMmS) {
  return isfinite(limits.speedMmS) && isfinite(limits.accelerationMmS2) &&
    limits.speedMmS > 0 && limits.speedMmS <= pulseSpeedMmS &&
    limits.accelerationMmS2 > 0;
}

inline double speedBound(Config c) {
  return c.amplitudeMm * (2 * PI_ * c.frequencyHz + 1.875 / RAMP_SECONDS);
}
inline double accelerationBound(Config c) {
  const double w = 2 * PI_ * c.frequencyHz;
  return c.amplitudeMm * (w*w + 3.75*w/RAMP_SECONDS +
                          5.774/(RAMP_SECONDS*RAMP_SECONDS));
}
inline bool valid(Config c, Limits limits = {MAX_SPEED_MM_S, MAX_ACCEL_MM_S2}) {
  return isfinite(c.amplitudeMm) && isfinite(c.frequencyHz) &&
    c.amplitudeMm >= 0.5 && c.amplitudeMm <= MAX_AMPLITUDE_MM &&
    c.frequencyHz >= 0.02 && c.frequencyHz <= 5.0 &&
    validLimits(limits, pulseSpeedLimit(MAX_STEPS_PER_SEGMENT)) &&
    speedBound(c) <= limits.speedMmS &&
    accelerationBound(c) <= limits.accelerationMmS2;
}
inline double smooth(double u) {
  if (u <= 0) return 0;
  if (u >= 1) return 1;
  return u*u*u*(10 + u*(-15 + 6*u));
}
inline double positionMm(Config c, double t, double finishAt = -1) {
  double envelope = smooth(t / RAMP_SECONDS);
  if (finishAt >= 0 && t >= finishAt)
    envelope = 1 - smooth((t - finishAt) / RAMP_SECONDS);
  return c.amplitudeMm * envelope * sin(2 * PI_ * c.frequencyHz * t);
}
inline int32_t positionSteps(Config c, double t, double finishAt = -1) {
  return (int32_t)lround(positionMm(c, t, finishAt) * STEPS_PER_MM);
}
} // namespace sine_motion
