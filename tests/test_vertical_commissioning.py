"""Hardware-free checks for standalone Z commissioning profiles and host protocol."""
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]

def test_profiles_and_bounds(tmp_path):
    source = tmp_path / 'check.cpp'
    source.write_text(r'''#include "vertical_profile.h"
#include <cassert>
#include <cmath>
using namespace vertical;
int main() {
    Settings s;
    assert(std::abs(s.stepsPerMm()-640.)<1e-9);
    assert(!s.valid()); // No invented stroke.
    s.travel=100;
    assert(s.valid());
    assert(validSine(s,20,1,25,10));
    assert(!validSine(s,20,1,20,10)); // Bottom clearance required.
    assert(!validSine(s,20,1,90,10));
    assert(!validSine(s,20,1,25,3)); // Finite startup/end ramp.
    assert(!validSine(s,20,2,25,10)); // Pulse-rate budget.
    assert(!validSine(s,NAN,1,25,10));
    assert(!validSine(s,20,1,25,INFINITY));
    Settings half=s;half.motorSteps=400;
    assert(!validSine(half,20,1,25,10));
    for(int i=0;i<=10000;i++) {
        double t=i*.001;
        double z=sinePosition(t,20,1,25,10);
        assert(z>=5-1e-9 && z<=45+1e-9);
        if(i) assert(std::abs(z-sinePosition(t-.001,20,1,25,10))/.001*s.stepsPerMm()<MAX_RATE);
    }
    assert(sinePosition(0,20,1,25,10)==25);
    assert(std::abs(sinePosition(10,20,1,25,10)-25)<1e-9);
    assert(std::abs(sinePosition(.0001,20,1,25,10)-25)<1e-7);
    assert(std::abs(sinePosition(9.9999,20,1,25,10)-25)<1e-7);
    assert(movePosition(0,0,25)==0);
    assert(movePosition(1,0,25)==25);
    assert(moveDuration(0,25)>=4.6875); // <=10 mm/s quintic transfer.
    assert(!validBottom(s,40,5)); // Requires declared capability, default off.
    s.bottomRated=true;
    assert(validBottom(s,40,5));
    assert(!validBottom(s,41,5));
    assert(!validBottom(s,40,6));
    assert(!validBottom(s,NAN,5));
}
''')
    binary=tmp_path/'check'
    subprocess.run(['c++','-std=c++17','-Wall','-Wextra','-Werror','-I',str(ROOT/'firmware/vertical_commissioning'),str(source),'-o',str(binary)],check=True)
    subprocess.run([str(binary)],check=True)


def test_host_command_boundary():
    import importlib.util
    import pytest
    spec=importlib.util.spec_from_file_location('vertical_client',ROOT/'scripts/vertical_commission.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    assert module.motion_command('sine')=='sine 20 1 25 10'
    assert module.motion_command('probe right -')=='probe right -'
    assert module.motion_command('probe left + 5')=='probe left + 5'
    assert module.motion_command('probe right - 20')=='probe right - 20'
    assert module.motion_command('direction left +')=='direction left +'
    for bad in ('home','bottom 40 5 CONTACT_OK','disable SUPPORTED','reference CONFIRM','sine nan 1 25 10','sine 20 inf 25 10','probe both +','probe left + 0','probe left + 21','probe right - nan','probe right + -5','direction left + 5','stop extra'):
        with pytest.raises(ValueError):module.motion_command(bad)


def test_actual_sketch_state_machine_and_pulses(tmp_path):
    (tmp_path/'Arduino.h').write_text(r'''
#pragma once
#include <cstdint>
#include <cstdio>
#include <initializer_list>
#include <cassert>
#define ARDUINO_TEENSY41 1
#define HIGH 1
#define LOW 0
#define OUTPUT 1
inline uint32_t clockUs=0;
inline int pins[40]={};
inline uint64_t rises[40]={};
inline uint32_t lastRise[40]={};
inline uint32_t micros(){return clockUs;}
inline void delayMicroseconds(uint32_t d){clockUs+=d;}
inline void noInterrupts(){}
inline void interrupts(){}
inline void pinMode(int,int){}
inline void digitalWrite(int p,int v){
 if(v && !pins[p]){
   assert(p!=2); // No cart pulse, ever.
   if(p==4 || p==6){if(rises[p])assert(clockUs-lastRise[p]>=8);lastRise[p]=clockUs;rises[p]++;}
 }
 pins[p]=v;
}
#define digitalWriteFast digitalWrite
struct SerialStub {
 void begin(int){} int available(){return 0;} int read(){return -1;}
 void println(const char*){} template<class...A> void printf(const char*,A...){}
};
inline SerialStub Serial;
''')
    (tmp_path/'IntervalTimer.h').write_text('''#pragma once
struct IntervalTimer { bool begin(void(*)(),int){return true;} void priority(int){} };
''')
    source=tmp_path/'sketch.cpp'
    source.write_text(r'''
#include "vertical_commissioning.ino"
void cmd(const char*s){char b[160];snprintf(b,sizeof b,"%s",s);command(b);}
void advance(uint32_t us,bool heartbeat=true,bool foreground=true){
 uint32_t startTime=clockUs;
 while(clockUs-startTime<us){
   clockUs+=4;pulses();
   if(heartbeat)lastPing=clockUs;
   if(foreground)loop();
 }
}
int main(){
 setup();assert(pins[8]==HIGH && !running);
 cmd("ping");cmd("configure 200 5 200 16 1");assert(configured);
 cmd("direction left +");assert(!confirmed[0]);
 cmd("sine 20 1 25 10");assert(!running);
 cmd("probe left +");advance(600000);assert(mode==IDLE && !fault);
 assert(position[0]==320 && position[1]==0);
 cmd("direction left +");assert(confirmed[0]);
 cmd("probe right +");advance(600000);assert(mode==IDLE && !fault);
 cmd("direction right -");assert(confirmed[1] && upSign[1]==-1);
 cmd("reference CONFIRM");assert(referenced && !position[0] && !position[1]);
 cmd("sine 20 1 25 10");assert(mode==MOVE);
 advance(15000000);assert(mode==IDLE && !fault && referenced);
 assert(position[0]==16000 && position[1]==16000);
 assert(rises[4]==rises[6]); // Mirrored DIR polarity, synchronized pulse counts.
 cmd("sine 20 2 25 10");assert(mode==IDLE); // Exceeds pulse budget.
 cmd("bottom 40 5 CONTACT_OK");advance(5100000);
 assert(mode==IDLE && !fault && bottomComplete && !referenced);
 assert(position[0] < -111000 && position[1] < -111000);
 cmd("reference CONFIRM");assert(referenced && position[0]==0);
 cmd("sine 20 1 25 10");advance(100000);cmd("stop");
 auto before=rises[4];advance(20000);assert(rises[4]==before && !referenced && pins[8]==LOW);
 cmd("reference CONFIRM");cmd("sine 20 1 25 10");advance(100000);
 advance(600000,false);assert(fault==1 && !running && !referenced);
 cmd("sine 20 1 25 10");assert(!running);cmd("clear");assert(!fault);
 cmd("ping");cmd("reference CONFIRM");cmd("sine 20 1 25 10");advance(100000);
 advance(10000,true,false);assert(fault==2 && !running);
 advance(1000);assert(!referenced);
 cmd("disable SUPPORTED");assert(pins[8]==HIGH && !energized);
 cmd("clear");cmd("ping");
 int32_t old=position[0];cmd("probe left + 5");advance(4800000);
 assert(!fault && mode==IDLE && position[0]==old+3200);
 old=position[1];cmd("probe right - 20");advance(18900000);
 assert(!fault && mode==IDLE && position[1]==old-12800);
 cmd("probe left + 21");assert(!running);
 cmd("probe left + nan");assert(!running);
 cmd("probe left + -1");assert(!running);
 cmd("probe left + 0");assert(!running);
}
''')
    binary=tmp_path/'sketch'
    subprocess.run(['c++','-std=c++17','-Wall','-Wextra','-Werror','-I',str(tmp_path),'-I',str(ROOT/'firmware/vertical_commissioning'),str(source),'-o',str(binary)],check=True)
    subprocess.run([str(binary)],check=True)
