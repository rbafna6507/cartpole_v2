#pragma once
#include <cstdint>
#include <cstddef>
#include <string>
#include <cmath>
#include <initializer_list>
extern uint64_t clock_us;extern void advanceClock(uint64_t n);extern bool pins[64];extern bool zPulsed;
constexpr int HIGH=1,LOW=0,OUTPUT=1;
inline uint32_t micros(){return uint32_t(clock_us);}
inline void __disable_irq(){} inline void __enable_irq(){}
inline void pinMode(int,int){}
inline void digitalWriteFast(int p,int v){pins[p]=v;if((p==4 || p==6)&&v)zPulsed=true;}
inline void digitalWrite(int p,int v){digitalWriteFast(p,v);}
inline void delayMicroseconds(unsigned n){advanceClock(n);}
struct SerialType{
 std::string rx,tx;int room=4096;
 void begin(int){} int available(){return rx.size();} int read(){char c=rx[0];rx.erase(0,1);return c;}
 int availableForWrite(){return room;}
 size_t write(const uint8_t *p,size_t n){tx.append((const char*)p,n);return n;}
};
extern SerialType Serial;
