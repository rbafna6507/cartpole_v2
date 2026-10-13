#include "../swingup/rail_recovery.h"
#include <cassert>
#include <cstdio>
#include <initializer_list>
void scenario(float initial_x,float initial_v,float initial_a,float drive,float jerk,float vmax=.8f){
 cart_motion::State m;m.velocity=initial_v;m.acceleration=initial_a;
 rail_recovery::State recovery;
 float x=initial_x;bool started=false,done=false;float peak=fabsf(x);
 for(int i=0;i<10000;++i){
  if(recovery.phase==rail_recovery::NONE && recovery.atEdge(x,.15f)){recovery.begin(x,.15f);started=true;}
  float request=x<0?-drive:drive;
  if(recovery.phase!=rail_recovery::NONE){
   if(recovery.update(x,m,.001f)){done=true;assert(fabsf(x)<=.13001f);assert(m.velocity*initial_x<=.0007f);assert(fabsf(m.velocity)<=.15501f);assert(fabsf(m.acceleration)<=1.50001f);break;}
   assert(!recovery.timedOut());
   request=recovery.demand(x,m,vmax,drive,jerk,.001f);
  }
  const auto previous=m;
  m=cart_motion::advance(m,x,request,vmax,drive,drive,jerk,.15f,.001f);
  if(m.brake_direction && recovery.phase==rail_recovery::NONE){recovery.begin(x,.15f,m.brake_direction);started=true;}
  x+=m.velocity*.001f;peak=fmaxf(peak,fabsf(x));
  assert(fabsf(m.acceleration-previous.acceleration)<=jerk*.001f+1e-5f);
  assert(fabsf(m.velocity)<=vmax+.002f);assert(fabsf(x)<.14f);
 }
 assert(started&&done);
 // Edge-started recovery must finish near its boundary without seeking center.
 if(fabsf(initial_x)>.135f && fabsf(initial_v)<.01f)assert(fabsf(x)>.12f);
 printf("x0=%+.3f v0=%+.3f: return complete at %+.3f mm; peak |x|=%.3f mm\n",initial_x,initial_v,x*1000,peak*1000);
}
void handoffChecks(){
 for(int sign:{-1,1}){
  rail_recovery::State r;r.begin(sign*.129f,.15f,sign);
  cart_motion::State m;m.velocity=-sign*.304f;m.acceleration=-sign*11.214f;
  assert(!r.update(sign*.129f,m,.001f)); // Old controller released this state.
  m.velocity=0;m.acceleration=0;
  assert(!r.update(sign*.136f,m,.001f));assert(r.phase==rail_recovery::RETURNING);
  m.velocity=-sign*.156f;assert(!r.update(sign*.129f,m,.001f));
  m.velocity=-sign*.15f;m.acceleration=-sign*1.501f;assert(!r.update(sign*.129f,m,.001f));
  m.acceleration=-sign*1.5f;m.brake_direction=sign;assert(!r.update(sign*.129f,m,.001f));
  m.brake_direction=0;assert(r.update(sign*.129f,m,.001f));
  // Residual outward drift after a late stop beyond the normal boundary must
  // permit inward return, not latch indefinitely at the normal boundary.
  r.begin(sign*.137f,.15f,sign);m.velocity=sign*.0002f;m.acceleration=0;m.brake_direction=sign;
  float x=sign*.137f;bool done=false;
  for(int i=0;i<2000;++i){
   if(r.update(x,m,.001f)){done=true;break;}
   const auto previous=m;
   m=cart_motion::advance(m,x,r.demand(x,m,.8f,12,60,.001f),.8f,12,12,60,.15f,.001f);
   x+=m.velocity*.001f;
   assert(fabsf(x)<.14f);assert(fabsf(m.acceleration-previous.acceleration)<=.06001f);
  }
  assert(done);
 }
 // Zero acceleration: triangular stop distance = v*sqrt(v/j); high-speed
 // case reaches the acceleration cap, and already-braking states stay finite.
 assert(fabsf(cart_motion::stoppingDistance(.8f,0,15,120)-.8f*sqrtf(.8f/120))<1e-6f);
 assert(fabsf(cart_motion::stoppingDistance(1,0,1,10)-.55f)<1e-6f);
 assert(cart_motion::stoppingDistance(0,0,12,60)==0);
 assert(cart_motion::stoppingDistance(0,-1,12,60)==0);
 assert(cart_motion::stoppingDistance(.01f,-5,12,60)>=0);
}
int main(){
 handoffChecks();
 rail_recovery::State r;
 assert(!r.atEdge(.134f,.15f));assert(r.atEdge(.136f,.15f));
 cart_motion::State low;low.velocity=.01f;
 assert(cart_motion::advance(low,.134f,0,.75f,15,15,50,.15f,.001f).brake_direction==0);
 for(int sign:{-1,1}){
  scenario(sign*.01f,sign*.8f,0,18,100);
  scenario(sign*.130f,sign*.1f,0,18,100);
  scenario(sign*.136f,0,0,18,100);
  scenario(sign*.136f,-sign*.4f,0,18,100);
  scenario(sign*.137f,0,0,.5f,10);
 }
 r.begin(.137f,.15f);for(int i=0;i<8100;++i)r.update(.137f,{},.001f);
 assert(r.timedOut());r.reset();assert(r.phase==rail_recovery::NONE&&!r.timedOut());
 // An early brake must settle before release even if already inside the boundary.
 r.begin(.05f,.15f,1);cart_motion::State inward;inward.velocity=-.01f;inward.acceleration=-1;
 assert(!r.update(.06f,inward,.001f));
 inward.velocity=0;inward.acceleration=0;assert(r.update(.06f,inward,.001f));
 // Crossing the boundary while still accelerating outward must not release.
 r.begin(.136f,.15f,1);cart_motion::State outward;outward.velocity=.004f;outward.acceleration=1;
 assert(!r.update(.129f,outward,.001f));
 assert(fabsf(cart_motion::stoppingDistance(.75f,0,15,50)-.09185587f)<1e-6f);
}
