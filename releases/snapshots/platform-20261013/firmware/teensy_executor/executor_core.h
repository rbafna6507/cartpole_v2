#pragma once
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include <stdio.h>
#include <stdlib.h>
#include <math.h>
#include <errno.h>

// One production implementation for the board and native fault tests. No heap,
// peripheral calls, or host-time assumptions. All deadlines use 1 ms board ticks.
namespace executor {
enum Fault : uint8_t { NONE=0,ACTION_EXPIRED=1,HOST_TIMEOUT=2,DURATION=3,ENCODER=4,LIMIT=5,DEADLINE=6,RAIL=7,CONTROLLER=8,HOMING=9 };
enum ReplyKind : uint8_t { SILENT,OK,ERROR,HELLO,STATE,INFO };
struct Reply {ReplyKind kind;const char* text;};
inline bool reached(uint32_t now,uint32_t end){return int32_t(now-end)>=0;}
inline uint16_t crc(const char* p,size_t n){uint16_t c=0xffff;while(n--){c^=uint16_t(uint8_t(*p++))<<8;for(int i=0;i<8;++i)c=c&0x8000?uint16_t((c<<1)^0x1021):uint16_t(c<<1);}return c;}
inline int frame(const char* p,char* out,size_t capacity){const size_t n=strlen(p);if(n>248)return -1;const int length=snprintf(out,capacity,"@%s*%04X\n",p,crc(p,n));return length<0 || size_t(length)>=capacity?-1:length;}
inline bool uintValue(const char* p,uint32_t& value){if(!p || !*p)return false;uint32_t v=0;for(;*p;++p){if(*p<'0'||*p>'9')return false;unsigned d=*p-'0';if(v>(UINT32_MAX-d)/10)return false;v=v*10+d;}value=v;return true;}
inline bool realValue(const char* p,float& value){
 if(!p||!*p)return false;
 // Decimal ASCII only: reject strtof's whitespace, hex, NaN and infinity forms.
 const char* q=p;if(*q=='-'||*q=='+')++q;bool digits=false;
 while(*q>='0'&&*q<='9'){digits=true;++q;}if(*q=='.'){++q;while(*q>='0'&&*q<='9'){digits=true;++q;}}
 if(!digits)return false;
 if(*q=='e'||*q=='E'){++q;if(*q=='-'||*q=='+')++q;bool exponent=false;while(*q>='0'&&*q<='9'){exponent=true;++q;}if(!exponent)return false;}
 if(*q)return false;errno=0;char* end;value=strtof(p,&end);return !*end && errno!=ERANGE && isfinite(value);
}
struct LineBuffer {
 char data[256]{};uint16_t n=0;bool invalid=false;
 bool feed(char ch,const char*& out){out=nullptr;if(ch=='\n'){if(!invalid&&n){data[n]=0;out=data;}n=0;invalid=false;return true;}if(uint8_t(ch)<32||uint8_t(ch)>126){invalid=true;return false;}if(n>=254){invalid=true;return false;}if(!invalid)data[n++]=ch;return false;}
};
struct Core {
 uint32_t sid=0,tick=0,acquisition_us=0,last_seq=0;
 uint32_t host_at=0,end_at=0,action_end=0;uint16_t rate=100;
 bool enabled=false,homed=false,healthy=false;volatile bool switches=true;
 uint32_t healthy_since=0;
 uint8_t limits=0,mode=0;Fault fault=NONE;float demand=0;
 void stop(){enabled=false;mode=fault==NONE?0:4;demand=0;last_seq=0;action_end=0;}
 void trip(Fault f){if(fault==NONE)fault=f;if(f==ENCODER||f==LIMIT||f==DEADLINE||f==RAIL||f==CONTROLLER||f==HOMING)homed=false;stop();}
 void sample(bool health,uint8_t raw){if(!health||raw||!healthy||limits)healthy_since=tick;healthy=health;limits=raw&15;if(enabled){if(!healthy)trip(ENCODER);else if(switches && limits && mode!=13)trip(LIMIT);}}
 void advance(uint32_t us){++tick;acquisition_us=us;if(!enabled)return;if(reached(tick,end_at))trip(DURATION);else if(uint32_t(tick-host_at)>=200)trip(HOST_TIMEOUT);else if((mode==12||mode==1)&&reached(tick,action_end))trip(ACTION_EXPIRED);}
 bool canStart()const{return !enabled && mode==0 && fault==NONE && homed && healthy && (!switches||(limits==0 && uint32_t(tick-healthy_since)>=5));}
 Reply command(const char* line){
  if(!strcmp(line,"stop")){stop();return {OK,"STOP"};}
  const size_t size=strlen(line);if(size>255||size<7||line[0]!='@')return {ERROR,"frame"};
  const size_t n=size && line[size-1]=='\n'?size-1:size;if(n<7||line[n-5]!='*')return {ERROR,"frame"};
  uint16_t received=0;for(size_t i=n-4;i<n;++i){char ch=line[i];unsigned d;if(ch>='0'&&ch<='9')d=ch-'0';else if(ch>='A'&&ch<='F')d=ch-'A'+10;else if(ch>='a'&&ch<='f')d=ch-'a'+10;else return {ERROR,"crc"};received=uint16_t((received<<4)|d);}
  if(received!=crc(line+1,n-6))return {ERROR,"crc"};
  char payload[249];const size_t length=n-6;if(length>=sizeof payload)return {ERROR,"frame"};memcpy(payload,line+1,length);payload[length]=0;
  for(size_t i=0;i<length;++i)if(uint8_t(payload[i])<32||uint8_t(payload[i])>126)return {ERROR,"ascii"};
  char* tokens[8];unsigned count=0;char* p=payload;
  // Canonical single-space tokens: no blank/trailing/extra fields accepted.
  while(*p){if(count==8||*p==' ')return {ERROR,"args"};tokens[count++]=p;while(*p&&*p!=' ')++p;if(*p){*p++=0;if(!*p)return {ERROR,"args"};}}
  if(count<3||strcmp(tokens[0],"V2"))return {ERROR,"version"};uint32_t session;if(!uintValue(tokens[2],session)||!session)return {ERROR,"session"};const char* cmd=tokens[1];
  if(!strcmp(cmd,"HELLO")){if(count!=3)return {ERROR,"args"};if(enabled)return {ERROR,"enabled"};sid=session;stop();return {HELLO,"HELLO"};}
  if(session!=sid)return {ERROR,"session"};
  if(!strcmp(cmd,"PING")){if(count!=3)return {ERROR,"args"};host_at=tick;return {SILENT,"PING"};}
  if(!strcmp(cmd,"INFO")){if(count!=3)return {ERROR,"args"};if(enabled)return {ERROR,"enabled"};return {INFO,"INFO"};}
  if(!strcmp(cmd,"STATUS")){if(count!=3)return {ERROR,"args"};return {STATE,"STATUS"};}
  if(!strcmp(cmd,"STOP")){if(count!=3)return {ERROR,"args"};stop();return {OK,"STOP"};}
  if(!strcmp(cmd,"CLEAR")){if(count!=3)return {ERROR,"args"};if(enabled)return {ERROR,"enabled"};if(!healthy||(switches&&(limits||uint32_t(tick-healthy_since)<5)))return {ERROR,"health"};fault=NONE;stop();return {OK,"CLEAR"};}
  if(!strcmp(cmd,"RATE")){uint32_t hz;if(count!=4||!uintValue(tokens[3],hz))return {ERROR,"args"};if(hz!=0&&hz!=100&&hz!=250&&hz!=500&&hz!=1000)return {ERROR,"rate"};rate=uint16_t(hz);return {OK,"RATE"};}
  if(!strcmp(cmd,"SWITCHES")){uint32_t on;if(count!=4||!uintValue(tokens[3],on)||on>1)return {ERROR,"args"};if(enabled)return {ERROR,"enabled"};if(on&&!switches)homed=false;switches=on;return {OK,"SWITCHES"};}
  if(!strcmp(cmd,"CENTER")){if(count!=3)return {ERROR,"args"};if(enabled||mode!=0||fault!=NONE||!healthy)return {ERROR,"health"};if(switches)return {ERROR,"switches"};homed=true;return {OK,"CENTER"};}
  if(!strcmp(cmd,"HOME")){if(count!=3)return {ERROR,"args"};if(enabled||mode!=0||fault!=NONE||!healthy||limits||uint32_t(tick-healthy_since)<5)return {ERROR,"health"};if(!switches)return {ERROR,"switches"};homed=false;enabled=true;mode=13;host_at=tick;end_at=tick+60000;return {OK,"HOME"};}
  if(!strcmp(cmd,"ARM")||!strcmp(cmd,"MODE")){
   const bool arm=!strcmp(cmd,"ARM");uint32_t duration;
   if(count!=(arm?4u:5u)||!uintValue(tokens[arm?3:4],duration)||duration<1||duration>60000)return {ERROR,"duration"};
   uint8_t desired=12;if(!arm){if(!strcmp(tokens[3],"auto"))desired=2;else if(!strcmp(tokens[3],"bal"))desired=3;else if(!strcmp(tokens[3],"manual"))desired=1;else return {ERROR,"mode"};}
   if(!canStart())return {ERROR,"health"};enabled=true;mode=desired;host_at=tick;end_at=tick+duration;action_end=tick+20;demand=0;last_seq=0;return {OK,arm?"ARM":"MODE"};
  }
  if(!strcmp(cmd,"A")||!strcmp(cmd,"V")){
   const bool accel=!strcmp(cmd,"A");uint32_t seq,observed,ttl;float value;
   if(count!=7||!uintValue(tokens[3],seq)||!uintValue(tokens[4],observed)||!uintValue(tokens[5],ttl)||!realValue(tokens[6],value))return {ERROR,"args"};
   if(!enabled||mode!=(accel?12:1))return {ERROR,"mode"};if(!seq||seq<=last_seq)return {ERROR,"sequence"};
   if(ttl<1||ttl>50||int32_t(tick-observed)<0||uint32_t(tick-observed)>20||reached(tick,observed+ttl))return {ERROR,"stale"};if(fabsf(value)>(accel?25.f:.15f))return {ERROR,"value"};
   last_seq=seq;action_end=observed+ttl;demand=value;return {SILENT,accel?"A":"V"};
  }
  return {ERROR,"command"};
 }
};
}
