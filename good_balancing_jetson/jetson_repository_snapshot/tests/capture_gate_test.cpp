#include "../swingup/swing_controller.h"
#include <cassert>
#include <cmath>
int main(){
 swing_control::Parameters p;const auto k=swing_control::gains(p);
 assert(swing_control::canCapture(p,k,0,0,0,0,0));
 assert(swing_control::canCapture(p,k,.08f,-.2f,0,0,1.1f));
 assert(!swing_control::canCapture(p,k,.55f,1,0,0,8));
 assert(!swing_control::canCapture(p,k,.05f,-1,0,.31f,0));
 assert(!swing_control::canCapture(p,k,.1f,0,.13f,0,0));
 assert(!swing_control::canCapture(p,k,.3f,0,0,0,-8));
 // Under catch_v and the position gate, but momentum will trigger braking.
 assert(!swing_control::canCapture(p,k,0,0,.11f,.29f,2));
 // Recorded failed handoff: actuator is moving away from the required response.
 assert(!swing_control::canCapture(p,k,.5844f,.018f,-.006f,-.479f,-.488f));
 // More available ceiling does not loosen the policy or capture criterion.
 const float demand=swing_control::approach(p,.7f,-2,.03f,.2f,-1,5,.001f);
 const float swing_cap=p.vmax_s, balance_cap=p.vmax_b;
 p.vmax=2.0f;
 assert(swing_control::speedLimit(p,false)==swing_cap);
 assert(swing_control::speedLimit(p,true)==balance_cap);
 assert(swing_control::approach(p,.7f,-2,.03f,.2f,-1,5,.001f)==demand);
 assert(!swing_control::canCapture(p,k,.05f,-1,0,.31f,0));
 // Symmetric inbound preparation; command shaping doesn't change plant state.
 const float a=swing_control::approach(p,.7f,-2,.03f,.2f,-1,5,.001f);
 const float b=swing_control::approach(p,-.7f,2,-.03f,-.2f,1,-5,.001f);
 assert(std::fabs(a+b)<1e-5f);
 // A lower swing cap must slew down, not clip or falsely trip a mode-speed fault.
 cart_motion::State m;m.velocity=.7f;m.acceleration=3;
 float x=0;
 for(int i=0;i<1000;i++){
  const auto before=m;
  m=cart_motion::advance(m,x,0,.4f,12,12,60,10,.001f);
  assert(std::fabs(m.acceleration-before.acceleration)<=.06001f);
  assert(std::fabs(m.velocity-before.velocity)<=.01201f);
  assert(m.velocity<.8f);
  if(i==0)assert(m.velocity>.69f);
  x+=m.velocity*.001f;
 }
 assert(m.velocity<=.401f);
}
