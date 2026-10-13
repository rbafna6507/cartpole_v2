#pragma once
#include <cstdint>
struct WireStub {
  bool healthy=true,status_healthy=true; uint8_t status=0x20,reg=0,index=0;
 unsigned status_reads=0,agc_reads=0,angle_reads=0;
  void beginTransmission(uint8_t){index=0;}
  void write(uint8_t value){if(index++==0)reg=value;}
  int endTransmission(bool=true){if(reg==0x0B)++status_reads;else if(reg==0x1A)++agc_reads;else if(reg==0x0C)++angle_reads;return healthy && (reg!=0x0B || status_healthy)?0:1;}
  int requestFrom(uint8_t,uint8_t n){index=0;return healthy?n:0;}
  int read(){++index;return reg==0x0B?status:reg==0x1A?64:0;}
  void end(){}
  void begin(){}
  void setSDA(int){}
  void setSCL(int){}
  void setClock(int){}
};
inline WireStub Wire1;
