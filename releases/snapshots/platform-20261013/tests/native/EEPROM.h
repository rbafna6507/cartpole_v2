#pragma once
#include <cstring>
struct EEPROMStub {
 unsigned char bytes[8]{};
 template<class T> void get(int p,T &v){std::memcpy(&v,bytes+p,sizeof(T));}
 template<class T> void put(int p,const T &v){std::memcpy(bytes+p,&v,sizeof(T));}
};
inline EEPROMStub EEPROM;
