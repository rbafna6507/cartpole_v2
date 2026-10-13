#pragma once
#include "Arduino.h"
extern int encoderCount;extern bool failRaw,failStatus,failConfig;
struct WireType {
  int reg=0,value=0,n=0,writes=0;
  void begin(){} void setSDA(int){} void setSCL(int){} void setClock(int){}
  void beginTransmission(int){writes=0;}
  void write(int v){if(writes++==0)reg=v;}
  int endTransmission(bool=true){return (failConfig && writes>1)?1:0;}
  int requestFrom(uint8_t,uint8_t count){advanceClock(80);
    if((reg==12 && failRaw) || (reg==11 && failStatus))return 0;
    value=reg==12?encoderCount:32;n=count;return count;
  }
  int read(){return n--==2?(value>>8)&255:value&255;}
};
extern WireType Wire1;
