#include "../swingup/rail_recovery.h"
#include <cstdio>
#include <cmath>
int main(){
 float x0,v0,a0,vmax,amax,j;int side,n=0,failed=0;float maxx=0,maxv=0,maxa=0,maxt=0;
 while(scanf("%f %f %f %d %f %f %f",&x0,&v0,&a0,&side,&vmax,&amax,&j)==7){
  n++;float x=x0;cart_motion::State m;m.velocity=v0;m.acceleration=a0;m.brake_direction=side;
  rail_recovery::State r;r.begin(x,.15f,side);bool done=false,rail=false,jerk=false;
  float peak=fabsf(x);
  for(int i=0;i<8000;++i){
   if(r.update(x,m,.001f)){done=true;maxv=fmaxf(maxv,fabsf(m.velocity));maxa=fmaxf(maxa,fabsf(m.acceleration));maxt=fmaxf(maxt,i*.001f);break;}
   const auto old=m;float request=r.demand(x,m,vmax,amax,j,.001f);
   m=cart_motion::advance(m,x,request,vmax,amax,amax,j,.15f,.001f);x+=m.velocity*.001f;peak=fmaxf(peak,fabsf(x));
   if(fabsf(x)>=.14f){rail=true;break;}
   if(fabsf(m.acceleration-old.acceleration)>j*.001f+.00005f){jerk=true;break;}
  }
  maxx=fmaxf(maxx,peak);
  if(!done || rail || jerk || fabsf(m.velocity)>.15501f || fabsf(m.acceleration)>1.50001f){
   failed++;printf("FAIL %d x0=%.5f v0=%.4f a0=%.3f side=%d j=%.0f peak=%.6f done=%d rail=%d jerk=%d\n",n,x0,v0,a0,side,j,peak,done,rail,jerk);
  }
 }
 printf("Recorded cases %d; failures %d; max |x| %.3f mm; max release |v| %.6f; max release |a| %.6f; max duration %.3f\n",n,failed,maxx*1000,maxv,maxa,maxt);
 return failed?1:0;
}
