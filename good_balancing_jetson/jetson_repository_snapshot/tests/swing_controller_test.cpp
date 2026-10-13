#include "../swingup/swing_controller.h"
#include "../swingup/rail_recovery.h"
#include "../swingup/spin_recovery.h"
#include <cassert>
#include <cstdio>
#include <initializer_list>

struct Result { float stable, max_x, max_speed; int catches; bool fault; };
Result simulate(float plant_length, float start_angle_offset, float initial_x,
                bool start_balancing=false, bool stuck_motor=false, FILE *trace=nullptr) {
  const float dt=0.001f;
  swing_control::Parameters p;
  const auto gains=swing_control::gains(p);
  cart_motion::State cart;
  swing_control::PumpState pump;
  rail_recovery::State recovery;
  swing_control::ResponseWatch response;
  spin_recovery::State spin;
  float x=initial_x, theta=start_balancing?start_angle_offset:swing_control::kPi+start_angle_offset;
  float omega=0, angle_hat=swing_control::wrap(theta), rate_hat=0;
  response.reset(swing_control::wrap(theta));
  int mode=start_balancing?3:2, catches=0;
  float stable=0, longest=0, max_x=0, max_speed=0;
  bool fault=false;
  if(trace)std::fprintf(trace,"time_s,mode,theta,omega,x,v,accel\n");
  for(int i=0;i<40000;++i) {
    const float measured=swing_control::wrap(roundf(theta*4096/(2*swing_control::kPi))*2*swing_control::kPi/4096);
    swing_control::estimate(measured,p.bw,dt,angle_hat,rate_hat);
    const uint32_t now=i*1000;
    if((mode==2 || mode==3 || mode==5 || mode==6) && spin_recovery::trigger(rate_hat)){
      spin.begin(now);recovery.reset();response.armed=false;pump.reset();mode=7;
    }
    if((mode==2 || mode==3) && recovery.atEdge(x,p.rail)){recovery.begin(x,p.rail,cart.brake_direction);mode=5;}
    float a=0;
    if(mode==2) {
      a=swing_control::swing(p,pump,angle_hat,rate_hat,x,cart.velocity,dt);
      if(swing_control::canCapture(p,gains,angle_hat,rate_hat,x,cart.velocity,cart.acceleration)) {
        mode=3; ++catches; response.armed=false;
        a=cart_motion::clamp(swing_control::balance(gains,angle_hat,rate_hat,x,cart.velocity),-p.amax_b,p.amax_b);
      }
    }else if(mode==3) {
      a=cart_motion::clamp(swing_control::balance(gains,angle_hat,rate_hat,x,cart.velocity),-p.amax_b,p.amax_b);
      if(fabsf(angle_hat)>p.giveup)mode=2;
    }
    if(mode==5 || mode==6){
      if(recovery.update(x,cart,dt)){
        mode=2;pump.reset();
        a=swing_control::swing(p,pump,angle_hat,rate_hat,x,cart.velocity,dt);
      }else if(recovery.timedOut()){fault=true;break;}
      else {mode=recovery.phase==rail_recovery::RETURNING?6:5;
        a=recovery.demand(x,cart,p.vmax,fmaxf(p.amax_s,p.amax_b),p.jmax,dt);}
    }
    if(mode>=7 && mode<=9){
      if(spin.update(x,cart,rate_hat,true,now)){
        mode=2;pump.reset();response.reset(measured);
        a=swing_control::swing(p,pump,angle_hat,rate_hat,x,cart.velocity,dt);
      }else if(spin.timedOut(now)){fault=true;break;}
      else{mode=spin.phase==spin_recovery::BRAKING?7:spin.phase==spin_recovery::CENTERING?8:9;
        a=spin.demand(x,cart,p.vmax,fmaxf(p.amax_s,p.amax_b),p.jmax,dt);}
    }
    const auto previous=cart;
    cart=cart_motion::advance(cart,x,a,p.vmax,mode==2?p.amax_s:p.amax_b,
                              fmaxf(p.amax_s,p.amax_b),p.jmax,p.rail,dt);
    if(cart.brake_direction && (mode==2 || mode==3)){recovery.begin(x,p.rail,cart.brake_direction);mode=5;}
    x+=cart.velocity*dt; // Firmware position is an inferred pulse position.
    assert(fabsf(cart.acceleration-previous.acceleration)<=p.jmax*dt+1e-5f);
    assert(fabsf(cart.acceleration)<=fmaxf(p.amax_s,p.amax_b)+1e-5f);
    assert(fabsf(cart.velocity)<=p.vmax+0.002f);
    assert(fabsf(x)<p.rail-0.01f);
    if((mode==2 || mode==5 || mode==6) && response.fault(measured,cart.velocity,dt)){fault=true;break;}
    const float actual_accel=stuck_motor?0:cart.acceleration;
    // Nonlinear acceleration-driven pendulum; sensitivity runs vary length.
    // Friction terms are representative approximations, not a motor model.
    auto pendulum_accel=[&](float q,float w) {
      return (9.81f*sinf(q)-actual_accel*cosf(q))/plant_length
             -0.37f*w-0.11f*tanhf(w/0.05f);
    };
    const float midpoint_rate=omega+0.5f*dt*pendulum_accel(theta,omega);
    omega+=dt*pendulum_accel(theta+0.5f*dt*omega,midpoint_rate);
    theta=swing_control::wrap(theta+dt*midpoint_rate);
    max_x=fmaxf(max_x,fabsf(x));max_speed=fmaxf(max_speed,fabsf(cart.velocity));
    if(mode==3 && fabsf(theta)<0.1f && fabsf(x)<0.10f) {
      stable+=dt;longest=fmaxf(longest,stable);
    }else stable=0;
    if(trace && i%10==0)std::fprintf(trace,"%.3f,%d,%.6f,%.6f,%.6f,%.6f,%.6f\n",i*dt,mode,theta,omega,x,cart.velocity,cart.acceleration);
  }
  return {longest,max_x,max_speed,catches,fault};
}
int main(int argc,char **argv) {
  int passed=0,total=0;
  for(float length:{0.163f,0.166f,0.169f})
    for(float tilt:{-0.03f,0.0f,0.03f}) {
      FILE *trace=(argc>1 && length==0.166f && tilt==0)?std::fopen(argv[1],"w"):nullptr;
      auto r=simulate(length,tilt,0,false,false,trace);
      if(trace)std::fclose(trace);
      std::printf("L=%.3f start tilt=%+.3f: balanced %.1fs, max |x| %.1fmm, max |v| %.3fm/s, catches %d\n",
                  length,tilt,r.stable,r.max_x*1000,r.max_speed,r.catches);
      assert(!r.fault && r.stable>10);
      ++passed;++total;
    }
  for(float position:{-0.01f,0.01f}) {
    const auto r=simulate(0.166f,0,position);
    assert(!r.fault && r.stable>10);++passed;++total;
  }
  for(float tilt:{-0.08f,0.08f}) {
    const auto r=simulate(0.166f,tilt,0,true);
    assert(!r.fault && r.stable>30);++passed;++total;
  }
  assert(simulate(0.166f,0,0,false,true).fault);
  // Reject a handoff that needs more acceleration than the configured motor cap.
  swing_control::Parameters p;const auto g=swing_control::gains(p);
  assert(!swing_control::canCapture(p,g,.4f,2.9f,0,0));
  assert(!swing_control::canCapture(p,g,0,0,.13f,0));
  // At rest the smoothed pump should have no sign-relay demand from tiny noise.
  swing_control::PumpState pump;
  pump.elapsed=2;
  const auto a=swing_control::swing(p,pump,swing_control::kPi,.03f,0,0,.001f);
  assert(fabsf(a)<.13f);
  std::printf("%d/%d closed-loop scenarios passed; response fault and capture/noise checks passed. Ideal motor tracking assumed.\n",passed,total);
}
