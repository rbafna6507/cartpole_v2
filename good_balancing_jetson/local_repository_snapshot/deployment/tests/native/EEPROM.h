#pragma once
#include <cstdint>
#include <cstring>
struct EEPROMType {
  uint8_t bytes[32]{};
  template<class T>void get(int i,T &v){std::memcpy(&v,bytes+i,sizeof(T));}
  template<class T>void put(int i,const T &v){std::memcpy(bytes+i,&v,sizeof(T));}
};
extern EEPROMType EEPROM;
