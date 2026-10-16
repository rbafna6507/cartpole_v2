// End-to-end stopped parameter and actual pulse/control regressions.
static void tunable_motion(){
 init();
 const struct {const char* name;const char* value;float expected;} rows[]={
  {"manual_speed_max","2.5",2.5f},{"vman","2",2},
  {"vmax","2.5",2.5f},{"vmax_s","2.5",2.5f},{"vmax_b","2.5",2.5f},
  {"approach_v","2",2},{"catch_v","2",2},{"catch_da","200",200},
  {"amax_s","200",200},{"amax_b","200",200},{"amax_m","200",200},
  {"jmax","10000",10000},{"jmax_m","10000",10000},
  {"rail_recover_v","2",2},{"rail_recover_a","200",200},{"rail_recover_s","60",60},
  {"rehome_v","2",2},{"rehome_a","200",200},{"rehome_j","10000",10000}
 };
 for(const auto& row:rows)parameter_write(row.name,row.value,row.expected);
 char maximum_speed[32];snprintf(maximum_speed,sizeof maximum_speed,"%.9g",double(cart_hardware::max_speed));
 parameter_write("vmax",maximum_speed,cart_hardware::max_speed);
 for(const char* name:{"vmax","vmax_s","vmax_b","approach_v","catch_v","manual_speed_max","rail_recover_v","rehome_v"}){
  parameter_reject(std::string("V2 PARAM 7 ")+name+" 2.67858");
  parameter_reject(std::string("V2 PARAM 7 ")+name+" 0");
 }
 for(const char* name:{"amax_s","amax_b","amax_m","catch_da","rail_recover_a","rehome_a"})parameter_reject(std::string("V2 PARAM 7 ")+name+" 200.01");
 for(const char* name:{"jmax","jmax_m","rehome_j"})parameter_reject(std::string("V2 PARAM 7 ")+name+" 10000.1");
 for(const char* name:{"amax_s","amax_b","amax_m","catch_da","rail_recover_a","rehome_a","jmax","jmax_m","rehome_j"})parameter_reject(std::string("V2 PARAM 7 ")+name+" 0");
 parameter_reject("V2 PARAM 7 manual_speed_max 1.99");
 parameter_reject("V2 PARAM 7 rail_recover_s .099");parameter_reject("V2 PARAM 7 rail_recover_s 60.01");
 for(const char* name:{"manual_speed_max","rail_margin","rail_fraction","rehome_j"})
  for(const char* invalid:{"nan","inf","-inf","0x1p0"})parameter_reject(std::string("V2 PARAM 7 ")+name+" "+invalid);
 cmd("V2 ARM 7 1000");cmd("V2 A 7 1 0 20 200");assert(executor_state.demand==200);
 parameter_reject("V2 PARAM 7 amax_b 40");parameter_reject("V2 PARAM 7 rehome_v .1");
 oracle_now_us+=1000;serviceControl();assert(g_energized&&fabsf(acc_cmd-10.f)<1e-5f);
 cmd("V2 STOP 7");cmd("V2 MODE 7 manual 1000");
 char action[100];snprintf(action,sizeof action,"V2 V 7 1 %u 20 2",executor_state.tick);cmd(action);
 assert(executor_state.demand==2);oracle_now_us+=1000;serviceControl();assert(g_energized&&fabsf(acc_cmd-10.f)<1e-5f);
 cmd("V2 STOP 7");executor_state.trip(executor::ENCODER);mode=M_FAULT;parameter_reject("V2 PARAM 7 rehome_v .1");cmd("V2 CLEAR 7");
 executor_state.sample(false,0);parameter_reject("V2 PARAM 7 manual_speed_max 2.6");
 for(float acceleration:{25.f,200.f})for(float jerk:{50.f,10000.f})for(int sign:{-1,1}){
  cart_motion::State motion;float x=0;bool latched=false,settled=false;
  for(unsigned tick=0;tick<5000;++tick){
   const float previous=motion.acceleration;
   motion=cart_motion::advance(motion,x,sign*acceleration,cart_hardware::max_speed,acceleration,acceleration,jerk,.3090375f,.001f,.002f);
   x+=motion.velocity*.001f;
   assert(fabsf(motion.velocity)<=cart_hardware::max_speed&&fabsf(motion.acceleration)<=acceleration);
   assert(fabsf(motion.acceleration-previous)<=jerk*.001f+.0001f&&fabsf(x)<.3080375f);
   if(motion.brake_direction==sign)latched=true;
   if(latched&&fabsf(motion.velocity)<.005f&&fabsf(motion.acceleration)<.1f){settled=true;break;}
  }
  assert(latched&&settled);
 }
 for(int sign:{-1,1}){
  init();complete_measured_home(16509);char speed[32];snprintf(speed,sizeof speed,"%.9g",double(cart_hardware::max_speed));
  for(const char* name:{"vmax","vmax_s","vmax_b"})parameter_write(name,speed,cart_hardware::max_speed);
  parameter_write("amax_s","200",200);parameter_write("amax_b","200",200);parameter_write("jmax","10000",10000);
  parameter_write("rail_fault_margin",".001",.001f);parameter_write("rail_margin",".002",.002f);
  cmd("V2 ARM 7 3000");bool latched=false,settled=false;float peak=0;
  for(unsigned ms=0;ms<2000;++ms){
   if(ms%10==0){char action[100];snprintf(action,sizeof action,"V2 A 7 %u %u 20 %d",ms+1,executor_state.tick,sign*200);cmd(action);cmd("V2 PING 7");}
   for(unsigned us=0;us<1000;us+=7){oracle_now_us+=7;onStepTimer();serviceControl();}
   assert(executor_state.fault==executor::NONE&&g_energized&&fabsf(xc)<p_rail-.001f&&fabsf(vc)<=cart_hardware::max_speed);
   peak=fmaxf(peak,fabsf(vc));if(cart_brake_direction==sign)latched=true;
   if(latched&&fabsf(vc)<.005f&&fabsf(acc_cmd)<.1f){settled=true;break;}
  }
  assert(latched&&settled&&peak>2.65f);cmd("V2 STOP 7");
 }
 for(bool returning:{false,true}){
  init();char cap[32];snprintf(cap,sizeof cap,"%.9g",double(cart_hardware::max_speed));parameter_write("vmax",cap,cart_hardware::max_speed);
  cmd(returning?"V2 REHOME 7":"V2 ARM 7 1000");vc=cart_hardware::max_speed+.001f;acc_cmd=0;
  oracle_now_us+=1000;serviceControl();
  assert(!g_energized&&executor_state.fault==executor::CONTROLLER&&!executor_state.homed&&ax_inc[0]==0);
  cmd("V2 HELLO 8");assert(executor_state.fault==executor::CONTROLLER&&!executor_state.homed&&!g_energized);
 }
 init();
 const struct {const char* name;float expected;} defaults[]={
  {"manual_speed_max",.15f},{"rail_fraction",.95f},{"rail_margin",.015f},
  {"rail_fault_margin",.010f},{"rail_hysteresis",.005f},{"rail_recover_v",.15f},
  {"rail_recover_a",1.5f},{"rail_recover_s",8},{"rehome_v",.08f},{"rehome_a",.5f},{"rehome_j",10}
 };
 for(const auto& row:defaults)assert(fabsf(parameter_read(row.name)-row.expected)<1e-7f);
}
static void tunable_geometry(){
 // Default tunable geometry must match every supported measured integer span.
 for(int span=10667;span<=20000;++span){
  const int half=span/2,legacy=(half*95)/100+400;
  assert(cart_homing::measuredRailCap(span)==float(half<legacy?half:legacy)/cart_homing::steps_per_m);
 }
 assert(cart_homing::measuredRailCap(16000,.75f,.015f)==6400.f/cart_homing::steps_per_m);
 assert(cart_homing::measuredRailCap(20000,.95f,.015f)==9900.f/cart_homing::steps_per_m);
 assert(cart_homing::measuredRailCap(20000,nextafterf(.95f,0.f),.015f)==9899.f/cart_homing::steps_per_m);
 init();complete_measured_home(16509);const uint32_t epoch=home_epoch;
 parameter_write("rail_fraction",".8",.8f);assert(fabsf(p_rail-.2626125f)<1e-6f);
 parameter_write("rail_margin",".025",.025f);assert(fabsf(p_rail-.2725875f)<1e-6f);
 parameter_write("rail_fault_margin",".024",.024f);
 parameter_reject("V2 PARAM 7 rail_fault_margin .02401");
 parameter_reject("V2 PARAM 7 rail_margin .0249");
 parameter_write("rail_fraction",".99",.99f);assert(fabsf(p_rail-.309525f)<1e-6f);
 parameter_write("rail",".2",.2f);parameter_write("rail_fraction",".5",.5f);
 assert(fabsf(p_rail-.1797375f)<1e-6f);parameter_write("rail_fraction",".99",.99f);assert(p_rail==.2f);
 assert(home_epoch==epoch&&executor_state.homed);
 const float cap=cart_homing::measuredRailCap(16509,.99f,.025f);
 char value[48];snprintf(value,sizeof value,"%.9g",double(cap));parameter_write("rail",value,cap);
 snprintf(value,sizeof value,"%.9g",double(nextafterf(cap,INFINITY)));parameter_reject(std::string("V2 PARAM 7 rail ")+value);
 parameter_write("rail",".2",.2f);
 ax_pos[0]=lroundf(.18f*CART_STEPS_PER_M);parameter_reject("V2 PARAM 7 rail .18");ax_pos[0]=0;
 parameter_write("rail_hysteresis",".05",.05f);parameter_reject("V2 PARAM 7 rail .075");
 cmd("V2 SWITCHES 7 0");cmd("V2 CENTER 7");parameter_write("rail_fraction",".8",.8f);assert(p_rail==.2f);
 parameter_reject("V2 PARAM 7 rail .27");
 for(const char* command:{"rail_fraction .499","rail_fraction .991","rail_margin .00199","rail_margin .0501","rail_fault_margin .00099","rail_fault_margin .0491","rail_hysteresis .00099","rail_hysteresis .0501"})parameter_reject(std::string("V2 PARAM 7 ")+command);
}
static void tunable_recovery(){
 // A configured recovery must actually change handoff and timeout behavior.
 init();parameter_write("rail_margin",".025",.025f);parameter_write("rail_hysteresis",".02",.02f);
 parameter_write("rail_recover_v",".03",.03f);parameter_write("rail_recover_a",".2",.2f);parameter_write("rail_recover_s",".1",.1f);
 xc=.238f;vc=acc_cmd=0;beginRailRecovery();assert(fabsf(rail_recovery_state.exit_boundary-.215f)<1e-6f);
 cmd("V2 MODE 7 auto 1000");mode=M_RAIL_RETURN;rail_recovery_state.phase=rail_recovery::RETURNING;
 ax_pos[0]=home_steps+lroundf(.23f*CART_STEPS_PER_M);response_watch.armed=false;
 for(unsigned i=0;i<105&&g_energized;++i){if(i%20==0)cmd("V2 PING 7");oracle_now_us+=1000;serviceControl();assert(fabsf(acc_cmd)<=.2001f);}
 assert(!g_energized&&mode==M_FAULT);
 // Move the independent software fault with the configured margin.
 init();parameter_write("rail_margin",".025",.025f);parameter_write("rail_fault_margin",".02",.02f);
 ax_pos[0]=home_steps+lroundf(.241f*CART_STEPS_PER_M);cmd("V2 ARM 7 1000");oracle_now_us+=1000;serviceControl();
 assert(executor_state.fault==executor::RAIL&&!g_energized);
}
static void tunable_auto_return_regular(){
 for(bool narrow:{false,true})for(bool high_auto:{true,false})for(int sign:{-1,1})for(bool near_rail:{false,true}){
  const float speed=high_auto?cart_hardware::max_speed:1.5f,acceleration=high_auto?200.f:25.f,jerk=high_auto?10000.f:50.f;
  const float margin=narrow?.002f:.015f,fault_margin=narrow?.001f:.01f;
  const float rail=cart_homing::measuredRailCap(16509,.95f,margin);
  const float return_v=high_auto?.2f:1.f,return_a=high_auto?2.f:200.f,return_j=high_auto?50.f:10000.f;
  cart_motion::State inherited;float x=0;bool reached=false;
  for(unsigned ms=0;ms<1000;++ms){
   const auto next=cart_motion::advance(inherited,x,sign*acceleration,speed,acceleration,acceleration,jerk,rail,.001f,margin);
   if(near_rail&&next.brake_direction){reached=true;break;}
   inherited=next;x+=inherited.velocity*.001f;
   if(!near_rail&&sign*inherited.velocity>(high_auto?1.6f:speed*.25f)&&sign*inherited.acceleration>acceleration*.1f){reached=true;break;}
  }
  if(!reached||inherited.brake_direction)std::cerr<<"seed high="<<high_auto<<" near="<<near_rail<<" x="<<x<<" v="<<inherited.velocity<<" a="<<inherited.acceleration<<" latch="<<inherited.brake_direction<<"\n";
  assert(reached&&inherited.brake_direction==0);
  init();complete_measured_home(16509);
  char speed_text[32];snprintf(speed_text,sizeof speed_text,"%.9g",double(speed));
  parameter_write("vmax",speed_text,speed);parameter_write("vmax_s",speed_text,speed);parameter_write("vmax_b",speed_text,speed);
  if(narrow){parameter_write("rail_fault_margin",".001",.001f);parameter_write("rail_margin",".002",.002f);}
  parameter_write("amax_s",high_auto?"200":"25",acceleration);parameter_write("amax_b",high_auto?"200":"25",acceleration);parameter_write("jmax",high_auto?"10000":"50",jerk);
  parameter_write("rehome_v",high_auto?".2":"1",return_v);parameter_write("rehome_a",high_auto?"2":"200",return_a);parameter_write("rehome_j",high_auto?"50":"10000",return_j);
  ax_pos[0]=lroundf(x*CART_STEPS_PER_M);const uint32_t epoch=home_epoch;const int32_t span=measured_home_span_steps;
  cmd("V2 MODE 7 auto 1");vc=inherited.velocity;acc_cmd=inherited.acceleration;response_watch.armed=false;
  float last_acc=acc_cmd;bool centered=false;oracle_now_us+=1000;serviceControl();
  assert(g_energized&&mode==M_REHOME&&executor_state.fault==executor::NONE);last_acc=acc_cmd;
  for(unsigned i=0;i<2200000&&executor_state.enabled;++i){
   oracle_now_us+=7;onStepTimer();const uint32_t tick=executor_state.tick;serviceControl();if(tick==executor_state.tick)continue;
   if(executor_state.fault!=executor::NONE)std::cerr<<"high-limit return fault="<<executor_state.fault<<" x="<<xc<<" v="<<vc<<" a="<<acc_cmd<<"\n";
   assert(executor_state.fault==executor::NONE&&fabsf(xc)<rail-fault_margin);
   assert(fabsf(vc)<=speed&&fabsf(acc_cmd)<=fmaxf(acceleration,return_a)+.001f);
   if(saved_return.phase==saved_center_return::State::CENTERING){centered=true;assert(fabsf(vc)<=return_v+.0001f&&fabsf(acc_cmd)<=return_a+.0001f);assert(fabsf(acc_cmd-last_acc)<=return_j*.001f+.0001f);}
   else assert(fabsf(acc_cmd-last_acc)<=jerk*.001f+.0001f);
   last_acc=acc_cmd;if(executor_state.tick%50==0)cmd("V2 PING 7");
  }
  assert(centered&&!g_energized&&mode==M_IDLE&&executor_state.fault==executor::NONE);
  assert(ax_pos[0]==home_steps&&executor_state.homed&&home_epoch==epoch&&measured_home_span_steps==span);
 }
}

// Compile the immutable baseline alongside production under distinct namespaces.
#define cart_motion archived_cart_motion
#define cart_hardware archived_cart_hardware
#define spin_recovery archived_spin_recovery
#define swing_control archived_swing_control
#define rail_recovery archived_rail_recovery
#include "../../archive/good_balancing_jetson/teensy_firmware/teensy_swingup/cart_motion.h"
#include "../../archive/good_balancing_jetson/teensy_firmware/teensy_swingup/swing_controller.h"
#include "../../archive/good_balancing_jetson/teensy_firmware/teensy_swingup/rail_recovery.h"
#undef cart_motion
#undef cart_hardware
#undef spin_recovery
#undef swing_control
#undef rail_recovery
static void preserved_defaults(){
 swing_control::Parameters p;archived_swing_control::Parameters old;
 const auto gains=swing_control::gains(p);const auto original=archived_swing_control::gains(old);
 assert(gains.k1==original.k1&&gains.k2==original.k2&&gains.k3==original.k3&&gains.k4==original.k4);
 for(int sign:{-1,1}){
  cart_motion::State m;archived_cart_motion::State baseline;float x=0;
  for(unsigned i=0;i<4000;++i){
   const float demand=sign*(i<1000?25.f:i<2500?-25.f:0.f);
   m=cart_motion::advance(m,x,demand,1.5f,25,25,150,.26f,.001f);
   baseline=archived_cart_motion::advance(baseline,x,demand,1.5f,25,25,150,.26f,.001f);
   assert(m.velocity==baseline.velocity&&m.acceleration==baseline.acceleration&&m.brake_direction==baseline.brake_direction);
   x+=m.velocity*.001f;
  }
 }
 for(float theta:{-.5f,-.2f,0.f,.2f,.5f})for(float x:{-.1f,0.f,.1f})for(float v:{-.2f,0.f,.2f}){
  assert(swing_control::canCapture(p,gains,theta,0,x,v)==archived_swing_control::canCapture(old,original,theta,0,x,v));
  swing_control::PumpState pump;archived_swing_control::PumpState oldpump;
  assert(swing_control::swing(p,pump,theta,.2f,x,v,.001f)==archived_swing_control::swing(old,oldpump,theta,.2f,x,v,.001f));
 }
 rail_recovery::State state;archived_rail_recovery::State prior;
 state.begin(.24f,.26f);prior.begin(.24f,.26f);
 assert(state.exit_boundary==prior.exit_boundary&&state.side==prior.side);
 cart_motion::State m;archived_cart_motion::State om;
 for(int i=0;i<8100;++i){
  assert(state.update(.24f,m,.001f)==prior.update(.24f,om,.001f));
  assert(state.demand(.24f,m,1.5f,25,150,.001f)==prior.demand(.24f,om,1.5f,25,150,.001f));
  assert(state.timedOut()==prior.timedOut());
 }
}

static void tunable_weak_return(){
 for(float center_j:{.00001f,.001f,.01f})for(float center_a:{.0001f,.5f})for(int sign:{-1,1}){
  cart_motion::State inherited;float x=0;
  for(unsigned i=0;i<2000;++i){
   const auto next=cart_motion::advance(inherited,x,sign*25.f,2.5f,25,25,50,.3090375f,.001f);
   if(next.brake_direction)break;
   inherited=next;x+=inherited.velocity*.001f;
  }
  assert(sign*x>0&&sign*inherited.velocity>.1f);
  init();complete_measured_home(16509);parameter_write("vmax","2.5",2.5f);parameter_write("vmax_s","2.5",2.5f);parameter_write("vmax_b","2.5",2.5f);parameter_write("jmax","50",50);
  char value[32];snprintf(value,sizeof value,"%.9g",double(center_j));parameter_write("rehome_j",value,center_j);
  snprintf(value,sizeof value,"%.9g",double(center_a));parameter_write("rehome_a",value,center_a);
  ax_pos[0]=lroundf(x*CART_STEPS_PER_M);cmd("V2 MODE 7 auto 1");vc=inherited.velocity;acc_cmd=inherited.acceleration;
  oracle_now_us+=1000;serviceControl();assert(g_energized&&mode==M_REHOME);
  float previous_a=acc_cmd;bool saw_center=false;
  for(unsigned i=0;i<2200000&&executor_state.enabled;++i){
   oracle_now_us+=7;onStepTimer();const uint32_t tick=executor_state.tick;serviceControl();if(tick==executor_state.tick)continue;
   assert(executor_state.fault==executor::NONE||executor_state.fault==executor::DURATION);
   assert(fabsf((ax_pos[0]-home_steps)/CART_STEPS_PER_M)<p_rail-.01f);
   if(executor_state.enabled){
    const bool centering=saved_return.phase==saved_center_return::State::CENTERING;
    const float jerk=centering?center_j:50.f;
    if(centering){saw_center=true;assert(fabsf(acc_cmd)<=center_a+1e-7f);assert(fabsf(vc)<=.080001f);}
    assert(fabsf(acc_cmd-previous_a)<=jerk*.001f+(centering?1e-7f:1e-5f));
   }
   previous_a=acc_cmd;if(executor_state.tick%50==0)cmd("V2 PING 7");
  }
  // Deliberately weak returns may time out; they must never drift into a rail
  // or violate the new phase's speed/acceleration/jerk on the way there.
  assert(saw_center&&!g_energized&&executor_state.homed);
  assert(executor_state.fault==executor::NONE||executor_state.fault==executor::DURATION);
 }
}
static void tunable_boundary_return(){
 for(int sign:{-1,1}){
  init();complete_measured_home(16509);
  // One counted step outside the normal boundary is still inside the fault
  // guard. A stationary cart must be allowed to depart gently toward home.
  ax_pos[0]=home_steps+sign*(int32_t(ceilf((p_rail-.015f)*CART_STEPS_PER_M))+1);
  cmd("V2 REHOME 7");oracle_now_us+=1000;serviceControl();
  assert(g_energized&&saved_return.phase==saved_center_return::State::CENTERING&&sign*vc<0);
  for(unsigned i=0;i<2200000&&executor_state.enabled;++i){
   oracle_now_us+=7;onStepTimer();const uint32_t tick=executor_state.tick;serviceControl();if(tick==executor_state.tick)continue;
   assert(executor_state.fault==executor::NONE&&fabsf(xc)<p_rail-.01f);
   if(executor_state.tick%50==0)cmd("V2 PING 7");
  }
  assert(!g_energized&&mode==M_IDLE&&executor_state.homed&&ax_pos[0]==home_steps);
 }
}
static void tunable_auto_return(){tunable_auto_return_regular();tunable_weak_return();tunable_boundary_return();}
