#pragma once
#include "cart_motion.h"
// Position target controller over the source firmware's jerk-limited velocity
// update. x is emitted-step position, NOT an independent position measurement.
namespace characterization {
struct Profile {
 cart_motion::State state;
 float target=0, vmax=.03f, amax=.3f, jerk=3.f, half=.15f;
 bool active=false;
 bool update(float x) {
  float desired=cart_motion::clamp(8*(target-x),-vmax,vmax);
  float acceleration=cart_motion::settledVelocityAccel(state.velocity,state.acceleration,desired,amax,jerk,.001f);
  state=cart_motion::advance(state,x,acceleration,vmax,amax,amax,jerk,half,.001f);
  if(fabsf(target-x)<.00010f && fabsf(state.velocity)<.001f && fabsf(state.acceleration)<.02f){state={};active=false;return true;}
  return false;
 }
};
}
