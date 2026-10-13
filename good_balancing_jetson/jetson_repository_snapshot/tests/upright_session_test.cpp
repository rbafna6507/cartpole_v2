#include "../swingup/upright_session.h"
#include "../swingup/swing_controller.h"
#include <cassert>
#include <cstdio>
#include <initializer_list>
using namespace upright_session;
void trajectory(float x,float v,float a){
 Return r;uint32_t start=0xffff0000u;r.begin(start);
 cart_motion::State m;m.velocity=v;m.acceleration=a;
 bool done=false;
 for(uint32_t us=0;us<11000000;us+=1000){
  if(r.update(x,m,start+us)){done=true;break;}
  assert(!r.timedOut(start+us));
  auto old=m;float request=r.demand(x,m,.8f,12,60,.001f);
  m=cart_motion::advance(m,x,request,.8f,12,12,60,.15f,.001f);x+=m.velocity*.001f;
  assert(fabsf(m.acceleration-old.acceleration)<.0601f);
  assert(fabsf(m.acceleration)<=12.001f);assert(fabsf(m.velocity)<=.802f);assert(fabsf(x)<.14f);
 }
 assert(done && fabsf(x)<=.003f && fabsf(m.velocity)<=.005f && fabsf(m.acceleration)<=.1f);
 r.reset();assert(r.center.phase==spin_recovery::NONE);
}
int main(){
 assert(canStart(0,0,0,0,0,0,true));
 for(int sign:{-1,1}){
  assert(!fallen(sign*49.99f*pi/180));assert(fallen(sign*50.01f*pi/180));
  assert(fallen(sign*pi));assert(!fallen(sign*2*pi));
  assert(!canStart(sign*11*pi/180,0,0,0,0,0,true));
  assert(!canStart(0,sign*11*pi/180,0,0,0,0,true));
  assert(!canStart(0,0,sign*1.01f,0,0,0,true));
  assert(!canStart(0,0,0,sign*.031f,0,0,true));
  trajectory(sign*.03f,sign*.6f,sign*2);trajectory(sign*.136f,0,0);trajectory(sign*.1f,-sign*.2f,0);
 }
 assert(!canStart(0,0,0,0,0,0,false));assert(!canStart(NAN,0,0,0,0,0,true));
 assert(!canStart(0,0,0,0,.01f,0,true));assert(!canStart(0,0,0,0,0,.2f,true));
 Return r;r.begin(0);assert(r.timedOut(10000001));r.reset();assert(!r.timedOut(10000001));
 swing_control::Parameters p;auto automatic=swing_control::gains(p),upright=swing_control::uprightGains(p);
 assert(p.pw==7 && p.bal_pw==8);assert(upright.k1<automatic.k1);
 p.bal_pw=7;assert(swing_control::uprightGains(p).k1==automatic.k1);
 puts("Upright start, signed fall boundary, gain isolation, jerk-limited center, timeout and reset passed.");
}
