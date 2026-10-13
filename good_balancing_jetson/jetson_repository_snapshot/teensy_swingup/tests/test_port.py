#!/usr/bin/env python3
"""Host regression checks of actual port code with mocked hardware.
Requires Python 3 and g++; does not measure real IRQ/USB/I2C timing.
"""
from pathlib import Path
import subprocess, tempfile, re
root=Path(__file__).resolve().parents[1]
s=(root/'teensy_swingup/teensy_swingup.ino').read_text()
pins='\n'.join(x for x in s.splitlines() if x.startswith('#define PIN_'))
block=s[s.index('enum { AX_CART'):s.index('// ============================== AS5600')]
block=re.sub(r'static inline uint32_t interruptMask\(\)\{.*?\n\}', 'static inline uint32_t interruptMask(){return 0;}',block,flags=re.S)
pre=r'''
#include <cassert>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include "cart_mechanics.h"
#define HIGH 1
#define LOW 0
#define OUTPUT 1
#define CART_MICROSTEPS 16
#define Z_MICROSTEPS 16
#define ISR_HZ cart_hardware::isr_hz
uint32_t clock_us=0;
uint32_t micros(){return clock_us;}
int levels[64]={};
int pin_touches[64]={};
void digitalWrite(int p,int v){levels[p]=v;++pin_touches[p];}
void digitalWriteFast(int p,int v){digitalWrite(p,v);}
void pinMode(int p,int){++pin_touches[p];}
void __disable_irq(){}
void __enable_irq(){}
void checkedPrintln(const char*){}
void onStepTimer();
void delayMicroseconds(unsigned n){clock_us+=n;onStepTimer();}
struct IntervalTimer{bool begin(void(*)(),unsigned){return true;}void priority(int){}};
'''
checks=r'''
#include "teensy_reference_store.h"
int main(){
 steppersInit();assert(step_timer_ready);
 for(int p:{16,17,20,24,25,26,27,28,29})assert(pin_touches[p]==0);
 energize(true);assert(levels[PIN_EN_ALL]==LOW);
 for(int axis=0;axis<N_AX;++axis)axSetRate(axis,40000,false);
 const int initial[3]={ax_pos[0],ax_pos[1],ax_pos[2]};
 const int ticks=10000;
 for(int n=0;n<ticks;++n){clock_us+=7;control_heartbeat_us=clock_us;onStepTimer();}
 const int expected=int(40000.0*ticks/ISR_HZ);
 for(int axis=0;axis<N_AX;++axis)assert(std::abs(ax_pos[axis]-initial[axis]-expected)<=1);
 assert(levels[PIN_CART_DIR]==HIGH);
 axSetRate(AX_CART,-40000,false);assert(levels[PIN_CART_DIR]==LOW);
 const int before=ax_pos[AX_CART];
 for(int n=0;n<ticks;++n){clock_us+=7;control_heartbeat_us=clock_us;onStepTimer();}
 assert(std::abs((before-ax_pos[AX_CART])-expected)<=1);
 energize(false);const int stopped=ax_pos[AX_CART];
 for(int n=0;n<100;++n){clock_us+=7;onStepTimer();}
 assert(ax_pos[AX_CART]==stopped && levels[PIN_EN_ALL]==HIGH);
 energize(true);axSetRate(AX_CART,10000,false);
 clock_us=control_heartbeat_us+CONTROL_STALL_US+1;onStepTimer();
 assert(!g_energized && timing_fault_pending && levels[PIN_EN_ALL]==HIGH);
 for(int axis=0;axis<N_AX;++axis)assert(ax_inc[axis]==0);
 energize(true);assert(!g_energized); // pending stall cannot be bypassed
 timing_fault_pending=false;step_timer_ready=false;energize(true);assert(!g_energized);
 uint16_t raw=0;
 assert(!teensy_reference_store::load(raw));
 assert(teensy_reference_store::save(4095));
 assert(teensy_reference_store::load(raw) && raw==4095);
 assert(!teensy_reference_store::save(4096));
 EEPROM.bytes[6]^=1;assert(!teensy_reference_store::load(raw));
 assert(teensy_reference_store::save(0));
 assert(teensy_reference_store::load(raw) && raw==0);
 EEPROM.bytes[0]=0;assert(!teensy_reference_store::load(raw));
 puts("PASS: three-axis DDS, reverse direction/counts, stop, stall lockout, timer-failure lockout, no microstep pin writes, EEPROM validity/corruption");
}
'''
with tempfile.TemporaryDirectory() as temp:
 t=Path(temp)
 (t/'EEPROM.h').write_text('''#pragma once
#include <cstring>
struct MockEEPROM{unsigned char bytes[64];MockEEPROM(){memset(bytes,255,sizeof(bytes));}
template<class T>void get(int a,T&v){memcpy(&v,bytes+a,sizeof(T));}
template<class T>void put(int a,const T&v){memcpy(bytes+a,&v,sizeof(T));}};
static MockEEPROM EEPROM;
''')
 (t/'test.cpp').write_text('#include <initializer_list>\n'+pre+pins+'\n'+block+checks)
 subprocess.run(['g++','-std=c++17','-O2','-I'+str(t),'-I'+str(root/'teensy_swingup'),str(t/'test.cpp'),'-o',str(t/'test')],check=True)
 subprocess.run([str(t/'test')],check=True)
