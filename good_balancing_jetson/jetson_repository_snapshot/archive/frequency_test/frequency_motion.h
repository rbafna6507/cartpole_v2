#pragma once
#include <math.h>

namespace frequency_test {
constexpr double pi = 3.14159265358979323846;
constexpr double rail_mm = 300, margin_mm = 15;
constexpr double max_travel_mm = rail_mm - 2 * margin_mm;
constexpr int motor_steps = 200, microsteps = 16, pulley_teeth = 60;
constexpr double belt_pitch_mm = 2;
constexpr int timer_hz = 125000;
constexpr double steps_per_m = motor_steps * microsteps * 1000.0 / (pulley_teeth * belt_pitch_mm);
constexpr double max_speed = timer_hz * 0.5 / steps_per_m;
struct Config {
  double travel_mm, hz, ramp_s;
  Config(double travel=100, double frequency=.25, double ramp=2)
    : travel_mm(travel), hz(frequency), ramp_s(ramp) {}
};
struct Sample { double x, v, a, j; };
inline double rampSeconds(Config c) { return c.ramp_s; }
inline Sample sample(Config c, double t, double finish_at = -1) {
  if (t <= 0) return {0, 0, 0, 0};
  const double ramp = rampSeconds(c);
  double e=1, d1=0, d2=0, d3=0;
  const bool finishing = finish_at >= 0 && t >= finish_at;
  double u = finishing ? (t-finish_at)/ramp : t/ramp;
  if (finishing && u >= 1) return {0,0,0,0};
  if (u < 1) {
    // Quintic amplitude envelope: zero velocity and acceleration at endpoints.
    e = u*u*u*(10+u*(-15+6*u));
    d1 = 30*u*u*(1-u)*(1-u)/ramp;
    d2 = 60*u*(1-u)*(1-2*u)/(ramp*ramp);
    d3 = (60-360*u+360*u*u)/(ramp*ramp*ramp);
    if (finishing) {e=1-e; d1=-d1; d2=-d2; d3=-d3;}
  }
  const double w=2*pi*c.hz, A=c.travel_mm/2000;
  const double s=sin(w*t), co=cos(w*t);
  return {A*e*s, A*(d1*s+e*w*co),
          A*(d2*s+2*d1*w*co-e*w*w*s),
          A*(d3*s+3*d2*w*co-3*d1*w*w*s-e*w*w*w*co)};
}
inline double speedBound(Config c) {
  return c.travel_mm/2000 * (2*pi*c.hz + 1.875/rampSeconds(c));
}
inline bool valid(Config c) {
  return isfinite(c.travel_mm) && isfinite(c.hz) && isfinite(c.ramp_s) &&
         c.ramp_s >= 0.5 && c.ramp_s <= 30 && c.travel_mm >= 1 &&
         c.travel_mm <= max_travel_mm && c.hz >= 0.02 && c.hz <= 5 &&
         speedBound(c) <= max_speed;
}
}
