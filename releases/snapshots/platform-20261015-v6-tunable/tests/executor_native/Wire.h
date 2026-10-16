#pragma once
#include <cstdint>
struct WireStub {
  bool healthy=true,status_healthy=true,conf_healthy=true,conf_writable=true;
  uint8_t status=0x20,reg=0,index=0,tx[4]{},tx_n=0; uint16_t raw=0,conf=0;
  unsigned status_reads=0,agc_reads=0,angle_reads=0;
  void beginTransmission(uint8_t){index=0;tx_n=0;}
  void write(uint8_t value){if(tx_n<4)tx[tx_n++]=value;if(index++==0)reg=value;}
  int endTransmission(bool=true){
    if(reg==0x0B)++status_reads;else if(reg==0x1A)++agc_reads;else if(reg==0x0C)++angle_reads;
    if(!healthy || (reg==0x0B&&!status_healthy) || ((reg==7||reg==8)&&!conf_healthy))return 1;
    if(conf_writable)for(unsigned n=1;n<tx_n;++n){const unsigned r=reg+n-1;if(r==7)conf=(conf&255)|(uint16_t(tx[n])<<8);if(r==8)conf=(conf&0xff00)|tx[n];}
    return 0;
  }
  int requestFrom(uint8_t,uint8_t n){index=0;return healthy?n:0;}
  int read(){++index;if(reg==7||reg==8)return reg+index-1==7?conf>>8:conf&255;return reg==0x0B?status:reg==0x1A?64:reg==0x0C?(index==1?raw>>8:raw&255):0;}
  void end(){}
  void begin(){}
  void setSDA(int){}
  void setSCL(int){}
  void setClock(int){}
};
inline WireStub Wire1;
