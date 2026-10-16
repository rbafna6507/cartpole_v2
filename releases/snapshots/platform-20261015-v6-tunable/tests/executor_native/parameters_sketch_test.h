static std::string parameter_exchange(const std::string& payload){
 resetTx();Serial.output.clear();Serial.capacity=4096;cmd(payload.c_str());
 for(int i=0;i<20;++i)serviceSerialTx();return Serial.output;
}
static float parameter_read(const char* name){
 const std::string response=parameter_exchange(std::string("V2 PARAM 7 ")+name);
 char actual_name[32];float value=0;
 assert(sscanf(response.c_str(),"@V2 PARAM 7 %31s %f",actual_name,&value)==2);
 assert(!strcmp(actual_name,name));return value;
}
static void parameter_write(const char* name,const char* value,float expected){
 const std::string response=parameter_exchange(std::string("V2 PARAM 7 ")+name+" "+value);
 char actual_name[32];float actual=0;
 assert(sscanf(response.c_str(),"@V2 PARAM 7 %31s %f",actual_name,&actual)==2);
 assert(!strcmp(actual_name,name));assert(fabsf(actual-expected)<1e-5f);
 assert(fabsf(parameter_read(name)-expected)<1e-5f);
 assert(!g_energized&&!executor_state.enabled&&native_pins[8]==HIGH);
}
static void parameter_reject(const std::string& payload){
 const swing_control::Parameters before=controller;
 const float before_k1=K1,before_k2=K2,before_k3=K3,before_k4=K4;
 const std::string response=parameter_exchange(payload);
 assert(response.find("@V2 ERR 7 ")==0);
 assert(!memcmp(&before,&controller,sizeof before));
 assert(K1==before_k1&&K2==before_k2&&K3==before_k3&&K4==before_k4);
}
static void parameter_jerk_motion(){
 init();assert(parameter_read("jmax")==150);
 parameter_write("jmax","600",600);
 cmd("V2 ARM 7 500");assert(g_energized&&mode==M_EXTERNAL);
 float greatest_acceleration=0,greatest_velocity=0;
 for(unsigned i=0;i<200;++i){
  if(i%10==0){
   char action[96];snprintf(action,sizeof action,"V2 A 7 %u %u 20 25",i+1,executor_state.tick);
   cmd(action);cmd("V2 PING 7");
  }
  oracle_now_us+=1000;serviceControl();
  assert(g_energized&&mode==M_EXTERNAL&&executor_state.fault==executor::NONE);
  if(i==0)assert(fabsf(acc_cmd-.6f)<1e-6f); // 600 m/s^3 * 1 ms.
  greatest_acceleration=fmaxf(greatest_acceleration,fabsf(acc_cmd));
  greatest_velocity=fmaxf(greatest_velocity,fabsf(vc));
  assert(fabsf(acc_cmd)<=25.f&&fabsf(vc)<=1.502f);
 }
 assert(greatest_acceleration>24.9f&&greatest_velocity>1.49f);
 cmd("V2 STOP 7");assert(!g_energized&&!executor_state.enabled);
 // Increasing automatic jerk must not accelerate the manual commissioning path.
 cmd("V2 MODE 7 manual 500");
 char action[96];snprintf(action,sizeof action,"V2 V 7 1 %u 20 .15",executor_state.tick);cmd(action);
 oracle_now_us+=1000;serviceControl();
 assert(g_energized&&mode==M_MANUAL&&fabsf(acc_cmd-.01f)<1e-6f);
 cmd("V2 STOP 7");
}
static void parameter_jerk_rails(){
 for(float jerk:{300.f,600.f})for(int direction:{-1,1}){
  cart_motion::State motion;float x=0;
  auto step=[&](float demand){
   const float previous_acceleration=motion.acceleration;
   motion=cart_motion::advance(motion,x,demand,1.5f,25.f,25.f,jerk,.26f,.001f);
   x+=motion.velocity*.001f;
   assert(isfinite(x)&&isfinite(motion.velocity)&&isfinite(motion.acceleration));
   assert(fabsf(motion.acceleration-previous_acceleration)<=jerk*.001f+1e-5f);
   assert(fabsf(motion.acceleration)<=25.f&&fabsf(motion.velocity)<=1.502f);
   assert(fabsf(x)<.25f); // Must stop before the independent hard-rail boundary.
  };
  auto settled=[&](){return fabsf(motion.velocity)<=.005f&&fabsf(motion.acceleration)<=.1f;};
  // Sustained outward demand must latch braking and settle before the rail.
  bool latched=false,stopped=false;
  for(unsigned i=0;i<2000;++i){
   step(direction*25.f);
   if(motion.brake_direction){assert(motion.brake_direction==direction);latched=true;}
   if(latched&&settled()){stopped=true;break;}
  }
  assert(latched&&stopped&&direction*x>.10f);
  // From the rail stop, an inward command must release the latch, cross the
  // center and settle at the opposite rail without clipping velocity/acceleration.
  latched=stopped=false;bool moved_inward=false;
  for(unsigned i=0;i<2000;++i){
   step(-direction*25.f);
   if(direction*motion.velocity<-.1f)moved_inward=true;
   if(motion.brake_direction==-direction)latched=true;
   if(latched&&settled()){stopped=true;break;}
  }
  assert(moved_inward&&latched&&stopped&&direction*x<-.10f);
  // Also reverse while velocity AND acceleration still point outward. The
  // request may jump, but actual acceleration must retain the same jerk bound.
  x=0;motion=cart_motion::State{};motion.velocity=direction*.6f;motion.acceleration=direction*5.f;
  bool reversed=false;
  for(unsigned i=0;i<500;++i){
   step(-direction*25.f);
   assert(motion.brake_direction==0&&direction*x<.05f);
   if(direction*motion.velocity<-.1f){reversed=true;break;}
  }
  assert(reversed);
  stopped=false;
  for(unsigned i=0;i<1000;++i){
   step(cart_motion::settledVelocityAccel(motion.velocity,motion.acceleration,0,25.f,jerk,.001f));
   if(settled()){stopped=true;break;}
  }
  assert(stopped&&fabsf(x)<.10f);
 }
}
static void parameter_values(){
 init();
 const struct {const char* name;const char* value;float expected;} rows[]={
  {"leff",".2",.2f},{"pw","6",6},{"pz","1.1",1.1f},{"bal_pw","5",5},
  {"pc1","-2",-2},{"pc2","-5",-5},{"vmax","1",1},{"vmax_s",".9",.9f},
  {"vmax_b",".8",.8f},{"approach_v",".2",.2f},{"catch_v",".25",.25f},
  {"approach_angle","1",1},{"catch_da","3",3},{"amax_s","20",20},
  {"amax_b","15",15},{"jmax","100",100},{"jmax","300",300},{"jmax","600",600},
  {"amax_m",".4",.4f},{"jmax_m","8",8},
  {"ke","5",5},{"kpx","50",50},{"kdx","3",3},{"phase_soft","1",1},
  {"catch_a",".5",.5f},{"catch_r","4",4},{"giveup","1",1},
  {"spin_trip_rad_s","100",100},{"spin_resume_rad_s","20",20},
  {"rail",".2",.2f},{"bw","20",20},{"vman",".04",.04f}
 };
 const bool homed=executor_state.homed,switches=executor_state.switches;
 unsigned char eeprom_before[8];memcpy(eeprom_before,EEPROM.bytes,8);
 const int32_t upright_before=enc_upright_raw;
 for(const auto& r:rows)parameter_write(r.name,r.value,r.expected);
 assert(executor_state.homed==homed&&executor_state.switches==switches);
 assert(memcmp(eeprom_before,EEPROM.bytes,8)==0&&enc_upright_raw==upright_before);
 const auto gains=swing_control::gains(controller);
 assert(K1==gains.k1&&K2==gains.k2&&K3==gains.k3&&K4==gains.k4);
 // Reading values does not reset pending controller state.
 pump.elapsed=2;parameter_read("pw");assert(pump.elapsed==2);
 // Successful writes reset transient demands and observers while disabled.
 vc=.2f;acc_cmd=2;pump.startup_kick=true;response_watch.armed=true;
 parameter_write("bw","30",30);
 assert(vc==0&&acc_cmd==0&&pump.elapsed==0&&!pump.startup_kick&&!response_watch.armed&&req_estimator_reset);
 init();assert(parameter_read("pw")==4.5f&&parameter_read("rail")==.26f&&parameter_read("jmax")==150);
 parameter_jerk_motion();
 parameter_jerk_rails();
}
static void parameter_bounds(){
 init();
 const struct {const char* name;const char* low;const char* high;} rows[]={
  {"leff",".0199","1.001"},{"pw",".099","30.1"},{"pz",".049","5.01"},
  {"bal_pw",".999","20.1"},{"pc1","-50.1","-.099"},{"pc2","-50.1","-.099"},
  {"vmax","0","2.67858"},{"vmax_s","0","2.67858"},{"vmax_b","0","2.67858"},
  {"approach_v","0","2.67858"},{"catch_v","0","2.67858"},
  {"approach_angle",".649","1.501"},{"catch_da","0","200.01"},
  {"amax_s","0","200.01"},{"amax_b","0","200.01"},{"jmax","0","10000.1"},
  {"amax_m","0","200.01"},{"jmax_m","0","10000.1"},
  {"ke","-.1","100.1"},{"kpx","-.1","1000.1"},{"kdx","-.1","100.1"},
  {"phase_soft","0","50.1"},{"catch_a",".049","1.201"},
  {"catch_r",".099","30.1"},{"giveup",".099","2.501"},
  {"spin_trip_rad_s","0","150.1"},{"spin_resume_rad_s","0","150"},
  {"rail",".02",".2601"},{"bw",".099","100.1"},{"vman","-.001",".151"}
 };
 for(const auto& r:rows){parameter_reject(std::string("V2 PARAM 7 ")+r.name+" "+r.low);parameter_reject(std::string("V2 PARAM 7 ")+r.name+" "+r.high);}
 for(const char* value:{"nan","inf","-inf","1e100","0x1p0","1,2"}){
  parameter_reject(std::string("V2 PARAM 7 pw ")+value);
  parameter_reject(std::string("V2 PARAM 7 jmax ")+value);
 }
 for(const char* name:{"missing","k1","zvmax","encoder_upright_raw"}){
  parameter_reject(std::string("V2 PARAM 7 ")+name);parameter_reject(std::string("V2 PARAM 7 ")+name+" 1");
 }
 parameter_reject("V2 PARAM 7 spin_trip_rad_s 10");
 parameter_write("leff",".02",.02f);parameter_write("leff","1",1);
 parameter_write("pc1","-50",-50);parameter_write("pc1","-.1",-.1f);
 parameter_write("vman","0",0);parameter_write("ke","0",0);
 parameter_write("spin_resume_rad_s","149",149);parameter_reject("V2 PARAM 7 spin_trip_rad_s 149");
}
static void parameter_guards(){
 init();cmd("V2 MODE 7 manual 1000");
 parameter_reject("V2 PARAM 7 pw");parameter_reject("V2 PARAM 7 pw 6");parameter_reject("V2 PARAM 7 jmax 600");
 assert(g_energized&&executor_state.enabled);cmd("V2 STOP 7");
 executor_state.trip(executor::ENCODER);mode=M_FAULT;
 assert(parameter_read("pw")==4.5f);parameter_reject("V2 PARAM 7 pw 6");parameter_reject("V2 PARAM 7 jmax 600");
 assert(executor_state.fault==executor::ENCODER);cmd("V2 CLEAR 7");
 executor_state.sample(false,12);parameter_reject("V2 PARAM 7 pw 6");parameter_reject("V2 PARAM 7 jmax 600");assert(parameter_read("pw")==4.5f);
 executor_state.sample(true,12);cmd("V2 CALIBRATE 7 upright");
 parameter_reject("V2 PARAM 7 pw");parameter_reject("V2 PARAM 7 pw 6");parameter_reject("V2 PARAM 7 jmax 600");
 assert(encoderCalibrationBusy());cmd("V2 STOP 7");
}
static void complete_measured_home(int32_t span){
 executor_state.switches=true;executor_state.tick+=5;executor_state.healthy_since=0;
 cmd("V2 HOME 7");assert(mode==M_HOMING);
 homing.negative=-span/2;homing.positive=span-span/2;
 homing.phase=cart_homing::Machine::CENTER;homing_centering=true;
 homing_center_target=0;ax_pos[0]=0;oracle_now_us+=1000;serviceControl();
 assert(executor_state.homed&&!executor_state.enabled&&!g_energized&&mode==M_IDLE);
}
static void parameter_rail(){
 init();parameter_reject("V2 PARAM 7 rail .27");
 parameter_write("rail",".26",.26f);complete_measured_home(16509);assert(p_rail==.26f);
 init();
 complete_measured_home(16509);
 // Nearer edge8254steps=309.525mm. Normal boundary294.0375mm.
 assert(fabsf(p_rail-.3090375f)<1e-6f);
 parameter_write("rail",".30",.30f);parameter_reject("V2 PARAM 7 rail .3091");
 complete_measured_home(20000);assert(fabsf(p_rail-.30f)<1e-6f);
 parameter_write("rail",".37125",.37125f);parameter_reject("V2 PARAM 7 rail .3713");
 cmd("V2 SWITCHES 7 0");cmd("V2 CENTER 7");assert(p_rail==.26f);
 parameter_reject("V2 PARAM 7 rail .27");
 // An explicit smaller preference survives both wider and narrower homes.
 parameter_write("rail",".2",.2f);complete_measured_home(10668);assert(p_rail==.2f);
 parameter_reject("V2 PARAM 7 rail .2001");parameter_write("rail",".18",.18f);
 complete_measured_home(20000);assert(p_rail==.18f);
 // Fault invalidation must not let a stale measurement authorize wider travel.
 executor_state.trip(executor::ENCODER);eStop();mode=M_FAULT;
 cmd("V2 CLEAR 7");parameter_reject("V2 PARAM 7 rail .30");
}
static void measured_rail_motion(){
 for(float jerk:{150.f,300.f,600.f})for(int direction:{-1,1}){
  init();complete_measured_home(16509);
  parameter_write("jmax",jerk==150?"150":jerk==300?"300":"600",jerk);
  cmd("V2 ARM 7 5000");
  bool latched=false,settled=false;float furthest=0;
  for(unsigned ms=0;ms<3000;++ms){
   if(ms%10==0){char action[96];snprintf(action,sizeof action,"V2 A 7 %u %u 20 %d",ms+1,executor_state.tick,direction*25);cmd(action);cmd("V2 PING 7");}
   for(unsigned us=0;us<1000;us+=7){oracle_now_us+=7;onStepTimer();serviceControl();}
   assert(executor_state.fault==executor::NONE&&g_energized);
   assert(fabsf(xc)<.2990375f&&fabsf(vc)<=1.502f);
   furthest=fmaxf(furthest,direction*xc);
   if(cart_brake_direction==direction)latched=true;
   if(latched&&fabsf(vc)<.005f&&fabsf(acc_cmd)<.1f){settled=true;break;}
  }
  assert(latched&&settled&&furthest>.28f); // Old245mm boundary fails this.
  cmd("V2 STOP 7");assert(!g_energized);
  // The independent software fault remains inside the physical switch contact.
  ax_pos[0]=direction*8000; //300mm >299.05mm hard bound, <309.525mm switch.
  cmd("V2 ARM 7 500");oracle_now_us+=1000;serviceControl();
  assert(executor_state.fault==executor::RAIL&&!g_energized&&!executor_state.homed);
 }
}
