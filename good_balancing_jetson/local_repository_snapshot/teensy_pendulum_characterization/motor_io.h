#pragma once
#include <IntervalTimer.h>
#include "cart_mechanics.h"
#include "motion_profile.h"
// Derived from the supplied teensy_swingup.ino DDS, pin map and stall cutoff.
constexpr int CART_STEP=2,CART_DIR=3,ENABLE_ALL=8;
volatile bool motorEnabled=false,pulseFault=false;
volatile uint32_t pulseInc=0,controlBeat=0;
volatile int32_t pulsePosition=0,railStepLimit=0;
volatile int8_t pulseDirection=1;
uint32_t pulseAccumulator=0;bool directionInitialized=false,timerReady=false;
IntervalTimer pulseTimer;
characterization::Profile profile;
bool homeValid=false,motionFault=false;
uint32_t motionId=0;uint64_t moveStarted=0;
constexpr float STEPS_PER_M=cart_hardware::steps_per_m;
inline uint32_t maskIRQ(){
#ifdef CHARACTERIZATION_NATIVE_TEST
 return 0;
#else
 uint32_t mask;asm volatile("mrs %0, primask":"=r"(mask)::"memory");return mask;
#endif
}
void disableMotor(){
 const uint32_t irq=maskIRQ();__disable_irq();
 digitalWriteFast(ENABLE_ALL,HIGH);motorEnabled=false;pulseInc=0;
 digitalWriteFast(CART_STEP,LOW);digitalWriteFast(4,LOW);digitalWriteFast(6,LOW);
 if(!irq)__enable_irq();
 homeValid=false;profile.active=false;profile.state={};
}
void pulseISR(){
 digitalWriteFast(CART_STEP,LOW);
 if(!motorEnabled)return;
 if(uint32_t(micros()-controlBeat)>5000){
  digitalWriteFast(ENABLE_ALL,HIGH);motorEnabled=false;pulseInc=0;pulseFault=true;return;
 }
 const uint32_t previous=pulseAccumulator;pulseAccumulator+=pulseInc;
 if(pulseAccumulator<previous){
  const int32_t next=pulsePosition+pulseDirection;
  if(next<=-railStepLimit || next>=railStepLimit){
   digitalWriteFast(ENABLE_ALL,HIGH);motorEnabled=false;pulseInc=0;pulseFault=true;return;
  }
  pulsePosition=next;digitalWriteFast(CART_STEP,HIGH);
 }
}
void motorRate(float velocity){
 if(!motorEnabled){pulseInc=0;return;}
 const int8_t direction=velocity>=0?1:-1;
 if(!directionInitialized || pulseDirection!=direction){
  pulseInc=0;delayMicroseconds(cart_hardware::step_timer_period_us+1);
  digitalWrite(CART_DIR,direction>0?HIGH:LOW); // same CART_INVERT=0 as source
  pulseDirection=direction;directionInitialized=true;delayMicroseconds(1);
 }
 const double rate=fminf(fabsf(velocity)*STEPS_PER_M,cart_hardware::isr_hz*.5);
 const uint32_t inc=uint32_t(rate*4294967296.0/cart_hardware::isr_hz);
 const uint32_t irq=maskIRQ();__disable_irq();pulseInc=motorEnabled?inc:0;if(!irq)__enable_irq();
}
void initMotor(){
 digitalWriteFast(ENABLE_ALL,HIGH);pinMode(ENABLE_ALL,OUTPUT);digitalWriteFast(ENABLE_ALL,HIGH);
 for(int pin: {2,3,4,5,6,7}){pinMode(pin,OUTPUT);digitalWrite(pin,LOW);}
 timerReady=pulseTimer.begin(pulseISR,cart_hardware::step_timer_period_us);pulseTimer.priority(32);
}
// Call only after operator has physically located the rail centre.
bool setHome(float travel_mm){
 if(!timerReady || motorEnabled || !isfinite(travel_mm) || travel_mm<100 || travel_mm>600)return false;
 profile.half=travel_mm/2000;profile.target=0;profile.state={};profile.active=false;
 const uint32_t irq=maskIRQ();__disable_irq();
 pulsePosition=0;pulseAccumulator=0;pulseInc=0;
 railStepLimit=int32_t((profile.half-.010f)*STEPS_PER_M);
 pulseFault=false;motionFault=false;homeValid=true;controlBeat=micros();
 motorEnabled=true;digitalWriteFast(ENABLE_ALL,LOW);
 if(!irq)__enable_irq();return true;
}
