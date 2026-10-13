#include <cassert>
#include <iostream>
#include "Arduino.h"
#include "Wire.h"
uint64_t clock_us=0,next_isr=0;unsigned interval=7;void (*isr)()=nullptr;
bool pins[64]={},zPulsed=false,failRaw=false;SerialType Serial;WireType Wire1;
std::function<int(uint64_t)> sensor=[](uint64_t){return 1000;};
void advanceClock(uint64_t n){uint64_t end=clock_us+n;while(isr && next_isr<=end){clock_us=next_isr;next_isr+=interval;isr();}clock_us=end;}
#include "../../teensy_pendulum_characterization.ino"
void advance(uint64_t duration,bool heartbeat=true){
 uint64_t until=clock_us+duration,last=clock_us;
 while(clock_us<until){advanceClock(20);if(heartbeat && clock_us-last>100000){Serial.rx+="PING\n";last=clock_us;}loop();}
}
void send(const char *s){Serial.rx+=s;Serial.rx+='\n';advance(3000);}
void beginDrive(){send("STOP");send("STREAM");send("HOME 300");assert(homeValid && motorEnabled);}
int main(int argc,char**argv){
 if(argc>1){clock_us=(1ULL<<32)-3000;setup();advance(12000);assert(now64()>(1ULL<<32));std::cout<<"Rollover passed\n";return 0;}
 setup();advance(10000);assert(!motorEnabled && pins[8]);
 send("MOVE 1 20");assert(!profile.active);assert(Serial.tx.find("ERROR_move")!=std::string::npos);
 send("STREAM");send("HOME nan");assert(!homeValid);send("HOME 300");assert(homeValid && motorEnabled);
 send("MOVE 1 20");assert(profile.active);advance(3000000);
 if(profile.active)std::cerr<<"Not settled x="<<pulsePosition/STEPS_PER_M<<" v="<<profile.state.velocity<<" a="<<profile.state.acceleration<<"\n";
 assert(!profile.active && motorEnabled);assert(fabsf(pulsePosition/STEPS_PER_M-.020f)<.0002f);
 send("MOVE 2 -20");advance(4000000);assert(!profile.active && motorEnabled);assert(fabsf(pulsePosition/STEPS_PER_M+.020f)<.0002f);
 send("MOVE 3 140");assert(!profile.active); // outside 30 mm target margin
 send("MOVE 4 20");advance(400000,false);assert(!motorEnabled && !homeValid);
 beginDrive();send("MOVE 5 20");advanceClock(6000);assert(!motorEnabled);loop();assert(!homeValid);
 beginDrive();failRaw=true;advance(30000);failRaw=false;assert(!motorEnabled && !homeValid);
 beginDrive();Serial.room=0;send("MOVE 6 20");advance(3000000);assert(txDrops>100 && !profile.active && motorEnabled);Serial.room=4096;advance(10000);
 send("STOP");assert(!homeValid && !motorEnabled && pins[8]);assert(!zPulsed);
 send("ARM");advance(900000);assert(mode==WAIT_RELEASE);
 uint64_t origin=clock_us;sensor=[origin](uint64_t t){return 1000-int(std::min<uint64_t>((t-origin)/2000,100));};advance(150000);assert(mode==RUNNING);
 std::cout<<"Motion, limits, watchdogs, encoder loss, backpressure, shared enable, release passed\n";
}
