#include "firmware_native.ino"
#include <cassert>
#include <string>
#include <iostream>
static void cmd(const char* payload){char data[256];assert(executor::frame(payload,data,sizeof data)>0);handleV2(data);}
static void init(uint16_t boot_conf=0){enc_consec_err=0;oracle_now_us=0;Wire1=WireStub{};Wire1.conf=boot_conf;executor_state=executor::Core{};timing_fault_pending=limit_fault_pending=false;homing_active=homing_centering=false;for(int i=0;i<64;++i)native_pins[i]=0;setup();assert(!g_energized&&!executor_state.homed&&executor_state.switches);cmd("V2 HELLO 7");cmd("V2 SWITCHES 7 0");cmd("V2 CENTER 7");assert(executor_state.homed);next_control_us=0;oracle_now_us=10000;control_heartbeat_us=10000;}
static void motion(){init();cmd("V2 ARM 7 1000");assert(g_energized&&mode==M_EXTERNAL);cmd("V2 A 7 1 0 20 25");oracle_now_us=11000;serviceControl();assert(mode==M_EXTERNAL&&g_energized);assert(fabsf(acc_cmd-.15f)<1e-6);assert(fabsf(vc-.00015f)<1e-7);assert(executor_state.demand==25);for(int i=2;i<=20;++i){oracle_now_us+=1000;serviceControl();}assert(!g_energized&&mode==M_FAULT&&executor_state.fault==executor::ACTION_EXPIRED);assert(ax_inc[0]==0&&native_pins[8]==HIGH);}
static void timing(){init();cmd("V2 MODE 7 auto 1000");oracle_now_us+=1000;serviceControl();oracle_now_us+=2000;serviceControl();assert(executor_state.fault==executor::DEADLINE&&!g_energized&&!executor_state.homed);init();cmd("V2 ARM 7 1000");oracle_now_us=15001;onStepTimer();assert(!g_energized&&timing_fault_pending&&native_pins[8]==HIGH);}
static void isr_homing_stall(){init();executor_state.switches=true;executor_state.mode=13;homing_active=true;homing_expected=1;homing_approach=true;g_energized=true;native_pins[26]=HIGH;oracle_now_us=20000;onStepTimer();assert(!g_energized&&timing_fault_pending&&native_pins[8]==HIGH);}
static void isr_limits(){init();cmd("V2 ARM 7 1000");executor_state.switches=true;native_pins[27]=HIGH;onStepTimer();assert(!g_energized&&limit_fault_pending);serviceControl();assert(!executor_state.homed&&executor_state.fault==executor::LIMIT);init();native_pins[28]=LOW;executor_state.switches=true;executor_state.mode=13;homing_active=true;homing_expected=1;homing_approach=true;g_energized=true;native_pins[26]=HIGH;ax_inc[0]=UINT32_MAX;onStepTimer();assert(g_energized&&ax_inc[0]==0&&!limit_fault_pending);}
static void reference_watchdog(){init();cmd("V2 MODE 7 manual 5000");for(int i=0;i<2000;++i){if(i%10==0){char action[100];snprintf(action,sizeof action,"V2 V 7 %u %u 50 0",unsigned(i+1),executor_state.tick);cmd(action);cmd("V2 PING 7");}oracle_now_us+=1000;serviceControl();assert(g_energized&&mode==M_MANUAL&&executor_state.fault==executor::NONE);}}
static void isr_center(){init();cmd("V2 ARM 7 1000");homing_active=homing_centering=true;homing_center_target=3;ax_pos[0]=2;ax_dir[0]=1;ax_acc[0]=UINT32_MAX;ax_inc[0]=UINT32_MAX;onStepTimer();assert(ax_pos[0]==3);for(int i=0;i<200;++i)onStepTimer();assert(ax_pos[0]==3&&ax_inc[0]==0);}
static void calibration(){teensy_reference_store::save(3485);unsigned char before[8];memcpy(before,EEPROM.bytes,8);init();assert(enc_upright_raw==3485&&reference_saved);assert(memcmp(before,EEPROM.bytes,8)==0);assert(fabsf(controller.rail-.26f)<1e-6&&fabsf(controller.pw-4.5f)<1e-6&&fabsf(controller.bal_pw-4.f)<1e-6);}
static void telemetry(){init();cmd("V2 ARM 7 1000");cmd("V2 A 7 1 0 20 2");oracle_now_us+=1000;serviceControl();resetTx();emitTelemetry();std::string frame1=latest_state.bytes;assert(frame1.find("@V2 S 7 1 ")==0);Serial.capacity=0;for(int i=0;i<5;++i){oracle_now_us+=1000;serviceControl();emitTelemetry();}assert(latest_pending&&dropped_serial_frames>=5);Serial.capacity=4096;for(int i=0;i<10;++i)serviceSerialTx();assert(Serial.output.find("@V2 S 7 6 ")!=std::string::npos);assert(Serial.output.find("@V2 S 7 1 ")==std::string::npos);}
static void wire(){init();cmd("V2 ARM 7 1000");cmd("V2 A 7 1 0 20 2");oracle_now_us+=1000;serviceControl();emitTelemetry();std::cout<<latest_state.bytes;}
static void bounced_isr_edge(){init();executor_state.switches=true;executor_state.tick=5;cmd("V2 HOME 7");assert(mode==M_HOMING&&homing.phase==cart_homing::Machine::SEEK_NEG);oracle_now_us+=1000;serviceControl();assert(ax_inc[0]>0);native_pins[26]=HIGH;onStepTimer();assert(ax_inc[0]==0);native_pins[26]=LOW;axSetRate(0,-800,CART_INVERT);assert(ax_inc[0]>0);onStepTimer();assert(ax_inc[0]==0);oracle_now_us+=1000;serviceControl();assert(homing.phase==cart_homing::Machine::VERIFY_NEG);assert(ax_inc[0]==0);for(int i=0;i<4;++i){oracle_now_us+=1000;serviceControl();}assert(!g_energized&&executor_state.fault==executor::HOMING);}
static int32_t irq_edge_position=0;
static void edge_irq(){native_irq_hook=nullptr;onStepTimer();assert(ax_pos[0]==irq_edge_position&&ax_inc[0]==0);}
static void edge_consume_race(){init();executor_state.switches=true;executor_state.tick=5;cmd("V2 HOME 7");oracle_now_us+=1000;serviceControl();native_pins[26]=HIGH;onStepTimer();native_pins[26]=LOW;axSetRate(0,-800,CART_INVERT);ax_acc[0]=UINT32_MAX;ax_inc[0]=UINT32_MAX;irq_edge_position=ax_pos[0];native_irq_hook=edge_irq;oracle_now_us+=1000;serviceControl();assert(homing.phase==cart_homing::Machine::VERIFY_NEG);}
static void hello_partial(){init();resetTx();emitTelemetry();Serial.output.clear();Serial.capacity=20;serviceSerialTx();assert(active_offset==20);cmd("V2 HELLO 8");Serial.capacity=4096;for(int i=0;i<20;++i)serviceSerialTx();int newlines=0;for(char ch:Serial.output)if(ch=='\n')++newlines;assert(newlines==2);assert(Serial.output.find("@V2 HELLO 8 1 1000*")!=std::string::npos);std::cout<<Serial.output;}
static void magnet(const std::string& condition){
 init();cmd("V2 MODE 7 manual 1000");cmd("V2 V 7 1 0 50 0");
 if(condition=="weak")Wire1.status=0x30;else if(condition=="strong")Wire1.status=0x28;else if(condition=="absent")Wire1.status=0;else if(condition=="readfailure")Wire1.status_healthy=false;else if(condition=="anglefailure")Wire1.healthy=false;
 const unsigned before_status=Wire1.status_reads,before_agc=Wire1.agc_reads;
 for(int i=0;i<10;++i){oracle_now_us+=1000;serviceControl();}
 if(condition=="healthy"){assert(g_energized&&executor_state.healthy&&executor_state.fault==executor::NONE);assert(Wire1.status_reads==before_status+1&&Wire1.agc_reads==before_agc);}
 else{assert(!g_energized&&!executor_state.healthy&&!executor_state.homed&&executor_state.fault==executor::ENCODER);if(condition=="readfailure")assert(enc_errors>0);}
}
static void info_snapshot(){teensy_reference_store::save(3485);init();resetTx();cmd("V2 INFO 7");for(int i=0;i<10;++i)serviceSerialTx();assert(Serial.output.find("@V2 INFO 7 executor-v7-vertical 3485 1 32 0 1 0 0.26 0 768 1 0 ")!=std::string::npos);std::cout<<Serial.output;}
static void info_homed(){init();executor_state.switches=true;executor_state.tick=5;cmd("V2 HOME 7");assert(mode==M_HOMING);homing.negative=-5334;homing.positive=5334;homing.phase=cart_homing::Machine::CENTER;homing_centering=true;homing_center_target=0;ax_pos[0]=0;oracle_now_us+=1000;serviceControl();assert(executor_state.homed&&!g_energized&&mode==M_IDLE);assert(fabsf(p_rail-.200025f)<1e-6f);resetTx();Serial.output.clear();cmd("V2 INFO 7");for(int i=0;i<10;++i)serviceSerialTx();assert(Serial.output.find(" 2 10668 0.200025 ")!=std::string::npos);std::cout<<Serial.output;}
static void magnet_stale(){init();eStop();oracle_now_us=20000;controlTick();assert(executor_state.healthy);oracle_now_us=20001;controlTick();assert(!executor_state.healthy);cmd("V2 ARM 7 1000");assert(!g_energized);while(executor_state.tick%10){oracle_now_us+=1000;controlTick();}assert(executor_state.healthy);}
static void whole_homing_info(){
 for(int half:{7000,10000}){
  init();native_pins[28]=native_pins[29]=HIGH;executor_state.switches=true;executor_state.tick=5;
  // At the widest allowed rail, begin near the far end: total motion >60s.
  if(half==10000)ax_pos[0]=9700;
  const uint32_t prior_epoch=home_epoch;cmd("V2 HOME 7");assert(mode==M_HOMING);
  unsigned seen=0;
  for(unsigned i=0;i<11000000 && executor_state.enabled;++i){native_pins[26]=ax_pos[0]<=-half;native_pins[27]=ax_pos[0]>=half;seen|=(native_pins[26]?1:0)|(native_pins[27]?2:0);oracle_now_us+=7;onStepTimer();onZTimer();serviceControl();if(executor_state.tick%100==0)cmd("V2 PING 7");}
  assert(seen==3);assert(executor_state.homed&&!g_energized&&mode==M_IDLE&&executor_state.fault==executor::NONE);assert(ax_pos[0]==0&&measured_home_span_steps==2*half&&home_epoch==prior_epoch+1);assert(fabsf(p_rail-(half==7000?.2625f:.37125f))<1e-6);
  resetTx();Serial.output.clear();cmd("V2 INFO 7");for(int i=0;i<10;++i)serviceSerialTx();assert(Serial.output.find(" "+std::to_string(prior_epoch+1)+(half==7000?" 14000 0.2625 ":" 20000 0.37125 "))!=std::string::npos);std::cout<<Serial.output;
 }
}
static void calibration_tick(){oracle_now_us+=1000;loop();assert(!g_energized&&native_pins[8]==HIGH&&ax_inc[0]==0);}
static void calibration_capture(const std::string& which){
 teensy_reference_store::save(3485);init();resetTx();Serial.output.clear();
 Wire1.raw=which=="hanging"?4094:1234;
 cmd(which=="hanging"?"V2 CALIBRATE 7 hanging":"V2 CALIBRATE 7 upright");
 assert(encoderCalibrationBusy());
 for(int i=0;i<399;++i){calibration_tick();if(i%50==0)cmd("V2 PING 7");}
 assert(enc_upright_raw==3485&&Serial.output.find("OK 7 CALIBRATE")==std::string::npos);
 // All required samples have now been observed. Persistence must precede ACK.
 calibration_tick();for(int i=0;i<20;++i)serviceSerialTx();
 const uint16_t expected=which=="hanging"?2046:1234;uint16_t stored;
 assert(!encoderCalibrationBusy()&&enc_upright_raw==expected&&reference_saved);
 assert(teensy_reference_store::load(stored)&&stored==expected);
 assert(Serial.output.find("OK 7 CALIBRATE")!=std::string::npos);
 assert(fabsf(th-(which=="hanging"?float(M_PI):0.f))<1e-5);
 assert(executor_state.homed&&!executor_state.switches&&!executor_state.enabled);
 // Boot loads the newly saved reference without overwriting it.
 init();assert(enc_upright_raw==expected&&reference_saved);
}
static void calibration_cancel(){
 teensy_reference_store::save(3485);init();Wire1.raw=1234;
 cmd("V2 CALIBRATE 7 upright");assert(encoderCalibrationBusy());for(int i=0;i<100;++i){calibration_tick();if(i%50==0)cmd("V2 PING 7");}
 cmd("V2 STOP 7");for(int i=0;i<500;++i)calibration_tick();
 uint16_t stored;assert(!encoderCalibrationBusy()&&enc_upright_raw==3485&&teensy_reference_store::load(stored)&&stored==3485);
}
static void calibration_cancel_before_save(bool hello){
 teensy_reference_store::save(3485);init();resetTx();Serial.output.clear();Wire1.raw=1234;
 unsigned char original[8];memcpy(original,EEPROM.bytes,8);cmd("V2 CALIBRATE 7 upright");
 for(int i=0;i<400;++i){oracle_now_us+=1000;serviceControl();if(i%50==0)cmd("V2 PING 7");}
 assert(reference_save_pending&&executor_state.calibration&&enc_upright_raw==3485);
 cmd(hello?"V2 HELLO 8":"V2 STOP 7");saveEncoderReference();
 for(int i=0;i<20;++i)serviceSerialTx();
 assert(!encoderCalibrationBusy()&&enc_upright_raw==3485);
 assert(memcmp(original,EEPROM.bytes,8)==0&&Serial.output.find("OK 7 CALIBRATE")==std::string::npos);
 assert(!g_energized&&!executor_state.enabled);
}
static void calibration_failure(const std::string& which){
 teensy_reference_store::save(3485);init();resetTx();Serial.output.clear();
 Wire1.raw=1234;cmd("V2 CALIBRATE 7 upright");assert(encoderCalibrationBusy());
 for(int i=0;i<5020;++i){
  if(which=="moving")Wire1.raw=1234+i%100;
  if(which=="magnet")Wire1.status=0x30;
  if(which=="save")EEPROM.fail_writes=true;
  calibration_tick();if(which!="watchdog"&&i%50==0)cmd("V2 PING 7");
 }
 assert(!encoderCalibrationBusy()&&enc_upright_raw==3485);
 assert(Serial.output.find("OK 7 CALIBRATE")==std::string::npos);
 const char* reason=which=="moving"?"calibration_timeout":which=="magnet"?"encoder":which=="save"?"save":"calibration_watchdog";
 assert(Serial.output.find(std::string("ERR 7 ")+reason)!=std::string::npos);
 EEPROM.fail_writes=false;
}
static void cart_only_pulses(){
 init();native_pins[28]=native_pins[29]=HIGH;executor_state.switches=true;
 executor_state.tick=5;executor_state.sample(true,12);cmd("V2 MODE 7 manual 1000");
 assert(g_energized&&executor_state.enabled);
 axSetRate(AX_Z1,1000,Z_INVERT);axSetRate(AX_Z2,1000,Z_INVERT);
 assert(ax_inc[AX_Z1]==0&&ax_inc[AX_Z2]==0);
 // Even stale legacy Z increments cannot emit pulses in this cart-only build.
 ax_acc[1]=ax_acc[2]=ax_inc[1]=ax_inc[2]=UINT32_MAX;
 const int32_t z1=ax_pos[1],z2=ax_pos[2];onStepTimer();
 assert(g_energized&&!limit_fault_pending&&ax_pos[1]==z1&&ax_pos[2]==z2);
 assert(native_pins[4]==LOW&&native_pins[6]==LOW);
 oracle_now_us+=1000;serviceControl();emitTelemetry();
 assert(executor_state.limits==12);
 assert(std::string(latest_state.bytes).find(" 1 207 ")!=std::string::npos);
 native_pins[27]=HIGH;onStepTimer();assert(!g_energized&&limit_fault_pending&&native_pins[8]==HIGH);
 serviceControl();assert(executor_state.fault==executor::LIMIT&&!executor_state.homed);
}
static void lcd_health(){init();Wire1.status=0x30;encStatusRead();oracle_now_us=300000;next_control_us=301000;serviceDisplay();std::string line(status_display::desired[4],status_display::cols);assert(line.find("ENCODER: NO DATA")==0);}

static void encoder_config_boot(){
 init(0xE3FF);assert(Wire1.conf==0xC3F0);assert(encoderHealthy());
 resetTx();Serial.output.clear();cmd("V2 INFO 7");for(int i=0;i<20;++i)serviceSerialTx();
 // Diagnostic preserves the pre-write register, including PM=3 and watchdog=1.
 assert(Serial.output.find(" 58367 50160 1 0 ")!=std::string::npos);
}
static void encoder_config_failed_write(){
 init();Wire1.conf=0x0303;Wire1.conf_writable=false;
 assert(!as5600FastFilter());assert(!encoderHealthy());
}
static void encoder_config_failed_read(){
 init();Wire1.conf_healthy=false;assert(!as5600FastFilter());assert(!encoderHealthy());
}
static void encoder_config_runtime(bool watchdog){
 init();cmd("V2 MODE 7 manual 1000");cmd("V2 V 7 1 0 50 0");assert(g_energized);
 Wire1.conf=watchdog?0x2300:0x0303;
 for(int i=0;i<10;++i){oracle_now_us+=1000;serviceControl();}
 assert(!g_energized&&!executor_state.healthy&&!executor_state.homed&&executor_state.fault==executor::ENCODER);
 assert(Wire1.conf==(watchdog?0x2300:0x0303)); // Do not silently repair during motion.
 cmd("V2 CLEAR 7");assert(executor_state.fault==executor::ENCODER);
}
static void encoder_config_recovery(){
 init();Wire1.conf=0x2303;encBusReinit();assert(Wire1.conf==0x0300);assert(encoderHealthy());
 Wire1.conf=0x0303;Wire1.conf_writable=false;encBusReinit();assert(!encoderHealthy());
}
static void encoder_config_info_guard(){
 init();Wire1.conf=0x0303;cmd("V2 INFO 7");cmd("V2 MODE 7 auto 1000");
 assert(!g_energized&&!executor_state.enabled&&!executor_state.healthy);
}
static void encoder_config_stale(){init();oracle_now_us=30001;encStatusRead();assert(!encoderHealthy());}

#include "parameters_sketch_test.h"
#include "rehome_sketch_test.h"
#include "motion_limits_sketch_test.h"
#include "hanging_offset_sketch_test.h"
#include "vertical_sketch_test.h"
int main(int argc,char** argv){assert(argc==2);std::string n=argv[1];if(n=="vertical_measurements")vertical_measurements();else if(n=="vertical_sine")vertical_sine();else if(n=="vertical_faults")vertical_faults();else if(n=="vertical_guards")vertical_guards();else if(n=="vertical_pulses")vertical_pulses();else if(n=="vertical_safety")vertical_safety();else if(n=="preserved_defaults")preserved_defaults();else if(n=="tunable_motion")tunable_motion();else if(n=="tunable_geometry")tunable_geometry();else if(n=="tunable_recovery")tunable_recovery();else if(n=="tunable_auto_return")tunable_auto_return();else if(n=="measured_rail_motion")measured_rail_motion();else if(n=="hanging_model_quality")hanging_model_quality();else if(n=="hanging_offset_capture")hanging_offset_capture();else if(n=="hanging_offset_cancel")hanging_offset_cancel();else if(n=="rehome_configured_speed")rehome_configured_speed();else if(n=="rehome_completion_snapshot")rehome_completion_snapshot();else if(n=="rehome_timeout")rehome_timeout();else if(n=="rehome_isr_limit")rehome_isr_limit();else if(n=="auto_expiry_fresh_health")auto_expiry_fresh_health();else if(n=="rehome_run")rehome_run();else if(n=="auto_return_braking")auto_return_braking();else if(n=="return_cancel")return_cancel();else if(n=="parameter_values")parameter_values();else if(n=="parameter_bounds")parameter_bounds();else if(n=="parameter_guards")parameter_guards();else if(n=="parameter_rail")parameter_rail();else if(n=="encoder_config_info_guard")encoder_config_info_guard();else if(n=="encoder_config_boot")encoder_config_boot();else if(n=="encoder_config_failed_write")encoder_config_failed_write();else if(n=="encoder_config_failed_read")encoder_config_failed_read();else if(n=="encoder_config_runtime")encoder_config_runtime(false);else if(n=="encoder_config_watchdog")encoder_config_runtime(true);else if(n=="encoder_config_recovery")encoder_config_recovery();else if(n=="encoder_config_stale")encoder_config_stale();else if(n=="calibrate_cancel_commit_stop")calibration_cancel_before_save(false);else if(n=="calibrate_cancel_commit_hello")calibration_cancel_before_save(true);else if(n=="calibrate_upright")calibration_capture("upright");else if(n=="calibrate_hanging")calibration_capture("hanging");else if(n=="calibrate_cancel")calibration_cancel();else if(n.rfind("calibrate_fail_",0)==0)calibration_failure(n.substr(15));else if(n=="cart_only_pulses")cart_only_pulses();else if(n=="lcd_health")lcd_health();else if(n=="magnet_stale")magnet_stale();else if(n=="whole_homing_info")whole_homing_info();else if(n.rfind("magnet_",0)==0)magnet(n.substr(7));else if(n=="info_snapshot")info_snapshot();else if(n=="info_homed")info_homed();else if(n=="edge_consume_race")edge_consume_race();else if(n=="hello_partial")hello_partial();else if(n=="bounced_isr_edge")bounced_isr_edge();else if(n=="wire")wire();else if(n=="isr_center")isr_center();else if(n=="calibration")calibration();else if(n=="reference_watchdog")reference_watchdog();else if(n=="motion")motion();else if(n=="timing")timing();else if(n=="isr_homing_stall")isr_homing_stall();else if(n=="isr_limits")isr_limits();else if(n=="telemetry")telemetry();else return 2;std::cout<<n<<" passed\n";}
