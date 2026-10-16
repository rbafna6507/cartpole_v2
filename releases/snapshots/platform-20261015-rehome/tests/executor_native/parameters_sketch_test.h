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
static void parameter_values(){
 init();
 const struct {const char* name;const char* value;float expected;} rows[]={
  {"leff",".2",.2f},{"pw","6",6},{"pz","1.1",1.1f},{"bal_pw","5",5},
  {"pc1","-2",-2},{"pc2","-5",-5},{"vmax","1",1},{"vmax_s",".9",.9f},
  {"vmax_b",".8",.8f},{"approach_v",".2",.2f},{"catch_v",".25",.25f},
  {"approach_angle","1",1},{"catch_da","3",3},{"amax_s","20",20},
  {"amax_b","15",15},{"jmax","100",100},{"amax_m",".4",.4f},{"jmax_m","8",8},
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
 init();assert(parameter_read("pw")==4.5f&&parameter_read("rail")==.26f);
}
static void parameter_bounds(){
 init();
 const struct {const char* name;const char* low;const char* high;} rows[]={
  {"leff",".0199","1.001"},{"pw",".099","30.1"},{"pz",".049","5.01"},
  {"bal_pw",".999","20.1"},{"pc1","-50.1","-.099"},{"pc2","-50.1","-.099"},
  {"vmax","0","1.51"},{"vmax_s","0","1.51"},{"vmax_b","0","1.51"},
  {"approach_v","0","1.51"},{"catch_v","0","1.51"},
  {"approach_angle",".649","1.501"},{"catch_da","0","25.1"},
  {"amax_s","0","25.1"},{"amax_b","0","25.1"},{"jmax","0","150.1"},
  {"amax_m","0",".501"},{"jmax_m","0","10.1"},
  {"ke","-.1","100.1"},{"kpx","-.1","1000.1"},{"kdx","-.1","100.1"},
  {"phase_soft","0","50.1"},{"catch_a",".049","1.201"},
  {"catch_r",".099","30.1"},{"giveup",".099","2.501"},
  {"spin_trip_rad_s","0","150.1"},{"spin_resume_rad_s","0","150"},
  {"rail",".02",".2601"},{"bw",".099","100.1"},{"vman","-.001",".151"}
 };
 for(const auto& r:rows){parameter_reject(std::string("V2 PARAM 7 ")+r.name+" "+r.low);parameter_reject(std::string("V2 PARAM 7 ")+r.name+" "+r.high);}
 for(const char* value:{"nan","inf","-inf","1e100","0x1p0","1,2"})parameter_reject(std::string("V2 PARAM 7 pw ")+value);
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
 parameter_reject("V2 PARAM 7 pw");parameter_reject("V2 PARAM 7 pw 6");
 assert(g_energized&&executor_state.enabled);cmd("V2 STOP 7");
 executor_state.trip(executor::ENCODER);mode=M_FAULT;
 assert(parameter_read("pw")==4.5f);parameter_reject("V2 PARAM 7 pw 6");
 assert(executor_state.fault==executor::ENCODER);cmd("V2 CLEAR 7");
 executor_state.sample(false,12);parameter_reject("V2 PARAM 7 pw 6");assert(parameter_read("pw")==4.5f);
 executor_state.sample(true,12);cmd("V2 CALIBRATE 7 upright");
 parameter_reject("V2 PARAM 7 pw");parameter_reject("V2 PARAM 7 pw 6");
 assert(encoderCalibrationBusy());cmd("V2 STOP 7");
}
static void parameter_rail(){
 init();parameter_write("rail",".2",.2f);cmd("V2 CENTER 7");assert(p_rail==.2f);
 // A measured physical home may reduce the effective preference further.
 executor_state.switches=true;executor_state.tick=5;cmd("V2 HOME 7");
 assert(mode==M_HOMING);homing.negative=-5334;homing.positive=5334;
 homing.phase=cart_homing::Machine::CENTER;homing_centering=true;
 homing_center_target=0;ax_pos[0]=0;oracle_now_us+=1000;serviceControl();
 assert(executor_state.homed&&p_rail<.196f&&p_rail>.195f);
 parameter_reject("V2 PARAM 7 rail .2");parameter_write("rail",".18",.18f);
 parameter_write("rail",".195",.195f);parameter_reject("V2 PARAM 7 rail .196");
 // A wider later home must retain the configured lower rail, not revert to .26.
 cmd("V2 HOME 7");assert(mode==M_HOMING);
 homing.negative=-7000;homing.positive=7000;homing.phase=cart_homing::Machine::CENTER;
 homing_centering=true;homing_center_target=0;ax_pos[0]=0;oracle_now_us+=1000;serviceControl();
 assert(executor_state.homed&&p_rail==.195f);
 parameter_write("rail",".25",.25f);parameter_reject("V2 PARAM 7 rail .26");
 cmd("V2 SWITCHES 7 0");cmd("V2 CENTER 7");assert(p_rail==.25f);
}
