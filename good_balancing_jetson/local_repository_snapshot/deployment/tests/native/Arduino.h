#pragma once
#include <cstdint>
#include <cstddef>
#include <string>
#include <cmath>
#include <initializer_list>
extern uint64_t clock_us;extern void advanceClock(uint64_t);
extern bool pins[64],zPulsed;extern unsigned cartPulses;
constexpr int HIGH=1,LOW=0,OUTPUT=1;
inline uint32_t micros(){return uint32_t(clock_us);}
inline void __disable_irq(){} inline void __enable_irq(){}
inline void pinMode(int,int){}
inline void digitalWriteFast(int p,int v){pins[p]=v;if((p==4 || p==6)&&v)zPulsed=true;if(p==2 && v)++cartPulses;}
inline void digitalWrite(int p,int v){digitalWriteFast(p,v);}
inline void delayMicroseconds(unsigned n){advanceClock(n);}
struct SerialType {
  bool present=true;std::string rx,tx;int room=4096;
  void begin(int){} explicit operator bool()const{return present;}
  int available(){return int(rx.size());}
  int read(){if(rx.empty())return -1;char c=rx[0];rx.erase(0,1);return uint8_t(c);}
  int availableForWrite(){return room;}
  size_t write(const uint8_t *p,size_t n){tx.append((const char*)p,n);return n;}
};
extern SerialType Serial;
