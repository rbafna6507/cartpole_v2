#include "../swingup/cart_motion.h"
#include "../swingup/swing_controller.h"
#include <cassert>
#include <cstdio>
#include <cstdlib>
#include <initializer_list>

constexpr float dt = 0.001f;

void checkStep(const cart_motion::State &previous, const cart_motion::State &next,
               float vmax, float amax, float jerk) {
  assert(fabsf(next.acceleration - previous.acceleration) <= jerk*dt + 1e-5f);
  assert(fabsf(next.acceleration) <= amax + 1e-5f);
  assert(fabsf(next.velocity) <= vmax + 0.002f);
}

void velocityTests() {
  cart_motion::State s;
  const float targets[] = {1.5f, -1.5f, 0.15f, 0.0f, -0.15f, 0.0f};
  for (float target : targets) {
    for (int i=0; i<2500; ++i) {
      const auto previous = s;
      float a = cart_motion::velocityAccel(s.velocity, target, 18, 500, dt);
      s = cart_motion::advance(s, 0, a, 1.5f, 18, 18, 500, 100, dt);
      checkStep(previous, s, 1.5f, 18, 500);
    }
    assert(fabsf(s.velocity - target) < 0.001f);
    assert(fabsf(s.acceleration) < 0.51f);
  }
}

void railTests(float vmax, float drive_amax, float brake_amax, float jerk) {
  // Persistent outward commands, rapid reversals, manual watchdog stop, and
  // randomized acceleration demands must remain inside the fault boundary.
  for (int scenario=0; scenario<8; ++scenario) {
    cart_motion::State s;
    float x = (scenario == 4 || scenario == 7) ? 0.132f :
              (scenario == 5 || scenario == 6) ? -0.132f : 0;
    float peak_x = 0, peak_v = 0;
    for (int i=0; i<30000; ++i) {
      float a = drive_amax;
      if (scenario == 1 || scenario == 5 || scenario == 7) a = -drive_amax;
      if (scenario == 2) a = ((i/83)%2 ? -1 : 1)*drive_amax;
      if (scenario == 3) {
        a = cart_motion::velocityAccel(s.velocity, i < 250 ? vmax : 0,
                                        drive_amax, jerk, dt);
      }
      if (scenario == 4) a = (2.0f*std::rand()/RAND_MAX - 1)*drive_amax;
      auto previous = s;
      s = cart_motion::advance(s, x, a, vmax, drive_amax, brake_amax,
                              jerk, 0.15f, dt);
      x += s.velocity*dt;
      checkStep(previous, s, vmax, brake_amax, jerk);
      if (fabsf(x) >= 0.14f) {
        std::printf("Rail failure scenario %d at %d: x=%g v=%g a=%g\n",scenario,i,x,s.velocity,s.acceleration);
        std::abort();
      }
      peak_x = fmaxf(peak_x, fabsf(x));
      peak_v = fmaxf(peak_v, fabsf(s.velocity));
    }
    std::printf("scenario %d: max |x|=%.3f mm, max |v|=%.3f m/s\n", scenario,peak_x*1000,peak_v);
  }
}

void speedRampRegression() {
  // Feasible state shortly before a speed cap: there is just enough room
  // to remove acceleration. Keep demanding outward acceleration to verify
  // the limiter anticipates the full jerk ramp instead of faulting later.
  for (int sign : {-1, 1}) {
    cart_motion::State s;
    s.velocity=sign*.72f; s.acceleration=sign*1.7f;
    for(int i=0;i<400;++i) {
      const auto previous=s;
      s=cart_motion::advance(s,0,sign*15.0f,.75f,15,15,50,100,.001f);
      checkStep(previous,s,.75f,15,50);
      assert(fabsf(s.velocity)<=.75001f);
    }
  }
}

int main() {
  speedRampRegression();
  velocityTests();
  swing_control::Parameters p;
  assert(fabsf(p.vmax - 0.8f) < 1e-6f);
  assert(fabsf(p.amax_s - 12.0f) < 1e-5f);
  assert(fabsf(p.amax_b - p.amax_s) < 1e-6f);
  assert(fabs(cart_hardware::steps_per_m - (3200.0 / .12)) < .003f);
  assert(fabsf(cart_hardware::max_speed - (1000000.0f/7/2/(3200.0f / .12f))) < 1e-6f);
  assert(p.vmax < cart_hardware::max_speed);
  assert(cart_hardware::pulley_teeth == 60);
  assert(fabsf(cart_hardware::mm_per_rev - 120) < 1e-6f);
  assert(fabsf(cart_hardware::requested_speed_rpm - 400) < 1e-3f);
  assert(fabsf(cart_hardware::requested_acceleration_rpm_s - 6000) < 1e-3f);
  assert(fabsf(cart_hardware::requested_jerk_rpm_s2 - 30000) < 1e-3f);
  assert(fabsf(p.jmax - 60.0f) < 1e-4f);
  assert(fabsf(cart_hardware::max_rpm - (1000000.0f/7/2*60/3200)) < 1e-3f);
  railTests(p.vmax, p.amax_s, p.amax_b, p.jmax);   // current swing-up and balance
  railTests(p.vmax, p.amax_m, p.amax_m, p.jmax_m); // current manual commands
  railTests(1.5f, 10, 18, 500);  // previous high limits
  railTests(1.5f, 18, 18, 500);  // balance/manual
  railTests(0.05f, 0.5f, 1, 50); // slow profile
  std::puts("Motion checks passed: jerk, acceleration, speed, reversals, rail braking.");
}
