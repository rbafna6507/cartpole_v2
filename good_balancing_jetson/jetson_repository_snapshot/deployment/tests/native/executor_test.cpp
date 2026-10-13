#include <cassert>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <string>
#include "../../firmware/deployment_executor/executor.h"

using deployment::Executor;
using deployment::Mode;
static std::string request(Executor &e, const char *p, uint32_t now, int client=1) {
  char reply[250]; e.handle(p, now, client, reply, sizeof reply); return reply;
}
static void sampled(Executor &e,uint32_t now,int raw=3953,float x=0) {
  e.sample(now, raw, true); e.tick(now, x);
}
static void prepared(Executor &e,uint32_t now=100000,int client=1,uint32_t session=7) {
  sampled(e,now);
  assert(request(e,"D1 home 0.15",now,client)=="D1 OK home");
  char text[60]; std::snprintf(text,sizeof text,"D1 arm %u",session);
  assert(request(e,text,now,client)=="D1 OK arm");
  assert(e.mode==Mode::ARMED && e.enabled() && e.homed);
  assert(request(e,"D1 state",now,client).find("D1 S ")==0);
}
static std::string act(Executor &e,uint32_t now,uint32_t observed,uint32_t seq=1,
                       const char *kind="a",const char *value="1",unsigned ttl=50,
                       uint32_t session=7,int client=1) {
  char text[180]; std::snprintf(text,sizeof text,"D1 act %u %u %u %u %s %s",
    session,seq,observed,ttl,kind,value); return request(e,text,now,client);
}
static void boot_home_arm_stop_clear() {
  Executor e;
  assert(e.mode==Mode::DISARMED && !e.enabled() && !e.homed);
  assert(request(e,"D1 arm 7",100000)=="D1 ERR home");
  sampled(e,100000);
  assert(request(e,"D1 home 0.15",100000)=="D1 OK home");
  assert(!e.enabled() && e.homed && e.x==0);
  assert(request(e,"D1 arm 7",100000)=="D1 OK arm");
  assert(e.enabled() && e.motion.velocity==0);
  assert(request(e,"D1 stop",100000)=="D1 OK stop");
  assert(e.mode==Mode::DISARMED && !e.homed && !e.enabled() && e.session==0);
  assert(request(e,"D1 clear",100000)=="D1 OK clear");
  assert(!e.homed && !e.enabled());
}
static void observation_anchored_expiry() {
  Executor e;prepared(e);
  assert(act(e,149000,100000)=="D1 OK act 1");
  sampled(e,149000);
  assert(e.mode==Mode::RUNNING && e.motion.acceleration>0);
  sampled(e,150000);
  assert(e.mode==Mode::FAULT && std::string(e.fault)=="deadline");
  assert(!e.homed && !e.enabled() && e.session==0);
  assert(request(e,"D1 home 0.15",150000)=="D1 ERR fault");
  assert(request(e,"D1 arm 8",150000)=="D1 ERR fault");
  assert(request(e,"D1 clear",150000)=="D1 OK clear");
  assert(e.mode==Mode::DISARMED && !e.homed);
}
static void armed_lease_and_passive_traffic() {
  Executor e;prepared(e);
  assert(request(e,"D1 info",190000).find("D1 I 1 1000 500")==0);
  assert(request(e,"D1 state",190000).find("D1 S ")==0);
  assert(request(e,"D1 stream 500",190000)=="D1 OK stream");
  sampled(e,200000);
  assert(e.mode==Mode::FAULT && std::string(e.fault)=="deadline");
  assert(request(e,"D1 stop",200000)=="D1 OK stop" && e.mode==Mode::FAULT);
}
static void rejects_unsafe_active_commands() {
  const char *invalid[]={
    "D1 act 7 1 100000 50 a nan", "D1 act 7 1 100000 50 a inf",
    "D1 act 7 1 100000 50 a 1e100", "D1 act 7 1 100000 50 a 0x1p0",
    "D1 act 7 1 100000 50 a 2.001", "D1 act 7 1 100000 50 v .251",
    "D1 act 7 1 100000 50 x .136", "D1 act 7 1 100000 9 a 0",
    "D1 act 7 1 100000 101 a 0", "D1 act 0 1 100000 50 a 0",
    "D1 act 8 1 100000 50 a 0", "D1 act 7 0 100000 50 a 0",
    "D1 act 7 1 100001 50 a 0", "D1 act 7 1 50000 50 a 0",
    "D1 act 7 1 99999 50 a 0", "D1 act 7 1 100000 50 z 0",
    "D1 act 7 1 100000 50 a 0 extra", "D1 act 7 1 100000 50 a",
    "D1 act 7 +1 100000 50 a 0", "D1 act 7 4294967296 100000 50 a 0",
    "D1 home 0.15", "D1 arm 8", "v 5", "D1 clear", "D1 stream 501"
  };
  for(const char *bad:invalid) {
    Executor e;prepared(e);
    assert(request(e,bad,100000).find("D1 ERR ")==0);
    assert(e.mode==Mode::FAULT && !e.enabled() && !e.homed);
  }
  Executor e;prepared(e);
  assert(act(e,100000,100000,1)=="D1 OK act 1");
  assert(act(e,100000,100000,1).find("D1 ERR ")==0 && e.mode==Mode::FAULT);
}
static void ownership_encoder_disconnect() {
  Executor e;prepared(e);
  assert(request(e,"D1 state",100000,2).find("D1 S ")==0);
  assert(act(e,100000,100000,1,"a","0",50,7,2)=="D1 ERR owner");
  assert(e.mode==Mode::FAULT);
  Executor f;prepared(f);f.disconnected(2);assert(f.enabled());
  f.disconnected(1);assert(f.mode==Mode::FAULT && std::string(f.fault)=="disconnect");
  Executor g;prepared(g);g.sample(101000,-1,false);
  assert(g.mode==Mode::FAULT && !g.enabled() && !g.encoder_valid);
  Executor h;sampled(h,100000);request(h,"D1 home 0.15",100000);
  assert(request(h,"D1 arm 9",106000)=="D1 ERR encoder" && !h.enabled());
}
static void wrap_and_sensor_coordinates() {
  Executor e;prepared(e,0xfffffff0u);
  assert(act(e,0x10u,0xfffffff0u)=="D1 OK act 1");
  sampled(e,0xfffffff0u+49999u);assert(e.enabled());
  sampled(e,0xfffffff0u+50000u);assert(e.mode==Mode::FAULT);
  Executor f;sampled(f,1000,3953);assert(std::fabs(f.theta)<1e-6f);
  sampled(f,2000,881);assert(std::fabs(f.theta-1.570796327f)<1e-6f);
  sampled(f,3000,1905);assert(std::fabs(std::fabs(f.theta)-3.141592654f)<1e-6f);
  Executor g;g.upright_raw=4095;sampled(g,1000,4095);sampled(g,2000,0);
  assert(g.theta>0 && std::fabs(g.omega)<1.6f);
}
static void cart_governor_bounds() {
  Executor e;prepared(e);float x=0;uint32_t now=100000;uint32_t seq=1;
  for(int i=0;i<6000;i++) {
    if(i%10==0){request(e,"D1 state",now);assert(act(e,now,now,seq++) .find("D1 OK")==0);}
    now+=1000;sampled(e,now,3953,x);x+=e.motion.velocity*.001f;
    assert(std::fabs(e.motion.velocity)<=.25001f);
    assert(std::fabs(e.motion.acceleration)<=2.00001f);
    assert(std::fabs(x)<.14f && e.enabled());
  }
  assert(x>.10f && x<.14f);
  sampled(e,now+1000,3953,.141f);assert(e.mode==Mode::FAULT);
  Executor f;prepared(f);sampled(f,101000,3953,NAN);assert(f.mode==Mode::FAULT);
}
static void lowlevel_velocity_and_position_targets() {
  for(const char *kind:{"v","x"}) {
    Executor e;prepared(e);float x=0;uint32_t now=100000,seq=1;
    const char *value=kind[0]=='v'?".05":".04";
    const int ticks=kind[0]=='v'?1000:4000;
    for(int i=0;i<ticks;i++) {
      if(i%10==0){request(e,"D1 state",now);assert(act(e,now,now,seq++,kind,value).find("D1 OK")==0);}
      const float prior=e.motion.acceleration;
      now+=1000;sampled(e,now,3953,x);x+=e.motion.velocity*.001f;
      assert(std::fabs(e.motion.acceleration-prior)<=.020001f && e.enabled());
    }
    if(kind[0]=='v')assert(e.motion.velocity>.049f && e.motion.velocity<.051f && x>.02f);
    else assert(std::fabs(x-.04f)<.004f && std::fabs(e.motion.velocity)<.01f);
  }
  Executor e;prepared(e);sampled(e,100001);request(e,"D1 state",100001);
  assert(act(e,100000,100001)=="D1 ERR observation" && !e.enabled());
  request(e,"D1 clear",100001);request(e,"D1 home .15",100001);
  assert(request(e,"D1 arm 7",100001)=="D1 ERR session" && !e.enabled());
}
static void exact_frames_and_parser_recovery() {
  // Removing CRC validation or losing overflow-discard state must fail here.
  deployment::FrameParser p;char payload[250];
  const char *valid="@D1 state*3372\n"; // independent Python binascii.crc_hqx fixture
  deployment::FrameResult result=deployment::FrameResult::NONE;
  for(const char *c=valid;*c;c++) result=p.feed(*c,payload,sizeof payload);
  assert(result==deployment::FrameResult::GOOD && std::string(payload)=="D1 state");
  const char *bad="@D1 state*0000\n";
  for(const char *c=bad;*c;c++) result=p.feed(*c,payload,sizeof payload);
  assert(result==deployment::FrameResult::BAD);
  for(int i=0;i<500;i++) assert(p.feed('X',payload,sizeof payload)==deployment::FrameResult::NONE);
  assert(p.feed('\n',payload,sizeof payload)==deployment::FrameResult::BAD);
  for(const char *c=valid;*c;c++) result=p.feed(*c,payload,sizeof payload);
  assert(result==deployment::FrameResult::GOOD);
  std::string nul="@D1 state";nul.push_back('\0');nul+="*3372\n";
  for(char c:nul)result=p.feed(c,payload,sizeof payload);
  assert(result==deployment::FrameResult::BAD);
  for(const char *c="@D1 state*3372\r\n";*c;c++)result=p.feed(*c,payload,sizeof payload);
  assert(result==deployment::FrameResult::BAD);
}
int main() {
  boot_home_arm_stop_clear();observation_anchored_expiry();armed_lease_and_passive_traffic();
  rejects_unsafe_active_commands();ownership_encoder_disconnect();wrap_and_sensor_coordinates();
  cart_governor_bounds();lowlevel_velocity_and_position_targets();exact_frames_and_parser_recovery();
  std::puts("executor tests: 9 groups passed");
}
