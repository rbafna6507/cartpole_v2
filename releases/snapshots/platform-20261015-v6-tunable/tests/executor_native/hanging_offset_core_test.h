static void hanging_offset_core(){
 Core c=ready();
 for(const char* value:{"257","-257","1.0","1e1","+1","nan","--1","4294967296"}){
  check_error(c,std::string("V2 CALIBRATE 7 hanging ")+value);assert(!c.calibration&&!c.enabled);
 }
 check_error(c,"V2 CALIBRATE 7 upright 1");
 for(int offset:{-256,-113,0,113,256}){
  assert(send(c,"V2 CALIBRATE 7 hanging "+std::to_string(offset)).kind==OK);
  assert(c.calibration==1&&c.calibration_offset==offset&&c.calibration_model&&!c.enabled);
  check_error(c,"V2 ARM 7 1000");check_error(c,"V2 CALIBRATE 7 hanging 0");
  assert(c.calibration_offset==offset);c.stop();assert(!c.calibration&&c.calibration_offset==0&&!c.calibration_model);
 }
 assert(send(c,"V2 CALIBRATE 7 hanging 113").kind==OK);send(c,"V2 HELLO 9");
 assert(c.calibration_offset==0&&!c.calibration&&!c.calibration_model);
 assert(send(c,"V2 CALIBRATE 9 hanging").kind==OK);assert(c.calibration_offset==0&&!c.calibration_model);c.stop();
 assert(send(c,"V2 CALIBRATE 9 upright").kind==OK);assert(c.calibration_offset==0&&!c.calibration_model);c.stop();
 c.sample(false,0);check_error(c,"V2 CALIBRATE 9 hanging 113");assert(c.calibration_offset==0);
}
