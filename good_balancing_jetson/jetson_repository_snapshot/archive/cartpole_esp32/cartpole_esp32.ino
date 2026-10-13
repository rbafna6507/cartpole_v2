// ============================================================================
//  cartpole_esp32.ino   -- v2, built around the actual hardware
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
//    4. 24V on M+ (not the VCC pin - that is an output). The 60T cart uses
//       120 mm of belt travel per motor revolution.
//
//  PINOUT
//    25 cart STEP    26 cart DIR
//    16 Z1   STEP    17 Z1   DIR
//    18 Z2   STEP    19 Z2   DIR
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
//  IMPORTANT: ball screws back-drive
//    SFU1605 is efficient enough to back-drive under load. Since all three
//    ENABLE lines share GPIO27, de-energizing to stop would drop the rail.
//    So 'stop' zeroes all velocities but KEEPS the motors energized. 'off'
//    de-energizes and is a separate, deliberate command.
//
//  PROTOCOL (921600 baud, newline terminated). See cartpole.py for the host.
//    host -> board                      board -> host
//      auto            swing-up           T <ms> <mode> <th> <thd> <x> <v>
//      bal             balance only         <a> <e> <z1> <z2> <agc> <dt_us>
//      manual          manual drive       = <key> <value>
//      v <m/s>         cart velocity      # <human readable log>
//      zv <mm/s>       both screws        ! <error>
//      zstop
//      stop            e-stop, stay energized
//      off / on        de-energize / energize
//      home            call this x = 0
//      zhome           call this z = 0
//      zero            re-zero encoder (pendulum hanging, still)
//      rate <hz>       telemetry rate, 0 = off
//      set <k> <v>     live-tune a parameter
//      get <k> / params / stat / help
// ============================================================================

#include <Arduino.h>
#include <Wire.h>
#include "soc/soc.h"        // REG_WRITE
#include "soc/gpio_reg.h"   // GPIO_OUT_W1TS_REG / GPIO_OUT_W1TC_REG

// ============================== PINS ========================================
#define PIN_CART_STEP   25
#define PIN_CART_DIR    26
#define PIN_Z1_STEP     16
#define PIN_Z1_DIR      17
#define PIN_Z2_STEP     18
#define PIN_Z2_DIR      19
#define PIN_EN_ALL      27        // shared ENABLE, active LOW
#define PIN_SDA         21
#define PIN_SCL         22
#define I2C_HZ          400000    // drop to 100000 if the cable to the cart is
                                  // long or you see enc_err climbing

#define CART_INVERT     1         // flip if 'v 0.05' moves the cart the wrong way
#define Z_INVERT        0         // flip if 'zv 5' lowers instead of raises
#define ENC_INVERT      0         // flip if theta goes negative when the pole
                                  // leans toward +x

// ========================== MECHANICS =======================================
// Big Easy Driver floating MS pins select 1/16: 3200 steps/rev.
// 60T GT2 gives 120 mm/rev and 26.667 steps/mm.
#define CART_MICROSTEPS 16        // MS pins floating -> BED default
#define Z_MICROSTEPS    16        // same
#define MOTOR_STEPS_REV 200       // 1.8 deg
#define PULLEY_TEETH    60        // GT2 60T
#define BELT_PITCH_MM   2.0f
#define Z_LEAD_MM       5.0f      // SFU1605

static const float CART_STEPS_PER_M =
    (MOTOR_STEPS_REV * CART_MICROSTEPS) / (PULLEY_TEETH * BELT_PITCH_MM * 1e-3f);
static const float Z_STEPS_PER_MM =
    (MOTOR_STEPS_REV * Z_MICROSTEPS) / Z_LEAD_MM;

#define GRAV            9.81f
#define CTRL_HZ         1000
// The A4988 needs >=1 us of STEP high AND >=1 us low, so the DDS spends one
// timer tick high and at least one low: max step rate is ISR_HZ/2.
//   80 kHz -> 40 k steps/s -> 1.50 m/s ->  750 rpm
//  120 kHz -> 60 k steps/s -> 2.25 m/s -> 1125 rpm
//  150 kHz -> 75 k steps/s -> 2.81 m/s -> 1406 rpm
// 120 kHz is an 8.3 us period and the ISR costs ~1.5 us, so roughly 18% of one
// core. This is the aggressive setting. If serial drops characters, the board
// resets, or 'stat' shows loop time climbing past ~250 us, back off to 80000.
// The motor itself holds torque to around 1200-1500 rpm on 24V, so past about
// 150 kHz you stop gaining anything real.
#define ISR_HZ          120000    // 3-channel step DDS; max rate = ISR_HZ/2
static const float DT = 1.0f / CTRL_HZ;

// Hard ceiling on cart speed, derived rather than guessed. Ask for more than
// this and the pulse generator clamps while the controller keeps believing the
// number it was given - so we clamp loudly at the point of entry instead.
static const float VMAX_CEIL = (ISR_HZ * 0.5f) / CART_STEPS_PER_M;

#define MANUAL_TIMEOUT_MS 250     // 'v' command watchdog: no news = stop

// ===================== LIVE-TUNABLE PARAMETERS ==============================
// Change any of these at runtime with  set <name> <value>  - no reflash.
float p_leff    = 0.20f;   // effective pendulum length, m  (see CALIBRATION)
float p_pw      = 7.07f;   // desired pendulum pole pair: natural freq, rad/s
float p_pz      = 0.707f;  //   ... and damping
float p_pc1     = -1.2f;   // desired cart poles, rad/s (negative)
float p_pc2     = -1.6f;
// SPEED PROFILE: the defaults below are the deliberately-crawling bring-up
// values, so the first power-up cannot hurt anything. Send 'fast' to switch to
// the values the controller actually needs, 'slow' to come back. A cart-pole
// physically cannot balance on the slow profile - the cart has to be able to
// accelerate under a falling pole, and 1 m/s^2 is nowhere near enough. Slow is
// for checking directions, distances and wiring, nothing more.
float p_vmax    = 0.05f;   // m/s - hard ceiling is ISR_HZ/2/steps_per_m = 2.25
float p_amax_s  = 0.5f;    // m/s^2 during swing-up
float p_amax_b  = 1.0f;    // m/s^2 while balancing
float p_ke      = 0.25f;   // energy pump gain
float p_kpx     = 15.0f;   // cart centring during swing-up
float p_kdx     = 6.0f;
float p_catch_a = 0.30f;   // rad  - hand off to the balancer inside this
float p_catch_r = 5.0f;    // rad/s
float p_giveup  = 0.55f;   // rad  - balancer gives up outside this
float p_rail    = 0.22f;   // m, centre to each physical end
float p_bw      = 20.0f;   // Hz, angle/rate estimator bandwidth
float p_vman    = 0.02f;   // m/s, manual jog speed
float p_zvmax   = 2.0f;    // mm/s
float p_zamax   = 20.0f;   // mm/s^2
float p_ztravel = 100.0f;  // mm of usable screw travel above z=0

// state-feedback gains, computed from the poles above: a = -(K.[th,thd,x,v])
float K1, K2, K3, K4;

struct Param { const char *name; float *ptr; bool recalc; };
static const Param PARAMS[] = {
  {"leff",&p_leff,true},   {"pw",&p_pw,true},      {"pz",&p_pz,true},
  {"pc1",&p_pc1,true},     {"pc2",&p_pc2,true},
  {"vmax",&p_vmax,false},  {"amax_s",&p_amax_s,false},{"amax_b",&p_amax_b,false},
  {"ke",&p_ke,false},      {"kpx",&p_kpx,false},   {"kdx",&p_kdx,false},
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
  int8_t d = (steps_per_sec >= 0.0f) ? 1 : -1;
  if (d != ax_dir[i]) {
    ax_dir[i] = d;
    bool high = (d > 0);
    if (invert) high = !high;
    digitalWrite(DIR_PIN[i], high ? HIGH : LOW);
  }
  float r = fabsf(steps_per_sec);
  const float RMAX = ISR_HZ * 0.5f;
  if (r > RMAX) r = RMAX;
  ax_inc[i] = (uint32_t)((double)r * 4294967296.0 / (double)ISR_HZ);
}

void steppersInit() {
  const uint8_t outs[] = { PIN_CART_STEP, PIN_CART_DIR, PIN_Z1_STEP, PIN_Z1_DIR,
                           PIN_Z2_STEP, PIN_Z2_DIR };
  for (uint8_t p : outs) { pinMode(p, OUTPUT); digitalWrite(p, LOW); }
  pinMode(PIN_EN_ALL, OUTPUT); digitalWrite(PIN_EN_ALL, HIGH);   // de-energized

  // Microstepping is whatever the drivers default to (1/16). MS1/MS2/MS3 are
  // deliberately not touched, so GPIO 32 / 33 / 13 are free for limit
  // switches or anything else you add later.

#if ESP_ARDUINO_VERSION_MAJOR >= 3
  g_timer = timerBegin(1000000);
  timerAttachInterrupt(g_timer, &onStepTimer);
  timerAlarm(g_timer, 1000000UL / ISR_HZ, true, 0);
#else
  g_timer = timerBegin(0, 80, true);
  timerAttachInterrupt(g_timer, &onStepTimer, true);
  timerAlarmWrite(g_timer, 1000000UL / ISR_HZ, true);
  timerAlarmEnable(g_timer);
#endif
}

bool g_energized = false;
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

inline float wrapPi(float a) {
  while (a >  (float)M_PI) a -= 2.0f*(float)M_PI;
  while (a < -(float)M_PI) a += 2.0f*(float)M_PI;
  return a;
}

// theta: 0 = upright, +-pi = hanging, positive = pole top leaning toward +x
float encTheta() {
  float a = (enc_ticks - enc_zero) * (2.0f*(float)M_PI / (float)ENC_CPR);
#if ENC_INVERT
  a = -a;
#endif
  return wrapPi(a + (float)M_PI);
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
  if (!enc_ok) Serial.println(F("! encoder not reading - values below are stale"));
  Serial.printf("# AS5600 status=0x%02X agc=%d  %s%s%s\n", st, ag,
                (st & 0x20) ? "magnet-ok " : "NO-MAGNET ",
                (st & 0x10) ? "too-weak "  : "",
                (st & 0x08) ? "too-strong" : "");
  if (ag >= 120)     Serial.println(F("# AGC at max gain - magnet too far, move it CLOSER"));
  else if (ag <= 8)  Serial.println(F("# AGC at min gain - magnet too close"));
  Serial.printf("# i2c errors=%lu  bus recoveries=%lu\n",
                (unsigned long)enc_errors, (unsigned long)enc_recoveries);
}

// Blocking version - setup() only, before the control task exists.
void encZeroBlocking() {
  Serial.println(F("# zeroing: hold the pendulum still, hanging down..."));
  int stable = 0; int32_t prev = enc_ticks; uint32_t t0 = millis();
  while (stable < 400 && millis() - t0 < 15000) {
    encUpdate();
    if (labs(enc_ticks - prev) <= 2) stable++; else stable = 0;
    prev = enc_ticks;
    delay(2);
  }
  enc_zero = enc_ticks;
  Serial.printf("# encoder zeroed, theta = %.3f rad\n", encTheta());
}

// ========================== CONTROLLER ======================================
enum Mode { M_IDLE=0, M_MANUAL, M_SWINGUP, M_BALANCE, M_FAULT };
volatile Mode mode = M_IDLE;
const char *MODE_NAME[] = {"IDLE","MANUAL","SWINGUP","BALANCE","FAULT"};

volatile float th=0, thd=0, xc=0, vc=0, acc_cmd=0, energy_n=-1;
volatile float z_mm=0;
volatile uint32_t loop_us=0;
static float th_hat=0, thd_hat=0;
static int   swing_sign=1;
static uint32_t stall_ms=0;
static int32_t home_steps=0, zhome_steps=0;

// Cross-context requests. loop() may only SET these; the control task is the
// only thing allowed to act on them, because it is the sole owner of the I2C
// bus once it exists. This is the whole fix for 'mag' returning nothing.
volatile bool req_diag = false, req_zero = false;
volatile bool diag_done = false, zero_done = false;
static bool zeroing = false;
static int  zero_stable = 0;
static int32_t zero_prev = 0;
static uint32_t zero_t0 = 0;

static float v_manual=0;
static uint32_t v_manual_deadline=0;
static float zv_target=0, zv_now=0;

// Two speed profiles. 'slow' is for bring-up: everything crawls, you have all
// the time in the world to hit stop, and a wiring mistake bumps the end of the
// rail instead of hitting it. 'fast' is what balancing actually requires.
void profileSlow() {
  p_vmax = 0.05f; p_vman = 0.02f; p_amax_s = 0.5f; p_amax_b = 1.0f;
  p_zvmax = 2.0f; p_zamax = 20.0f;
}
void profileFast() {
  // Preserve the previous 20T linear fast-profile limit after the 60T swap.
  p_vmax = 0.72f; p_vman = 0.15f; p_amax_s = 9.0f; p_amax_b = 18.0f;
  p_zvmax = 15.0f; p_zamax = 120.0f;
}

// Exact pole placement. With a = -(K1*th + K2*thd + K3*x + K4*v) the closed
// loop characteristic polynomial of this plant is
//   s^4 + (K4 - K2/L)s^3 + (K3 - g/L - K1/L)s^2 - (g*K4/L)s - (g*K3/L)
// Matching that to (s^2+2*z*w*s+w^2)(s-pc1)(s-pc2) inverts in closed form.
void computeGains() {
  float b1 = 2.0f*p_pz*p_pw, b0 = p_pw*p_pw;
  float c1 = -(p_pc1 + p_pc2), c0 = p_pc1*p_pc2;
  float a3 = b1 + c1;
  float a2 = b0 + b1*c1 + c0;
  float a1 = b1*c0 + b0*c1;
  float a0 = b0*c0;
  const float L = p_leff, g = GRAV;
  K3 = -a0*L/g;
  K4 = -a1*L/g;
  K1 = L*K3 - g - L*a2;
  K2 = L*(K4 - a3);
  // K3 and K4 come out NEGATIVE and that is correct: to bring the cart back to
  // centre you must first accelerate AWAY from centre to tip the pole inward.
  // The system is non-minimum phase. "Fixing" those signs guarantees a fall.
}

// Alpha-beta tracking differentiator. Differencing a 12-bit encoder at 1 kHz
// would give ~1.5 rad/s of quantisation hash; this smooths it and handles the
// +-pi wrap without a glitch.
void estimate(float theta_meas) {
  float w = 2.0f*(float)M_PI*p_bw;
  float err = wrapPi(theta_meas - th_hat);
  th_hat  = wrapPi(th_hat + (thd_hat + 2.0f*w*err)*DT);
  thd_hat += w*w*err*DT;
  th = theta_meas;
  thd = thd_hat;
}

float balanceAccel() { return -(K1*th + K2*thd + K3*xc + K4*vc); }

// Energy shaping (Astrom-Furuta). With E = 0.5*thd^2 + (g/L)cos(th),
// dE/dt = -(a/L)*thd*cos(th), so pumping toward upright means
//   a = k*(E - E_up)*sign(thd*cos(th))
float swingAccel() {
  float Eup = GRAV/p_leff;
  float E   = 0.5f*thd*thd + Eup*cosf(th);
  energy_n  = E/Eup;                        // 1.0 at the top, -1.0 hanging
  float dE  = E - Eup;

  float s = thd*cosf(th);                   // hold sign through the deadband,
  if      (s >  0.05f) swing_sign =  1;     // otherwise it chatters at thd=0
  else if (s < -0.05f) swing_sign = -1;

  float a = p_ke*dE*(float)swing_sign;

  if (fabsf(thd) < 0.08f && fabsf(dE) > 1.0f) {   // dead start: nothing to
    stall_ms += 1000/CTRL_HZ;                     // take the sign from
    if (stall_ms > 250) a = (float)swing_sign*p_amax_s;
    if (stall_ms > 330) { stall_ms = 0; swing_sign = -swing_sign; }
  } else stall_ms = 0;

  a += -(p_kpx*xc + p_kdx*vc);
  return constrain(a, -p_amax_s, p_amax_s);
}

void eStop() {
  mode = M_IDLE;
  v_manual = 0; vc = 0; acc_cmd = 0; zv_target = 0; zv_now = 0;
  for (int i=0;i<N_AX;i++) ax_inc[i] = 0;
  // deliberately NOT de-energizing: the ball screws back-drive and the rail
  // would sink. Use 'off' for that, on purpose.
}

void controlTask(void *) {
  TickType_t wake = xTaskGetTickCount();
  for (;;) {
    vTaskDelayUntil(&wake, pdMS_TO_TICKS(1000/CTRL_HZ));
    uint32_t t_start = micros();

    encUpdate();

    // Serve bus requests here, where we already own Wire.
    if (req_diag) { req_diag = false; encDiagRead(); diag_done = true; }
    if (req_zero) {
      req_zero = false; zeroing = true;
      zero_stable = 0; zero_prev = enc_ticks; zero_t0 = millis();
    }
    if (zeroing) {
      if (labs(enc_ticks - zero_prev) <= 2) zero_stable++; else zero_stable = 0;
      zero_prev = enc_ticks;
      if (zero_stable >= 400 || millis() - zero_t0 > 15000) {
        enc_zero = enc_ticks; th_hat = encTheta(); thd_hat = 0;
        zeroing = false; zero_done = true;
      }
    }

    estimate(encTheta());
    xc = (ax_pos[AX_CART] - home_steps) / CART_STEPS_PER_M;
    z_mm = (ax_pos[AX_Z1] - zhome_steps) / Z_STEPS_PER_MM;

    float rail_hard = p_rail - 0.01f, rail_soft = p_rail - 0.05f;
    if (mode != M_IDLE && mode != M_FAULT && fabsf(xc) > rail_hard) {
      Serial.println(F("! rail limit -> FAULT"));
      mode = M_FAULT; eStop(); mode = M_FAULT;
    }

    float a = 0.0f;
    switch (mode) {
      case M_MANUAL:
        if (millis() > v_manual_deadline) v_manual = 0;   // key-release watchdog
        {
          // Ramp, don't jump. A dead-stop step to 0.15 m/s is 12,000 steps/s
          // at 1/16, which is ~750 full steps/s - well past what a NEMA 17
          // will start into from rest with the rotor and cart inertia hanging
          // off it. It would just buzz and slip, and the position count would
          // silently drift away from reality.
          float dv = p_amax_b*DT;
          if      (vc < v_manual - dv) vc += dv;
          else if (vc > v_manual + dv) vc -= dv;
          else                         vc  = v_manual;
        }
        if (xc >  rail_soft && vc > 0) vc = 0;
        if (xc < -rail_soft && vc < 0) vc = 0;
        axSetRate(AX_CART, vc*CART_STEPS_PER_M, CART_INVERT);
        goto zaxis;

      case M_SWINGUP:
        a = swingAccel();
        if (fabsf(th) < p_catch_a && fabsf(thd) < p_catch_r) {
          mode = M_BALANCE; Serial.println(F("# caught -> BALANCE"));
        }
        break;

      case M_BALANCE: {
        float Eup = GRAV/p_leff;
        energy_n = (0.5f*thd*thd + Eup*cosf(th))/Eup;
        a = constrain(balanceAccel(), -p_amax_b, p_amax_b);
        if (fabsf(th) > p_giveup) {
          mode = M_SWINGUP; Serial.println(F("# lost it -> SWINGUP"));
        }
        break;
      }

      default:                                   // IDLE / FAULT
        vc = 0; acc_cmd = 0;
        axSetRate(AX_CART, 0, CART_INVERT);
        goto zaxis;
    }

    if (fabsf(xc) > rail_soft && xc*vc > 0.0f)   // soft rail overrides all
      a = -(xc > 0 ? 1.0f : -1.0f)*p_amax_b;

    acc_cmd = a;
    vc += a*DT;
    vc = constrain(vc, -p_vmax, p_vmax);
    if (xc >  rail_hard && vc > 0) vc = 0;       // anti-windup at the wall
    if (xc < -rail_hard && vc < 0) vc = 0;
    axSetRate(AX_CART, vc*CART_STEPS_PER_M, CART_INVERT);

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
static uint16_t tele_hz = 100;

void printParams() {
  for (int i=0;i<N_PARAMS;i++) Serial.printf("= %s %.5f\n", PARAMS[i].name, *PARAMS[i].ptr);
  Serial.printf("= cart_steps_per_m %.2f\n", CART_STEPS_PER_M);
  Serial.printf("= z_steps_per_mm %.2f\n", Z_STEPS_PER_MM);
}

void handleLine(char *line) {
  char *cmd = strtok(line, " \t");
  if (!cmd) return;
  char *a1 = strtok(nullptr, " \t");

  if      (!strcmp(cmd,"stop"))  { eStop(); Serial.println(F("# STOP")); }
  else if (!strcmp(cmd,"off"))   { eStop(); energize(false);
                                   Serial.println(F("# de-energized - hold the rail")); }
  else if (!strcmp(cmd,"on"))    { energize(true); Serial.println(F("# energized")); }
  else if (!strcmp(cmd,"auto"))  { energize(true); vc=0; swing_sign=1;
                                   mode=M_SWINGUP; Serial.println(F("# SWINGUP")); }
  else if (!strcmp(cmd,"bal"))   { energize(true); vc=0; mode=M_BALANCE;
                                   Serial.println(F("# BALANCE")); }
  else if (!strcmp(cmd,"manual")){ energize(true); vc=0; v_manual=0;
                                   mode=M_MANUAL; Serial.println(F("# MANUAL")); }
  else if (!strcmp(cmd,"v")) {
    if (mode != M_MANUAL) { energize(true); mode = M_MANUAL; }
    v_manual = a1 ? constrain(atof(a1), -p_vmax, p_vmax) : 0;
    v_manual_deadline = millis() + MANUAL_TIMEOUT_MS;
  }
  else if (!strcmp(cmd,"zv"))    { energize(true);
                                   zv_target = a1 ? constrain(atof(a1),-p_zvmax,p_zvmax) : 0; }
  else if (!strcmp(cmd,"zstop")) { zv_target = 0; }
  else if (!strcmp(cmd,"slow"))  { eStop(); profileSlow();
                                   Serial.println(F("# SLOW profile - bring-up only, will not balance")); }
  else if (!strcmp(cmd,"fast"))  { eStop(); profileFast();
                                   Serial.println(F("# FAST profile - full speed, keep clear")); }
  else if (!strcmp(cmd,"home"))  { home_steps = ax_pos[AX_CART];
                                   Serial.println(F("# x = 0 here")); }
  else if (!strcmp(cmd,"zhome")) { zhome_steps = ax_pos[AX_Z1];
                                   Serial.println(F("# z = 0 here")); }
  else if (!strcmp(cmd,"zero"))  { eStop(); req_zero = true;
                                   Serial.println(F("# zeroing: hold the pendulum still, hanging...")); }
  else if (!strcmp(cmd,"mag"))   { req_diag = true; }
  else if (!strcmp(cmd,"rate"))  { tele_hz = a1 ? atoi(a1) : 0;
                                   Serial.printf("# telemetry %u Hz\n", tele_hz); }
  else if (!strcmp(cmd,"params")){ printParams(); }
  else if (!strcmp(cmd,"get")) {
    for (int i=0;i<N_PARAMS;i++)
      if (a1 && !strcmp(a1,PARAMS[i].name)) { Serial.printf("= %s %.5f\n",PARAMS[i].name,*PARAMS[i].ptr); return; }
    Serial.println(F("! no such param"));
  }
  else if (!strcmp(cmd,"set")) {
    char *a2 = strtok(nullptr," \t");
    if (!a1 || !a2) { Serial.println(F("! usage: set <key> <value>")); return; }
    for (int i=0;i<N_PARAMS;i++) if (!strcmp(a1,PARAMS[i].name)) {
      float want = atof(a2);
      // No clamp - your machine, your call. But say so, because above the
      // ceiling the pulse generator saturates while the controller keeps
      // integrating vc to the number you asked for, and the velocity feedback
      // term stops describing the real cart.
      if (PARAMS[i].ptr == &p_vmax && want > VMAX_CEIL)
        Serial.printf("! note: %.2f is past the %.2f m/s pulse ceiling - "
                      "steps saturate, vc will read high. Raise ISR_HZ.\n",
                      want, VMAX_CEIL);
      *PARAMS[i].ptr = want;
      if (PARAMS[i].recalc) computeGains();
      Serial.printf("= %s %.5f\n", PARAMS[i].name, *PARAMS[i].ptr);
      return;
    }
    Serial.println(F("! no such param"));
  }
  else if (!strcmp(cmd,"stat")) {
    Serial.printf("# mode=%s energized=%d theta=%+.3f thd=%+.2f x=%+.4f v=%+.3f "
                  "z=%.1fmm agc=%d i2c_err=%lu loop=%luus\n",
                  MODE_NAME[mode], (int)g_energized, th, thd, xc, vc, z_mm,
                  enc_agc, (unsigned long)enc_errors, (unsigned long)loop_us);
    float mm_per_rev = PULLEY_TEETH * BELT_PITCH_MM;
    Serial.printf("# motor %.0f rpm now, %.0f rpm at vmax, %.0f rpm at ceiling "
                  "(%.0f steps/s max)\n",
                  fabsf(vc)*60000.0f/mm_per_rev, p_vmax*60000.0f/mm_per_rev,
                  VMAX_CEIL*60000.0f/mm_per_rev, ISR_HZ*0.5f);
    Serial.printf("# K = [%.3f %.3f %.3f %.3f]\n", K1,K2,K3,K4);
  }
  else if (!strcmp(cmd,"help")) {
    Serial.println(F("# auto bal manual v<mps> zv<mmps> zstop stop off on"));
    Serial.println(F("# slow fast home zhome zero mag rate<hz> set get params stat"));
  }
  else Serial.println(F("! unknown command (try 'help')"));
}

void pollSerial() {
  static char buf[96]; static uint8_t n = 0;
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n' || c == '\r') {
      if (n) { buf[n] = 0; handleLine(buf); n = 0; }
    } else if (n < sizeof(buf)-1) buf[n++] = c;
  }
}

void emitTelemetry() {
  Serial.printf("T %lu %d %.4f %.3f %.5f %.4f %.3f %.4f %.2f %.2f %d %lu\n",
                (unsigned long)millis(), (int)mode, th, thd, xc, vc, acc_cmd,
                energy_n, z_mm, z_mm, enc_agc, (unsigned long)loop_us);
}

// ============================== SETUP =======================================
void setup() {
  Serial.begin(921600);
  Serial.setTxBufferSize(2048);
  delay(300);
  Serial.println(F("\n# ESP32 cart-pole v2"));

  // I2C comes up FIRST, while nothing else is competing for the CPU. Bringing
  // the 120 kHz step interrupt up first meant the very first bus transactions
  // happened under ~20% interrupt load, on a 5 ms timeout, with no retries.
  Wire.begin(PIN_SDA, PIN_SCL, I2C_HZ);
  Wire.setTimeOut(50);
  delay(50);

  Serial.println(F("# scanning i2c..."));
  for (uint8_t a = 1; a < 127; a++) {
    Wire.beginTransmission(a);
    if (Wire.endTransmission() == 0)
      Serial.printf("#   device at 0x%02X%s\n", a,
                    a == AS5600_ADDR ? "  <- AS5600" :
                    a == 0x06        ? "  <- MT6701, different chip" : "");
    delay(1);
  }

  encDiagRead();
  enc_last_raw = encReadRaw();
  enc_ok = (enc_last_raw >= 0);
  if (!enc_ok) { Serial.println(F("! encoder not answering - check SDA=21 SCL=22, "
                                  "3V3, and DIR tied to GND")); enc_last_raw = 0; }
  encPrintMagnet();
  if (as5600FastFilter()) Serial.println(F("# AS5600 slow filter -> 2x (0.29 ms lag)"));
  else                    Serial.println(F("! AS5600 CONF write failed"));
  enc_ticks = 0;

  steppersInit();

  computeGains();
  Serial.printf("# cart %.1f steps/mm (1/%d), Z %.1f steps/mm\n",
                CART_STEPS_PER_M/1000.0f, CART_MICROSTEPS, Z_STEPS_PER_MM);
  Serial.printf("# cart speed ceiling %.2f m/s\n", VMAX_CEIL);
  delay(300);
  encZeroBlocking();
  th_hat = encTheta();
  home_steps = ax_pos[AX_CART];
  zhome_steps = ax_pos[AX_Z1];
  Serial.printf("# K = [%.3f %.3f %.3f %.3f]\n", K1,K2,K3,K4);
  Serial.println(F("# SLOW profile active. 'fast' when you want to balance."));
  Serial.println(F("# ready. 'help' for commands."));

  xTaskCreatePinnedToCore(controlTask, "ctrl", 4096, nullptr, 5, nullptr, 1);
}

void loop() {
  pollSerial();

  if (diag_done) { diag_done = false; encPrintMagnet(); }
  if (zero_done) { zero_done = false;
                   Serial.printf("# encoder zeroed, theta = %.3f rad\n", th); }
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
//  speed-limited. The 60T conversion preserves the prior linear speed limits.
//
//  LOST STEPS LOOK EXACTLY LIKE BAD TUNING. After any crash, check that the
//  reported x = 0 is still the physical centre. If it has drifted, you are
//  losing steps: lower amax/vmax, raise Vref, or raise the motor supply
//  voltage. Note the rotor itself is not free - an illustrative 87 g.cm^2 through a 19.10 mm
//  pitch radius reflects to ~0.024 kg of apparent cart mass. Actual inertia
//  has not been measured.
// ============================================================================
