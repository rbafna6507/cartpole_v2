/* Teensy pendulum characterization v3, based on supplied motion firmware.
   Pendulum Lab acquisition: measurement only, AS5600, Teensy 4.x or ESP32.
   Cart STEP2/DIR3, shared ENABLE8; Z step pins4/6 held LOW. Fix cart for free decay.
   ASCII protocol, 921600 baud on ESP32; USB Serial on Teensy.
   INFO | STREAM | ARM | GO | STOP | PING
   All data/events carry 64-bit board timestamps. Raw counts never zeroed/filtered.
*/
#include <Arduino.h>
#include <Wire.h>
#include <math.h>
#include <stdarg.h>
#include <stdio.h>
#include <string.h>

#if !defined(ARDUINO_TEENSY41)
#error "This characterization fork targets Teensy 4.1 only."
#endif
#include <initializer_list>
#include "motor_io.h"
static const char *BOARD="teensy41_characterization";
static const int SDA_PIN=17,SCL_PIN=16;
#define Wire Wire1

constexpr uint32_t PERIOD_US=1000, HOLD_US=800000, MAX_WAIT_US=60000000;
constexpr uint64_t MAX_RUN_US=60000000ULL, WATCHDOG_US=2000000ULL;
constexpr float RAD_PER_TICK=6.283185307179586f/4096.0f;
constexpr uint8_t ADDRESS=0x36;
enum Mode {IDLE, STREAMING, WAIT_HOLD, WAIT_RELEASE, RUNNING};
Mode mode=IDLE;
uint64_t nextSample=0,lastGood=0,lastHost=0,modeStart=0,releaseTime=0;
uint64_t holdSince=0,quietSince=0;
uint32_t seq=0,missed=0,errors=0,txDrops=0;
int rawLast=-1; int64_t ticks=0;
float omega=0,holdReference=0,heldTicks=0,quietReference=0;
bool angleContinuous=true;
bool magnetHealthy=false;uint64_t lastMagnetStatus=0;

// Bounded TX queue decouples USB/UART backpressure from sampling. Events reserve
// queue slots; sequence gaps and txDrops expose lost rows. Never block on Serial.
constexpr unsigned QSIZE=48, LINE_SIZE=384;
char queueLines[QSIZE][LINE_SIZE];
uint16_t lengths[QSIZE]; unsigned qHead=0,qTail=0,qCount=0,qOffset=0;
void enqueue(bool event,const char *fmt,...) {
  if(qCount >= QSIZE-(event?0:4)) {txDrops++;return;}
  va_list args;va_start(args,fmt);
  int n=vsnprintf(queueLines[qHead],LINE_SIZE,fmt,args);va_end(args);
  if(n<0 || n>=int(LINE_SIZE)-1){txDrops++;return;}
  queueLines[qHead][n++]='\n';lengths[qHead]=n;
  qHead=(qHead+1)%QSIZE;qCount++;
}
void pumpTx(){
  if(!qCount)return;
  int room=Serial.availableForWrite();if(room<=0)return;
  unsigned remaining=lengths[qTail]-qOffset;
  unsigned n=remaining<unsigned(room)?remaining:unsigned(room);
  size_t sent=Serial.write((const uint8_t*)queueLines[qTail]+qOffset,n);
  qOffset+=sent;
  if(qOffset==lengths[qTail]){qTail=(qTail+1)%QSIZE;qCount--;qOffset=0;}
}
uint64_t now64(){
  static uint32_t last=0;static uint64_t upper=0;
  uint32_t low=micros();if(low<last)upper+=1ULL<<32;last=low;return upper+low;
}
int regRead(uint8_t reg,uint8_t count){
  Wire.beginTransmission(ADDRESS);Wire.write(reg);
  if(Wire.endTransmission(false)!=0){errors++;return -1;}
  if(Wire.requestFrom(ADDRESS,count)!=count){errors++;return -1;}
  int v=Wire.read();if(count==2)v=(v<<8)|Wire.read();return v;
}
void event(const char *name,uint64_t t){
  enqueue(true,"E %llu %s",(unsigned long long)t,name);
}
void finish(const char *reason,uint64_t t){
  disableMotor();
  enqueue(true,"E %llu END %s %lu %lu %lu",(unsigned long long)t,reason,
    (unsigned long)errors,(unsigned long)missed,(unsigned long)txDrops);
  mode=IDLE;
}
void info(uint64_t t){
  int conf=regRead(0x07,2); // read only: do NOT alter AS5600 filtering/OTP
  enqueue(true,"I protocol=3 board=%s sample_hz=1000 sda=%d scl=%d conf=%d motor_control=1",
    BOARD,SDA_PIN,SCL_PIN,conf);
  enqueue(true,"I steps_per_m=%.8f cart_step=2 cart_dir=3 enable=8 limits_connected=0 filter_write_ok=%d",STEPS_PER_M,conf==0x0300);
  enqueue(true,"I home=%d enabled=%d travel_mm=%.3f vmax_mm_s=%.3f amax_mm_s2=%.3f jerk_mm_s3=%.3f",homeValid,motorEnabled,profile.half*2000,profile.vmax*1000,profile.amax*1000,profile.jerk*1000);
  enqueue(true,"E %llu INFO",(unsigned long long)t);
}
void command(char *line,uint64_t t){
  lastHost=t;
  if(!strcmp(line,"PING"))return;
  unsigned long id=0;float a=0,b=0,c=0;char extra=0;
  if(sscanf(line,"PING %lu %c",&id,&extra)==1){enqueue(true,"E %llu PONG %lu",(unsigned long long)t,id);return;}
  if(!strcmp(line,"OFF")){disableMotor();event("OFF",t);return;}
  if(sscanf(line,"HOME %f %c",&a,&extra)==1){
    if(mode==STREAMING && lastGood && t-lastGood<10000 && magnetHealthy && t-lastMagnetStatus<100000 && setHome(a))event("HOME",t);else event("ERROR_home",t);return;
  }
  if(sscanf(line,"LIMITS %f %f %f %c",&a,&b,&c,&extra)==3){
    if(profile.active || !isfinite(a)||!isfinite(b)||!isfinite(c)||a<1||a>250||b<10||b>2000||c<100||c>20000){event("ERROR_limits",t);return;}
    profile.vmax=a/1000;profile.amax=b/1000;profile.jerk=c/1000;event("LIMITS",t);return;
  }
  if(sscanf(line,"MOVE %lu %f %c",&id,&a,&extra)==2){
    // Absolute target in mm from the manually established centre; no implicit homing.
    if(!homeValid||!motorEnabled||motionFault||profile.active||mode!=STREAMING||!isfinite(a)||fabsf(a)>1000*(profile.half-.030f)||fabsf(a/1000-pulsePosition/STEPS_PER_M)>.100f){event("ERROR_move",t);return;}
    profile.target=a/1000;profile.active=true;motionId=id;moveStarted=t;
    enqueue(true,"E %llu MOVE_ACCEPT %lu %.3f",(unsigned long long)t,id,a);return;
  }

  if(!strcmp(line,"INFO")){info(t);return;}
  if(!strcmp(line,"STOP")){finish("host_stop",t);return;}
  if(!strcmp(line,"STREAM") || !strcmp(line,"ARM")){
    if(mode!=IDLE){event("ERROR_busy",t);return;}
    seq=missed=errors=txDrops=0;rawLast=-1;ticks=0;lastGood=0;omega=0;
    holdSince=quietSince=releaseTime=0;angleContinuous=true;
    mode=(!strcmp(line,"ARM"))?WAIT_HOLD:STREAMING;modeStart=t;
    event(mode==WAIT_HOLD?"ARMED":"STREAM",t);return;
  }
  if(!strcmp(line,"GO")){
    if(mode==STREAMING || mode==WAIT_HOLD || mode==WAIT_RELEASE){
      mode=RUNNING;releaseTime=t;quietSince=0;event("RELEASE_manual",t);
    }else event("ERROR_not_armed",t);
    return;
  }
  event("ERROR_unknown_command",t);
}
char input[48];unsigned inputUsed=0;bool inputOverflow=false;
void pumpRx(uint64_t t){
  // Limit work per loop, and do not wait for a newline.
  for(unsigned k=0;k<64 && Serial.available();k++){
    char c=Serial.read();
    if(c=='\r')continue;
    if(c=='\n'){
      if(inputOverflow)event("ERROR_command_too_long",t);
      else{input[inputUsed]=0;command(input,t);}
      inputUsed=0;inputOverflow=false;
    }else if(inputUsed<sizeof(input)-1) input[inputUsed++]=c;
    else inputOverflow=true;
  }
}
void serviceMotor(uint64_t t);
void sample(uint64_t t,uint32_t late){
  bool capture=mode!=IDLE;
  uint32_t thisSeq=capture?seq++:0;
  static uint32_t sensorSamples=0;
  uint64_t readStart=now64();int raw=regRead(0x0c,2);uint64_t readEnd=now64();
  uint64_t stamp=(readStart+readEnd)/2;int status=-1,agc=-1,mag=-1;
  if(sensorSamples++%50==0){status=regRead(0x0b,1);agc=regRead(0x1a,1);mag=regRead(0x1b,2);if(mag>=0)mag&=4095;
    magnetHealthy=status>=0 && (status&32) && !(status&24);lastMagnetStatus=now64();}
  float theta=NAN;float velocity=NAN;
  uint32_t goodDt=lastGood?uint32_t(stamp-lastGood):0;
  if(raw>=0){
    raw&=4095;
    if(rawLast<0){rawLast=raw;ticks=raw;omega=0;}
    else{
      int delta=raw-rawLast;if(delta>2048)delta-=4096;if(delta<-2048)delta+=4096;
      ticks+=delta;rawLast=raw;
      if(goodDt>20000)angleContinuous=false; // possible missing motion; analysis must inspect
      float inst=goodDt?delta*RAD_PER_TICK/(goodDt*1e-6f):0;
      float alpha=1-expf(-float(goodDt)*1e-6f/0.025f);omega+=alpha*(inst-omega);
    }
    lastGood=stamp;theta=ticks*RAD_PER_TICK;velocity=omega;
    if(mode==WAIT_HOLD){
      if(!holdSince){holdSince=stamp;holdReference=theta;}
      if(fabsf(theta-holdReference)>.008f || fabsf(omega)>.12f){holdSince=stamp;holdReference=theta;}
      if(stamp-holdSince>=HOLD_US){heldTicks=theta;mode=WAIT_RELEASE;event("HELD_release_now",stamp);}
    }else if(mode==WAIT_RELEASE){
      if(fabsf(theta-heldTicks)>.020f && fabsf(omega)>.18f){
        mode=RUNNING;releaseTime=stamp;quietSince=0;event("RELEASE_auto",stamp);
      }
    }
    if(mode==RUNNING){
      if(!quietSince){quietSince=stamp;quietReference=theta;}
      if(fabsf(theta-quietReference)>.004f || fabsf(omega)>.05f){quietSince=stamp;quietReference=theta;}
    }
  }else {holdSince=quietSince=0;}
  serviceMotor(now64());
  const int32_t positionSnapshot=pulsePosition;
  if(capture)enqueue(false,"D %lu,%llu,%lu,%d,%lld,%.7f,%.5f,%d,%d,%d,%lu,%lu,%lu,%lu,%d,%d,%ld,%.7f,%.7f,%.7f,%lu,%d,%d,%d",
    (unsigned long)thisSeq,(unsigned long long)stamp,(unsigned long)goodDt,raw,
    (long long)ticks,theta,velocity,status,agc,mag,(unsigned long)errors,
    (unsigned long)missed,(unsigned long)txDrops,(unsigned long)(readEnd-readStart),
    raw>=0?1:0,angleContinuous?1:0,
    (long)positionSnapshot,positionSnapshot/STEPS_PER_M,profile.state.velocity,profile.state.acceleration,
    (unsigned long)motionId,profile.active?1:0,motorEnabled?1:0,homeValid?1:0);
  if(mode==RUNNING && quietSince && stamp-releaseTime>5000000ULL && stamp-quietSince>3000000ULL)
    finish("quiet",stamp);
  else if(mode==RUNNING && stamp-releaseTime>=MAX_RUN_US)finish("capture_timeout",stamp);
  else if((mode==WAIT_HOLD || mode==WAIT_RELEASE) && stamp-modeStart>=MAX_WAIT_US)finish("arm_timeout",stamp);
}
void serviceMotor(uint64_t t){
  const char *fault=nullptr;
  if(pulseFault){pulseFault=false;fault="pulse_stall_or_boundary";}
  else if(motorEnabled && t-lastHost>300000)fault="host_timeout";
  else if(motorEnabled && (!lastGood || t-lastGood>10000))fault="encoder_stale";
  else if(motorEnabled && (!magnetHealthy || t-lastMagnetStatus>200000))fault="magnet_status";
  else if(profile.active && t-moveStarted>20000000)fault="move_timeout";
  if(fault){disableMotor();motionFault=true;enqueue(true,"E %llu FAULT %s",(unsigned long long)t,fault);}
  if(motorEnabled && profile.active){
    const bool done=profile.update(pulsePosition/STEPS_PER_M);
    if(profile.state.brake_direction){disableMotor();motionFault=true;event("FAULT_rail_brake",t);}
    else if(fabsf(profile.state.velocity)>profile.vmax+.002f){disableMotor();motionFault=true;event("FAULT_velocity",t);}
    else {motorRate(profile.state.velocity);if(done)enqueue(true,"E %llu MOVE_DONE %lu",(unsigned long long)t,(unsigned long)motionId);}
  }
  controlBeat=micros();
}
void setup(){
  // Shared enable also affects both Z drivers. They receive no step pulses.
  digitalWriteFast(ENABLE_ALL,HIGH);pinMode(ENABLE_ALL,OUTPUT);digitalWriteFast(ENABLE_ALL,HIGH);
  Serial.begin(115200);Wire.begin();Wire.setSDA(SDA_PIN);Wire.setSCL(SCL_PIN);Wire.setClock(400000);
  // Preserve the source firmware's volatile SF=2x, normal power/no hysteresis.
  Wire.beginTransmission(ADDRESS);Wire.write(0x07);Wire.write(0x03);Wire.write(0x00);Wire.endTransmission();
  initMotor();lastHost=now64();nextSample=lastHost+PERIOD_US;
  enqueue(true,"I protocol=3 board=%s ready=1 motor_control=1",BOARD);
}
void loop(){
  uint64_t t=now64();pumpRx(t);t=now64();
  if(mode!=IDLE && t-lastHost>WATCHDOG_US)finish("host_watchdog",t);
  if(t>=nextSample){
    uint32_t slots=uint32_t((t-nextSample)/PERIOD_US);
    if(slots && motorEnabled){disableMotor();motionFault=true;event("FAULT_control_deadline",t);}
    if(mode!=IDLE){missed+=slots;seq+=slots;}
    nextSample+=(uint64_t(slots)+1)*PERIOD_US;sample(t,slots);
  }
  pumpTx();
}
