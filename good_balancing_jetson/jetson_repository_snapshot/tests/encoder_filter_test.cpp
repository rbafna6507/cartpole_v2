#include "../swingup/swing_controller.h"
#include <cassert>
#include <cmath>
#include <cstdio>
#include <cstdint>
#include <initializer_list>

constexpr float dt=.001f, pi=swing_control::kPi, lsb=2*pi/4096;
float quantize(float x){return swing_control::wrap(std::round(x/lsb)*lsb);}
struct Response { double lag_ms, gain; };
Response sinusoid(float bw,float hz) {
  float a=0,r=0;double c=0,s=0;int count=0;
  for(int i=0;i<20000;++i){
    const double phase=2*double(pi)*hz*i*dt;
    swing_control::estimate(quantize(.05f*std::sin(phase)),bw,dt,a,r);
    if(i>=2000){c+=r*std::cos(phase);s+=r*std::sin(phase);++count;}
  }
  return {std::atan2(s,c)/(2*pi*hz)*1000,2*std::hypot(c,s)/count/(.05*2*pi*hz)};
}
int main(){
  swing_control::Parameters p;assert(p.bw==50);
  for(float bad:{0.f,-1.f,500.f,INFINITY,NAN})assert(!swing_control::validEstimatorBandwidth(bad));
  for(float good:{.1f,10.f,30.f,100.f})assert(swing_control::validEstimatorBandwidth(good));
  float reset_angle=-1.f,reset_rate=4128061.5f;
  swing_control::resetEstimate(.0828f,reset_angle,reset_rate);
  assert(std::fabs(reset_angle-.0828f)<1e-6f && reset_rate==0);
  for(int i=0;i<100;++i)swing_control::estimate(.0828f,p.bw,dt,reset_angle,reset_rate);
  assert(std::fabs(reset_rate)<.0001f);
  for(float hz:{1.f,3.f,5.f}){
    const auto old=sinusoid(10,hz),now=sinusoid(p.bw,hz);
    assert(old.lag_ms>25 && now.lag_ms>0 && now.lag_ms<11);
    assert(now.gain>.97 && now.gain<1.02);
    std::printf("%.0f Hz: rate lag %.2f -> %.2f ms, gain %.3f -> %.3f\n",hz,old.lag_ms,now.lag_ms,old.gain,now.gain);
  }
  // Full rotations through both signed wrap boundaries: no false rate spikes.
  for(float speed:{-40.f,-6.f,6.f,40.f}){
    float angle=3.1f,rate=0;
    for(int i=0;i<4000;++i){
      const float measured=quantize(3.1f+speed*i*dt);
      swing_control::estimate(measured,p.bw,dt,angle,rate);
      assert(std::isfinite(angle) && std::isfinite(rate));
      if(i>150)assert(std::fabs(rate-speed)<.2f);
    }
  }
  // Bounded one-count stationary jitter at +/-pi cannot look like a spin.
  for(float bw:{.1f,30.f,100.f}){
    float angle=pi-lsb/2,rate=0;
    for(int i=0;i<10000;++i){
      const float measured=quantize(pi-lsb/2+(i%2?lsb/2:-lsb/2));
      swing_control::estimate(measured,bw,dt,angle,rate);
      assert(std::isfinite(rate) && std::fabs(rate)<1);
    }
  }
  // Deterministic stationary jitter: RMS reported to make the tradeoff visible.
  uint32_t seed=32;float a_old=0,r_old=0,a_new=0,r_new=0;
  double e_old=0,e_new=0;int n=0;
  for(int i=0;i<20000;++i){
    seed=1664525u*seed+1013904223u;
    const float measured=(int((seed>>24)%3)-1)*lsb;
    swing_control::estimate(measured,10,dt,a_old,r_old);
    swing_control::estimate(measured,p.bw,dt,a_new,r_new);
    if(i>=1000){e_old+=r_old*r_old;e_new+=r_new*r_new;++n;}
  }
  const double noise_old=std::sqrt(e_old/n),noise_new=std::sqrt(e_new/n);
  assert(noise_new<.16);
  std::printf("Synthetic one-count jitter rate RMS %.4f -> %.4f rad/s\n",noise_old,noise_new);
  puts("PASS: phase delay, rate amplitude, rotation wrap, bandwidth boundaries, and stationary jitter");
}
