#pragma once
#include <Arduino.h>
#include <IntervalTimer.h>
#include "cart_mechanics.h"
#include "executor.h"

// Source-derived 7 us DDS, GPIO map, DIR setup and IRQ masking. Only cart pulses.
namespace stepper {
constexpr int STEP=2,DIR=3,ENABLE=8,Z1_STEP=4,Z2_STEP=6;
enum class Fault : uint8_t { NONE, TIMING, DEADLINE, RAIL };
volatile bool enabled=false;
volatile Fault pending=Fault::NONE;
volatile uint32_t increment=0,heartbeat=0,expiry=0;
volatile int32_t position=0,rail_limit=0;
volatile int8_t direction=1;
uint32_t accumulator=0;bool initialized_direction=false,timer_ready=false;
IntervalTimer timer;
inline uint32_t interruptMask() {
#ifdef DEPLOYMENT_NATIVE_TEST
  return 0;
#else
  uint32_t mask;asm volatile("mrs %0, primask":"=r"(mask)::"memory");return mask;
#endif
}
inline void lowSteps() {
  digitalWriteFast(STEP,LOW);digitalWriteFast(Z1_STEP,LOW);digitalWriteFast(Z2_STEP,LOW);
}
inline void inhibit(Fault fault) {
  digitalWriteFast(ENABLE,HIGH);enabled=false;increment=0;lowSteps();
  if(pending==Fault::NONE)pending=fault;
}
void pulseISR() {
  lowSteps();if(!enabled)return;
  const uint32_t now=micros();
  // Lease is enforced in the pulse ISR even if the foreground is blocked.
  if(int32_t(now-expiry)>=0){inhibit(Fault::DEADLINE);return;}
  if(uint32_t(now-heartbeat)>5000){inhibit(Fault::TIMING);return;}
  const uint32_t prior=accumulator;accumulator+=increment;
  if(accumulator<prior) {
    const int32_t next=position+direction;
    if(next<=-rail_limit || next>=rail_limit){inhibit(Fault::RAIL);return;}
    position=next;digitalWriteFast(STEP,HIGH);
  }
}
inline void disable() {
  const uint32_t irq=interruptMask();__disable_irq();
  digitalWriteFast(ENABLE,HIGH);enabled=false;increment=0;lowSteps();
  if(!irq)__enable_irq();
}
inline void clearFault() {
  const uint32_t irq=interruptMask();__disable_irq();
  if(!enabled)pending=Fault::NONE;
  if(!irq)__enable_irq();
}
inline void initialize() {
  // Output latch HIGH precedes output direction, then reassert disable.
  digitalWriteFast(ENABLE,HIGH);pinMode(ENABLE,OUTPUT);digitalWriteFast(ENABLE,HIGH);
  for(int pin:{STEP,DIR,Z1_STEP,5,Z2_STEP,7}){pinMode(pin,OUTPUT);digitalWrite(pin,LOW);}
  enabled=false;increment=0;
  timer_ready=timer.begin(pulseISR,cart_hardware::step_timer_period_us);timer.priority(32);
}
inline void home(float half) {
  const uint32_t irq=interruptMask();__disable_irq();
  if(!enabled) {
    position=0;accumulator=0;increment=0;
    rail_limit=int32_t((half-.010f)*cart_hardware::steps_per_m);
  }
  if(!irq)__enable_irq();
}
inline void syncEnable(bool desired,uint32_t lease) {
  const uint32_t irq=interruptMask();__disable_irq();
  expiry=lease;
  if(desired && timer_ready && pending==Fault::NONE) {
    if(!enabled)heartbeat=micros();
    enabled=true;digitalWriteFast(ENABLE,LOW);
  }else{digitalWriteFast(ENABLE,HIGH);enabled=false;increment=0;lowSteps();}
  if(!irq)__enable_irq();
}
inline void rate(float velocity) {
  if(!enabled || !std::isfinite(velocity)){increment=0;return;}
  const int8_t next_direction=velocity>=0?1:-1;
  if(!initialized_direction || direction!=next_direction) {
    increment=0;delayMicroseconds(cart_hardware::step_timer_period_us+1);
    digitalWrite(DIR,next_direction>0?HIGH:LOW); // working source CART_INVERT=0
    direction=next_direction;initialized_direction=true;delayMicroseconds(1);
  }
  const double pulses=fminf(fabsf(velocity)*cart_hardware::steps_per_m,cart_hardware::isr_hz*.5f);
  const uint32_t inc=uint32_t(pulses*4294967296.0/cart_hardware::isr_hz);
  const uint32_t irq=interruptMask();__disable_irq();
  increment=enabled?inc:0;if(!irq)__enable_irq();
}
} // namespace stepper
