#include "../swingup/swing_controller.h"
#include <cassert>
#include <initializer_list>
#include <cmath>
#include <cstdio>
int main(){
 swing_control::Parameters p;p.ke=0;p.kpx=0;p.kdx=0;
 const float dt=.001f,pi=swing_control::kPi;
 for(float error:{-.2f,-.10f,0.f,.1f,.2f}){
  swing_control::PumpState s;cart_motion::State m;float x=0;
  for(int i=0;i<200;++i){
   float a=swing_control::swing(p,s,pi+error,0,x,m.velocity,dt,m.acceleration);
   if(i<118)assert(a==1);if(i>120)assert(a==0);
   auto next=cart_motion::advance(m,x,a,p.vmax,p.amax_s,p.amax_s,p.jmax,p.rail,dt);
   assert(fabsf(next.acceleration-m.acceleration)<=p.jmax*dt+.00001f);
   x+=next.velocity*dt;m=next;
  }
  assert(fabsf(x)<.025f);
 }
 for(float x:{-.13f,.13f}){swing_control::PumpState s;assert(swing_control::swing(p,s,pi,0,x,0,dt)==0);}
 for(float w:{-2.f,2.f}){swing_control::PumpState s;assert(swing_control::swing(p,s,pi,w,0,0,dt)==0);}
 swing_control::PumpState up;assert(swing_control::swing(p,up,0,0,0,0,dt)==0);
 swing_control::PumpState active;active.elapsed=2;assert(swing_control::swing(p,active,pi,0,0,0,dt)==0);
 swing_control::PumpState p2;p.amax_s=.4f;assert(swing_control::swing(p,p2,pi,0,0,0,dt)==.4f);
 std::puts("Startup kick: bounded duration, angle offsets, no edge/upright/moving rearm, acceleration and jerk limits passed");
}
