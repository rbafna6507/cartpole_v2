#pragma once
#include <cstdint>
#include <cstddef>
#include <string>
#include <memory>
#include <algorithm>
struct IPAddress {IPAddress(int,int,int,int){}};
namespace qindesign {namespace network {
struct State {bool connected=true;std::string rx,tx;int space=8192;};
struct EthernetClient {
 std::shared_ptr<State> s;
 explicit operator bool() const{return s&&s->connected;}
 void abort(){if(s)s->connected=false;}
 bool connected(){return bool(*this);}
 void setNoDelay(bool){}
 int available(){return s?s->rx.size():0;}
 int read(){if(!available())return -1;char c=s->rx[0];s->rx.erase(0,1);return c;}
 int availableForWrite(){return s?s->space:0;}
 size_t write(const uint8_t *p,size_t n){n=std::min(n,(size_t)s->space);s->tx.append((const char*)p,n);return n;}
};
inline EthernetClient pending;
struct EthernetServer {EthernetServer(int){} void begin(){} EthernetClient accept(){auto c=pending;pending={};return c;}};
struct EthernetType {bool link=true;bool begin(IPAddress,IPAddress,IPAddress){return true;} bool linkState(){return link;}};
inline EthernetType Ethernet;
}}
