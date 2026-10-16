static void rehome_core_guards(){
 Core c=ready();check_error(c,"V2 REHOME 8");check_error(c,"V2 REHOME 7 extra");
 assert(send(c,"V2 REHOME 7").kind==OK);assert(c.enabled&&c.mode==14&&c.fault==NONE&&c.homed);
 check_error(c,"V2 REHOME 7");check_error(c,"V2 HOME 7");
 send(c,"V2 STOP 7");assert(!c.enabled&&c.mode==0&&c.homed);
 c.homed=false;check_error(c,"V2 REHOME 7");c.homed=true;c.healthy=false;check_error(c,"V2 REHOME 7");
 c.healthy=true;c.switches=true;c.limits=1;check_error(c,"V2 REHOME 7");c.limits=0;c.tick=5;
 c.calibration=1;check_error(c,"V2 REHOME 7");c.calibration=0;c.trip(ENCODER);check_error(c,"V2 REHOME 7");
}
static void auto_return_intent(){
 for(unsigned mode:{2,3,5,6,7,8,9,10,11}){
  Core c=ready();assert(send(c,"V2 MODE 7 auto 1").kind==OK);c.mode=mode;c.advance(1000);
  assert(c.enabled&&c.mode==14&&c.fault==NONE&&c.homed);
  for(unsigned i=1;i<15000;++i){if(i%100==0)send(c,"V2 PING 7");c.advance(i*1000);assert(c.enabled&&c.mode==14);}
  c.advance(15001000);assert(!c.enabled&&c.fault==DURATION&&c.mode==4);
 }
 for(const char* payload:{"V2 ARM 7 1","V2 MODE 7 manual 1","V2 MODE 7 bal 1"}){
  Core c=ready();assert(send(c,payload).kind==OK);c.advance(1000);assert(!c.enabled&&c.fault==DURATION&&c.mode==4);
 }
 Core c=ready();send(c,"V2 MODE 7 auto 1");send(c,"V2 STOP 7");c.advance(1000);assert(!c.enabled&&c.mode==0);
 c=ready();send(c,"V2 MODE 7 auto 1");c.trip(LIMIT);c.advance(1000);assert(!c.enabled&&c.fault==LIMIT&&c.mode==4);
 c=ready();c.tick=UINT32_MAX-10;send(c,"V2 MODE 7 auto 20");for(int i=0;i<20;++i)c.advance(i);assert(c.mode==14&&c.enabled&&c.fault==NONE);
}
static void return_safety_precedence(){
 Core c=ready();send(c,"V2 MODE 7 auto 200");for(int i=0;i<200;++i)c.advance(i);assert(!c.enabled&&c.fault==HOST_TIMEOUT);
 c=ready();send(c,"V2 MODE 7 auto 1");c.healthy=false;c.advance(1000);assert(!c.enabled&&c.fault==ENCODER&&!c.homed);
 c=ready();send(c,"V2 MODE 7 auto 1");c.homed=false;c.advance(1000);assert(!c.enabled&&c.fault==HOMING);
 c=ready();c.tick=5;c.switches=true;send(c,"V2 MODE 7 auto 1");c.limits=1;c.advance(1000);assert(!c.enabled&&c.fault==LIMIT&&!c.homed);
 c=ready();send(c,"V2 REHOME 7");for(int i=0;i<200;++i)c.advance(i);assert(!c.enabled&&c.fault==HOST_TIMEOUT);
}
