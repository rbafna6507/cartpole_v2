static void rehome_run(){
 for(int offset:{-5000,5000,0}){
  init();home_steps=1234;ax_pos[0]=home_steps+offset;measured_home_span_steps=14000;
  const uint32_t epoch=home_epoch;const float rail=p_rail;
  resetTx();Serial.output.clear();cmd("V2 REHOME 7");for(int i=0;i<20;++i)serviceSerialTx();
  assert(Serial.output.find("@V2 OK 7 REHOME*")!=std::string::npos);
  assert(g_energized&&mode==14&&executor_state.mode==14);float last_a=acc_cmd;
  for(unsigned i=0;i<2200000 && executor_state.enabled;++i){
   oracle_now_us+=7;onStepTimer();const uint32_t tick=executor_state.tick;serviceControl();
   if(executor_state.tick!=tick){assert(fabsf(vc)<=.08001f&&fabsf(acc_cmd)<=.50001f);assert(fabsf(acc_cmd-last_a)<=.0101f);last_a=acc_cmd;if(executor_state.tick%100==0)cmd("V2 PING 7");}
  }
  assert(!g_energized&&mode==M_IDLE&&executor_state.fault==executor::NONE&&executor_state.homed);
  assert(ax_pos[0]==home_steps&&home_steps==1234&&home_epoch==epoch&&measured_home_span_steps==14000&&p_rail==rail);
 }
}
static void auto_return_braking(){
 for(unsigned initial_mode:{2,3,5,6,7,8,9})for(int sign:{-1,1}){
  init();home_steps=0;ax_pos[0]=-sign*3000;cmd("V2 MODE 7 auto 1");mode=(Mode)initial_mode;executor_state.mode=initial_mode;
  vc=sign*1.f;acc_cmd=sign*3.f;const uint32_t epoch=home_epoch;oracle_now_us+=1000;serviceControl();
  assert(g_energized&&mode==14&&executor_state.mode==14&&executor_state.fault==executor::NONE);
  assert(vc*sign>.99f&&acc_cmd*sign>2.8f); // Inherited command is jerk-ramped, never reset.
  float previous_a=acc_cmd;bool centered_slow=false;
  for(unsigned i=0;i<2200000&&executor_state.enabled;++i){
   oracle_now_us+=7;onStepTimer();uint32_t tick=executor_state.tick;serviceControl();
   if(tick!=executor_state.tick){assert(fabsf(acc_cmd-previous_a)<=.1501f);previous_a=acc_cmd;assert(fabsf(vc)<=1.5001f);if(fabsf(vc)<.002f)centered_slow=true;if(executor_state.tick%100==0)cmd("V2 PING 7");}
  }
  assert(centered_slow&&!g_energized&&mode==M_IDLE&&executor_state.fault==executor::NONE);
  assert(ax_pos[0]==home_steps&&executor_state.homed&&home_epoch==epoch);
 }
}
static void return_cancel(){
 for(int cause=0;cause<5;++cause){
  init();home_steps=0;ax_pos[0]=4000;cmd("V2 REHOME 7");assert(mode==14&&g_energized);
  if(cause==0)cmd("V2 STOP 7");else if(cause==1){executor_state.trip(executor::LIMIT);}else if(cause==2){Wire1.healthy=false;}else if(cause==3){executor_state.homed=false;}else{executor_state.host_at=executor_state.tick-200;}
  oracle_now_us+=1000;serviceControl();assert(!g_energized&&mode!=14&&ax_inc[0]==0);
  for(int i=0;i<10;++i){oracle_now_us+=1000;serviceControl();assert(!g_energized&&mode!=14);}
 }
}

static void rehome_timeout(){
 init();home_steps=0;ax_pos[0]=5000;cmd("V2 REHOME 7");assert(mode==14);
 // A stalled physical response/count target cannot extend the bounded return.
 for(int i=0;i<15000;++i){if(i%100==0)cmd("V2 PING 7");oracle_now_us+=1000;serviceControl();}
 assert(!g_energized&&mode==M_FAULT&&executor_state.fault==executor::DURATION);
}
static void rehome_isr_limit(){
 init();executor_state.switches=true;executor_state.tick=5;home_steps=0;ax_pos[0]=3000;cmd("V2 REHOME 7");assert(g_energized&&mode==14);
 native_pins[26]=HIGH;onStepTimer();assert(!g_energized&&limit_fault_pending&&native_pins[8]==HIGH);
 oracle_now_us+=1000;serviceControl();assert(executor_state.fault==executor::LIMIT&&!executor_state.homed&&mode==M_FAULT);
}
static void auto_expiry_fresh_health(){
 init();cmd("V2 MODE 7 auto 1");Wire1.healthy=false;oracle_now_us+=1000;serviceControl();
 assert(!g_energized&&executor_state.fault==executor::ENCODER&&mode==M_FAULT&&!executor_state.homed);
 assert(saved_return.phase==saved_center_return::State::OFF);
}

static void center_snapshot_irq(){native_mask_hook=nullptr;onStepTimer();}
static void rehome_completion_snapshot(){
 init();home_steps=0;ax_pos[0]=-1;cmd("V2 REHOME 7");vc=.0002f;acc_cmd=0;
 ax_dir[0]=1;ax_acc[0]=ax_inc[0]=UINT32_MAX;native_mask_hook=center_snapshot_irq;
 oracle_now_us+=1000;serviceControl();assert(!g_energized&&mode==M_IDLE&&ax_pos[0]==home_steps);
 assert(xc==0); // Snapshot matches the atomic counted midpoint, not an earlier read.
}

static void rehome_configured_speed(){
 init();parameter_write("vmax",".04",.04f);home_steps=0;ax_pos[0]=3000;cmd("V2 REHOME 7");
 for(unsigned i=0;i<2200000&&executor_state.enabled;++i){oracle_now_us+=7;onStepTimer();uint32_t tick=executor_state.tick;serviceControl();if(tick!=executor_state.tick){assert(fabsf(vc)<=.04001f);if(executor_state.tick%100==0)cmd("V2 PING 7");}}
 assert(!g_energized&&mode==M_IDLE&&executor_state.fault==executor::NONE&&ax_pos[0]==home_steps);
}
