#pragma once
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <cstdlib>
#include <cfloat>
#include <cmath>
#include "cart_motion.h"
#include "encoder_reference.h"

namespace deployment {
constexpr float MAX_V=.25f, MAX_A=2.0f, MAX_J=20.0f, MAX_HALF=.15f;
constexpr float MIN_HALF=.03f, CONTROL_DT=.001f;
constexpr uint32_t ARM_LEASE_US=100000, SENSOR_AGE_US=3000;
enum class Mode { DISARMED, ARMED, RUNNING, FAULT };
enum class FrameResult { NONE, GOOD, BAD };

inline uint16_t crc16(const char *p,size_t n) {
  uint16_t crc=0xffff;
  while(n--) {
    crc^=uint16_t(uint8_t(*p++))<<8;
    for(int i=0;i<8;i++)crc=(crc&0x8000)?uint16_t((crc<<1)^0x1021):uint16_t(crc<<1);
  }
  return crc;
}
inline int hexDigit(char c) {
  if(c>='0' && c<='9')return c-'0';
  if(c>='A' && c<='F')return c-'A'+10;
  if(c>='a' && c<='f')return c-'a'+10;
  return -1;
}
inline size_t frame(const char *payload,char *out,size_t size) {
  const size_t n=std::strlen(payload);
  if(n+7>256 || size<n+8)return 0;
  const int written=std::snprintf(out,size,"@%s*%04X\n",payload,crc16(payload,n));
  return written>0?size_t(written):0;
}
struct FrameParser {
  // 255 bytes before newline; complete frames never exceed 256 bytes.
  char line[256]{};size_t used=0;bool bad=false;
  void reset(){used=0;bad=false;}
  FrameResult feed(char c,char *payload,size_t size) {
    if(c!='\n') {
      if(c<32 || c>126)bad=true;
      if(used<255)line[used++]=c;else bad=true;
      return FrameResult::NONE;
    }
    const size_t n=used;const bool invalid=bad;reset();
    if(invalid || n<7 || line[0]!='@' || line[n-5]!='*')return FrameResult::BAD;
    uint16_t expected=0;
    for(size_t i=n-4;i<n;i++) {
      const int digit=hexDigit(line[i]);if(digit<0)return FrameResult::BAD;
      expected=uint16_t((expected<<4)|digit);
    }
    const size_t count=n-6;
    if(count==0 || count>=size || crc16(line+1,count)!=expected)return FrameResult::BAD;
    std::memcpy(payload,line+1,count);payload[count]=0;return FrameResult::GOOD;
  }
};
inline bool uint32(const char *s,uint32_t &n) {
  if(!s || !*s)return false;
  n=0;
  for(;*s;s++) {
    if(*s<'0' || *s>'9')return false;
    const uint32_t digit=uint32_t(*s-'0');
    if(n>(UINT32_MAX-digit)/10)return false;
    n=n*10+digit;
  }
  return true;
}
inline bool finiteFloat(const char *s,float &n) {
  if(!s || !*s)return false;
  // Forbid hex floats, inf/nan, locale whitespace and trailing junk.
  for(const char *p=s;*p;p++)
    if(!((*p>='0' && *p<='9') || *p=='+' || *p=='-' || *p=='.' || *p=='e' || *p=='E'))return false;
  char *end=nullptr;const double d=std::strtod(s,&end);
  if(end==s || *end || !std::isfinite(d) || std::fabs(d)>FLT_MAX)return false;
  n=float(d);return std::isfinite(n);
}
inline const char *modeName(Mode m) {
  switch(m){case Mode::ARMED:return "ARMED";case Mode::RUNNING:return "RUNNING";
    case Mode::FAULT:return "FAULT";default:return "DISARMED";}
}
struct Executor {
  Mode mode=Mode::DISARMED;
  bool homed=false,encoder_valid=false,hardware_ready=true;
  uint32_t session=0,sequence=0,sample_us=0,deadline=0,last_session=0;
  unsigned home_generation=0,stream_hz=0;
  int owner=0,raw=0,upright_raw=encoder_reference::upright_raw;
  const char *fault="none";
  float theta=0,omega=0,x=0,half=MAX_HALF,target=0;
  char kind='a';cart_motion::State motion{};
  uint32_t observed[64]{};unsigned observed_count=0,observed_next=0;
  bool prior_sensor=false;float prior_theta=0;
  bool enabled()const{return mode==Mode::ARMED || mode==Mode::RUNNING;}
  void invalidate() {
    homed=false;owner=0;session=sequence=0;motion={};target=0;
    observed_count=observed_next=0;
  }
  void latch(const char *reason) {
    if(mode!=Mode::FAULT)fault=reason;
    mode=Mode::FAULT;invalidate();
  }
  void disconnected(int client){if(enabled() && client==owner)latch("disconnect");}
  void invalidInput(){if(enabled())latch("input");}
  void checkDeadline(uint32_t now) {
    if(enabled() && int32_t(now-deadline)>=0)latch("deadline");
  }
  void sample(uint32_t now,int count,bool valid) {
    const uint32_t dt=now-sample_us;
    sample_us=now;encoder_valid=valid && count>=0 && count<4096;
    if(!encoder_valid){prior_sensor=false;if(enabled())latch("encoder");return;}
    raw=count;theta=encoder_reference::angle_from_upright(raw,false,upright_raw);
    if(prior_sensor && dt>0 && dt<=5000) {
      float difference=theta-prior_theta;
      if(difference>3.141592654f)difference-=6.283185307f;
      if(difference<-3.141592654f)difference+=6.283185307f;
      const float measured=difference/(float(dt)*1e-6f);
      // 30 Hz first-order estimate; raw quantized angle stays in telemetry.
      const float gain=float(dt)*1e-6f/(.005305165f+float(dt)*1e-6f);
      omega+=gain*(measured-omega);
    }else omega=0;
    prior_sensor=true;prior_theta=theta;
  }
  void tick(uint32_t now,float pulse_x) {
    x=pulse_x;checkDeadline(now);if(!enabled())return;
    if(!std::isfinite(x) || std::fabs(x)>=half-.010f){latch("rail");return;}
    if(!encoder_valid || uint32_t(now-sample_us)>SENSOR_AGE_US){latch("encoder");return;}
    if(mode==Mode::ARMED)return;
    float acceleration=target;
    if(kind=='v')acceleration=cart_motion::settledVelocityAccel(motion.velocity,motion.acceleration,target,MAX_A,MAX_J,CONTROL_DT);
    if(kind=='x') {
      const float error=target-x;
      const float vtarget=cart_motion::clamp(error*4.0f,-MAX_V,MAX_V);
      acceleration=cart_motion::settledVelocityAccel(motion.velocity,motion.acceleration,vtarget,MAX_A,MAX_J,CONTROL_DT);
    }
    motion=cart_motion::advance(motion,x,acceleration,MAX_V,MAX_A,MAX_A,MAX_J,half,CONTROL_DT);
    if(!std::isfinite(motion.velocity) || !std::isfinite(motion.acceleration))latch("numeric");
  }
  void rememberSample() {
    // Only sample timestamps emitted in state replies/stream are accepted.
    for(unsigned i=0;i<observed_count;i++)if(observed[i]==sample_us)return;
    observed[observed_next]=sample_us;observed_next=(observed_next+1)%64;
    if(observed_count<64)++observed_count;
  }
  bool knownSample(uint32_t time)const {
    for(unsigned i=0;i<observed_count;i++)if(observed[i]==time)return true;
    return false;
  }
  void state(char *out,size_t size) {
    rememberSample();const unsigned flags=(encoder_valid?1u:0u)|(homed?2u:0u)|(enabled()?4u:0u);
    std::snprintf(out,size,"D1 S %lu %s %.7g %.7g %.7g %.7g %.7g %d %u %lu %lu %s",
      (unsigned long)sample_us,modeName(mode),double(theta),double(omega),double(x),
      double(motion.velocity),double(motion.acceleration),raw,flags,
      (unsigned long)sequence,(unsigned long)session,fault);
  }
  void error(const char *code,char *out,size_t size) {
    invalidInput();std::snprintf(out,size,"D1 ERR %s",code);
  }
  void handle(const char *payload,uint32_t now,int client,char *out,size_t size) {
    checkDeadline(now);
    char copy[250];const size_t length=std::strlen(payload);
    if(!length || length>=sizeof copy){error("syntax",out,size);return;}
    std::memcpy(copy,payload,length+1);
    char *tokens[10]{};unsigned n=0;bool in=false;
    for(char *p=copy;*p;p++) {
      if(*p==' '){*p=0;in=false;continue;}
      if(*p<33 || *p>126){error("syntax",out,size);return;}
      if(!in){if(n==10){error("syntax",out,size);return;}tokens[n++]=p;in=true;}
    }
    if(n<2 || std::strcmp(tokens[0],"D1")){error("version",out,size);return;}
    const char *verb=tokens[1];
    if(!std::strcmp(verb,"stop") && n==2) {
      const bool latched=mode==Mode::FAULT;invalidate();if(!latched)mode=Mode::DISARMED;
      std::snprintf(out,size,"D1 OK stop");return;
    }
    if(!std::strcmp(verb,"state") && n==2){state(out,size);return;}
    if(!std::strcmp(verb,"info") && n==2) {
      std::snprintf(out,size,"D1 I 1 1000 500 60 26666.666667 0.15 0.25 2 20 encoder");return;
    }
    if(!std::strcmp(verb,"stream") && n==3) {
      uint32_t hz;if(!uint32(tokens[2],hz) || hz>500){error("stream",out,size);return;}
      stream_hz=hz;std::snprintf(out,size,"D1 OK stream");return;
    }
    if(!std::strcmp(verb,"clear") && n==2) {
      if(enabled()){error("active",out,size);return;}
      if(!hardware_ready){error("timer",out,size);return;}
      invalidate();mode=Mode::DISARMED;fault="none";
      std::snprintf(out,size,"D1 OK clear");return;
    }
    if(mode==Mode::FAULT){error("fault",out,size);return;}
    if(!std::strcmp(verb,"home") && n==3) {
      if(mode!=Mode::DISARMED){error("active",out,size);return;}
      float span;if(!finiteFloat(tokens[2],span) || span<MIN_HALF || span>MAX_HALF){error("rail",out,size);return;}
      half=span;x=0;motion={};homed=true;++home_generation;
      observed_count=observed_next=0;
      std::snprintf(out,size,"D1 OK home");return;
    }
    if(!std::strcmp(verb,"arm") && n==3) {
      if(mode!=Mode::DISARMED){error("active",out,size);return;}
      if(!homed){error("home",out,size);return;}
      if(!hardware_ready){error("timer",out,size);return;}
      if(!encoder_valid || uint32_t(now-sample_us)>SENSOR_AGE_US){error("encoder",out,size);return;}
      uint32_t identity;if(!uint32(tokens[2],identity) || !identity || identity==last_session){error("session",out,size);return;}
      session=last_session=identity;sequence=0;owner=client;mode=Mode::ARMED;
      deadline=now+ARM_LEASE_US;std::snprintf(out,size,"D1 OK arm");return;
    }
    if(!std::strcmp(verb,"act") && n==8) {
      if(!enabled()){error("disarmed",out,size);return;}
      if(client!=owner){error("owner",out,size);return;}
      uint32_t identity,seq,observed_us,ttl;
      if(!uint32(tokens[2],identity) || identity!=session || !identity){error("session",out,size);return;}
      if(!uint32(tokens[3],seq) || seq<=sequence){error("sequence",out,size);return;}
      if(!uint32(tokens[4],observed_us) || int32_t(now-observed_us)<0 || !knownSample(observed_us)){error("observation",out,size);return;}
      if(!uint32(tokens[5],ttl) || ttl<10 || ttl>100){error("ttl",out,size);return;}
      if(uint32_t(now-observed_us)>=ttl*1000){error("stale",out,size);return;}
      if(std::strlen(tokens[6])!=1 || (tokens[6][0]!='a' && tokens[6][0]!='v' && tokens[6][0]!='x')){error("kind",out,size);return;}
      float value;if(!finiteFloat(tokens[7],value)){error("value",out,size);return;}
      const char new_kind=tokens[6][0];
      const float bound=new_kind=='a'?MAX_A:(new_kind=='v'?MAX_V:half-.015f);
      if(std::fabs(value)>bound){error("bounds",out,size);return;}
      sequence=seq;deadline=observed_us+ttl*1000;kind=new_kind;target=value;mode=Mode::RUNNING;
      std::snprintf(out,size,"D1 OK act %lu",(unsigned long)seq);return;
    }
    error("syntax",out,size);
  }
};
} // namespace deployment
