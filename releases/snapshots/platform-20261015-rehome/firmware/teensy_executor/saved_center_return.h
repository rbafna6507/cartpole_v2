#pragma once
#include <stdint.h>
#include "cart_motion.h"

// Return to the existing counted midpoint. Never establishes a new reference.
// The first phase accepts inherited auto velocity/acceleration unchanged and
// brakes through the original governor. Only the settled centering phase uses
// the lower speed/acceleration/jerk bounds.
namespace saved_center_return {
constexpr uint32_t deadline_ticks=15000;
constexpr float brake_speed=1.5f,brake_acceleration=25.f,brake_jerk=150.f;
constexpr float center_speed=.08f,center_acceleration=.5f,center_jerk=10.f;
struct State {
 enum Phase:uint8_t {OFF,BRAKING,CENTERING};
 Phase phase=OFF;float demand=0;
 void reset(){phase=OFF;demand=0;}
 void begin(){phase=BRAKING;demand=0;}
 bool settledAtCenter(int32_t error_steps,const cart_motion::State& motion)const{
  return error_steps==0 && fabsf(motion.velocity)<=.0005f && fabsf(motion.acceleration)<=.01f;
 }
 cart_motion::State advance(cart_motion::State motion,float x,float rail,float dt,float configured_speed=brake_speed){
  if(phase==BRAKING && fabsf(motion.velocity)<=.002f && fabsf(motion.acceleration)<=.02f)phase=CENTERING;
  const bool braking=phase==BRAKING;
  const float acceleration=braking?brake_acceleration:center_acceleration;
  const float jerk=braking?brake_jerk:center_jerk;
  const float speed=fminf(braking?brake_speed:center_speed,configured_speed);
  const float target=braking?0:cart_motion::clamp(-3*x,-speed,speed);
  demand=cart_motion::settledVelocityAccel(motion.velocity,motion.acceleration,target,acceleration,jerk,dt);
  return cart_motion::advance(motion,x,demand,speed,acceleration,acceleration,jerk,rail,dt);
 }
};
}
