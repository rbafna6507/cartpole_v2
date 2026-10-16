static void hanging_offset_capture(){
 for(int raw:{0,2047,2305,4095})for(int offset:{-256,-113,0,113,256}){
  teensy_reference_store::save(370);init();resetTx();Serial.output.clear();Wire1.raw=raw;
  std::string request="V2 CALIBRATE 7 hanging "+std::to_string(offset);cmd(request.c_str());
  assert(encoderCalibrationBusy());
  for(int i=0;i<400;++i){calibration_tick();if(i%50==0)cmd("V2 PING 7");}
  assert(enc_upright_raw==370&&Serial.output.find("OK 7 CALIBRATE")==std::string::npos);
  calibration_tick();for(int i=0;i<20;++i)serviceSerialTx();
  int expected=(raw+2048+offset+4096)%4096;uint16_t stored;
  assert(enc_upright_raw==expected&&reference_saved&&!encoderCalibrationBusy());
  assert(teensy_reference_store::load(stored)&&stored==expected);
  assert(Serial.output.find("OK 7 CALIBRATE")!=std::string::npos);
  assert(executor_state.homed&&!g_energized&&executor_state.calibration_offset==0);
  init();assert(enc_upright_raw==expected);
 }
}
static void hanging_offset_cancel(){
 teensy_reference_store::save(370);init();Wire1.raw=2305;
 cmd("V2 CALIBRATE 7 hanging 113");
 for(int i=0;i<401;++i){oracle_now_us+=1000;serviceControl();if(i%50==0)cmd("V2 PING 7");}
 assert(reference_save_pending);cmd("V2 STOP 7");saveEncoderReference();assert(enc_upright_raw==370&&!reference_save_pending);
 // A later legacy hanging capture must not inherit the cancelled correction.
 cmd("V2 CALIBRATE 7 hanging");
 for(int i=0;i<400;++i){calibration_tick();if(i%50==0)cmd("V2 PING 7");}
 assert(enc_upright_raw==257&&!g_energized);
}

static void hanging_model_quality(){
 // Explicit zero correction still requires the model capture duration and median.
 teensy_reference_store::save(370);init();Wire1.raw=0;
 cmd("V2 CALIBRATE 7 hanging 0");
 for(int i=0;i<401;++i){
  Wire1.raw=(i>=100&&i<301)?3:0;
  calibration_tick();if(i%50==0)cmd("V2 PING 7");
  if(i<400)assert(enc_upright_raw==370);
 }
 assert(enc_upright_raw==2051&&!encoderCalibrationBusy());
 // A three-count first-to-last-quarter drift fits the span but must not save.
 teensy_reference_store::save(370);init();cmd("V2 CALIBRATE 7 hanging 0");
 for(int i=0;i<401;++i){
  Wire1.raw=i<200?2305:2308;
  calibration_tick();if(i%50==0)cmd("V2 PING 7");
 }
 assert(enc_upright_raw==370&&encoderCalibrationBusy());
 cmd("V2 STOP 7");assert(!encoderCalibrationBusy());
 // Same source window crosses raw wrap; the circular median remains zero.
 teensy_reference_store::save(370);init();cmd("V2 CALIBRATE 7 hanging 0");
 for(int i=0;i<401;++i){
  Wire1.raw=(4095+i%3)%4096;
  calibration_tick();if(i%50==0)cmd("V2 PING 7");
 }
 assert(enc_upright_raw==2048&&!encoderCalibrationBusy());
}
