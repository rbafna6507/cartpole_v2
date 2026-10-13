// Exploratory robustness screen, not a physical validation or parameter fit.
#include "../../teensy_working_jetson_compatible/teensy_swingup/swing_controller.h"
#include <cstdio>
#include <cmath>
#include <initializer_list>
int main(){
 for(float bandwidth:{8.f,12.f,20.f,30.f})for(float factor:{.8f,1.f,1.2f,1.4f,1.6f,1.8f,2.f}){
  int ok=0,n=0;float worst=15,peak=0;
  for(float L:{.15f,.162f,.175f})for(float lag:{0.f,.02f,.04f})for(float noise:{.003f,.015f})for(float start:{.025f,.15f}){
   swing_control::Parameters p;p.leff=.124;p.pw=4.5;p.pz=.85;p.pc1=-3;p.pc2=-4;p.bw=bandwidth;p.rail=.26;
   auto k=swing_control::gains(p);k.k2*=factor;
   cart_motion::State c;float q=start,w=0,x=0,qh=q,wh=0,actual=0,mx=0;int i;
   for(i=0;i<15000;i++){
    float measured=q+noise*sinf(i*.001f*2*3.14159265f*35);
    swing_control::estimate(measured,p.bw,.001,qh,wh);
    float request=swing_control::balance(k,qh,wh,x,c.velocity);
    c=cart_motion::advance(c,x,request,p.vmax,p.amax_b,p.amax_b,p.jmax,p.rail,.001);
    x+=c.velocity*.001;actual=lag==0?c.acceleration:actual+.001/lag*(c.acceleration-actual);
    float alpha=(9.81f*sinf(q)-actual*cosf(q))/L-.2f*w;
    q+=w*.001+.5f*alpha*.000001;w+=alpha*.001;mx=fmaxf(mx,fabsf(x));
    if(fabsf(q)>.6 || fabsf(x)>.24 || c.brake_direction)break;
   }
   n++;if(i==15000)ok++;worst=fminf(worst,i*.001f);peak=fmaxf(peak,mx);
  }
  printf("bw %.0f k2_factor %.1f passes %d/%d worst_s %.3f peak_x %.3f\n",bandwidth,factor,ok,n,worst,peak);
 }
}
