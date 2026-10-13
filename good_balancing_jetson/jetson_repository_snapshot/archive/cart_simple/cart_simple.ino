// Sine-wave cart motion on a GT2 belt linear actuator.
//
// Driver : SparkFun Big Easy Driver (A4988), BED-CART wiring
// Motor  : 200 full steps/rev (1.8 deg)
// Pulley : 60 tooth GT2 -> 60 * 2 mm = 120 mm of belt per revolution
//
// The carriage follows  x(t) = amplitude * sin(2*pi*frequency*t)  around the
// position it was at on reset. "amp 100" means 100 mm each way, 200 mm total
// sweep. Type commands at 115200 baud, one per line. "help" lists them.
//
// No libraries needed.

// ---- Pins (BED-CART) -------------------------------------------------------
const int STEP_PIN = 18;  // D25
const int DIR_PIN  = 19;  // D26
const int EN_PIN   = 27;  // D27, active LOW: LOW = coils energised
// MS1/MS2/MS3 are not wired. The Big Easy Driver's on-board pull-ups hold them
// high, which is the board default of 1/16 microstepping.

// ---- Mechanics -------------------------------------------------------------
const float FULL_STEPS_PER_REV = 200.0f;
const int   MICROSTEPS         = 16;      // board default, MS pins left open
const float MM_PER_REV         = 120.0f;  // 60 teeth * 2 mm GT2 pitch
const float STEPS_PER_MM       = (FULL_STEPS_PER_REV * MICROSTEPS) / MM_PER_REV;  // 26.667

// ---- Limits ----------------------------------------------------------------
const float MAX_STEP_RATE_HZ = 10000.0f;  // ceiling for this software stepper
const float MAX_AMP_MM       = 400.0f;    // keep the carriage on the rail
const float MAX_FREQ_HZ      = 10.0f;
const float AMP_SLEW_MMS     = 25.0f;     // how fast the sine grows or shrinks
const float CENTER_SLEW_MMS  = 25.0f;     // return-to-centre speed
const unsigned long TICK_US  = 200;       // setpoint update period (5 kHz)

const unsigned long MIN_STEP_US = (unsigned long)(1000000.0f / MAX_STEP_RATE_HZ);

// ---- State -----------------------------------------------------------------
double phase = 0.0;          // radians, wrapped to [0, 2*pi)
float  ampCmd = 50.0f;       // commanded amplitude, mm each way
float  ampNow = 0.0f;        // actual amplitude, ramps toward ampCmd
float  freqHz = 0.25f;
bool   running = false;
bool   stopping = false;     // shrinking to zero, then halt
long   posSteps = 0;         // current position, steps from centre
long   targetSteps = 0;
long   holdSteps = 0;        // where to sit when not running
int    lastDir = 0;

unsigned long lastTick = 0;
unsigned long lastStep = 0;
unsigned long stepInterval = MIN_STEP_US;

char line[64];
size_t lineLen = 0;

// ---- Stepping --------------------------------------------------------------
void stepOnce(int dir) {
  if (dir != lastDir) {
    digitalWrite(DIR_PIN, dir > 0 ? HIGH : LOW);
    delayMicroseconds(5);  // DIR setup time before the pulse
    lastDir = dir;
  }
  digitalWrite(STEP_PIN, HIGH);
  delayMicroseconds(3);    // A4988 needs at least 1 us; 3 is comfortable
  digitalWrite(STEP_PIN, LOW);
  posSteps += dir;
}

float peakSpeedMms(float amp, float f) { return 2.0f * PI * f * amp; }

// ---- Setpoint --------------------------------------------------------------
void updateSetpoint(float dt) {
  if (running) {
    phase += 2.0 * PI * (double)freqHz * (double)dt;
    while (phase >= 2.0 * PI) phase -= 2.0 * PI;

    float goal = stopping ? 0.0f : ampCmd;
    float maxChange = AMP_SLEW_MMS * dt;
    if (ampNow < goal) ampNow = min(goal, ampNow + maxChange);
    else if (ampNow > goal) ampNow = max(goal, ampNow - maxChange);

    if (stopping && ampNow <= 0.0f) {
      running = false;
      stopping = false;
      phase = 0.0;
      holdSteps = 0;
      Serial.println("stopped at centre");
    }

    targetSteps = lroundf(ampNow * sinf((float)phase) * STEPS_PER_MM);
    // Rate follows the sine's own slope, capped at the software ceiling.
    float v = fabsf(2.0f * PI * freqHz * ampNow * cosf((float)phase));
    float rate = constrain(v * STEPS_PER_MM, 1.0f, MAX_STEP_RATE_HZ);
    stepInterval = max(MIN_STEP_US, (unsigned long)(1000000.0f / rate));
  } else {
    targetSteps = holdSteps;
    stepInterval = max(MIN_STEP_US,
                       (unsigned long)(1000000.0f / (CENTER_SLEW_MMS * STEPS_PER_MM)));
  }
}

// ---- Commands --------------------------------------------------------------
void printStatus() {
  Serial.printf("running=%d amp_cmd=%.1fmm amp_now=%.1fmm freq=%.3fHz "
                "pos=%.2fmm peak=%.1fmm/s enabled=%d\n",
                running ? 1 : 0, ampCmd, ampNow, freqHz,
                posSteps / STEPS_PER_MM, peakSpeedMms(ampCmd, freqHz),
                digitalRead(EN_PIN) == LOW ? 1 : 0);
}

bool checkSpeed(float amp, float f) {
  float rate = peakSpeedMms(amp, f) * STEPS_PER_MM;
  if (rate > MAX_STEP_RATE_HZ) {
    Serial.printf("rejected: peak %.0f mm/s needs %.0f steps/s, ceiling is %.0f. "
                  "Lower amp or freq.\n",
                  peakSpeedMms(amp, f), rate, MAX_STEP_RATE_HZ);
    return false;
  }
  return true;
}

void setAmp(float mm) {
  if (mm < 0.0f || mm > MAX_AMP_MM) {
    Serial.printf("amp must be 0..%.0f mm\n", MAX_AMP_MM);
    return;
  }
  if (!checkSpeed(mm, freqHz)) return;
  ampCmd = mm;
  Serial.printf("amp = %.1f mm each way (%.1f mm sweep), peak %.1f mm/s\n",
                ampCmd, 2 * ampCmd, peakSpeedMms(ampCmd, freqHz));
}

void setFreq(float hz) {
  if (hz <= 0.0f || hz > MAX_FREQ_HZ) {
    Serial.printf("freq must be >0 and <=%.0f Hz\n", MAX_FREQ_HZ);
    return;
  }
  if (!checkSpeed(ampCmd, hz)) return;
  freqHz = hz;
  Serial.printf("freq = %.3f Hz (period %.2f s), peak %.1f mm/s\n",
                freqHz, 1.0f / freqHz, peakSpeedMms(ampCmd, freqHz));
}

void handleCommand(char *cmd) {
  float a, f;

  if (!strcmp(cmd, "")) return;

  if (sscanf(cmd, "sine %f %f", &a, &f) == 2) {
    if (!checkSpeed(a, f)) return;
    setAmp(a);
    setFreq(f);
    if (!running) handleCommand((char *)"start");
    return;
  }
  if (sscanf(cmd, "amp %f", &a) == 1) { setAmp(a); return; }
  if (sscanf(cmd, "freq %f", &f) == 1) { setFreq(f); return; }

  if (!strcmp(cmd, "start") || !strcmp(cmd, "run")) {
    if (!checkSpeed(ampCmd, freqHz)) return;
    if (posSteps != 0) {
      Serial.println("not at centre; run 'center' first");
      return;
    }
    digitalWrite(EN_PIN, LOW);
    stopping = false;
    running = true;
    Serial.printf("running: %.1f mm each way at %.3f Hz, ramping up\n", ampCmd, freqHz);
    return;
  }
  if (!strcmp(cmd, "stop")) {
    if (running) { stopping = true; Serial.println("ramping down to centre"); }
    else Serial.println("already stopped");
    return;
  }
  if (!strcmp(cmd, "halt")) {
    running = false; stopping = false; ampNow = 0.0f; phase = 0.0;
    holdSteps = posSteps;
    Serial.println("halted in place");
    return;
  }
  if (!strcmp(cmd, "center") || !strcmp(cmd, "centre")) {
    running = false; stopping = false; ampNow = 0.0f; phase = 0.0;
    holdSteps = 0;
    Serial.println("returning to centre");
    return;
  }
  if (!strcmp(cmd, "zero")) {
    if (running) { Serial.println("stop first"); return; }
    posSteps = 0; holdSteps = 0;
    Serial.println("centre set here");
    return;
  }
  if (!strcmp(cmd, "enable"))  { digitalWrite(EN_PIN, LOW);  Serial.println("driver enabled");  return; }
  if (!strcmp(cmd, "disable")) {
    running = false; stopping = false; ampNow = 0.0f;
    digitalWrite(EN_PIN, HIGH);
    Serial.println("driver disabled, position reference lost");
    return;
  }
  if (!strcmp(cmd, "status")) { printStatus(); return; }
  if (!strcmp(cmd, "help")) {
    Serial.println(
      "sine <mm> <hz>  set both and start, e.g. 'sine 100 0.25'\n"
      "amp <mm>        amplitude each way, ramps smoothly\n"
      "freq <hz>       frequency, applies immediately\n"
      "start / stop    stop ramps the amplitude down to centre\n"
      "halt            stop where it is\n"
      "center          slew back to centre\n"
      "zero            call the present position centre\n"
      "enable/disable  driver coils\n"
      "status          print current state");
    return;
  }
  Serial.printf("unknown command: %s (try 'help')\n", cmd);
}

void readSerial() {
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\r') continue;
    if (c == '\n') {
      line[lineLen] = '\0';
      handleCommand(line);
      lineLen = 0;
    } else if (lineLen < sizeof(line) - 1) {
      line[lineLen++] = c;
    }
  }
}

// ---- Arduino ---------------------------------------------------------------
void setup() {
  Serial.begin(115200);

  pinMode(STEP_PIN, OUTPUT);
  pinMode(DIR_PIN, OUTPUT);
  pinMode(EN_PIN, OUTPUT);

  digitalWrite(STEP_PIN, LOW);
  digitalWrite(DIR_PIN, LOW);

  digitalWrite(EN_PIN, LOW);  // enable the driver (active low)
  delay(10);

  lastTick = micros();
  lastStep = lastTick;

  Serial.printf("\nsine cart ready. %.3f steps/mm, ceiling %.0f steps/s (%.0f mm/s)\n",
                STEPS_PER_MM, MAX_STEP_RATE_HZ, MAX_STEP_RATE_HZ / STEPS_PER_MM);
  Serial.println("this position is centre. type 'sine 100 0.25' or 'help'");
}

void loop() {
  readSerial();

  unsigned long now = micros();
  if (now - lastTick >= TICK_US) {
    updateSetpoint((now - lastTick) * 1e-6f);
    lastTick = now;
  }

  long error = targetSteps - posSteps;
  // Near the sine's turning points the commanded rate drops to nothing, so let
  // the tracker fall back to full speed whenever it is more than a step behind.
  unsigned long interval = (error > 2 || error < -2) ? MIN_STEP_US : stepInterval;

  if (error != 0 && (now - lastStep) >= interval) {
    stepOnce(error > 0 ? 1 : -1);
    lastStep = now;
  }
}
