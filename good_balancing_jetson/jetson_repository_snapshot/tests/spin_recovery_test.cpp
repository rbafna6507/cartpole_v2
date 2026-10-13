#include "../swingup/spin_recovery.h"
#include <cassert>
#include <cstdio>
#include <initializer_list>
using namespace spin_recovery;
void thresholdTests(){
 for(float w:{0.f,25.f,-25.f,30.f,-30.f,149.999f,150.f,-149.999f,-150.f})assert(!trigger(w));
 for(float w:{150.001f,-150.001f,160.f,-160.f})assert(trigger(w));
}
void customTests(){
 assert(validLimits(50,10));assert(!validLimits(10,10));assert(!validLimits(5,10));assert(!validLimits(50,0));assert(!validLimits(INFINITY,10));
 assert(trigger(36,35));assert(!trigger(36,50));assert(trigger(-51,50));
 State s;cart_motion::State m;s.begin(0);assert(!s.update(0,m,20,true,0,20));assert(s.update(0,m,19.9f,true,0,20));
}
void stateTests(){
 State s;cart_motion::State m;
 for(float w:{10.f,-10.f,25.f,-25.f}){
  s.begin(0);assert(!s.update(0,m,w,true,0));assert(s.phase==WAITING);
  assert(!s.update(0,m,w,true,60000000));assert(!s.timedOut(60000000));
  assert(s.update(0,m,w<0?-9.999f:9.999f,true,60000000));assert(s.phase==NONE);
 }
 s.begin(0);assert(!s.update(0,m,0,false,0));assert(s.update(0,m,0,true,0));
 s.begin(0);assert(!s.update(.01f,m,0,true,0));assert(s.phase==CENTERING);
 m.velocity=.006f;assert(!s.update(0,m,0,true,0));m.velocity=0;
 m.acceleration=.101f;assert(!s.update(0,m,0,true,0));m.acceleration=0;
 assert(s.update(0,m,0,true,0)); // No dwell or pendulum-angle condition.
 s.begin(0);s.update(0,m,12,true,0);
 assert(!s.update(.01f,m,0,true,60000000));assert(s.phase==CENTERING);
 assert(!s.timedOut(60000000));assert(s.timedOut(70000001));
 s.reset();uint32_t start=0xffff0000u;s.begin(start);
 assert(!s.timedOut(start+10000000u));assert(s.timedOut(start+10000001u));
 s.reset();assert(s.phase==NONE&&!s.timedOut(60000000));
}
void trajectory(float x,float v,float a){
 State s;s.begin(0);cart_motion::State m;m.velocity=v;m.acceleration=a;
 bool done=false;float peak=fabsf(x);
 for(uint32_t now=0;now<10000000;now+=1000){
  assert(!s.update(x,m,12,true,now));
  if(s.phase==WAITING){assert(s.update(x,m,9.9f,true,now));done=true;break;}
  assert(!s.timedOut(now));
  float demand=s.demand(x,m,.8f,12,60,.001f);auto old=m;
  m=cart_motion::advance(m,x,demand,.8f,12,12,60,.15f,.001f);x+=m.velocity*.001f;
  peak=fmaxf(peak,fabsf(x));
  assert(fabsf(m.acceleration-old.acceleration)<=.06001f);
  assert(fabsf(m.velocity)<=.802f);assert(fabsf(x)<.14f);
 }
 assert(done);assert(fabsf(x)<=.003f);assert(fabsf(m.velocity)<=.005f);
 printf("PASS center then immediate low-rate release; peak |x| %.2f mm\n",peak*1000);
}
int main(){thresholdTests();customTests();stateTests();
 for(int d:{-1,1}){trajectory(d*.03f,d*.6f,d*2);trajectory(d*.136f,0,0);trajectory(d*.1f,-d*.2f,0);}
 puts("Rate recovery checks passed.");
}
