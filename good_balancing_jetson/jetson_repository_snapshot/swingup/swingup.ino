// ============================================================================
//  cartpole_swingup_balance_esp32.ino -- 60T / 300 mm travel, centered startup, jerk-limited cart
//
//  PARTS
//    encoder : AS5600 module (12-bit, I2C, 3.3V, 23x23mm)
//    drivers : 3x SparkFun Big Easy Driver (A4988, Rs = 0.11 ohm)
//    cart    : NEMA 17 + GT2 belt
//    height  : 2x SFU1605 ball screw stage (5 mm lead) + NEMA 17
//
//  HARDWARE PREREQUISITES - do these before flashing
//    1. Solder the 3/5V jumper CLOSED on all three Big Easy Drivers.
//       The A4988 needs Vih >= 0.7*VDD. At 5V logic that is 3.5V, and the
//       ESP32 only drives 3.3V. Without the jumper you get intermittent
//       missed steps that look exactly like a controller tuning problem.
//    2. Set driver current with the pot: I = Vref / (8 * 0.11) = Vref / 0.88.
//       The ball-screw motors are 1.5A -> Vref = 1.32V. Measure at TP1 with
//       the motor unplugged.
//    3. Tie the AS5600 module's DIR pin to GND. Floating = undefined count
//       direction.
//    4. 24V on M+ (not the VCC pin - that is an output). The 60T cart default of
//       0.8 m/s corresponds to 400 RPM.
//
//  PINOUT
//    25 cart STEP    26 cart DIR
//    18 Z1   STEP    19 Z1   DIR
//    16 Z2   STEP    17 Z2   DIR  (RX2 / TX2)
//    27 ENABLE for ALL THREE drivers (active low)
//    21 SDA          22 SCL          AS5600 on 3V3, DIR pin -> GND
//    MS1/MS2/MS3 are left UNCONNECTED on all three drivers. The BED pulls
//    them high, which is its 1/16 default: 26.667 steps/mm on a 60T GT2 belt,
//    640 steps/mm on a 5 mm ball-screw lead.
//
//  WHY ACCELERATION IS THE CONTROL INPUT
//    A stepper is a kinematic actuator - you command position, not force. So
//    the plant reduces to
//        theta_ddot = ( g*sin(theta) - a*cos(theta) ) / L_EFF
//        x_ddot     = a
//    with theta measured from UPRIGHT and L_EFF = I_pivot/(m*r_com). Cart
//    mass, belt friction and motor torque never enter the model, as long as
//    you don't lose steps.
//
//  STOP / STARTUP
//    GPIO27 is active-low ENABLE shared by all drivers. Startup, stop and
//    faults disable all drivers. Support the height assembly when disabled.
//    auto, bal, manual, v, zv or on explicitly enable the drivers.
//
//  PROTOCOL (115200 baud, newline terminated). See cartpole.py for the host.
//    host -> board                      board -> host
//      auto            swing-up           T <ms> <mode> <th> <thd> <x> <v>
//      bal             balance only         <a> <e> <z1> <z2> <agc> <dt_us>
//      manual          manual drive       = <key> <value>
//      v <m/s>         cart velocity      # <human readable log>
//      zv <mm/s>       both screws        ! <error>
//      zstop
//      stop            stop pulses and disable all drivers
//      off / on        de-energize / energize
//      home            call this x = 0
//      zhome           call this z = 0
//      zero            save down and opposite upright (hanging, still)
//      upright [count] save current upright or explicit raw count; persists
//      rate <hz>       telemetry rate, 0 = off
//      set <k> <v>     live-tune a parameter
//      get <k> / params / stat / help
// ============================================================================

#include <Arduino.h>
#include <Wire.h>
#include <Preferences.h>
#include "driver/gpio.h"
#include "cart_motion.h"
#include "rail_recovery.h"
#include "spin_recovery.h"
#include "upright_session.h"
#include "swing_controller.h"
#include "encoder_reference.h"
#include "serial_frame.h"
#include <cstdarg>
#include "soc/soc.h"        // REG_WRITE
#include "soc/gpio_reg.h"   // GPIO_OUT_W1TS_REG / GPIO_OUT_W1TC_REG

// ============================== PINS ========================================
#define PIN_CART_STEP   25
#define PIN_CART_DIR    26
#define PIN_Z1_STEP     18
#define PIN_Z1_DIR      19
#define PIN_Z2_STEP     16
#define PIN_Z2_DIR      17
#define PIN_EN_ALL      27        // shared ENABLE, active LOW
#define PIN_SDA         21
#define PIN_SCL         22
#define I2C_HZ          400000    // drop to 100000 if the cable to the cart is
                                  // long or you see enc_err climbing

#define CART_INVERT     0         // v19: reverse cart polarity for upright trial; encoder sign unchanged
#define Z_INVERT        0         // flip if 'zv 5' lowers instead of raises
#define ENC_INVERT      0         // flip if theta goes negative when the pole
                                  // leans toward +x

// One owner (setup/loop) writes UART frames; the control task queues messages.
// Every firmware line is @payload*CRC16, including STOP and parameter replies.
void checkedPrintln(const char *text) {
  size_t length=strlen(text);
  while(length && (text[length-1]=='\n' || text[length-1]=='\r'))--length;
  Serial.printf("@%.*s*%04X\n",(int)length,text,serial_frame::checksum(text,length));
}
void checkedPrintln(const __FlashStringHelper *text) {
  checkedPrintln(reinterpret_cast<const char *>(text));
}
void checkedPrintf(const char *format, ...) {
  char text[256];va_list args;va_start(args,format);
  const int length=vsnprintf(text,sizeof(text),format,args);va_end(args);
  if(length<0 || length>=(int)sizeof(text)){
    checkedPrintln("! serial message too long; discarded");return;
  }
  checkedPrintln(text);
}

// ========================== MECHANICS =======================================
// Big Easy Driver factory default is 1/16 with MS pins unconnected.
// On the 60T GT2 pulley this is 26.667 steps/mm.
// If you ever want more headroom without touching the timer: jumper MS3 to GND
// for 1/8 (13.333 steps/mm), or MS1+MS3 for 1/4 (6.667 steps/mm).
#define CART_MICROSTEPS cart_hardware::microsteps        // MS pins floating -> BED default
#define Z_MICROSTEPS    16        // same
#define MOTOR_STEPS_REV cart_hardware::motor_steps       // 1.8 deg
#define PULLEY_TEETH    cart_hardware::pulley_teeth        // measured hardware: GT2 60T = 120 mm/rev
#define BELT_PITCH_MM   cart_hardware::belt_pitch_mm
#define Z_LEAD_MM       5.0f      // SFU1605

static const float CART_STEPS_PER_M =
    cart_hardware::steps_per_m;
static const float Z_STEPS_PER_MM =
    (MOTOR_STEPS_REV * Z_MICROSTEPS) / Z_LEAD_MM;

#define GRAV            9.81f
#define CTRL_HZ         1000
// A 7 us timer period gives 142857.14 ticks/s and 71428.57 steps/s.
// At 60T / 1:16, 0.8 m/s needs 21333.333 steps/s; DDS uses this same period.
#define ISR_HZ          cart_hardware::isr_hz
static const float DT = 1.0f / CTRL_HZ;

// Hard ceiling on cart speed, derived rather than guessed. Ask for more than
// this and the pulse generator clamps while the controller keeps believing the
// number it was given - so we clamp loudly at the point of entry instead.
static const float VMAX_CEIL = cart_hardware::max_speed;

#define MANUAL_TIMEOUT_MS 250     // 'v' command watchdog: no news = stop

// ===================== LIVE-TUNABLE PARAMETERS ==============================
// Change any of these at runtime with  set <name> <value>  - no reflash.
// Current arm: 125 mm / 11.05 g plus two 5.85 g end weights.
// L_eff=0.124 m from 20 low-angle cycles in the pre-175 mm captures.
swing_control::Parameters controller;
float &p_leff = controller.leff;
float &p_pw = controller.pw;
float &p_pz = controller.pz;
float &p_pc1 = controller.pc1;
float &p_pc2 = controller.pc2;
float &p_vmax = controller.vmax;
float &p_vmax_s = controller.vmax_s;
float &p_vmax_b = controller.vmax_b;
float &p_amax_s = controller.amax_s;
float &p_amax_b = controller.amax_b;
float &p_jmax = controller.jmax;
float &p_amax_m = controller.amax_m;
float &p_jmax_m = controller.jmax_m;
float &p_ke = controller.ke;
float &p_kpx = controller.kpx;
float &p_kdx = controller.kdx;
float &p_phase_soft = controller.phase_soft;
float &p_catch_a = controller.catch_a;
float &p_catch_r = controller.catch_r;
float &p_giveup = controller.giveup;
float &p_rail = controller.rail;
float &p_bw = controller.bw;
float &p_vman = controller.vman;
float p_zvmax   = 2.0f;    // mm/s
float p_zamax   = 20.0f;   // mm/s^2
float p_ztravel = 100.0f;  // mm of usable screw travel above z=0

// state-feedback gains, computed from the poles above: a = -(K.[th,thd,x,v])
float K1, K2, K3, K4;

struct Param { const char *name; float *ptr; bool recalc; };
static const Param PARAMS[] = {
  {"spin_trip_rad_s",&controller.spin_trip_rad_s,false},
  {"spin_resume_rad_s",&controller.spin_resume_rad_s,false},
  {"bal_pw",&controller.bal_pw,false},
  {"leff",&p_leff,true},   {"pw",&p_pw,true},      {"pz",&p_pz,true},
  {"pc1",&p_pc1,true},     {"pc2",&p_pc2,true},
  {"vmax_s",&p_vmax_s,false},{"vmax_b",&p_vmax_b,false},
  {"approach_v",&controller.approach_v,false},{"catch_v",&controller.catch_v,false},
  {"approach_angle",&controller.approach_angle,false},{"catch_da",&controller.catch_da,false},
  {"vmax",&p_vmax,false},  {"amax_s",&p_amax_s,false},{"amax_b",&p_amax_b,false},
  {"amax_m",&p_amax_m,false},{"jmax_m",&p_jmax_m,false},
  {"phase_soft",&p_phase_soft,false},{"jmax",&p_jmax,false},  {"ke",&p_ke,false},      {"kpx",&p_kpx,false},   {"kdx",&p_kdx,false},
  {"catch_a",&p_catch_a,false},{"catch_r",&p_catch_r,false},
  {"giveup",&p_giveup,false},{"rail",&p_rail,false},{"bw",&p_bw,false},
  {"vman",&p_vman,false},  {"zvmax",&p_zvmax,false},{"zamax",&p_zamax,false},
  {"ztravel",&p_ztravel,false},
  {"k1",&K1,false}, {"k2",&K2,false}, {"k3",&K3,false}, {"k4",&K4,false},
};
static const int N_PARAMS = sizeof(PARAMS)/sizeof(PARAMS[0]);

// ==================== STEP PULSE GENERATOR (3 axes) =========================
// Direct digital synthesis: a 32-bit phase accumulator per axis, ticked at
// ISR_HZ. Accumulator overflow == one step. Exact average rate, exact step
// count, no drift. No floating point in the ISR - the ESP32 FPU is not safe
// to touch from an interrupt under FreeRTOS.

enum { AX_CART = 0, AX_Z1, AX_Z2, N_AX };

DRAM_ATTR static const uint32_t AX_MASK[N_AX] = {
  (1UL << PIN_CART_STEP), (1UL << PIN_Z1_STEP), (1UL << PIN_Z2_STEP)
};
DRAM_ATTR static const uint32_t ALL_STEP_MASK =
  (1UL<<PIN_CART_STEP) | (1UL<<PIN_Z1_STEP) | (1UL<<PIN_Z2_STEP);

volatile bool g_energized = false;
volatile uint32_t ax_inc[N_AX] = {0,0,0};
volatile int32_t  ax_pos[N_AX] = {0,0,0};
volatile int8_t   ax_dir[N_AX] = {1,1,1};
DRAM_ATTR static uint32_t ax_acc[N_AX] = {0,0,0};

hw_timer_t *g_timer = nullptr;

// W1TS / W1TC are "write 1 to set" / "write 1 to clear" registers: writing a
// mask flips exactly those pins and leaves every other pin alone, with no
// read-modify-write and no chance of racing the main loop over a shared port.
// That is why all three STEP pins must live in GPIO 0-31 - pins 32+ are a
// different register pair (GPIO_OUT1_W1TS_REG).
void IRAM_ATTR onStepTimer() {
  REG_WRITE(GPIO_OUT_W1TC_REG, ALL_STEP_MASK);   // end pulses started last tick
  if (!g_energized) return;
  uint32_t set = 0;
  for (int i = 0; i < N_AX; i++) {
    uint32_t inc = ax_inc[i];
    if (!inc) continue;
    uint32_t prev = ax_acc[i];
    ax_acc[i] = prev + inc;
    if (ax_acc[i] < prev) { ax_pos[i] += ax_dir[i]; set |= AX_MASK[i]; }
  }
  if (set) REG_WRITE(GPIO_OUT_W1TS_REG, set);
}

static const uint8_t DIR_PIN[N_AX] = { PIN_CART_DIR, PIN_Z1_DIR, PIN_Z2_DIR };

void axSetRate(int i, float steps_per_sec, bool invert) {
  if (!g_energized) { ax_inc[i] = 0; return; }
  int8_t d = (steps_per_sec >= 0.0f) ? 1 : -1;
  // Write DIR even on the first positive command: ax_dir starts at +1,
  // but GPIO starts LOW. With non-inverted polarity the required level is HIGH.
  ax_dir[i] = d; // Position counts retain the logical command sign.
  const bool high = (d > 0) != invert;
  digitalWrite(DIR_PIN[i], high ? HIGH : LOW);
  float r = fabsf(steps_per_sec);
  const float RMAX = ISR_HZ * 0.5f;
  if (r > RMAX) r = RMAX;
  ax_inc[i] = (uint32_t)((double)r * 4294967296.0 / (double)ISR_HZ);
}

void steppersInit() {
  const uint8_t outs[] = { PIN_CART_STEP, PIN_CART_DIR, PIN_Z1_STEP, PIN_Z1_DIR,
                           PIN_Z2_STEP, PIN_Z2_DIR };
  for (uint8_t p : outs) { pinMode(p, OUTPUT); digitalWrite(p, LOW); }
  // ENABLE was already driven HIGH at the first instruction in setup().

  // Microstepping is whatever the drivers default to (1/16). MS1/MS2/MS3 are
  // deliberately not touched, so GPIO 32 / 33 are free for limit
  // switches or anything else you add later.

#if ESP_ARDUINO_VERSION_MAJOR >= 3
  g_timer = timerBegin(1000000);
  timerAttachInterrupt(g_timer, &onStepTimer);
  timerAlarm(g_timer, cart_hardware::step_timer_period_us, true, 0);
#else
  g_timer = timerBegin(0, 80, true);
  timerAttachInterrupt(g_timer, &onStepTimer, true);
  timerAlarmWrite(g_timer, cart_hardware::step_timer_period_us, true);
  timerAlarmEnable(g_timer);
#endif
}

void energize(bool on) {
  g_energized = on;
  digitalWrite(PIN_EN_ALL, on ? LOW : HIGH);
}

// ============================== AS5600 ======================================
#define AS5600_ADDR   0x36
#define REG_STATUS    0x0B
#define REG_RAWANGLE  0x0C
#define REG_CONF_HI   0x07
#define REG_AGC       0x1A
#define ENC_CPR       4096

static int32_t enc_last_raw = 0, enc_ticks = 0, enc_zero = 0;
volatile int32_t enc_upright_raw = encoder_reference::upright_raw;
volatile bool reference_saved = false;
void loadEncoderReference() {
  Preferences storage;
  if(storage.begin("cartpole",true)){
    const uint16_t raw=storage.getUShort("upright",65535);storage.end();
    if(raw<ENC_CPR){enc_upright_raw=raw;reference_saved=true;}
  }
}
volatile uint8_t enc_agc = 0;
volatile uint8_t enc_status = 0;
volatile uint32_t enc_errors = 0;

bool as5600Write8(uint8_t reg, uint8_t val) {
  Wire.beginTransmission(AS5600_ADDR);
  Wire.write(reg); Wire.write(val);
  return Wire.endTransmission() == 0;
}
int16_t as5600Read8(uint8_t reg) {
  Wire.beginTransmission(AS5600_ADDR);
  Wire.write(reg);
  if (Wire.endTransmission(false) != 0) return -1;
  if (Wire.requestFrom((uint8_t)AS5600_ADDR,(uint8_t)1) != 1) return -1;
  return Wire.read();
}

// The single most important line in this file for control performance:
// the AS5600's Slow Filter defaults to 16x, which is 2.2 ms of propagation
// delay. That is pure phase lag in a 1 kHz balance loop and it hard-caps how
// stiff you can make the controller. SF=2x drops it to 0.286 ms. Costs a
// little LSB noise, which the estimator cleans up anyway. CONF is volatile,
// so this has to be rewritten every boot.
//   CONF high byte: [--][WD][FTH2:0][SF1:0]
//   SF: 00=16x(2.2ms) 01=8x(1.1ms) 10=4x(0.55ms) 11=2x(0.286ms)
//   FTH=000 -> slow filter only
bool as5600FastFilter() {
  bool ok  = as5600Write8(REG_CONF_HI, 0b00000011);   // FTH=000, SF=2x
  ok &= as5600Write8(REG_CONF_HI + 1, 0b00000000);    // PM=NOM, HYST off
  return ok;
}

// ---------------------------------------------------------------------------
//  SINGLE-OWNER I2C RULE
//  Everything from here down touches Wire, and exactly one context may do so:
//  setup() owns the bus before the control task exists, the control task owns
//  it exclusively afterwards. loop() must NEVER touch Wire - serial commands
//  set request flags and read cached values instead.
//
//  Why: Arduino's TwoWire takes its lock inside beginTransmission and drops it
//  at endTransmission. A register read is endTransmission(false) followed by a
//  separate requestFrom, so the lock is released in the middle of a repeated
//  start. A second caller slips into that gap and both transactions come back
//  garbage or NACK. That is precisely why 'mag' failed here while the
//  single-threaded scanner sketch read the same encoder fine.
// ---------------------------------------------------------------------------

volatile bool     enc_ok = false;
volatile uint32_t enc_recoveries = 0;
static   uint32_t enc_consec_err = 0;

void encBusReinit() {
  Wire.end();
  delay(2);
  Wire.begin(PIN_SDA, PIN_SCL, I2C_HZ);
  Wire.setTimeOut(50);
  as5600FastFilter();          // CONF is volatile, re-apply after a re-init
  enc_recoveries++;
}

int32_t encReadRaw() {
  Wire.beginTransmission(AS5600_ADDR);
  Wire.write(REG_RAWANGLE);
  if (Wire.endTransmission(false) != 0) { enc_errors++; return -1; }
  if (Wire.requestFrom((uint8_t)AS5600_ADDR,(uint8_t)2) != 2) { enc_errors++; return -1; }
  uint16_t hi = Wire.read(), lo = Wire.read();
  return ((hi << 8) | lo) & 0x0FFF;
}

void encUpdate() {
  int32_t raw = encReadRaw();
  if (raw < 0) {
    // Hold the last value through a one-off glitch, but a sustained run of
    // failures means the bus is wedged (a stretched clock, a brown-out on the
    // module). Rebuild it rather than running the controller blind.
    if (++enc_consec_err >= 50) { enc_consec_err = 0; encBusReinit(); }
    enc_ok = false;
    return;
  }
  enc_consec_err = 0;
  enc_ok = true;
  int32_t d = raw - enc_last_raw;
  if (d >  ENC_CPR/2) d -= ENC_CPR;
  if (d < -ENC_CPR/2) d += ENC_CPR;
  enc_ticks += d;
  enc_last_raw = raw;
}

int32_t encZeroRaw() {
  // enc_ticks is relative to the first sample, not the sensor absolute zero.
  const int32_t raw_zero=enc_last_raw-(enc_ticks-enc_zero)%ENC_CPR;
  return (raw_zero%ENC_CPR+ENC_CPR)%ENC_CPR;
}

inline float wrapPi(float a) {
  while (a >  (float)M_PI) a -= 2.0f*(float)M_PI;
  while (a < -(float)M_PI) a += 2.0f*(float)M_PI;
  return a;
}

// theta: 0 = upright, +-pi = hanging, positive = pole top leaning toward +x
float encTheta() {
  // One live reference for the observer, capture gate, balance and telemetry.
  return encoder_reference::angle_from_upright(enc_last_raw, ENC_INVERT != 0, enc_upright_raw);
}

// Magnet diagnostics. The reviews on these modules are full of people who got
// the wrong magnet - check this before blaming the controller.
//   STATUS bit5 MD = detected, bit4 ML = too weak, bit3 MH = too strong
//   AGC should sit mid-range (~64 of 0..128 at 3.3V). Railed = bad air gap.
// Bus access - control task (or setup) only.
void encDiagRead() {
  int16_t st = as5600Read8(REG_STATUS);
  int16_t ag = as5600Read8(REG_AGC);
  if (st >= 0) enc_status = st;
  if (ag >= 0) enc_agc = ag;
}

// Printing only - safe from loop(), reads the cached copies.
void encPrintMagnet() {
  uint8_t st = enc_status, ag = enc_agc;
  if (!enc_ok) checkedPrintln(F("! encoder not reading - values below are stale"));
  checkedPrintf("# AS5600 status=0x%02X agc=%d  %s%s%s\n", st, ag,
                (st & 0x20) ? "magnet-ok " : "NO-MAGNET ",
                (st & 0x10) ? "too-weak "  : "",
                (st & 0x08) ? "too-strong" : "");
  if (ag >= 120)     checkedPrintln(F("# AGC at max gain - magnet too far, move it CLOSER"));
  else if (ag <= 8)  checkedPrintln(F("# AGC at min gain - magnet too close"));
  checkedPrintf("# i2c errors=%lu  bus recoveries=%lu\n",
                (unsigned long)enc_errors, (unsigned long)enc_recoveries);
}

// ========================== CONTROLLER ======================================
enum Mode { M_IDLE=0, M_MANUAL, M_SWINGUP, M_BALANCE, M_FAULT, M_RAIL_BRAKE, M_RAIL_RETURN, M_SPIN_BRAKE, M_SPIN_CENTER, M_SPIN_WAIT, M_BAL_BRAKE, M_BAL_CENTER };
volatile Mode mode = M_IDLE;
const char *MODE_NAME[] = {"IDLE","MANUAL","SWINGUP","BALANCE","FAULT","RAIL_BRAKE","RAIL_RETURN","SPIN_BRAKE","SPIN_CENTER","SPIN_WAIT","BAL_BRAKE","BAL_CENTER"};

volatile float th=0, thd=0, xc=0, vc=0, acc_cmd=0, energy_n=-1;
volatile float z_mm=0;
volatile uint32_t loop_us=0;
static float th_hat=0, thd_hat=0;
volatile bool req_estimator_reset=false;
static swing_control::PumpState pump;
static swing_control::ResponseWatch response_watch;
static int32_t home_steps=0, zhome_steps=0;

// Cross-context requests. loop() may only SET these; the control task is the
// only thing allowed to act on them, because it is the sole owner of the I2C
// bus once it exists. This is the whole fix for 'mag' returning nothing.
volatile bool req_diag = false, req_encoder = false;
// 0 none, 1 hanging capture, 2 upright capture, 3 explicit upright count.
volatile int calibration_request=0;
volatile int32_t requested_upright_raw=0;
volatile bool reference_save_pending=false;
constexpr uint32_t HOST_TIMEOUT_MS=1500;
volatile uint32_t last_host_command_ms=0;
struct ControlMessage {char text[160];};
QueueHandle_t control_messages=nullptr;
volatile uint32_t dropped_control_messages=0;
void controlLog(const char *text){
  ControlMessage message;snprintf(message.text,sizeof(message.text),"%s",text);
  if(!control_messages || xQueueSend(control_messages,&message,0)!=pdTRUE)++dropped_control_messages;
}
void flushControlMessages(){
  ControlMessage message;
  while(control_messages && xQueueReceive(control_messages,&message,0)==pdTRUE)checkedPrintln(message.text);
}
volatile bool diag_done = false;
static volatile bool zeroing = false;
static bool capture_upright=false;
static encoder_reference::StillCapture reference_capture;
static uint32_t zero_t0=0;
bool encoderCalibrationBusy(){return calibration_request!=0 || zeroing || reference_save_pending;}
void cancelEncoderCalibration(){calibration_request=0;zeroing=false;}
void applyEncoderReference(int32_t raw){
  // The pending request or zeroing flag keeps motion blocked during this update.
  reference_saved=false;
  enc_upright_raw=encoder_reference::normalize(raw);
  enc_zero=enc_ticks+encoder_reference::difference(encoder_reference::opposite(enc_upright_raw),enc_last_raw);
  th=th_hat=encTheta();thd=thd_hat=0;energy_n=cosf(th);
  pump.reset();response_watch.armed=false;
  char message[120];snprintf(message,sizeof(message),"# upright reference applied: %ld counts, theta=%.2fdeg; saving",(long)enc_upright_raw,th*180/M_PI);
  controlLog(message);
  reference_save_pending=true; // Publish only after the complete reference is ready.
}
// Non-real-time persistence. All motion commands remain blocked until finished.
void saveEncoderReference(){
  if(!reference_save_pending)return;
  Preferences storage;bool ok=false;
  if(storage.begin("cartpole",false)){
    ok=storage.putUShort("upright",(uint16_t)enc_upright_raw)==sizeof(uint16_t);storage.end();
  }
  reference_saved=ok;
  checkedPrintf("= encoder_upright_raw %ld\n",(long)enc_upright_raw);
  checkedPrintf("= encoder_reference_saved %d\n",(int)ok);
  checkedPrintln(ok?F("# encoder reference saved; drivers disabled. Ready for a new motion command."):
                    F("! encoder reference active but SAVE FAILED; it will not survive reset"));
  reference_save_pending=false;
}

static float v_manual=0;
static uint32_t v_manual_deadline=0;
static float zv_target=0, zv_now=0;
static int cart_brake_direction=0;
static rail_recovery::State rail_recovery_state;
static bool recovery_was_manual=false;
static spin_recovery::State spin_recovery_state;
static upright_session::Return upright_return;
static bool upright_only=false;
volatile bool req_balance=false;
bool inUprightReturn(){return mode==M_BAL_BRAKE || mode==M_BAL_CENTER;}
bool inSpinRecovery(){return mode==M_SPIN_BRAKE || mode==M_SPIN_CENTER || mode==M_SPIN_WAIT;}

// Exact pole placement. With a = -(K1*th + K2*thd + K3*x + K4*v) the closed
// loop characteristic polynomial of this plant is
//   s^4 + (K4 - K2/L)s^3 + (K3 - g/L - K1/L)s^2 - (g*K4/L)s - (g*K3/L)
// Matching that to (s^2+2*z*w*s+w^2)(s-pc1)(s-pc2) inverts in closed form.
void computeGains() {
  const auto k = swing_control::gains(controller);
  K1=k.k1; K2=k.k2; K3=k.k3; K4=k.k4;
}

// Alpha-beta tracking differentiator. Differencing a 12-bit encoder at 1 kHz
// would give ~1.5 rad/s of quantisation hash; this smooths it and handles the
// +-pi wrap without a glitch.
void estimate(float theta_meas) {
  if(req_estimator_reset){
    swing_control::resetEstimate(theta_meas,th_hat,thd_hat);
    req_estimator_reset=false;
  }
  swing_control::estimate(theta_meas, p_bw, DT, th_hat, thd_hat);
  th = theta_meas;  // telemetry retains the raw encoder angle
  thd = thd_hat;
}

swing_control::Gains currentGains() {
  if(upright_only)return swing_control::uprightGains(controller);
  return {K1,K2,K3,K4};
}
float balanceAccel() {
  return swing_control::balance(currentGains(), th_hat, thd, xc, vc);
}
float swingAccel() {
  energy_n = swing_control::energy(th_hat, thd, p_leff);
  const auto feedback=currentGains();
  return swing_control::swing(controller, pump, th_hat, thd, xc, vc, DT, acc_cmd, &feedback);
}

void eStop() {
  energize(false); // Disable immediately; ISR also suppresses pulses/counts.
  cancelEncoderCalibration();
  mode = M_IDLE;
  req_balance=false; upright_only=false; upright_return.reset();
  cart_brake_direction = 0;
  rail_recovery_state.reset(); recovery_was_manual=false;
  spin_recovery_state.reset();
  pump.reset(); response_watch.armed = false;
  v_manual = 0; vc = 0; acc_cmd = 0; zv_target = 0; zv_now = 0;
  for (int i=0;i<N_AX;i++) ax_inc[i] = 0;
  REG_WRITE(GPIO_OUT_W1TC_REG, ALL_STEP_MASK);
}

void beginUprightReturn(const char *reason) {
  upright_return.begin(micros());
  rail_recovery_state.reset(); spin_recovery_state.reset();
  response_watch.armed=false; pump.reset(); v_manual=0; zv_target=0;
  mode=M_BAL_BRAKE;
  controlLog(reason);
}

void beginRailRecovery() {
  if(upright_only){beginUprightReturn("# upright trial rail protection -> BAL_BRAKE; return to center and stop");return;}
  if (mode==M_RAIL_BRAKE || mode==M_RAIL_RETURN) return;
  recovery_was_manual = mode==M_MANUAL;
  rail_recovery_state.begin(xc,p_rail,cart_brake_direction);
  // Keep the startup response watch active through recovery.
  mode=M_RAIL_BRAKE;
  controlLog("# rail recovery -> BRAKING; pendulum control paused");
}

void beginSpinRecovery() {
  spin_recovery_state.begin(micros());
  rail_recovery_state.reset(); recovery_was_manual=false;
  response_watch.armed=false; pump.reset();
  v_manual=0; zv_target=0;
  mode=M_SPIN_BRAKE;
  char message[150];snprintf(message,sizeof(message),"# pendulum |theta_dot| >%.2f rad/s -> SPIN_BRAKE; center and wait below %.2f rad/s",controller.spin_trip_rad_s,controller.spin_resume_rad_s);
  controlLog(message);
}

void controlTask(void *) {
  TickType_t wake = xTaskGetTickCount();
  for (;;) {
    vTaskDelayUntil(&wake, pdMS_TO_TICKS(1000/CTRL_HZ));
    uint32_t t_start = micros();

    encUpdate();
    if(((mode!=M_IDLE && mode!=M_FAULT) || zv_target!=0 || zv_now!=0) &&
        uint32_t(millis()-last_host_command_ms)>HOST_TIMEOUT_MS){
      eStop();mode=M_FAULT;controlLog("! host link timeout -> FAULT; drivers disabled");
    }
    if(req_encoder){
      req_encoder=false;encDiagRead();
      char sample[160];
      snprintf(sample,sizeof(sample),"E %lu %ld %ld %u %u %lu %d %d",
        (unsigned long)millis(),(long)enc_last_raw,(long)encZeroRaw(),
        (unsigned)enc_agc,(unsigned)enc_status,(unsigned long)enc_errors,(int)enc_ok,(int)g_energized);
      controlLog(sample);
    }

    // Never continue closed-loop control on stale angle data. A single failed
    // transaction is held over; five consecutive failures (~5 ms) latch a
    // fault and stop pulse generation.
    if (mode != M_IDLE && mode != M_FAULT && enc_consec_err >= 5) {
      controlLog("! encoder stale -> FAULT");
      eStop(); mode = M_FAULT;
    }

    // Serve bus requests here, where we already own Wire.
    if (req_diag) { req_diag = false; encDiagRead(); diag_done = true; }
    if(calibration_request){
      const int request=calibration_request;
      if(mode!=M_IDLE || g_energized){
        calibration_request=0;controlLog("! encoder reference rejected: stop first");
      }else if(request==3){
        if(enc_ok && enc_consec_err==0)applyEncoderReference(requested_upright_raw);
        else controlLog("! encoder reference rejected: no fresh encoder reading");
        calibration_request=0;
      }else{
        zeroing=true;capture_upright=request==2;reference_capture.reset();zero_t0=millis();
        calibration_request=0;
      }
    }
    if(zeroing){
      if(reference_capture.add(enc_last_raw,enc_ok && enc_consec_err==0)){
        const int32_t raw=reference_capture.mean();
        applyEncoderReference(capture_upright?raw:encoder_reference::opposite(raw));
        zeroing=false;
      }else if(millis()-zero_t0>5000){
        zeroing=false;controlLog("! calibration FAILED: need 0.4s still with fresh encoder readings; retry upright or zero");
      }
    }

    estimate(encTheta());
    xc = (ax_pos[AX_CART] - home_steps) / CART_STEPS_PER_M;
    z_mm = (ax_pos[AX_Z1] - zhome_steps) / Z_STEPS_PER_MM;

    float rail_hard = p_rail - 0.01f;
    if (mode != M_IDLE && mode != M_FAULT && fabsf(xc) > rail_hard) {
      controlLog("! rail limit -> FAULT");
      mode = M_FAULT; eStop(); mode = M_FAULT;
    }

    // Consume the one-shot start in the control task using fresh sensor state.
    // Rejection never arms a future automatic capture.
    if(req_balance){
      req_balance=false;
      if(mode!=M_IDLE || encoderCalibrationBusy() || !upright_session::canStart(th,th_hat,thd,xc,vc,acc_cmd,enc_ok && enc_consec_err==0)){
        char reason[160];snprintf(reason,sizeof(reason),"! bal rejected: angle=%.2fdeg estimate=%.2fdeg rate=%.2f x=%.1fmm; need +/-10deg, rate<=1, x<=30mm, stopped + healthy",th*180/M_PI,th_hat*180/M_PI,thd,xc*1000);
        controlLog(reason);
      }else{
        upright_only=true; energize(true); mode=M_BALANCE;
        controlLog("# BALANCE");
        controlLog("# upright-only; >50deg -> brake, center, disable; no automatic restart");
      }
    }
    if(upright_only && mode==M_BALANCE && upright_session::fallen(th))
      beginUprightReturn("# upright fall >50deg -> BAL_BRAKE; return to center and stop");

    const bool automatic=mode==M_SWINGUP || mode==M_BALANCE ||
        ((mode==M_RAIL_BRAKE || mode==M_RAIL_RETURN) && !recovery_was_manual);
    if(!upright_only && automatic && enc_ok && spin_recovery::trigger(thd,controller.spin_trip_rad_s))beginSpinRecovery();

    if ((mode==M_MANUAL || mode==M_SWINGUP || mode==M_BALANCE) &&
        rail_recovery_state.atEdge(xc,p_rail)) beginRailRecovery();

    float a = 0.0f;
    switch (mode) {
      case M_MANUAL:
        if ((int32_t)(millis() - v_manual_deadline) >= 0) v_manual = 0;
        a = cart_motion::velocityAccel(vc, v_manual, p_amax_m, p_jmax_m, DT);
        break;

      case M_SWINGUP:
        a = swingAccel();
        if (swing_control::canCapture(controller, currentGains(), th_hat, thd, xc, vc, acc_cmd)) {
          mode = M_BALANCE; response_watch.armed = false;
          a = constrain(balanceAccel(), -p_amax_b, p_amax_b);
          controlLog("# caught -> BALANCE");
        }
        break;

      case M_BALANCE: {
        float Eup = GRAV/p_leff;
        energy_n = (0.5f*thd*thd + Eup*cosf(th))/Eup;
        a = constrain(balanceAccel(), -p_amax_b, p_amax_b);
        if (!upright_only && fabsf(th_hat) > p_giveup) {
          mode = M_SWINGUP;
          controlLog("# lost it -> SWINGUP");
        }
        break;
      }

      case M_RAIL_BRAKE:
      case M_RAIL_RETURN: {
        cart_motion::State current;
        current.velocity=vc; current.acceleration=acc_cmd;
        current.brake_direction=cart_brake_direction;
        const float recovery_amax=recovery_was_manual?p_amax_m:max(p_amax_s,p_amax_b);
        const float recovery_jerk=recovery_was_manual?p_jmax_m:p_jmax;
        if(rail_recovery_state.update(xc,current,DT)) {
          char handoff[96];snprintf(handoff,sizeof(handoff),"# rail handoff x=%.5f v=%.4f a=%.3f",xc,vc,acc_cmd);
          controlLog(handoff);
          if(recovery_was_manual) {
            recovery_was_manual=false; mode=M_MANUAL;
            v_manual=0; v_manual_deadline=millis();
            a=cart_motion::velocityAccel(vc,0,p_amax_m,p_jmax_m,DT);
            controlLog("# back inside operating range -> MANUAL");
            break;
          }
          pump.reset();
          mode=M_SWINGUP;
          a=swingAccel();
          controlLog("# back inside operating range -> SWINGUP");
        } else if(rail_recovery_state.timedOut()) {
          eStop(); mode=M_FAULT;
          controlLog("! rail recovery timeout -> FAULT");
          goto zaxis;
        } else {
          if(mode==M_RAIL_BRAKE && rail_recovery_state.phase==rail_recovery::RETURNING) {
            mode=M_RAIL_RETURN; controlLog("# rail speed and acceleration settled -> RETURN_INSIDE");
          }
          a=rail_recovery_state.demand(xc,current,p_vmax,recovery_amax,recovery_jerk,DT);
        }
        break;
      }

      case M_BAL_BRAKE:
      case M_BAL_CENTER: {
        cart_motion::State current;
        current.velocity=vc;current.acceleration=acc_cmd;current.brake_direction=cart_brake_direction;
        const uint32_t now=micros();
        if(upright_return.update(xc,current,now)){
          eStop();controlLog("# upright trial centered -> STOP; drivers disabled; send bal for another trial");
          goto zaxis;
        }
        if(upright_return.timedOut(now)){
          eStop();mode=M_FAULT;controlLog("! upright return timeout -> FAULT; drivers disabled");
          goto zaxis;
        }
        mode=upright_return.braking()?M_BAL_BRAKE:M_BAL_CENTER;
        a=upright_return.demand(xc,current,p_vmax,max(p_amax_s,p_amax_b),p_jmax,DT);
        break;
      }

      case M_SPIN_BRAKE:
      case M_SPIN_CENTER:
      case M_SPIN_WAIT: {
        cart_motion::State current;
        current.velocity=vc;current.acceleration=acc_cmd;current.brake_direction=cart_brake_direction;
        const uint32_t now=micros();
        const auto previous=spin_recovery_state.phase;
        if(spin_recovery_state.update(xc,current,thd,enc_ok,now,controller.spin_resume_rad_s)) {
          pump.reset();response_watch.reset(th);mode=M_SWINGUP;
          a=swingAccel();
          char message[100];snprintf(message,sizeof(message),"# centered and |theta_dot| <%.2f rad/s -> SWINGUP",controller.spin_resume_rad_s);
          controlLog(message);
        } else if(spin_recovery_state.timedOut(now)) {
          eStop();mode=M_FAULT;
          controlLog("! spin recovery centering timeout -> FAULT");
          goto zaxis;
        } else {
          mode=spin_recovery_state.phase==spin_recovery::BRAKING?M_SPIN_BRAKE:
               spin_recovery_state.phase==spin_recovery::CENTERING?M_SPIN_CENTER:M_SPIN_WAIT;
          if(previous!=spin_recovery_state.phase){char notice[64];snprintf(notice,sizeof(notice),"# spin recovery -> %s",MODE_NAME[mode]);controlLog(notice);}
          a=spin_recovery_state.demand(xc,current,p_vmax,max(p_amax_s,p_amax_b),p_jmax,DT);
        }
        break;
      }

      default:                                   // IDLE / FAULT
        vc = 0; acc_cmd = 0; cart_brake_direction = 0;
        axSetRate(AX_CART, 0, CART_INVERT);
        goto zaxis;
    }

    {
      cart_motion::State motion;
      motion.velocity = vc;
      motion.acceleration = acc_cmd;
      motion.brake_direction = cart_brake_direction;
      const bool use_manual_limits=mode==M_MANUAL ||
        ((mode==M_RAIL_BRAKE || mode==M_RAIL_RETURN) && recovery_was_manual);
      const float drive_amax = use_manual_limits ? p_amax_m :
                               ((mode==M_RAIL_BRAKE || mode==M_RAIL_RETURN || inSpinRecovery() || inUprightReturn()) ? max(p_amax_s,p_amax_b) :
                                (mode == M_SWINGUP ? p_amax_s : p_amax_b));
      const float brake_amax = use_manual_limits ? p_amax_m : max(p_amax_s, p_amax_b);
      const float jerk = use_manual_limits ? p_jmax_m : p_jmax;
      const float mode_speed=use_manual_limits?p_vmax:
          mode==M_SWINGUP?swing_control::speedLimit(controller,false):
          mode==M_BALANCE?swing_control::speedLimit(controller,true):
          swing_control::recoverySpeedLimit(controller);
      // A lower mode cap is approached through jerk limiting; only the hard
      // ceiling below is a fault. Never clip velocity on a mode transition.
      motion = cart_motion::advance(motion, xc, a, mode_speed, drive_amax,
                                    brake_amax, jerk, p_rail, DT);
      vc = motion.velocity;
      acc_cmd = motion.acceleration;
      cart_brake_direction = motion.brake_direction;
      if (cart_brake_direction && (mode==M_MANUAL || mode==M_SWINGUP || mode==M_BALANCE))
        beginRailRecovery();
      // Only exceptional stops bypass the jerk ramp. Never keep integrating
      // a speed the pulse generator cannot produce.
      if (fabsf(vc) > p_vmax + 0.002f) {
        controlLog("! motion speed limit -> FAULT");
        eStop(); mode = M_FAULT;
      }
      if ((mode==M_SWINGUP || ((mode==M_RAIL_BRAKE || mode==M_RAIL_RETURN) && !recovery_was_manual)) && response_watch.fault(th, vc, DT)) {
        controlLog("! no pendulum response to cart command -> FAULT; check motor tracking and recenter");
        eStop(); mode = M_FAULT;
      }
      axSetRate(AX_CART, vc*CART_STEPS_PER_M, CART_INVERT);
    }

  zaxis:
    {   // both screws get the identical command so the rail cannot rack
      float dv = p_zamax*DT;
      if      (zv_now < zv_target - dv) zv_now += dv;
      else if (zv_now > zv_target + dv) zv_now -= dv;
      else                              zv_now  = zv_target;
      if (z_mm >= p_ztravel && zv_now > 0) zv_now = 0;
      if (z_mm <= 0.0f      && zv_now < 0) zv_now = 0;
      float zr = zv_now*Z_STEPS_PER_MM;
      axSetRate(AX_Z1, zr, Z_INVERT);
      axSetRate(AX_Z2, zr, Z_INVERT);
    }

    loop_us = micros() - t_start;
  }
}

// ============================= PROTOCOL =====================================
static uint16_t tele_hz = 25;

void printParams() {
  for (int i=0;i<N_PARAMS;i++) checkedPrintf("= %s %.5f\n", PARAMS[i].name, *PARAMS[i].ptr);
  checkedPrintln(F("# firmware swingup-125mm-60t-v34"));
  checkedPrintf("# pins cart STEP=%d DIR=%d; Z1 STEP=%d DIR=%d; Z2 STEP=%d DIR=%d\n",
                PIN_CART_STEP, PIN_CART_DIR, PIN_Z1_STEP, PIN_Z1_DIR, PIN_Z2_STEP, PIN_Z2_DIR);
  checkedPrintf("= cart_steps_per_m %.2f\n", CART_STEPS_PER_M);
  checkedPrintf("= pulley_teeth %d\n", PULLEY_TEETH);
  checkedPrintf("= cart_mm_per_rev %.2f\n", cart_hardware::mm_per_rev);
  checkedPrintf("= z_steps_per_mm %.2f\n", Z_STEPS_PER_MM);
  checkedPrintf("= vmax_ceiling %.5f\n", VMAX_CEIL);
  checkedPrintf("= rpm_ceiling %.3f\n", cart_hardware::max_rpm);
  checkedPrintf("= host_timeout_ms %lu\n",(unsigned long)HOST_TIMEOUT_MS);
  checkedPrintln(F("# vmax is the hard ceiling; vmax_s/vmax_b select swing/balance limits. Capture speed is catch_v."));
  checkedPrintln(F("= encoder_snapshot 1"));
  checkedPrintln(F("= serial_crc16 1"));
  checkedPrintf("= cart_invert %d\n",CART_INVERT);
  checkedPrintf("= encoder_invert %d\n",ENC_INVERT);
  checkedPrintf("= encoder_upright_raw %ld\n",(long)enc_upright_raw);
  checkedPrintf("= encoder_reference_saved %d\n",(int)reference_saved);
  checkedPrintln(F("= encoder_reference_mutable 1"));
  checkedPrintln(F("= bal_fall_deg 50"));
  checkedPrintln(F("= bal_start_deg 10"));
  const auto bk=swing_control::uprightGains(controller);
  checkedPrintf("= bal_k1 %.7f\n",bk.k1);
  checkedPrintf("= bal_k2 %.7f\n",bk.k2);
  checkedPrintf("= bal_k3 %.7f\n",bk.k3);
  checkedPrintf("= bal_k4 %.7f\n",bk.k4);
}

void handleLine(char *line) {
  char *cmd = strtok(line, " \t");
  if (!cmd) return;
  last_host_command_ms=millis();
  char *a1 = strtok(nullptr, " \t");
  if(encoderCalibrationBusy() && (!strcmp(cmd,"auto") || !strcmp(cmd,"bal") ||
      !strcmp(cmd,"manual") || !strcmp(cmd,"v") || !strcmp(cmd,"zv") || !strcmp(cmd,"on") ||
      !strcmp(cmd,"zero") || !strcmp(cmd,"upright"))){
    checkedPrintln(F("! encoder calibration active; wait for saved acknowledgment or stop to cancel"));return;
  }
  // Repeated GUI/manual commands cannot bypass the latched overspeed recovery.
  // stop/off always remain available and cancel recovery.
  if((inSpinRecovery() || inUprightReturn()) && (!strcmp(cmd,"auto") || !strcmp(cmd,"bal") ||
      !strcmp(cmd,"manual") || !strcmp(cmd,"v") || !strcmp(cmd,"zv"))) {
    checkedPrintln(F("! recovery active; wait for completion or use stop"));return;
  }

  if      (!strcmp(cmd,"ping")) { /* keepalive: no response traffic */ }
  else if (!strcmp(cmd,"enc")) { req_encoder=true; }
  else if (!strcmp(cmd,"stop"))  { eStop(); checkedPrintln(F("# STOP")); }
  else if (!strcmp(cmd,"off"))   { eStop(); energize(false);
                                   checkedPrintln(F("# de-energized - hold the rail")); }
  else if (!strcmp(cmd,"on"))    { energize(true); checkedPrintln(F("# energized")); }
  else if (!strcmp(cmd,"auto"))  {
    if (!enc_ok) { checkedPrintln(F("! encoder not healthy")); return; }
    eStop(); energize(true); response_watch.reset(th); mode=M_SWINGUP;
    checkedPrintln(F("# SWINGUP"));
  }
  else if (!strcmp(cmd,"bal"))   {
    if (!enc_ok) { checkedPrintln(F("! encoder not healthy")); return; }
    if(mode!=M_IDLE){checkedPrintln(F("! stop before starting an upright trial"));return;}
    req_balance=true;
  }
  else if (!strcmp(cmd,"manual")){ eStop(); energize(true);
                                   mode=M_MANUAL; checkedPrintln(F("# MANUAL")); }
  else if (!strcmp(cmd,"v")) {
    if(mode==M_RAIL_BRAKE || mode==M_RAIL_RETURN) return; // ignore held jog keys during recovery
    if (mode != M_MANUAL) { eStop(); energize(true); mode = M_MANUAL; }
    v_manual = a1 ? constrain(atof(a1), -p_vmax, p_vmax) : 0;
    v_manual_deadline = millis() + MANUAL_TIMEOUT_MS;
  }
  else if (!strcmp(cmd,"zv"))    { energize(true);
                                   zv_target = a1 ? constrain(atof(a1),-p_zvmax,p_zvmax) : 0; }
  else if (!strcmp(cmd,"zstop")) { zv_target = 0; }
  else if (!strcmp(cmd,"home"))  {
    if (mode != M_IDLE) { checkedPrintln(F("! stop and place cart at physical center before home")); return; }
    home_steps = ax_pos[AX_CART];
                                   checkedPrintln(F("# x = 0 here")); }
  else if (!strcmp(cmd,"zhome")) { zhome_steps = ax_pos[AX_Z1];
                                   checkedPrintln(F("# z = 0 here")); }
  else if (!strcmp(cmd,"zero") || !strcmp(cmd,"upright")) {
    const bool vertical=!strcmp(cmd,"upright");int32_t raw=0;
    if((!vertical && a1) || (a1 && (!encoder_reference::parse_count(a1,raw) || strtok(nullptr," \t")))){
      checkedPrintln(F("! usage: zero (hanging), upright (held vertical), or upright <integer 0..4095>"));return;
    }
    eStop();
    requested_upright_raw=raw;
    calibration_request=vertical?(a1?3:2):1;
    checkedPrintln(vertical?F("# upright calibration: hold straight up and still; drivers disabled"):
                           F("# zero: hold hanging down and still; upright target will be updated; drivers disabled"));
  }
  else if (!strcmp(cmd,"mag"))   { req_diag = true; }
  else if (!strcmp(cmd,"rate"))  { tele_hz = a1 ? constrain(atoi(a1),0,100) : 0;
                                   checkedPrintf("# telemetry %u Hz\n", tele_hz); }
  else if (!strcmp(cmd,"params")){ printParams(); }
  else if (!strcmp(cmd,"get")) {
    for (int i=0;i<N_PARAMS;i++)
      if (a1 && !strcmp(a1,PARAMS[i].name)) { checkedPrintf("= %s %.5f\n",PARAMS[i].name,*PARAMS[i].ptr); return; }
    checkedPrintln(F("! no such param"));
  }
  else if (!strcmp(cmd,"set")) {
    char *a2 = strtok(nullptr," \t");
    if (!a1 || !a2) { checkedPrintln(F("! usage: set <key> <value>")); return; }
    for (int i=0;i<N_PARAMS;i++) if (!strcmp(a1,PARAMS[i].name)) {
      char *end = nullptr;
      float want = strtof(a2, &end);
      if (end == a2 || *end || !isfinite(want)) {
        checkedPrintln(F("! expected a finite number")); return;
      }
      float *ptr = PARAMS[i].ptr;
      const bool motion_limit = ptr == &p_vmax || ptr == &p_vmax_s || ptr == &p_vmax_b ||
          ptr == &controller.approach_v || ptr == &controller.catch_v ||
          ptr == &controller.approach_angle || ptr == &controller.catch_da || ptr == &p_amax_s ||
          ptr == &p_amax_b || ptr == &p_jmax || ptr == &p_rail ||
          ptr == &p_amax_m || ptr == &p_jmax_m;
      const bool spin_limit=ptr==&controller.spin_trip_rad_s || ptr==&controller.spin_resume_rad_s;
      const bool gain_change=PARAMS[i].recalc || ptr==&controller.bal_pw || ptr==&p_bw ||
          ptr==&K1 || ptr==&K2 || ptr==&K3 || ptr==&K4;
      if ((motion_limit || gain_change || spin_limit) && mode != M_IDLE) {
        checkedPrintln(F("! stop before changing motion limits, balance gains or spin limits")); return;
      }
      if (((motion_limit || ptr == &p_leff || ptr == &p_bw || ptr == &p_phase_soft) && want <= 0) ||
          (ptr == &p_rail && want <= rail_recovery::edge_margin+rail_recovery::inside_hysteresis) ||
          ((ptr == &p_vmax || ptr == &p_vmax_s || ptr == &p_vmax_b ||
            ptr==&controller.approach_v || ptr==&controller.catch_v) && want > VMAX_CEIL) ||
          (ptr==&controller.approach_angle && (want<0.65f || want>1.5f))) {
        checkedPrintf("! invalid motion limit (vmax ceiling %.5f m/s)\n", VMAX_CEIL);
        return;
      }
      if((ptr==&controller.bal_pw && (want<1 || want>20)) ||
         ((ptr==&p_pw || ptr==&p_pz) && want<=0) ||
         ((ptr==&p_pc1 || ptr==&p_pc2) && want>=0)){
        checkedPrintln(F("! invalid poles: bal_pw 1..20, pw/pz positive, pc1/pc2 negative"));return;
      }
      if(ptr==&p_bw && !swing_control::validEstimatorBandwidth(want)){
        checkedPrintln(F("! estimator bw must be 0.1..100 Hz"));return;
      }
      if(spin_limit && !spin_recovery::validLimits(
          ptr==&controller.spin_trip_rad_s?want:controller.spin_trip_rad_s,
          ptr==&controller.spin_resume_rad_s?want:controller.spin_resume_rad_s)){
        checkedPrintln(F("! spin limits require 0 < spin_resume_rad_s < spin_trip_rad_s"));return;
      }
      // User-locked motion ceilings (2026-09-18); bw is independently tunable 0.1..100 Hz.
      const float user_max=ptr==&controller.spin_trip_rad_s?150.0f:
          ptr==&p_jmax?150.0f:
          (ptr==&p_amax_s || ptr==&p_amax_b)?25.0f:
          (ptr==&p_vmax || ptr==&p_vmax_s || ptr==&p_vmax_b)?1.5f:INFINITY;
      if(want>user_max){
        checkedPrintf("! user-locked maximum %s %.5f\n",PARAMS[i].name,user_max);return;
      }
      *PARAMS[i].ptr = want;
      if(ptr==&p_bw)req_estimator_reset=true;
      if (PARAMS[i].recalc) computeGains();
      checkedPrintf("= %s %.5f\n", PARAMS[i].name, *PARAMS[i].ptr);
      return;
    }
    checkedPrintln(F("! no such param"));
  }
  else if (!strcmp(cmd,"stat")) {
    checkedPrintf("# mode=%s energized=%d theta=%+.3f thd=%+.2f x=%+.4f v=%+.3f "
                  "z=%.1fmm agc=%d i2c_err=%lu loop=%luus\n",
                  MODE_NAME[mode], (int)g_energized, th, thd, xc, vc, z_mm,
                  enc_agc, (unsigned long)enc_errors, (unsigned long)loop_us);
    checkedPrintf("# ENABLE GPIO27 output=%s (LOW=enabled, HIGH=disabled)\n",
                  (REG_READ(GPIO_OUT_REG) & (1UL<<PIN_EN_ALL)) ? "HIGH" : "LOW");
    float mm_per_rev = PULLEY_TEETH * BELT_PITCH_MM;
    checkedPrintf("# motor %.0f rpm now, %.0f rpm at vmax, %.0f rpm at ceiling "
                  "(%.0f steps/s max)\n",
                  fabsf(vc)*60000.0f/mm_per_rev, p_vmax*60000.0f/mm_per_rev,
                  VMAX_CEIL*60000.0f/mm_per_rev, ISR_HZ*0.5f);
    if(inSpinRecovery())checkedPrintf("# overspeed recovery %s; |theta_dot|=%.2f rad/s, resume below %.1f rad/s when centered\n",
        MODE_NAME[mode],fabsf(thd),controller.spin_resume_rad_s);
    checkedPrintf("# serial baud=115200, host timeout=%lu ms, dropped events=%lu\n",(unsigned long)HOST_TIMEOUT_MS,(unsigned long)dropped_control_messages);
    checkedPrintf("# K = [%.3f %.3f %.3f %.3f]\n", K1,K2,K3,K4);
  }
  else if (!strcmp(cmd,"help")) {
    checkedPrintln(F("# auto bal manual v<mps> zv<mmps> zstop stop off on"));
    checkedPrintln(F("# home zhome zero upright [count] mag enc ping rate<hz> set get params stat"));
    checkedPrintln(F("# zero: hanging down -> save upright half a turn away. upright: held straight up -> save current count."));
  }
  else checkedPrintln(F("! unknown command (try 'help')"));
}

void pollSerial() {
  static char buf[96];static uint8_t n=0;static bool overflow=false;
  while(Serial.available()){
    const char c=Serial.read();
    if(c=='\n' || c=='\r'){
      if(overflow)checkedPrintln(F("! command too long; discarded"));
      else if(n){buf[n]=0;handleLine(buf);}
      n=0;overflow=false;
    }else if(!overflow){if(n<sizeof(buf)-1)buf[n++]=c;else overflow=true;}
  }
}

void emitTelemetry() {
  checkedPrintf("T %lu %d %.4f %.3f %.5f %.4f %.3f %.4f %.2f %.2f %d %lu\n",
                (unsigned long)millis(), (int)mode, th, thd, xc, vc, acc_cmd,
                energy_n, z_mm, z_mm, enc_agc, (unsigned long)loop_us);
}

// ============================== SETUP =======================================
void setup() {
  // Preload HIGH before enabling output, before serial delays/I2C/zeroing.
  gpio_set_level((gpio_num_t)PIN_EN_ALL, 1);
  pinMode(PIN_EN_ALL, OUTPUT); // Register GPIO with Arduino before digitalWrite().
  g_energized = false;
  Serial.setRxBufferSize(1024);
  Serial.setTxBufferSize(4096);
  Serial.begin(115200);
  delay(300);
  checkedPrintln(F("# ESP32 cart-pole swingup-125mm-60t-v34"));

  // I2C comes up FIRST, while nothing else is competing for the CPU. Bringing
  // the 125 kHz step interrupt up first meant the very first bus transactions
  // happened under ~20% interrupt load, on a 5 ms timeout, with no retries.
  Wire.begin(PIN_SDA, PIN_SCL, I2C_HZ);
  Wire.setTimeOut(50);
  delay(50);

  checkedPrintln(F("# scanning i2c..."));
  for (uint8_t a = 1; a < 127; a++) {
    Wire.beginTransmission(a);
    if (Wire.endTransmission() == 0)
      checkedPrintf("#   device at 0x%02X%s\n", a,
                    a == AS5600_ADDR ? "  <- AS5600" :
                    a == 0x06        ? "  <- MT6701, different chip" : "");
    delay(1);
  }

  encDiagRead();
  enc_last_raw = encReadRaw();
  enc_ok = (enc_last_raw >= 0);
  if (!enc_ok) { checkedPrintln(F("! encoder not answering - check SDA=21 SCL=22, "
                                  "3V3, and DIR tied to GND")); enc_last_raw = 0; }
  encPrintMagnet();
  if (as5600FastFilter()) checkedPrintln(F("# AS5600 slow filter -> 2x (0.29 ms lag)"));
  else                    checkedPrintln(F("! AS5600 CONF write failed"));
  enc_ticks = 0;

  steppersInit();

  computeGains();
  checkedPrintf("# cart %.1f steps/mm (1/%d), Z %.1f steps/mm\n",
                CART_STEPS_PER_M/1000.0f, CART_MICROSTEPS, Z_STEPS_PER_MM);
  checkedPrintf("# cart speed ceiling %.2f m/s\n", VMAX_CEIL);
  delay(300);
  loadEncoderReference();
  enc_zero=enc_ticks+encoder_reference::difference(encoder_reference::opposite(enc_upright_raw),enc_last_raw);
  checkedPrintf("# upright reference %ld counts (%s); startup retains it\n",(long)enc_upright_raw,reference_saved?"saved":"fallback; use upright or zero to calibrate");
  th = th_hat = encTheta();
  home_steps = ax_pos[AX_CART];
  zhome_steps = ax_pos[AX_Z1];
  checkedPrintf("# K = [%.3f %.3f %.3f %.3f]\n", K1,K2,K3,K4);
  checkedPrintf("# Cart defaults: leff=%.3f m, vmax=%.3f m/s, amax_s=%.1f, amax_b=%.1f m/s^2, jmax=%.1f m/s^3\n",
                p_leff, p_vmax, p_amax_s, p_amax_b, p_jmax);
  checkedPrintln(F("# Startup position is x=0: place cart at physical center before reset; no homing motion."));
  checkedPrintln(F("# Travel 300 mm; normal range +/-135 mm. Predictive braking -> return inside range; fault +/-140 mm."));
  checkedPrintf("# Pendulum |theta_dot| >%.2f rad/s: brake, center, then resume below %.2f rad/s; no full-turn check or dwell.\n",controller.spin_trip_rad_s,controller.spin_resume_rad_s);
  checkedPrintln(F("# bal: explicit upright-only start within 10deg; >50deg fall brakes, centers and disables; no restart."));
  checkedPrintln(F("# Drivers DISABLED. Motion commands enable; stop disables all drivers."));
  checkedPrintln(F("# ready. 'help' for commands."));

  control_messages=xQueueCreate(24,sizeof(ControlMessage));
  if(!control_messages){eStop();mode=M_FAULT;checkedPrintln(F("! serial event queue allocation failed"));return;}
  last_host_command_ms=millis();
  xTaskCreatePinnedToCore(controlTask, "ctrl", 4096, nullptr, 5, nullptr, 1);
}

void loop() {
  pollSerial();
  flushControlMessages();

  if (diag_done) { diag_done = false; encPrintMagnet(); }
  saveEncoderReference();
  static uint32_t last = 0;
  if (tele_hz) {
    uint32_t period = 1000000UL / tele_hz;
    if (micros() - last >= period) { last = micros(); emitTelemetry(); }
  }
  delayMicroseconds(200);
}

// ============================================================================
//  CALIBRATION, in order. Do not skip 1 and 2.
//
//  1. STEPS/M must be exact. 'manual', then 'home', drive the cart with the
//     host tool, and compare reported x against a ruler. If they disagree,
//     your pulley or microstep constants are wrong - fix the constants, don't
//     fudge a scale factor.
//
//  2. L_EFF. Let the pendulum hang, give it a small push, time 10 swings.
//     T = 2*pi*sqrt(L_EFF/g), so L_EFF = g*(T/(2*pi))^2. Every gain in the
//     balancer is derived from this number, so measure it rather than guess.
//     Then:  set leff <value>
//
//  3. Direction checks. 'manual' and drive right: theta must go POSITIVE when
//     you tilt the pole top in the direction the cart moved for positive v.
//     If not, flip ENC_INVERT (or CART_INVERT) and reflash.
//
//  4. Balance first, swing-up second. Hold the pole upright, send 'bal'. It
//     should fight you. Oscillating fast -> lower pw. Drifting into the rail
//     -> make pc1/pc2 more negative. Buzzing -> lower bw.
//
//  5. Then 'auto'. Never builds enough energy -> raise amax_s or lower kpx
//     (the centring term steals energy). Flies past the top -> lower ke, or
//     widen catch_r.
//
//  IF SWING-UP STALLS AT A FIXED AMPLITUDE, suspect the velocity ceiling
//  before the gains. The energy pump does work at a rate -(a/L)*thd*cos(th),
//  so the moment the cart saturates at vmax the acceleration goes to zero and
//  pumping stops dead for the rest of that half-swing. Watch 'v' in the
//  dashboard: if it is flat-topped at +-vmax for long stretches, you are
//  speed-limited, not tuning-limited, and no gain will fix it.
//
//  LOST STEPS LOOK EXACTLY LIKE BAD TUNING. After any crash, check that the
//  reported x = 0 is still the physical centre. If it has drifted, you are
//  losing steps: lower amax/vmax, raise Vref, or raise the motor supply
//  voltage. Note the rotor itself is not free - 87 g.cm^2 through a 6.37 mm
//  pitch radius reflects to ~0.22 kg of apparent cart mass, which for a light
//  cart is comparable to the cart itself.
// ============================================================================
