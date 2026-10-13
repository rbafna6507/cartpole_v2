#pragma once
extern void (*isr)();extern unsigned interval;extern uint64_t next_isr;
extern bool timerAvailable;
struct IntervalTimer {
  bool begin(void(*fn)(),unsigned us){if(!timerAvailable)return false;isr=fn;interval=us;next_isr=clock_us+us;return true;}
  void priority(int){}
};
