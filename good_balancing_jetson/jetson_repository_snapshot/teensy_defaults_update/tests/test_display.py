"""Exercise display output and bounded incremental refresh with a mock LCD."""
from pathlib import Path
import subprocess, tempfile
root=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory() as d:
 p=Path(d)
 (p/'SPI.h').write_text('#pragma once\n#include <cstdint>\n#define OUTPUT 1\n#define LOW 0\n#define HIGH 1\ninline void pinMode(int,int){}\ninline void digitalWrite(int,int){}\n')
 (p/'ST7735_t3.h').write_text('#pragma once\n')
 (p/'ST7789_t3.h').write_text('''#pragma once
struct ST7789_t3 {
 int draws=0;
 ST7789_t3(int,int,int,int,int){}
 void init(int,int){} void setRotation(int){} void fillScreen(int){}
 void setTextSize(int){} void setTextColor(int,int){} void setCursor(int,int){}
 void print(const char*){}
 void drawChar(int,int,char,int,int,int){++draws;}
};
''')
 (p/'test.cpp').write_text('''#include "status_display.h"
#include <cassert>
using namespace status_display;
void flush(){for(int i=0;i<400;++i){int old=lcd.draws;service();assert(lcd.draws-old<=1);}}
int main(){
 begin();snapshot("DISCONNECTED",0x8410,false,false,false,false,0,0,0,nullptr);flush();
 assert(!memcmp(shown[1],"DISCONNECTED",12));
 snapshot("IDLE",0xFFFF,true,false,true,true,12,40,0,nullptr);flush();
 assert(!memcmp(shown[1],"IDLE                ",20));
 snapshot("FAULT",0xF800,false,false,false,true,0,0,0,"host link timeout -> FAULT; drivers disabled");flush();
 assert(!memcmp(shown[1],"FAULT",5));assert(!memcmp(shown[2],"HOST: DISCONNECTED",18));
 assert(!memcmp(shown[8],"host link timeout",17));
 int old=lcd.draws;flush();assert(lcd.draws==old);
}
''')
 subprocess.run(['g++','-std=c++17','-Wall','-Wextra','-Werror','-I'+d,'-I'+str(root/'teensy_swingup'),str(p/'test.cpp'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
print('PASS: LCD disconnected/idle/fault, stale text clearing, one glyph maximum per service, unchanged screen skips writes')
