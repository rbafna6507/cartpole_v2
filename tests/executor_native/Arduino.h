#pragma once
#include <cstdint>
#include <cstddef>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <cstdlib>
#include <algorithm>
#include <string>
#define ARDUINO_TEENSY41 1
#define HIGH 1
#define LOW 0
#define OUTPUT 1
#define INPUT_PULLUP 2
struct __FlashStringHelper;
#define F(s) (reinterpret_cast<const __FlashStringHelper *>(s))
inline uint64_t oracle_now_us=0;
inline float oracle_theta=0, oracle_x=0, oracle_demand=0;
inline uint32_t micros(){return static_cast<uint32_t>(oracle_now_us);}
inline uint32_t millis(){return static_cast<uint32_t>(oracle_now_us/1000);}
inline void delay(unsigned long){}
inline void delayMicroseconds(unsigned int){}
inline void pinMode(int,int){}
inline int native_pins[64]{};
inline void digitalWrite(int pin,int value){native_pins[pin]=value;}
inline void digitalWriteFast(int pin,int value){native_pins[pin]=value;}
inline int digitalReadFast(int pin){return native_pins[pin];}
inline void __disable_irq(){}
inline void (*native_irq_hook)()=nullptr;
inline void __enable_irq(){if(native_irq_hook)native_irq_hook();}
using std::isfinite;
template<class A, class B, class C> inline auto constrain(A a,B b,C c){return std::min(static_cast<A>(c),std::max(static_cast<A>(b),a));}
template<class T> inline T max(T a,T b){return std::max(a,b);}
struct SerialStub {
  explicit operator bool() const{return true;}
  void begin(int){}
  std::string output;
  int capacity=4096;
  int availableForWrite(){return capacity;}
  int available(){return 0;}
  int read(){return -1;}
  size_t write(const uint8_t* p,size_t n){output.append(reinterpret_cast<const char*>(p),n);return n;}
};
inline SerialStub Serial;
