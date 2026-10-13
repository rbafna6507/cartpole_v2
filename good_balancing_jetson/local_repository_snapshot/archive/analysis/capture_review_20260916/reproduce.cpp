// Diagnostic of the production capture gate, not a reconstruction of hidden
// estimator state or measured hardware motion. Compile from this directory.
#include "../../swingup/swing_controller.h"
#include <cassert>
#include <cstdio>
int main() {
  swing_control::Parameters p;
  p.amax_s=20; p.amax_b=16; p.jmax=40;
  const auto k=swing_control::gains(p);
  // Representative state near the 275.8 s capture; here theta is deliberately
  // supplied as the estimated state, which was not recorded by the firmware.
  float theta=.0844f, omega=-2.828f, x=-.11272f;
  cart_motion::State s; s.velocity=.479f; s.acceleration=4.96f;
  const float demand=swing_control::balance(k,theta,omega,x,s.velocity);
  const float ramp=fabsf(demand-s.acceleration)/p.jmax;
  const bool accepted=swing_control::canCapture(p,k,theta,omega,x,s.velocity,s.acceleration);
  assert(accepted && ramp>.20f);
  std::printf("Representative state accepted=%d; balance demand=%.4f m/s^2; acceleration=%.4f; full slew=%.1f ms; gate forecast=100 ms\n",accepted,demand,s.acceleration,ramp*1000);
  float max_jerk=0; int first_rail=-1,first_lost=-1;
  for(int ms=1;ms<=300;ms++) {
    const auto old=s;
    s=cart_motion::advance(s,x,swing_control::balance(k,theta,omega,x,s.velocity),p.vmax,p.amax_b,p.amax_s,p.jmax,p.rail,.001f);
    const float jerk=fabsf(s.acceleration-old.acceleration)/.001f;
    max_jerk=fmaxf(max_jerk,jerk); assert(jerk<=p.jmax+.001f);
    x+=s.velocity*.001f;
    omega+=(swing_control::kGravity*sinf(theta)-s.acceleration*cosf(theta))/p.leff*.001f;
    theta=swing_control::wrap(theta+omega*.001f);
    if(s.brake_direction && first_rail<0) first_rail=ms;
    if(fabsf(theta)>p.giveup && first_lost<0) {first_lost=ms;break;}
  }
  std::printf("Idealized nonlinear continuation: giveup at %d ms; first rail brake %d ms (-1=none before exit); max command jerk %.4f m/s^3\n",first_lost,first_rail,max_jerk);
}
