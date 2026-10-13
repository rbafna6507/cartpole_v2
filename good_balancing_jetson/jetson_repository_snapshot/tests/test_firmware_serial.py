"""Execute firmware parser and watchdog code against mocked UART/time."""
from pathlib import Path
import subprocess
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]
SOURCE=(ROOT/'swingup/swingup.ino').read_text()
def block(start):
    brace=SOURCE.index('{',start);end=brace+1;depth=1
    while depth:
        depth+=(SOURCE[end]=='{')-(SOURCE[end]=='}');end+=1
    return SOURCE[start:end]
class FirmwareSerialTest(unittest.TestCase):
    def test_command_framing_and_motion_timeout(self):
        parser=block(SOURCE.index('void pollSerial()'))
        zero=block(SOURCE.index('int32_t encZeroRaw()'))
        watchdog=block(SOURCE.index('if(((mode!=M_IDLE'))
        harness=r'''
#include <cstdint>
#include <string>
#include <vector>
#include <cassert>
#define F(x) x
struct Uart {
 std::string input;int errors=0;
 int available(){return input.size();}
 char read(){char c=input[0];input.erase(0,1);return c;}
 void println(const char*){++errors;}
} Serial;
void checkedPrintln(const char* text){Serial.println(text);}
std::vector<std::string> commands;
void handleLine(char* line){commands.push_back(line);}
enum {M_IDLE,M_MANUAL,M_SWINGUP,M_BALANCE,M_FAULT,M_RAIL_BRAKE,M_RAIL_RETURN,M_SPIN_BRAKE,M_SPIN_CENTER,M_SPIN_WAIT,M_BAL_BRAKE,M_BAL_CENTER};
uint32_t clock_ms=0,last_host_command_ms=0;
constexpr uint32_t HOST_TIMEOUT_MS=1500;
uint32_t millis(){return clock_ms;}
int mode=M_IDLE,stops=0;float zv_target=0,zv_now=0;bool enabled=true;
void eStop(){++stops;enabled=false;mode=M_IDLE;zv_target=zv_now=0;}
void controlLog(const char*){}
'''+ '\nint32_t enc_last_raw=0,enc_ticks=0,enc_zero=0;constexpr int ENC_CPR=4096;\n'+zero+parser+'\nvoid tick(){'+watchdog+'}\n'+r'''
int main(){
 enc_last_raw=20;enc_ticks=120;enc_zero=0;assert(encZeroRaw()==3996);
 enc_last_raw=1000;enc_ticks=-4096;enc_zero=5;assert(encZeroRaw()==1005);
 Serial.input="st";pollSerial();assert(commands.empty());
 Serial.input="op\r\nparams\n";pollSerial();assert(commands.size()==2 && commands[0]=="stop" && commands[1]=="params");
 Serial.input="auto "+std::string(110,'x');pollSerial();assert(commands.size()==2);
 Serial.input="\nstop\n";pollSerial();assert(Serial.errors==1 && commands.size()==3 && commands.back()=="stop");
 clock_ms=2000;tick();assert(stops==0);
 for(int m: {M_MANUAL,M_SWINGUP,M_BALANCE,M_RAIL_BRAKE,M_RAIL_RETURN,M_SPIN_BRAKE,M_SPIN_CENTER,M_SPIN_WAIT,M_BAL_BRAKE,M_BAL_CENTER}){
   mode=m;enabled=true;last_host_command_ms=100;clock_ms=1600;int before=stops;
   tick();assert(stops==before && enabled);
   clock_ms=1601;tick();assert(stops==before+1 && !enabled && mode==M_FAULT);
   tick();assert(stops==before+1);
 }
 mode=M_IDLE;enabled=true;zv_target=.1f;clock_ms=5000;tick();assert(!enabled && mode==M_FAULT);
 mode=M_IDLE;enabled=true;zv_now=.1f;tick();assert(!enabled && mode==M_FAULT);
 mode=M_SWINGUP;enabled=true;last_host_command_ms=UINT32_MAX-1000;clock_ms=499;tick();assert(enabled);
 clock_ms=500;tick();assert(!enabled && mode==M_FAULT);
}
'''
        with tempfile.TemporaryDirectory() as d:
            cpp=Path(d)/'serial.cpp';exe=Path(d)/'serial';cpp.write_text(harness)
            subprocess.run(['clang++','-std=c++11','-Wall','-Wextra','-Werror',str(cpp),'-o',str(exe)],check=True)
            subprocess.run([str(exe)],check=True)
if __name__=='__main__':unittest.main()
