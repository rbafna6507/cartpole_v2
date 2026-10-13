// ESP32 Dev Module, Arduino ESP32 core 3.3.2, FastAccelStepper 1.2.8.
// Serial Monitor: 115200 baud, Newline. Commands: center, run 25 0.5, stop, !
// limits 1250 7500 = allowed mm/s and mm/s^2; check 25 2.2 = preview only.
// Amplitude is mm FROM CENTER (25 means 50 mm total travel); frequency is Hz.
#include <Arduino.h>
#include <FastAccelStepper.h>
#include <cstring>
#include "SineMotion.h"

namespace sm = sine_motion;
constexpr uint8_t STEP_PIN = 18, DIR_PIN = 19, ENABLE_PIN = 27;
constexpr bool INVERT_DIRECTION = true;
constexpr double DEFAULT_AMPLITUDE_MM = 25.0;
constexpr double DEFAULT_FREQUENCY_HZ = 0.5;
constexpr uint32_t SEGMENT_TICKS = TICKS_PER_S / 1000; // 1 ms samples
constexpr uint32_t LOOKAHEAD_TICKS = TICKS_PER_S / 62; // about 16 ms queued

FastAccelStepperEngine engine;
FastAccelStepper* cart = nullptr;
sm::Config wave = {DEFAULT_AMPLITUDE_MM, DEFAULT_FREQUENCY_HZ};
sm::Limits limits = {sm::MAX_SPEED_MM_S, sm::MAX_ACCEL_MM_S2};
int maxSegmentSteps = sm::MAX_STEPS_PER_SEGMENT;
bool active = false, centered = false, draining = false;
uint64_t segment = 0;
uint32_t tickRemainder = 0;
double finishAt = -1;

void halt(const char* reason) {
  if (cart) cart->forceStopAndNewPosition(0);
  active = false; centered = false; draining = false;
  Serial.println(reason);
  // Do not release shared ENABLE: the two height motors must keep holding.
}

// Stream absolute position samples into the hardware pulse queue. Bypassing
// moveTo()'s trapezoidal ramps preserves the requested sinusoidal trajectory.
// Absolute rounding avoids accumulating step-position error each cycle.
void fillQueue(bool start) {
  while (active && !draining && cart->ticksInQueue() < LOOKAHEAD_TICKS) {
    const double nextTime = (segment + 1) * sm::SEGMENT_SECONDS;
    const int32_t target = sm::positionSteps(wave, nextTime, finishAt);
    const int32_t delta = target - cart->getPositionAfterCommandsCompleted();
    if (labs(delta) > maxSegmentSteps) { halt("FAULT: excessive step demand; recenter."); return; }
    const uint32_t duration = SEGMENT_TICKS + tickRemainder;
    uint32_t actual = 0;
    const auto result = cart->moveTimed((int16_t)delta, duration, &actual, start);
    if (result == MOVE_TIMED_BUSY) return; // Retry without advancing phase.
    if (result != MOVE_TIMED_OK && result != MOVE_TIMED_EMPTY) {
      halt("FAULT: pulse queue error; recenter."); return;
    }
    if (start && result == MOVE_TIMED_EMPTY) {
      halt("FAULT: pulse queue underrun; recenter."); return;
    }
    tickRemainder = duration - actual; // Carry integer timer rounding forward.
    ++segment;
    if (finishAt >= 0 && nextTime >= finishAt + sm::RAMP_SECONDS)
      draining = true;
  }
}

bool number(const char* word, double& value) {
  if (!word) return false;
  char* end;
  value = strtod(word, &end);
  return end != word && *end == '\0' && isfinite(value);
}

void printLimits() {
  Serial.printf("Limits: speed=%.3f mm/s (%.1f RPM), acceleration=%.3f mm/s^2 (%.1f RPM/s).\n",
    limits.speedMmS, limits.speedMmS * 0.5,
    limits.accelerationMmS2, limits.accelerationMmS2 * 0.5);
  Serial.printf("Pulse-budget speed cap=%.3f mm/s; amplitude=0.5..135 mm; frequency=0.02..5 Hz.\n",
    sm::pulseSpeedLimit(maxSegmentSteps));
}

void printDemand(sm::Config c) {
  const double w = 2 * sm::PI_ * c.frequencyHz;
  const double v = c.amplitudeMm * w, a = v * w;
  Serial.printf("Steady peaks: %.2f mm/s (%.1f RPM), %.2f mm/s^2 (%.1f RPM/s), %.0f pulses/s.\n",
    v, v * 0.5, a, a * 0.5, v * sm::STEPS_PER_MM);
  Serial.printf("Ramp-inclusive bounds: %.2f mm/s, %.2f mm/s^2.\n",
    sm::speedBound(c), sm::accelerationBound(c));
}

void command(char* line) {
  char* cmd = strtok(line, " \t");
  if (!cmd) return;
  if (!strcmp(cmd, "limits")) {
    char* speed = strtok(nullptr, " \t");
    if (!speed) { printLimits(); return; }
    sm::Limits requested;
    char* accel = strtok(nullptr, " \t");
    if (!number(speed, requested.speedMmS) || !number(accel, requested.accelerationMmS2) ||
        strtok(nullptr, " \t") ||
        !sm::validLimits(requested, sm::pulseSpeedLimit(maxSegmentSteps))) {
      Serial.println("Use: limits <positive_mm/s> <positive_mm/s^2>; speed must fit the pulse budget.");
      printLimits(); return;
    }
    if (!cart || active || cart->isRunning()) {
      Serial.println("Stop before changing limits."); return;
    }
    limits = requested;
    printLimits();
  } else if (!strcmp(cmd, "stop")) {
    if (active && finishAt < 0) {
      // Start after already queued motion and after the startup ramp.
      finishAt = fmax(segment * sm::SEGMENT_SECONDS, sm::RAMP_SECONDS);
      Serial.println("Finishing smoothly at center (up to 4 seconds).");
    }
  } else if (!strcmp(cmd, "center")) {
    if (active || (cart && cart->isRunning())) {
      Serial.println("Stop before setting center."); return;
    }
    if (!cart) return;
    cart->setCurrentPosition(0);
    centered = true;
    Serial.println("Current physical position is now center. No homing movement.");
  } else if (!strcmp(cmd, "run") || !strcmp(cmd, "check")) {
    const bool preview = !strcmp(cmd, "check");
    sm::Config requested = {DEFAULT_AMPLITUDE_MM, DEFAULT_FREQUENCY_HZ};
    char* amp = strtok(nullptr, " \t");
    char* hz = strtok(nullptr, " \t");
    if ((amp && (!number(amp, requested.amplitudeMm) ||
                 !number(hz, requested.frequencyHz))) || strtok(nullptr, " \t")) {
      Serial.println("Use: run/check <amplitude_mm> <frequency_hz>");
      return;
    }
    // Avoid diagnostic printing while hardware is consuming the pulse queue.
    if (active || (cart && cart->isRunning())) {
      Serial.println("Stop before checking or starting another waveform."); return;
    }
    printDemand(requested);
    if (!sm::valid(requested, limits) ||
        sm::speedBound(requested) > sm::pulseSpeedLimit(maxSegmentSteps)) {
      Serial.println("Rejected: waveform exceeds amplitude, frequency, speed or acceleration limit.");
      printLimits(); return;
    }
    if (preview) { Serial.println("Accepted by software limits. No motion commanded."); return; }
    if (!cart || active || cart->isRunning() || !centered) {
      Serial.println("Requires stopped cart and confirmed physical center: center"); return;
    }
    wave = requested; segment = 0; tickRemainder = 0; finishAt = -1;
    draining = false; active = true;
    // Print before starting so USB transmission cannot delay initial queue fill.
    Serial.printf("Run: +/-%.3f mm, %.3f Hz, 2 s startup. stop = smooth finish; ! = halt.\n",
                  wave.amplitudeMm, wave.frequencyHz);
    fillQueue(false);
    if (active) cart->moveTimed(0, 0, nullptr, true);
  } else {
    Serial.println("Commands: center | run/check [amplitude_mm frequency_hz] | limits [mm/s mm/s^2] | stop | !");
  }
}

void setup() {
  // Shared enable is active LOW. Hold all motors; only the cart receives steps.
  const uint8_t quietPins[] = {16, 17, 18, 19};
  for (uint8_t pin : quietPins) { pinMode(pin, OUTPUT); digitalWrite(pin, LOW); }
  pinMode(ENABLE_PIN, OUTPUT); digitalWrite(ENABLE_PIN, LOW);
  Serial.setTxBufferSize(2048);
  Serial.begin(115200);
  engine.init();
  cart = engine.stepperConnectToPin(STEP_PIN);
  if (!cart) { Serial.println("FAULT: could not initialize step output."); return; }
  const uint32_t backendSteps = SEGMENT_TICKS / cart->getMaxSpeedInTicks();
  if (backendSteps < (uint32_t)maxSegmentSteps) maxSegmentSteps = backendSteps;
  if (limits.speedMmS > sm::pulseSpeedLimit(maxSegmentSteps))
    limits.speedMmS = sm::pulseSpeedLimit(maxSegmentSteps);
  cart->setDirectionPin(DIR_PIN, !INVERT_DIRECTION);
  cart->setAutoEnable(false); // Shared enable managed above, never auto-released.
  Serial.println("Cart sine ready. Physically center cart, then send: center");
  Serial.println("Then: run 25 0.5 | stop = smooth finish | ! = immediate halt");
  printLimits();
}

void loop() {
  if (!cart) { delay(10); return; }
  if (active && !draining) {
    if (!cart->isRunning()) halt("FAULT: pulse queue stopped; recenter.");
    else fillQueue(true);
  }
  if (active && draining && !cart->isRunning()) {
    active = false; draining = false;
    centered = cart->getCurrentPosition() == 0;
    Serial.println(centered ? "Finished at commanded center." : "FAULT: recenter before running.");
  }

  static char line[80];
  static uint8_t length = 0;
  static bool overflow = false;
  // Nonblocking, bounded parser; no parseFloat(), delay() or per-step printing.
  for (int i = 0; i < 32 && Serial.available(); ++i) {
    char c = Serial.read();
    if (c == '!') {
      halt("Halted. Physically recenter, then send: center");
      length = 0; overflow = true; // Discard the remainder of this line.
    } else if (c == '\n' || c == '\r') {
      if (!overflow && length) { line[length] = '\0'; command(line); }
      length = 0; overflow = false;
    } else if (length < sizeof(line) - 1) line[length++] = c;
    else overflow = true;
  }
}
