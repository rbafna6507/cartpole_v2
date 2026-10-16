#pragma once
#include <cstring>
struct EEPROMStub {
 unsigned char bytes[8]{};
 bool fail_writes=false;
 template<class T> void get(int p,T &v){std::memcpy(&v,bytes+p,sizeof(T));}
 template<class T> void put(int p,const T &v){if(!fail_writes)std::memcpy(bytes+p,&v,sizeof(T));}
};
inline EEPROMStub EEPROM;
