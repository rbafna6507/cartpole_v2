#include <cassert>
#include <cstdio>
#define DEPLOYMENT_NATIVE_TEST
#include "Arduino.h"
#include "Wire.h"
#include "EEPROM.h"
uint64_t clock_us=0,next_isr=0;unsigned interval=7,cartPulses=0;
bool pins[64]{},zPulsed=false,timerAvailable=true;
int encoderCount=3953;bool failRaw=false,failStatus=false,failConfig=false;
void (*isr)()=nullptr;
SerialType Serial;WireType Wire1;EEPROMType EEPROM;
void advanceClock(uint64_t n) {
  const uint64_t end=clock_us+n;
  while(isr && next_isr<=end){clock_us=next_isr;next_isr+=interval;isr();}
  clock_us=end;
}
#include "../../firmware/deployment_executor/deployment_executor.ino"
using namespace deployment_firmware;
static void cycles(unsigned n) {for(unsigned i=0;i<n;i++){advanceClock(100);loop();}}
static std::string framed(const std::string &p) {
  char out[257];const auto n=deployment::frame(p.c_str(),out,sizeof out);assert(n);return std::string(out,n);
}
static void serialCommand(const std::string &p) {
  Serial.rx+=framed(p);cycles(8);
}
static void armSerial(uint32_t session=7) {
  serialCommand("D1 clear");serialCommand("D1 home 0.15");
  assert(!stepper::enabled && pins[8] && core.homed && stepper::position==0);
  serialCommand("D1 arm "+std::to_string(session));
  assert(stepper::enabled && !pins[8]);serialCommand("D1 state");
}
static void serialAction(unsigned ttl=50) {
  const uint32_t timestamp=core.sample_us;serialCommand("D1 state");
  // state emitted during serialCommand may be newer; use a known emitted sample.
  assert(core.knownSample(timestamp));
  serialCommand("D1 act "+std::to_string(core.session)+" 1 "+std::to_string(timestamp)+" "+std::to_string(ttl)+" a 1");
  assert(core.mode==deployment::Mode::RUNNING);
}
int main() {
  setup();cycles(30);
  assert(pins[8] && !stepper::enabled && cartPulses==0 && !zPulsed);
  armSerial();serialAction();cycles(200);
  assert(cartPulses>0 && !zPulsed);
  // Independent ISR must expire the observation-anchored lease without loop().
  while(int32_t(core.deadline-micros())>3000)cycles(1);
  assert(stepper::enabled);
  advanceClock(4000);
  assert(!stepper::enabled && pins[8] && !pins[2]);
  loop();assert(core.mode==deployment::Mode::FAULT && std::string(core.fault)=="deadline");
  serialCommand("D1 stop");assert(core.mode==deployment::Mode::FAULT);
  armSerial(8);serialAction();advanceClock(6000);
  assert(!stepper::enabled && pins[8]);loop();
  assert(core.mode==deployment::Mode::FAULT && std::string(core.fault)=="timing");
  armSerial(9);serialAction();failRaw=true;cycles(15);
  assert(core.mode==deployment::Mode::FAULT && !stepper::enabled);failRaw=false;
  armSerial(10);Serial.rx="@D1 act bad*0000\n";cycles(8);
  assert(core.mode==deployment::Mode::FAULT && pins[8]);
  armSerial(12);serialAction();Serial.present=false;cycles(1);
  assert(!stepper::enabled && core.mode==deployment::Mode::FAULT && std::string(core.fault)=="disconnect");
  Serial.present=true;cycles(1);
  armSerial(13);serialAction();
  // Pulse-side rail boundary remains authoritative independently of governor.
  stepper::position=stepper::rail_limit-1;stepper::rate(.25f);advanceClock(1000);
  assert(!stepper::enabled && pins[8] && stepper::position<stepper::rail_limit);
  loop();assert(std::string(core.fault)=="rail");
  serialCommand("D1 clear");serialCommand("D1 home 0.15");
  using namespace qindesign::network;
  auto peer=std::make_shared<State>();pending.s=peer;cycles(5);
  assert(net_active);
  peer->rx=framed("D1 arm 11");cycles(8);assert(stepper::enabled);
  auto second=std::make_shared<State>();pending.s=second;cycles(5);assert(!second->connected);
  peer->connected=false;cycles(1);
  assert(!stepper::enabled && core.mode==deployment::Mode::FAULT && std::string(core.fault)=="disconnect");
  serialCommand("D1 clear");
  auto clogged=std::make_shared<State>();pending.s=clogged;cycles(5);
  clogged->space=0;clogged->rx=std::string(4000,'x');
  const auto before=clogged->rx.size();loop();
  assert(before-clogged->rx.size()<=128 && pins[8]);
  clogged->connected=false;cycles(1);
  armSerial(14);Serial.room=0;
  for(int i=0;i<64;i++)serialCommand("D1 state");
  assert(core.mode==deployment::Mode::FAULT && std::string(core.fault)=="tx" && pins[8]);
  Serial.room=4096;cycles(30);
  // Existing EEPROM reference is retained, not overwritten at boot.
  assert(teensy_reference_store::save(100));core=deployment::Executor();setup();cycles(20);
  assert(core.upright_raw==100 && pins[8] && !zPulsed);
  failConfig=true;core=deployment::Executor();setup();cycles(20);
  assert(!core.encoder_valid && pins[8]);failConfig=false;
  timerAvailable=false;core=deployment::Executor();setup();cycles(20);
  serialCommand("D1 clear");
  assert(core.mode==deployment::Mode::FAULT && std::string(core.fault)=="timer" && pins[8]);
  std::puts("hardware integration tests: boot/home/arm, DDS watchdog/lease, encoder, CRC, TCP ownership/budget and EEPROM passed");
}
