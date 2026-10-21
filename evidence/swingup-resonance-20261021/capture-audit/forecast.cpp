#include <iostream>
#include <iomanip>
#include <string>
#include "swing_controller.h"
using namespace swing_control;
int main(){
 Parameters p;p.leff=.124f;p.pw=3;p.pz=.85f;p.bal_pw=4.5f;p.pc1=-5;p.pc2=-6;p.vmax=1.5f;p.vmax_s=1.5f;p.vmax_b=1.5f;p.approach_v=.2f;p.catch_v=.3f;p.approach_angle=.8f;p.catch_da=4;p.amax_s=25;p.amax_b=25;p.jmax=150;p.ke=4;p.kpx=40;p.kdx=2;p.phase_soft=2;p.catch_a=.25f;p.catch_r=3;p.giveup=.8f;p.rail=.3090375f;p.rail_margin=.015f;
 std::string key;float t,q,w,x,v,a;
 std::cout<<std::setprecision(9);
 while(std::cin>>key>>t>>q>>w>>x>>v>>a){
  for(float pz:{.85f,1.f}){
   p.pz=pz;auto k=gains(p);float demand=balance(k,q,w,x,v);int gates=0;
   if(fabs(q)>=p.catch_a)gates|=1;
   if(fabs(w)>=p.catch_r)gates|=2;
   if(fabs(x)>=fmin(.12f,p.rail-2*p.rail_margin))gates|=4;
   if(fabs(v)>=fmin(p.catch_v,speedLimit(p,true)))gates|=8;
   if(fabs(demand)>=p.amax_b)gates|=16;
   if(fabs(demand-a)>p.catch_da)gates|=32;
   if(fabs(q)>.2f&&q*w>0)gates|=64;
   bool cap=canCapture(p,k,q,w,x,v,a);auto strict=p;strict.catch_v=.15f;bool capslow=canCapture(strict,k,q,w,x,v,a);
   float qq=q,ww=w,xx=x,initial=kGravity/p.leff*q*q+w*w,maxq=fabs(q),maxx=fabs(x);cart_motion::State motion;motion.velocity=v;motion.acceleration=a;int brake=0,diverge=0;
   for(int i=0;i<36;i++){
    float request=balance(k,qq,ww,xx,motion.velocity);motion=cart_motion::advance(motion,xx,request,speedLimit(p,true),p.amax_b,fmax(p.amax_s,p.amax_b),p.jmax,p.rail,.005f,p.rail_margin);
    if(motion.brake_direction)brake=1;xx+=motion.velocity*.005f;float alpha=(kGravity*sinf(qq)-motion.acceleration*cosf(qq))/p.leff;qq=wrap(qq+ww*.005f+.5f*alpha*.005f*.005f);ww+=alpha*.005f;maxq=fmax(maxq,fabs(qq));maxx=fmax(maxx,fabs(xx));if(fabs(qq)>=p.giveup||fabs(xx)>p.rail-p.rail_margin-p.rail_hysteresis)diverge=1;
   }
   float final=kGravity/p.leff*qq*qq+ww*ww;
   std::cout<<key<<' '<<t<<' '<<pz<<' '<<gates<<' '<<cap<<' '<<capslow<<' '<<demand<<' '<<qq<<' '<<ww<<' '<<xx<<' '<<motion.velocity<<' '<<motion.acceleration<<' '<<final/(initial+1e-9f)<<' '<<brake<<' '<<diverge<<' '<<maxq<<' '<<maxx<<'\n';
  }
 }
}
