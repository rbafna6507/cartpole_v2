static void vertical_guards(){
 init();cmd("V2 ZMOVE 7 both 2 2");assert(!g_energized);
 cmd("V2 ZREF 7 both");assert(executor_state.z.refs==3);
 for(const char* s:{"V2 ZMOVE 7 both nan 2","V2 ZMOVE 7 both 21 2","V2 ZMOVE 7 both -1 2","V2 ZMOVE 7 both 1 41","V2 ZMOVE 7 both 1 1e-30","V2 ZSINE 7 20 1 25 3"}){cmd(s);assert(!g_energized);}
 cmd("V2 ZMOVE 7 left 2 2");assert(mode==M_VERTICAL&&g_energized&&executor_state.z.phase==1);
 cmd("V2 ZREF 7 both");assert(executor_state.z.phase==1);
 cmd("V2 ZSTOP 7");assert(!g_energized&&executor_state.z.refs==2);
 cmd("V2 HELLO 8");assert(executor_state.z.refs==0);
}
static void vertical_pulses(){
 init();cmd("V2 ZREF 7 both");cmd("V2 ZMOVE 7 both 2 2");
 for(int ms=0;ms<2100&&executor_state.enabled;++ms){if(ms%50==0)cmd("V2 PING 7");oracle_now_us+=1000;serviceControl();for(int t=0;t<250;++t)onZTimer();}
 assert(!g_energized&&executor_state.z.refs==3&&executor_state.z.phase==0);
 assert(z_count[0]==1280&&z_count[1]==1280);
 assert(native_pins[5]==LOW&&native_pins[7]==HIGH);
 cmd("V2 MODE 7 auto 5000");cmd("V2 ZMOVE 7 both 1 2");assert(executor_state.z.phase==1);
 cmd("V2 ZSTOP 7");assert(g_energized&&executor_state.enabled&&mode==M_SWINGUP&&executor_state.z.refs==0);
 cmd("V2 STOP 7");assert(!g_energized);
}
static void vertical_safety(){
 init();cmd("V2 ZREF 7 both");cmd("V2 ZMOVE 7 both 2 2");oracle_now_us+=6000;onZTimer();assert(!g_energized&&timing_fault_pending);serviceControl();assert(executor_state.z.phase==0&&executor_state.z.refs==0);
 init();cmd("V2 ZHOME 7 left");assert(executor_state.z.phase==2&&executor_state.z.selected==1);
 for(int i=0;i<5002&&executor_state.enabled;++i){if(i%50==0)cmd("V2 PING 7");oracle_now_us+=1000;serviceControl();for(int t=0;t<250;++t)onZTimer();}
 assert(!g_energized&&executor_state.z.bottom==1&&executor_state.z.refs==0);
}

static void vertical_sine(){
 init();cmd("V2 ZREF 7 both");cmd("V2 ZSINE 7 20 1 25 10");assert(executor_state.z.phase==3);
 bool sine=false;int32_t maximum=0,minimum=128000;
 for(int ms=0;ms<16000&&executor_state.enabled;++ms){if(ms%50==0)cmd("V2 PING 7");oracle_now_us+=1000;serviceControl();
  if(executor_state.z.phase==4){sine=true;maximum=std::max(maximum,int32_t(z_count[0]));minimum=std::min(minimum,int32_t(z_count[0]));}
  for(int t=0;t<250;++t){onZTimer();if(native_pins[4]==HIGH){onStepTimer();assert(native_pins[4]==HIGH);}}
 }
 assert(sine&&!g_energized&&executor_state.fault==executor::NONE&&executor_state.z.refs==3);
 assert(z_count[0]==16000&&z_count[1]==16000&&maximum>28000&&minimum<4000);
 cmd("V2 STOP 7");assert(executor_state.z.refs==3);
 resetTx();Serial.output.clear();cmd("V2 ZSTATUS 7");for(int i=0;i<20;++i)serviceSerialTx();
 assert(Serial.output.find("@V2 Z 7 0 3 25.000000 25.000000 0*")!=std::string::npos);
}
static void vertical_faults(){
 for(int reason=0;reason<3;++reason){
  init();cmd("V2 ZREF 7 both");cmd("V2 ZMOVE 7 both 20 2");
  if(reason==0){executor_state.switches=true;native_pins[27]=HIGH;onZTimer();}
  if(reason==1)Wire1.status=0x30;
  for(int ms=0;ms<210;++ms){oracle_now_us+=1000;serviceControl();for(int t=0;t<250;++t)onZTimer();}
  assert(!g_energized&&executor_state.z.refs==0&&executor_state.z.phase==0);
  assert(executor_state.fault==(reason==0?executor::LIMIT:reason==1?executor::ENCODER:executor::HOST_TIMEOUT));
 }
}

static void vertical_measurements(){
 init();cmd("V2 ZREF 7 both");cmd("V2 ZMOVE 7 both 2 2");
 oracle_now_us+=1000;serviceControl();const float before=th,before_estimate=th_hat;
 Wire1.raw=(Wire1.raw+100)%4096;ax_pos[AX_CART]=home_steps+100;
 oracle_now_us+=1000;serviceControl();emitTelemetry();
 assert(mode==M_VERTICAL&&g_energized&&ax_inc[AX_CART]==0);
 assert(fabsf(th-before)>.1f&&th_hat!=before_estimate&&fabsf(th-encTheta())<1e-6f);
 assert(fabsf(xc-100.f/CART_STEPS_PER_M)<1e-6f);
 float wire_th=0,wire_est=0,wire_rate=0,wire_x=0;
 assert(sscanf(latest_state.bytes,"@V2 S %*u %*u %*u %*u %*u %f %f %f %f",&wire_th,&wire_est,&wire_rate,&wire_x)==4);
 assert(fabsf(wire_th-th)<1e-5f&&fabsf(wire_est-th_hat)<1e-5f&&fabsf(wire_x-xc)<1e-6f);
}
