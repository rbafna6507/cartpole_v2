#include "../../teensy_working_jetson_compatible/teensy_swingup/swing_controller.h"
#include <cstdio>
#include <cmath>
int main(){
 for(float L:{.124f,.166f,.200f})for(float lag:{0.0f,.015f}){
  swing_control::Parameters p;p.leff=.166;p.bal_pw=4;p.pc1=-1;p.pc2=-2;p.bw=12;p.rail=.28;p.vmax=.5;p.amax_s=p.amax_b=12;p.jmax=150;
  auto k=swing_control::uprightGains(p);cart_motion::State c;float q=.025,w=0,x=0,qh=q,wh=0,actual=0,mx=0,mq=0;int i=0;
  for(;i<15000;i++){
   float measured=q+.003f*sinf(i*.001f*2*3.14159265f*35);
   swing_control::estimate(measured,p.bw,.001,qh,wh);
   float request=swing_control::balance(k,qh,wh,x,c.velocity);
   c=cart_motion::advance(c,x,request,p.vmax,p.amax_b,p.amax_b,p.jmax,p.rail,.001);
   x+=c.velocity*.001;actual=lag==0?c.acceleration:actual+.001/lag*(c.acceleration-actual);
   float alpha=(9.81f*sinf(q)-actual*cosf(q))/L-.37f*w;
   q+=w*.001+.5f*alpha*.000001;w+=alpha*.001;mx=fmaxf(mx,fabsf(x));mq=fmaxf(mq,fabsf(q));
   if(fabsf(q)>.3491 || fabsf(x)>.12)break;
  }
  printf("L=%.3f lag=%.3f duration=%.3f max_angle=%.2fdeg max_x=%.1fmm final_angle=%.2fdeg\n",L,lag,i*.001,mq*180/3.14159265,mx*1000,q*180/3.14159265);
 }
}
