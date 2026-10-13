#pragma once
#include <cstdint>
#include <cstdio>
#include <cstdarg>
#include <string>
#include <deque>
#include <algorithm>
constexpr int HIGH=1, LOW=0, OUTPUT=1;
inline int pins[40] = {};
inline bool configured[40] = {};
inline int levelAtOutputEnable[40] = {};
inline uint32_t fakeMillis = 0;
// Match Arduino-ESP32 3.x: writes before pinMode do not change the latch.
inline void digitalWrite(int pin, int value) { if(configured[pin]) pins[pin]=value; }
inline void pinMode(int pin, int) { levelAtOutputEnable[pin]=pins[pin]; configured[pin]=true; }
inline int digitalRead(int pin) { return pins[pin]; }
inline void delay(int) {}
inline uint32_t millis() { return fakeMillis; }
inline uint32_t micros() { return fakeMillis*1000; }
struct FakeSerial {
  std::string output;
  std::deque<char> input;
  void begin(int) {}
  void setTxBufferSize(size_t) {}
  size_t availableForWrite() { return 128; }
  void write(const uint8_t* p,size_t n) { output.append(reinterpret_cast<const char*>(p),n); }
  int available() { return input.size(); }
  char read() { char c=input.front(); input.pop_front(); return c; }
  void print(const char* s) { output += s; }
  void println(const char* s="") { output += s; output += '\n'; }
  void printf(const char* format, ...) {
    char b[2048]; va_list args; va_start(args,format);
    vsnprintf(b,sizeof(b),format,args); va_end(args); output += b;
  }
};
inline FakeSerial Serial;
