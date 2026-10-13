#pragma once
extern void (*isr)();extern unsigned interval;extern uint64_t next_isr;
struct IntervalTimer{bool begin(void(*fn)(),unsigned us){isr=fn;interval=us;next_isr=clock_us+us;return true;}void priority(int){}};
