#pragma once
#include <cstdint>
#include <cstddef>
struct IPAddress{template<class... T> IPAddress(T...){}};
namespace qindesign::network {
struct EthernetClient {
 explicit operator bool() const{return false;}
 void abort(){} void setNoDelay(bool){} int available(){return 0;}
 int read(){return -1;} int availableForWrite(){return 0;}
 size_t write(const uint8_t*,size_t n){return n;}
};
struct EthernetServer{explicit EthernetServer(int){} void begin(){} EthernetClient accept(){return {};}};
struct EthernetStub{bool begin(IPAddress,IPAddress,IPAddress){return false;} bool linkState(){return false;}};
inline EthernetStub Ethernet;
}
