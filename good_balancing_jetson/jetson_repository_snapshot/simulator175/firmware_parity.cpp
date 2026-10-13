// Host-side reference fixtures for the JavaScript firmware-equation port.
#include "../swingup/swing_controller.h"
#include <cstdio>
#include <cmath>
int main(){
  swing_control::Parameters p;auto k=swing_control::gains(p);
  std::printf("geometry %d %.9g %.9g %.9g %.9g\n",cart_hardware::pulley_teeth,cart_hardware::steps_per_m,p.vmax,p.amax_s,p.jmax);
  std::printf("gain %.9g %.9g %.9g %.9g\n",k.k1,k.k2,k.k3,k.k4);
  auto uk=swing_control::uprightGains(p);
  std::printf("upright_gain %.9g %.9g %.9g %.9g\n",uk.k1,uk.k2,uk.k3,uk.k4);
  float angle=3.1f,rate=0;
  for(int i=0;i<1000;++i){
    const float measured=swing_control::wrap(3.1f+i*.007f+.0015f*std::sin(i*1.3f));
    const float previous_angle=angle,previous_rate=rate;
    swing_control::estimate(measured,p.bw,.001f,angle,rate);
    std::printf("estimate %.9g %.9g %.9g %.9g %.9g %.9g\n",p.bw,measured,previous_angle,previous_rate,angle,rate);
  }
  for(int i=0;i<100;++i){
    float v=.02f*i,a=12*std::sin(i*.31f),j=20+5*i;
    std::printf("stop %.9g %.9g %.9g %.9g %.9g\n",v,a,j,cart_motion::stoppingDistance(v,a,15,j),cart_motion::settledVelocityAccel(v,a,0,15,j,.001f));
  }
  for(int i=0;i<100;++i){
    float x=.13f*std::sin(i*.37f),request=8*std::sin(i*.61f);
    cart_motion::State s;s.velocity=1.2f*std::sin(i*.19f);s.acceleration=6*std::cos(i*.23f);
    auto n=cart_motion::advance(s,x,request,1.5f,6,6,150,.15f,.001f);
    std::printf("motion %.9g %.9g %.9g %.9g %.9g %.9g %d\n",x,request,s.velocity,s.acceleration,n.velocity,n.acceleration,n.brake_direction);
  }
  for(int i=0;i<80;++i){
    float q=.8f*std::sin(i*.51f),w=3*std::cos(i*.23f),x=.10f*std::sin(i*.13f);
    float v=.6f*std::sin(i*.47f),a=8*std::cos(i*.23f),pump=10*std::sin(i*.63f);
    std::printf("approach %.9g %.9g %.9g %.9g %.9g %.9g %.9g\n",q,w,x,v,a,pump,swing_control::approach(p,q,w,x,v,a,pump,.001f));
  }
  for(int i=0;i<100;++i){
    float theta=.65f*std::sin(i*.71f),omega=3.2f*std::cos(i*.43f);
    float x=.13f*std::sin(i*.37f),v=.75f*std::sin(i*.19f),a=15*std::cos(i*.23f);
    std::printf("capture %.9g %.9g %.9g %.9g %.9g %d\n",theta,omega,x,v,a,
      swing_control::canCapture(p,k,theta,omega,x,v,a));
  }
}
