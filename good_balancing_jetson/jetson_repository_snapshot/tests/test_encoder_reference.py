"""Exercise live angle mapping, calibration capture, persistence and command guards."""
from pathlib import Path
import subprocess,tempfile,unittest
ROOT=Path(__file__).resolve().parents[1]
SOURCE=(ROOT/'swingup/swingup.ino').read_text()
def block(marker):
    start=SOURCE.index(marker);brace=SOURCE.index('{',start);end=brace+1;depth=1
    while depth:
        depth+=(SOURCE[end]=='{')-(SOURCE[end]=='}');end+=1
    return SOURCE[start:end]
class EncoderReferenceTest(unittest.TestCase):
    def test_live_reference_capture_and_persistence(self):
        harness=r'''
#include <cassert>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>
#define ENC_INVERT 0
#define ENC_CPR 4096
#define F(x) x
int32_t enc_last_raw=0,enc_ticks=0,enc_zero=0,enc_upright_raw=3953,requested_upright_raw=0;
int calibration_request=0;bool zeroing=false,capture_upright=false,reference_saved=false,reference_save_pending=false;
float th=0,th_hat=0,thd=0,thd_hat=0,energy_n=0;
struct Pump{void reset(){}}pump;
struct Watch{bool armed=true;}response_watch;
bool storage_ok=true,write_ok=true,enc_ok=true,g_energized=false;
int stored_raw=65535,enc_consec_err=0,mode=0;constexpr int M_IDLE=0;
uint32_t now=0,zero_t0=0;uint32_t millis(){return now;}
struct Preferences{
 bool begin(const char*,bool){return storage_ok;}
 uint16_t getUShort(const char*,uint16_t fallback){return stored_raw==65535?fallback:stored_raw;}
 size_t putUShort(const char*,uint16_t raw){if(!write_ok)return 0;stored_raw=raw;return 2;}
 void end(){}
};
std::vector<std::string> messages;
void controlLog(const char*s){messages.emplace_back(s);}
void checkedPrintln(const char*s){messages.emplace_back(s);}
template<typename...Args>void checkedPrintf(const char*,Args...){}
'''
        harness='#include "'+str(ROOT/'swingup/encoder_reference.h')+'"\n'+harness
        harness+='encoder_reference::StillCapture reference_capture;\n'
        for marker in ['void loadEncoderReference()', 'float encTheta()', 'bool encoderCalibrationBusy()', 'void cancelEncoderCalibration()', 'void applyEncoderReference(int32_t raw)', 'void saveEncoderReference()']:
            harness+=block(marker)+'\n'
        harness+='void eStop(){g_energized=false;mode=M_IDLE;cancelEncoderCalibration();}\n'
        harness+='void issue(const char *input){char line[128];snprintf(line,sizeof(line),"%s",input);char *cmd=strtok(line," ");char *a1=strtok(nullptr," ");'+block('if (!strcmp(cmd,"zero") || !strcmp(cmd,"upright"))')+'}\n'
        harness+='void tick(){'+block('if(calibration_request){')+block('if(zeroing){')+'}\n'
        # Exercise the actual motion guard, without running or mocking unrelated motor commands.
        harness+='bool blocked(const char *cmd){'+block('if(encoderCalibrationBusy() &&').replace('return;','return true;')+'return false;}\n'
        harness+=r'''
int main(){
 using namespace encoder_reference;
 for(const char* text:{"upright -1","upright 4096","upright 12.5","upright 14 junk","zero 3"}){
   issue(text);assert(calibration_request==0 && !zeroing);
 }
 issue("upright 3769");assert(calibration_request==3 && requested_upright_raw==3769 && !g_energized);
 cancelEncoderCalibration();issue("upright");assert(calibration_request==2);cancelEncoderCalibration();
 issue("zero");assert(calibration_request==1);cancelEncoderCalibration();
 enc_last_raw=3953;assert(encTheta()==0);
 for(int ref=0;ref<4096;ref+=17)for(int raw=0;raw<4096;raw+=13){
  float a=angle_from_upright(raw,false,ref);assert(std::abs(a)<=3.141593f);
  assert(angle_from_upright(raw,true,ref)==-a);
 }
 enc_upright_raw=3769;enc_last_raw=3769;assert(encTheta()==0);
 enc_last_raw=0;float a=encTheta();enc_last_raw=4095;float b=encTheta();
 assert(std::abs(a-b-radians_per_count)<1e-6);
 int32_t n=0;assert(parse_count("0",n)&&n==0);assert(parse_count("4095",n)&&n==4095);
 for(const char *bad:{"","-1","4096","10.5","1e3","12x","+5","99999999999999999999"})assert(!parse_count(bad,n));
 assert(opposite(4095)==2047 && opposite(2048)==0 && opposite(0)==2048);
 StillCapture c;
 for(int i=0;i<400;i++)assert(c.add(i%2?4095:1,true)==(i==399));
 assert(c.mean()==0);
 c.reset();for(int i=0;i<1000;i++)assert(!c.add(i%4096,true)); // slow drift must never qualify
 c.reset();for(int i=0;i<399;i++)assert(!c.add(25,true));
 assert(!c.add(25,false));assert(c.count==0);assert(!c.add(25,true));
 // Upright held at a different count: no old-angle-window restriction.
 enc_last_raw=3769;enc_ticks=100;calibration_request=2;
 assert(blocked("bal") && blocked("auto") && blocked("on") && blocked("v") && blocked("zv"));
 assert(!blocked("stop") && !blocked("params"));
 for(int i=0;i<400;i++){now++;tick();}
 assert(!zeroing && reference_save_pending && enc_upright_raw==3769);
 assert(th==0 && th_hat==0 && thd==0 && thd_hat==0 && !response_watch.armed);
 assert(encoderCalibrationBusy() && !g_energized);saveEncoderReference();
 assert(reference_saved && stored_raw==3769 && !encoderCalibrationBusy());
 enc_upright_raw=3953;reference_saved=false;loadEncoderReference();assert(enc_upright_raw==3769 && reference_saved);
 // Explicit down-zero changes upright by half a turn and resets the observer.
 enc_last_raw=4095;enc_ticks=200;calibration_request=1;
 for(int i=0;i<400;i++){now++;tick();}
 assert(enc_upright_raw==2047 && std::abs(std::abs(th)-3.141593f)<1e-5);
 saveEncoderReference();assert(stored_raw==2047);
 // Exact count, failed save (active reference retained, not reported as saved).
 calibration_request=3;requested_upright_raw=42;write_ok=false;tick();
 assert(enc_upright_raw==42 && reference_save_pending);saveEncoderReference();
 assert(!reference_saved && !reference_save_pending && stored_raw==2047);write_ok=true;
 // Invalid encoder reads cannot qualify a stationary capture or direct assignment.
 int32_t before=enc_upright_raw;enc_ok=false;calibration_request=2;
 for(int i=0;i<5100;i++){now++;tick();}assert(!zeroing && enc_upright_raw==before);
 calibration_request=3;requested_upright_raw=100;tick();assert(enc_upright_raw==before);
 // Stop cancels pending and ongoing calibration; it cannot commit later.
 enc_ok=true;calibration_request=2;tick();assert(zeroing);
 cancelEncoderCalibration();for(int i=0;i<1000;i++){now++;tick();}assert(enc_upright_raw==before);
 calibration_request=1;cancelEncoderCalibration();tick();assert(!zeroing);
 // Setup never calibrates from the startup pose; no saved value falls back.
 stored_raw=65535;enc_upright_raw=3953;reference_saved=false;loadEncoderReference();
 assert(enc_upright_raw==3953 && !reference_saved);
}
'''
        with tempfile.TemporaryDirectory() as d:
            cpp=Path(d)/'reference.cpp';exe=Path(d)/'reference';cpp.write_text(harness)
            subprocess.run(['clang++','-std=c++11','-Wall','-Wextra','-Werror',str(cpp),'-o',str(exe)],check=True)
            subprocess.run([str(exe)],check=True)
        setup=block('void setup()')
        self.assertIn('loadEncoderReference();',setup)
        self.assertNotIn('encZeroBlocking',setup)
        self.assertNotIn('applyEncoderReference',setup)
if __name__=='__main__':unittest.main()
