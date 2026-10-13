"""Exercise actual firmware set-bw validation and control-task reset integration."""
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / 'swingup/swingup.ino').read_text()

def block(marker):
    start = SOURCE.index(marker)
    end = SOURCE.index('{', start) + 1
    depth = 1
    while depth:
        depth += (SOURCE[end] == '{') - (SOURCE[end] == '}')
        end += 1
    return SOURCE[start:end]

class FilterCommandTest(unittest.TestCase):
    def test_reject_unstable_bandwidth_and_reset_in_control_task(self):
        setter = block('else if (!strcmp(cmd,"set"))')
        estimator = block('void estimate(float theta_meas)')
        names = sorted(set(re.findall(r'\bp_[a-z0-9_]+', setter)) - {'p_bw'})
        harness = f'#include "{ROOT}/swingup/swing_controller.h"\n#include "{ROOT}/swingup/rail_recovery.h"\n'
        harness += '''
#include <cassert>
#include <cmath>
#include <cstring>
#include <cstdlib>
#define F(x) x
swing_control::Parameters controller;
float &p_bw=controller.bw;
float K1=0,K2=0,K3=0,K4=0;
float th=0,thd=0,th_hat=0,thd_hat=0;
constexpr float DT=.001f,VMAX_CEIL=3;
constexpr int M_IDLE=0;
int mode=M_IDLE;
volatile bool req_estimator_reset=false;
void computeGains(){}
void checkedPrintln(const char*){}
template<typename... Args>void checkedPrintf(const char*,Args...){}
struct Param{const char*name;float*ptr;bool recalc;};
Param PARAMS[]={{"bw",&p_bw,false},{"spin_trip_rad_s",&controller.spin_trip_rad_s,false},{"spin_resume_rad_s",&controller.spin_resume_rad_s,false},{"jmax",&p_jmax,false},{"amax_s",&p_amax_s,false},{"amax_b",&p_amax_b,false},{"vmax",&p_vmax,false},{"vmax_s",&p_vmax_s,false},{"vmax_b",&p_vmax_b,false}};
constexpr int N_PARAMS=9;
'''
        harness = harness.replace('Param PARAMS[]=', 'float '+','.join(n+'=1' for n in names)+';\nParam PARAMS[]=')
        harness += estimator + '\n'
        harness += '''void issue(const char*input){
char line[128];std::strcpy(line,input);
char*cmd=std::strtok(line," ");char*a1=std::strtok(nullptr," ");
if(false){}
''' + setter + '\n}\n'
        harness += '''int main(){
// Exercise validation from a known prior runtime setting, independent of boot defaults.
p_bw=50;
issue("set vmax 1.5");issue("set vmax 1.5001");assert(p_vmax==1.5f);
issue("set vmax_s 1.5");issue("set vmax_s 2");assert(p_vmax_s==1.5f);
issue("set vmax_b 1.5");issue("set vmax_b 2");assert(p_vmax_b==1.5f);
issue("set amax_s 25");issue("set amax_s 26");assert(p_amax_s==25);
issue("set amax_b 25");issue("set amax_b 26");assert(p_amax_b==25);
issue("set jmax 100");assert(p_jmax==100);issue("set jmax 150");issue("set jmax 151");assert(p_jmax==150);
issue("set spin_trip_rad_s 151");assert(controller.spin_trip_rad_s==150);
issue("set spin_trip_rad_s 60");assert(controller.spin_trip_rad_s==60);
issue("set spin_resume_rad_s 20");assert(controller.spin_resume_rad_s==20);
issue("set spin_trip_rad_s 10");assert(controller.spin_trip_rad_s==60);
issue("set spin_resume_rad_s 60");assert(controller.spin_resume_rad_s==20);
issue("set spin_resume_rad_s 0");assert(controller.spin_resume_rad_s==20);
mode=3;issue("set spin_trip_rad_s 70");issue("set spin_resume_rad_s 15");assert(controller.spin_trip_rad_s==60 && controller.spin_resume_rad_s==20);mode=M_IDLE;
for(const char*input:{"set bw 500","set bw 100.01","set bw 0.01","set bw nan","set bw inf"}){
issue(input);assert(p_bw==50 && !req_estimator_reset);
}
mode=3;issue("set bw 30");assert(p_bw==50 && !req_estimator_reset);
mode=M_IDLE;th_hat=-1;thd_hat=4128061.5f;
issue("set bw 30");assert(req_estimator_reset && thd_hat>4000000);
estimate(.0828f);assert(!req_estimator_reset && std::fabs(th_hat-.0828f)<1e-6f && std::fabs(thd)<.0001f);
issue("set bw 100");assert(p_bw==100 && req_estimator_reset);
estimate(.09f);assert(!req_estimator_reset && std::fabs(thd)<.0001f);
issue("set bw 50");assert(p_bw==50 && req_estimator_reset);
estimate(.1f);assert(std::fabs(thd)<.0001f);
}
'''
        harness = '#include <initializer_list>\n' + harness
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder)/'check.cpp'
            binary = Path(folder)/'check'
            source.write_text(harness)
            subprocess.run(['clang++','-std=c++11','-O2',str(source),'-o',str(binary)],check=True)
            subprocess.run([str(binary)],check=True)

if __name__ == '__main__':
    unittest.main()
