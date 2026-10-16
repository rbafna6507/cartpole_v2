#include "executor_core.h"
#include "cart_homing.h"
#include <cassert>
#include <cstdio>
#include <cstring>
#include <string>
#include <iostream>
using namespace executor;
static Reply send(Core& c, const std::string& p){char b[256];assert(frame(p.c_str(), b, sizeof b)>0);return c.command(b);}
static Core ready(){Core c;c.sample(true,0);assert(send(c,"V2 HELLO 7").kind==HELLO);assert(send(c,"V2 SWITCHES 7 0").kind==OK);assert(send(c,"V2 CENTER 7").kind==OK);return c;}
static void arm(Core& c,uint32_t duration=1000){assert(send(c,"V2 ARM 7 "+std::to_string(duration)).kind==OK);}
static void check_error(Core& c,const std::string& p){assert(send(c,p).kind==ERROR);}
static void framing(){
 assert(crc("123456789",9)==0x29B1);Core c;c.sample(true,0);char b[256];frame("V2 HELLO 7",b,sizeof b);b[3]^=1;assert(c.command(b).kind==ERROR);assert(c.sid==0);
 check_error(c,"V2 HELLO 0");check_error(c,"V2 HELLO 4294967296");check_error(c,"V2 HELLO -1");check_error(c,"V2 HELLO 7 extra");
 assert(send(c,"V2 HELLO 7").kind==HELLO);check_error(c,"V2 ARM 7 +1");check_error(c,"V2 RATE 7 999");check_error(c,"V2 HELLO 8\t");
 LineBuffer line;const char* out=nullptr;for(int i=0;i<300;++i)assert(!line.feed('a',out));assert(line.feed('\n',out));assert(out==nullptr);for(char ch:std::string("stop\n"))line.feed(ch,out);assert(out && !strcmp(out,"stop"));
 for(char ch:std::string("V2\x01HELLO\n"))line.feed(ch,out);assert(!out);
 assert(c.command("auto").kind==ERROR);assert(c.command("stop").kind==OK);assert(!c.enabled);
}
static void stable_switches(){Core c;c.sample(true,0);send(c,"V2 HELLO 7");check_error(c,"V2 HOME 7");for(int i=0;i<5;++i)c.advance(i);assert(send(c,"V2 HOME 7").kind==OK);c.stop();c.sample(true,1);c.sample(true,0);check_error(c,"V2 HOME 7");for(int i=0;i<5;++i)c.advance(i);assert(send(c,"V2 HOME 7").kind==OK);}
static void boot_session(){Core c;assert(!c.enabled&&!c.homed&&c.switches&&c.sid==0);assert(send(c,"V2 HELLO 7").kind==HELLO);check_error(c,"V2 ARM 7 1000");c=ready();arm(c);check_error(c,"V2 HELLO 9");assert(c.sid==7&&c.enabled);check_error(c,"V2 STOP 9");assert(c.enabled);assert(send(c,"V2 STOP 7").kind==OK);assert(c.homed&&!c.enabled);assert(send(c,"V2 HELLO 9").kind==HELLO);assert(c.last_seq==0&&c.homed&&!c.enabled);}
static void actions(){Core c=ready();arm(c);assert(send(c,"V2 A 7 1 0 20 2.5").kind==SILENT);assert(c.last_seq==1&&c.demand==2.5f);check_error(c,"V2 A 7 1 0 50 3");check_error(c,"V2 A 9 2 0 50 3");check_error(c,"V2 A 7 2 0 0 3");check_error(c,"V2 A 7 2 0 51 3");check_error(c,"V2 A 7 2 0 20 nan");check_error(c,"V2 A 7 2 0 20 inf");check_error(c,"V2 A 7 2 0 20 1e99");check_error(c,"V2 A 7 2 0 20 26");check_error(c,"V2 A 7 2 0 20 2 extra");check_error(c,"V2 V 7 2 0 20 0.1");assert(c.last_seq==1&&c.demand==2.5f);for(int i=0;i<19;++i)c.advance(1000*i);assert(c.enabled);c.advance(20000);assert(!c.enabled&&c.fault==ACTION_EXPIRED);assert(send(c,"V2 STOP 7").kind==OK);check_error(c,"V2 ARM 7 1000");assert(send(c,"V2 CLEAR 7").kind==OK);arm(c);assert(c.last_seq==0&&c.demand==0);}
static void wrap(){Core c=ready();c.tick=UINT32_MAX-5;arm(c);assert(send(c,"V2 A 7 1 4294967290 10 1").kind==SILENT);for(int i=0;i<9;++i)c.advance(i);assert(c.enabled);c.advance(10);assert(!c.enabled&&c.tick==4);c=ready();c.tick=100;arm(c);check_error(c,"V2 A 7 1 101 20 1");check_error(c,"V2 A 7 1 79 50 1");check_error(c,"V2 A 7 1 80 20 1");assert(send(c,"V2 A 7 4294967295 80 21 1").kind==SILENT);check_error(c,"V2 A 7 1 100 20 1");}
static void guards(){Core c=ready();check_error(c,"V2 ARM 7 0");check_error(c,"V2 ARM 7 60001");c.sample(false,0);check_error(c,"V2 ARM 7 1000");c.sample(true,0);arm(c);check_error(c,"V2 CENTER 7");check_error(c,"V2 CLEAR 7");check_error(c,"V2 SWITCHES 7 1");c.trip(ENCODER);assert(!c.homed&&!c.enabled);assert(send(c,"V2 CLEAR 7").kind==OK);check_error(c,"V2 ARM 7 1000");}
static void watchdogs(){Core c=ready();arm(c,1);c.advance(1000);assert(!c.enabled&&c.fault==DURATION);c=ready();assert(send(c,"V2 MODE 7 auto 1000").kind==OK);for(int i=0;i<199;++i)c.advance(i);assert(c.enabled);check_error(c,"V2 PING 9");c.advance(200);assert(!c.enabled&&c.fault==HOST_TIMEOUT);c=ready();arm(c);send(c,"V2 A 7 1 0 20 1");for(int i=0;i<20;++i){send(c,"V2 PING 7");c.advance(i);}assert(c.fault==ACTION_EXPIRED);c=ready();assert(send(c,"V2 MODE 7 manual 1000").kind==OK);check_error(c,"V2 V 7 1 0 20 0.16");assert(send(c,"V2 V 7 1 0 20 -.15").kind==SILENT);assert(c.demand==-.15f);}
static void switches(){Core c;c.sample(true,15);send(c,"V2 HELLO 7");check_error(c,"V2 ARM 7 1000");check_error(c,"V2 HOME 7");check_error(c,"V2 CENTER 7");assert(send(c,"V2 SWITCHES 7 0").kind==OK);assert(send(c,"V2 CENTER 7").kind==OK);arm(c);c.sample(true,15);assert(c.enabled);send(c,"V2 STOP 7");assert(send(c,"V2 SWITCHES 7 1").kind==OK);assert(!c.homed);check_error(c,"V2 HOME 7");c.sample(true,0);for(int i=0;i<5;++i)c.advance(i);assert(send(c,"V2 HOME 7").kind==OK);assert(c.mode==13&&c.enabled&&!c.homed);c.stop();c.homed=true;arm(c);c.sample(true,1);assert(!c.enabled&&!c.homed&&c.fault==LIMIT);}
static void homing_success(){
 // Contact-to-contact widths from the former short fixture through the new
 // 750 mm cap; start near either end to exercise the total deadline too.
 for(int half:{7000,9000,10000})for(int start:{-half+300,0,half-300}){
  cart_homing::Machine m;assert(m.start(0,start,0));int32_t pos=start;uint32_t tick=0;double fraction=0;unsigned seen=0;
  for(;tick<75000&&!m.done()&&!m.failed();++tick){uint8_t raw=(pos<=-half?1:0)|(pos>=half?2:0);seen|=raw;m.update(tick,pos,raw);float v=m.velocity(pos);if((raw&1)&&v<0)assert(false);if((raw&2)&&v>0)assert(false);fraction+=v*cart_homing::steps_per_m/1000;int n=(int)fraction;pos+=n;fraction-=n;}
  assert(m.done());assert(seen==3);assert(m.negative==-half&&m.positive==half);assert(pos==m.center());assert(m.span()==2*half);assert(fabsf(m.safeRail(.26f)-(half==7000?.2575f:.26f))<1e-6);
 }
 cart_homing::Machine m; m.negative=-5334;m.positive=5334;assert(m.safeRail(.26f)<.196f);
 // A missing contact must stop within 750 mm; an oversize measured span fails.
 assert(m.start(0,0,0));m.update(1,-20001,0);assert(m.failed());
 assert(m.start(0,0,0));m.negative=0;m.enter(cart_homing::Machine::SEEK_POS,10,134);m.update(20,20001,0);assert(m.failed());
 assert(m.start(0,0,0));m.negative=-10001;m.positive=10000;m.enter(cart_homing::Machine::CLEAR_POS,10,9800);m.released=true;m.release_pos=9800;m.update(20,9600,0);assert(m.failed());
 assert(m.start(0,0,0));m.enter(cart_homing::Machine::SEEK_POS,74000,0);m.update(75000,0,0);assert(m.failed());
}
static void homing_faults(){cart_homing::Machine m;assert(!m.start(0,0,1));assert(!m.start(0,0,12));assert(m.start(0,0,0));m.update(1,0,2);assert(m.failed());assert(m.start(0,0,0));m.update(27000,0,0);assert(m.failed());assert(m.start(0,0,0));m.update(1,-20001,0);assert(m.failed());assert(m.start(0,0,0));m.update(1,-100,1);assert(m.velocity()==0);for(unsigned i=2;i<8;++i)m.update(i,-100,1);assert(m.velocity()>0);m.update(2000,-100,1);assert(m.failed());assert(m.start(0,0,0));m.cancel();assert(!m.active()&&!m.done());}
static void homing_more_faults(){
 cart_homing::Machine m;assert(m.start(0,0,0));m.update(1,0,3);assert(m.failed());
 assert(m.start(0,0,0));m.update(1,0,8);assert(m.failed());
 assert(m.start(0,0,0));m.update(1,-100,1);for(unsigned i=2;i<8;++i)m.update(i,-100,0);assert(m.failed());
 assert(m.start(0,0,0));int32_t pos=0;double fractional=0;
 for(uint32_t tick=0;tick<60000&&!m.done()&&!m.failed();++tick){uint8_t raw=(pos<=-2000?1:0)|(pos>=2000?2:0);m.update(tick,pos,raw);fractional+=m.velocity(pos)*cart_homing::steps_per_m/1000;int n=int(fractional);pos+=n;fractional-=n;}
 assert(m.failed()&&!m.done());
 Core c;c.sample(true,0);send(c,"V2 HELLO 7");for(int i=0;i<5;++i)c.advance(i);assert(send(c,"V2 HOME 7").kind==OK);for(int i=0;i<200;++i)c.advance(i);assert(!c.enabled&&c.fault==HOST_TIMEOUT&&!c.homed);
}
static void calibration_guards(){
 Core c=ready();check_error(c,"V2 CALIBRATE 8 upright");
 check_error(c,"V2 CALIBRATE 7 wrong");check_error(c,"V2 CALIBRATE 7 upright extra");
 assert(send(c,"V2 CALIBRATE 7 upright").kind==OK);assert(!c.enabled);
 check_error(c,"V2 ARM 7 1000");check_error(c,"V2 MODE 7 auto 1000");
 check_error(c,"V2 HOME 7");check_error(c,"V2 CENTER 7");check_error(c,"V2 CALIBRATE 7 hanging");
 assert(send(c,"V2 INFO 7").kind==INFO);assert(send(c,"V2 STOP 7").kind==OK);
 arm(c);check_error(c,"V2 CALIBRATE 7 hanging");c.trip(ENCODER);
 check_error(c,"V2 CALIBRATE 7 hanging");assert(send(c,"V2 CLEAR 7").kind==OK);
 c.sample(false,0);check_error(c,"V2 CALIBRATE 7 upright");
 c.sample(true,12);assert(send(c,"V2 CALIBRATE 7 hanging").kind==OK);
 assert(send(c,"V2 HELLO 9").kind==HELLO);
 assert(send(c,"V2 CALIBRATE 9 upright").kind==OK);
}
static void cart_only_switches(){
 Core c;c.sample(true,12);send(c,"V2 HELLO 7");
 // User's flags=201: encoder healthy, profile on, unused 3/4 open.
 check_error(c,"V2 HOME 7");
 for(int i=0;i<5;++i){c.advance(i);c.sample(true,i%2?4:12);}
 assert(c.limits==12);assert(send(c,"V2 HOME 7").kind==OK);
 assert(c.enabled&&c.mode==13&&!c.homed);c.stop();c.homed=true;
 arm(c);c.sample(true,12);assert(c.enabled&&c.fault==NONE);
 c.sample(true,13);assert(!c.enabled&&!c.homed&&c.fault==LIMIT);
 check_error(c,"V2 CLEAR 7");c.sample(true,12);check_error(c,"V2 CLEAR 7");
 for(int i=0;i<5;++i){c.advance(i);c.sample(true,12);}
 assert(send(c,"V2 CLEAR 7").kind==OK);assert(!c.homed&&!c.enabled&&c.fault==NONE);
 check_error(c,"V2 ARM 7 1000");assert(send(c,"V2 HOME 7").kind==OK);
 c.stop();c.homed=true;arm(c);c.sample(true,14);
 assert(!c.enabled&&!c.homed&&c.fault==LIMIT);
}
static void info_guards(){Core c=ready();assert(send(c,"V2 INFO 7").kind==INFO);check_error(c,"V2 INFO 8");check_error(c,"V2 INFO 7 extra");arm(c);check_error(c,"V2 INFO 7");c.trip(ENCODER);assert(send(c,"V2 INFO 7").kind==INFO);}
static void homing_duration(){
 Core c;c.sample(true,0);send(c,"V2 HELLO 7");
 for(int i=0;i<5;++i)c.advance(i*1000);
 assert(send(c,"V2 HOME 7").kind==OK);
 for(uint32_t elapsed=1;elapsed<75000;++elapsed){
  if(elapsed%100==0)assert(send(c,"V2 PING 7").kind==SILENT);
  c.advance((elapsed+5)*1000);assert(c.enabled&&c.fault==NONE);
 }
 c.advance(75005000);assert(!c.enabled&&c.fault==DURATION);
}
#include "parameters_core_test.h"
#include "rehome_core_test.h"
int main(int argc,char** argv){assert(argc==2);std::string n=argv[1];if(n=="rehome_core_guards")rehome_core_guards();else if(n=="auto_return_intent")auto_return_intent();else if(n=="return_safety_precedence")return_safety_precedence();else if(n=="homing_duration")homing_duration();else if(n=="parameter_core_guards")parameter_core_guards();else if(n=="calibration_guards")calibration_guards();else if(n=="cart_only_switches")cart_only_switches();else if(n=="info_guards")info_guards();else if(n=="homing_more_faults")homing_more_faults();else if(n=="stable_switches")stable_switches();else if(n=="framing")framing();else if(n=="boot_session")boot_session();else if(n=="actions")actions();else if(n=="wrap")wrap();else if(n=="guards")guards();else if(n=="watchdogs")watchdogs();else if(n=="switches")switches();else if(n=="homing_success")homing_success();else if(n=="homing_faults")homing_faults();else return 2;std::cout<<n<<" passed\n";}
