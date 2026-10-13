"""Verify firmware-generated UART frames with Python's independent CRC implementation."""
import binascii
from pathlib import Path
import subprocess
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]
SOURCE=(ROOT/'swingup/swingup.ino').read_text()
def block(signature):
    start=SOURCE.index(signature);brace=SOURCE.index('{',start);depth=1;end=brace+1
    while depth:
        depth+=(SOURCE[end]=='{')-(SOURCE[end]=='}');end+=1
    return SOURCE[start:end]
class ChecksumTest(unittest.TestCase):
    def test_actual_firmware_formatter_and_crc_match_python(self):
        harness='''#include <cstdio>
#include <cstdarg>
#include <cstring>
#include <cassert>
#include "'''+str(ROOT/'swingup/serial_frame.h')+'''"
struct Port {
 void printf(const char* format,...) {va_list args;va_start(args,format);vprintf(format,args);va_end(args);}
} Serial;
'''+block('void checkedPrintln(const char *text)')+'\n'+block('void checkedPrintf(const char *format, ...)')+'''
int main(){
 assert(serial_frame::checksum("123456789",9)==0x29b1);
 checkedPrintln("# STOP");
 checkedPrintf("= pc1 %.5f\\n",-0.8);
 checkedPrintf("E %u %u %u %u %u %u %u %u",174964,3416,1403,72,103,0,1,0);
 checkedPrintln("T 18021 0 -3.0879 0 0 0 0 -1 0 0 106 527\\r\\n");
 char big[300];memset(big,'x',sizeof(big)-1);big[299]=0;checkedPrintf("%s",big);
}
'''
        # Exercise the exact new capability/gain replies, each its own CRC frame.
        replies=block('void printParams()')
        replies=replies[replies.index('  checkedPrintln(F("= bal_fall_deg'):replies.rindex('}')]
        harness='#define F(x) x\n#include "'+str(ROOT/'swingup/swing_controller.h')+'"\nswing_control::Parameters controller;\n'+harness
        harness=harness.replace(' char big[300];',replies+'\n char big[300];')
        with tempfile.TemporaryDirectory() as d:
            cpp=Path(d)/'crc.cpp';exe=Path(d)/'crc';cpp.write_text(harness)
            subprocess.run(['clang++','-std=c++11','-Wall','-Wextra','-Werror',str(cpp),'-o',str(exe)],check=True)
            lines=subprocess.check_output([str(exe)]).splitlines()
        self.assertEqual(len(lines),11)
        for frame in lines:
            self.assertTrue(frame.startswith(b'@'))
            payload,checksum=frame[1:].rsplit(b'*',1)
            self.assertEqual(int(checksum,16),binascii.crc_hqx(payload,0xffff))
        self.assertTrue(lines[1].startswith(b'@= pc1 -0.80000*'))
        self.assertTrue(lines[-1].startswith(b'@! serial message too long; discarded*'))
if __name__=='__main__':unittest.main()
