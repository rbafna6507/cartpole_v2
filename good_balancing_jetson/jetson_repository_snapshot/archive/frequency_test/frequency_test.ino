// Dedicated, open-loop cart frequency test. No swing-up or Z-axis movement.
// Flash this sketch for the GUI; flash swingup again to restore that controller.
#include <Arduino.h>
#include <initializer_list>
#include "xtensa/core-macros.h"
#include "soc/soc.h"
#include "soc/gpio_reg.h"
#include "frequency_motion.h"

namespace ft = frequency_test;
constexpr int STEP=25, DIR=26, ENABLE=27;
constexpr bool INVERT=true;
constexpr uint32_t STEP_MASK=1UL<<STEP;
constexpr int HEARTBEAT_TICKS=ft::timer_hz*3/4; // 750 ms, enforced in ISR
constexpr int HARD_STEPS=(int)(0.140*ft::steps_per_m);
portMUX_TYPE pulse_mux=portMUX_INITIALIZER_UNLOCKED;
volatile uint32_t increment=0, phase_acc=0;
volatile int32_t position_steps=0;
volatile int8_t direction=1;
volatile uint8_t dir_hold=0;
volatile bool armed=false, isr_fault=false;
volatile uint32_t lease_ticks=0;
volatile uint32_t timer_ticks=0, pulse_count=0, previous_tick=0, max_tick_gap=0;
volatile uint32_t last_rise=0, last_fall=0, min_high=UINT32_MAX, min_low=UINT32_MAX;
uint32_t update_count=0, max_update_us=0, stats_start=0;
hw_timer_t *timer=nullptr;

enum State {IDLE, RAMP_UP, RUNNING, RAMP_DOWN, FAULT};
State state=IDLE;
const char* names[]={"IDLE","RAMP_UP","RUNNING","RAMP_DOWN","FAULT"};
ft::Config config={100,0.25};
ft::Sample reference={0,0,0,0};
uint32_t last_control_us=0, last_stream_us=0, last_ping_ms=0;
double elapsed=0, finish_at=-1, interval_velocity=0;
bool centered=false;

void IRAM_ATTR tick() {
  portENTER_CRITICAL_ISR(&pulse_mux);
  const uint32_t cycles=XTHAL_GET_CCOUNT();
  ++timer_ticks;
  if (previous_tick) max_tick_gap=max((uint32_t)max_tick_gap,(uint32_t)(cycles-previous_tick));
  previous_tick=cycles;
  REG_WRITE(GPIO_OUT_W1TC_REG,STEP_MASK);
  if (last_rise) {
    min_high=min((uint32_t)min_high,(uint32_t)(cycles-last_rise));
    last_rise=0;last_fall=cycles;
  }
  if (armed && (++lease_ticks > HEARTBEAT_TICKS ||
      position_steps > HARD_STEPS || position_steps < -HARD_STEPS)) {
    increment=0; armed=false; isr_fault=true;
  }
  if (dir_hold) --dir_hold;
  else if (increment) {
    uint32_t previous=phase_acc;
    phase_acc+=increment;
    if (phase_acc<previous) {
      position_steps+=direction;
      const uint32_t edge=XTHAL_GET_CCOUNT();
      if (last_fall) min_low=min((uint32_t)min_low,(uint32_t)(edge-last_fall));
      last_rise=edge;++pulse_count;
      REG_WRITE(GPIO_OUT_W1TS_REG,STEP_MASK);
    }
  }
  portEXIT_CRITICAL_ISR(&pulse_mux);
}

void stopNow(const char* reason, bool fault=false) {
  portENTER_CRITICAL(&pulse_mux);
  increment=0; armed=false;
  portEXIT_CRITICAL(&pulse_mux);
  state=fault?FAULT:IDLE; reference={0,0,0,0}; interval_velocity=0;
  // Immediate stops require physical center confirmation before another run.
  centered=false;
  Serial.printf("# %s\n",reason);
  // Keep ENABLE asserted: shared height axes must not be released by a stop.
}

void setVelocity(double v) {
  const int8_t d=v>=0?1:-1;
  const uint32_t inc=(uint32_t)(fabs(v)*ft::steps_per_m*4294967296.0/ft::timer_hz);
  portENTER_CRITICAL(&pulse_mux);
  if (d!=direction) {
    direction=d; increment=0; dir_hold=1;
    const bool high=(d>0)!=INVERT;
    REG_WRITE(high?GPIO_OUT_W1TS_REG:GPIO_OUT_W1TC_REG,1UL<<DIR);
  }
  increment=inc;
  portEXIT_CRITICAL(&pulse_mux);
}

void hello() {
  Serial.printf("# FREQUENCY_TEST_V2 rail_mm=300 margin_mm=15 max_travel_mm=270 max_speed=%.8f steps_per_m=%.8f\n",ft::max_speed,ft::steps_per_m);
}
bool number(const char* word, double &value) {
  if (!word) return false;
  char* end=nullptr; value=strtod(word,&end);
  return end!=word && !*end && isfinite(value);
}
void command(char* line) {
  char* cmd=strtok(line," \t"); if (!cmd) return;
  if (!strcmp(cmd,"ping")) {
    last_ping_ms=millis();
    portENTER_CRITICAL(&pulse_mux); lease_ticks=0; portEXIT_CRITICAL(&pulse_mux);
  } else if (!strcmp(cmd,"hello")) hello();
  else if (!strcmp(cmd,"stop")) stopNow("STOP");
  else if (!strcmp(cmd,"center")) {
    if (armed) {Serial.println("! stop before setting physical center");return;}
    portENTER_CRITICAL(&pulse_mux);
    position_steps=0; phase_acc=0; isr_fault=false;
    portEXIT_CRITICAL(&pulse_mux);
    elapsed=0; state=IDLE; centered=true;
    Serial.println("# CENTERED");
  } else if (!strcmp(cmd,"run")) {
    ft::Config wanted;
    char* amp=strtok(nullptr," \t"); char* hz=strtok(nullptr," \t");
    char* ramp=strtok(nullptr," \t");
    if (!number(amp,wanted.travel_mm) || !number(hz,wanted.hz) || !number(ramp,wanted.ramp_s) ||
        strtok(nullptr," \t") || !ft::valid(wanted)) {
      Serial.println("! invalid test: travel 1..270 mm, frequency 0.02..5 Hz, ramp 0.5..30 s, pulse ceiling includes ramp");return;
    }
    if (state!=IDLE || armed || !centered || labs(position_steps)>3 ||
        millis()-last_ping_ms>500) {
      Serial.println("! run requires IDLE, confirmed physical center and live host");return;
    }
    config=wanted; elapsed=0; finish_at=-1; reference={0,0,0,0};
    digitalWrite(ENABLE,LOW);
    portENTER_CRITICAL(&pulse_mux);
    lease_ticks=0; phase_acc=0; isr_fault=false; armed=true;
    last_rise=last_fall=0; min_high=min_low=UINT32_MAX;
    update_count=max_update_us=timer_ticks=pulse_count=max_tick_gap=0;
    stats_start=micros();
    portEXIT_CRITICAL(&pulse_mux);
    state=RAMP_UP; last_control_us=micros();
    Serial.printf("# RUN %.6f %.6f ramp_s=%.6f\n",config.travel_mm,config.hz,ft::rampSeconds(config));
  } else if (!strcmp(cmd,"finish")) {
    if (armed && finish_at<0) {
      // Wait until amplitude ramp-up completes, avoiding an envelope jump.
      finish_at=fmax(elapsed,ft::rampSeconds(config));
    }
    Serial.println("# FINISH requested");
  } else Serial.println("! unknown command");
}

void setup() {
  // Z STEP pins stay low; Z axes never receive motion commands in this sketch.
  for (int pin : {STEP,DIR,16,17,18,19}) {pinMode(pin,OUTPUT);digitalWrite(pin,LOW);}
  pinMode(ENABLE,OUTPUT);digitalWrite(ENABLE,LOW);
  digitalWrite(DIR,INVERT?LOW:HIGH);
  Serial.setTxBufferSize(2048);
  Serial.begin(921600);
#if ESP_ARDUINO_VERSION_MAJOR >= 3
  timer=timerBegin(1000000);timerAttachInterrupt(timer,&tick);timerAlarm(timer,8,true,0);
#else
  timer=timerBegin(0,80,true);timerAttachInterrupt(timer,&tick,true);timerAlarmWrite(timer,8,true);timerAlarmEnable(timer);
#endif
  hello();
}
void loop() {
  static char buffer[100];static unsigned length=0;static bool overflow=false;
  // Bound parsing work so a noisy serial stream cannot starve control updates.
  for (int n=0;n<64 && Serial.available();++n) {
    char c=Serial.read();
    if (c=='\n' || c=='\r') {
      if (overflow) Serial.println("! command too long");
      else if (length) {buffer[length]=0;command(buffer);}
      length=0;overflow=false;
    } else if (length<sizeof(buffer)-1) buffer[length++]=c;
    else overflow=true;
  }
  if (isr_fault) {
    isr_fault=false;stopNow("FAULT host watchdog or rail boundary",true);
  }
  uint32_t now=micros(), delta=now-last_control_us;
  if (armed && delta>=1000) {
    last_control_us=now;
    ++update_count;max_update_us=max(max_update_us,delta);
    if (delta>5000) stopNow("FAULT control timing gap",true);
    else {
      const double dt=delta*1e-6;
      elapsed+=dt;
      reference=ft::sample(config,elapsed,finish_at);
      const auto next=ft::sample(config,elapsed+0.001,finish_at);
      interval_velocity=(next.x-reference.x)/0.001;
      if (fabs(interval_velocity)>ft::max_speed || fabs(reference.x)>0.135001)
        stopNow("FAULT waveform limit",true);
      else if (finish_at>=0 && elapsed>=finish_at+ft::rampSeconds(config)) {
        stopNow("FINISHED");
        centered=labs(position_steps)<=3;
      } else {
        state=finish_at>=0 && elapsed>=finish_at?RAMP_DOWN:
              elapsed<ft::rampSeconds(config)?RAMP_UP:RUNNING;
        setVelocity(interval_velocity);
      }
    }
  }
  if ((uint32_t)(now-last_stream_us)>=20000 && Serial.availableForWrite()>180) {
    last_stream_us=now;
    Serial.printf("F %lu %s %.6f %.7f %.7f %.7f %.7f %.7f %.7f %d\n",
      (unsigned long)millis(),names[state],elapsed,reference.x,reference.v,
      reference.a,reference.j,position_steps/ft::steps_per_m,interval_velocity,(int)centered);
  }
  const uint32_t span=now-stats_start;
  if (span>=1000000 && Serial.availableForWrite()>180) {
    uint32_t ticks,pulses,gap,high,low;
    portENTER_CRITICAL(&pulse_mux);
    ticks=timer_ticks;pulses=pulse_count;gap=max_tick_gap;high=min_high;low=min_low;
    timer_ticks=pulse_count=max_tick_gap=0;min_high=min_low=UINT32_MAX;
    portEXIT_CRITICAL(&pulse_mux);
    const float mhz=ESP.getCpuFreqMHz();
    Serial.printf("D %lu %.1f %lu %.1f %.3f %.3f %.3f %.1f\n",
      (unsigned long)millis(),update_count*1e6/span,(unsigned long)max_update_us,
      ticks*1e6/span,gap/mhz,high==UINT32_MAX?0:high/mhz,
      low==UINT32_MAX?0:low/mhz,pulses*1e6/span);
    update_count=max_update_us=0;stats_start=now;
  }
  delayMicroseconds(50);
}
