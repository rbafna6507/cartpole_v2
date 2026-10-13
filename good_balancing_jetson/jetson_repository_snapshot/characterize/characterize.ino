// Free-swing pendulum characterization for ESP32 + AS5600.
// Commands (921600 baud): ARM, STOP, STATUS, HELP
// Keep the cart mechanically fixed and motors off during this test.

#include <Arduino.h>
#include <Wire.h>
#include "quiet_motion.h"

#define SDA_PIN 21
#define SCL_PIN 22
#define AS5600_ADDR 0x36
#define REG_STATUS 0x0B
#define REG_RAWANGLE 0x0C
#define REG_AGC 0x1A
#define SAMPLE_HZ 500
#define MAX_CAPTURE_MS 45000UL
#define START_SPEED_RAD_S 0.18f
#define MIN_CAPTURE_MS 7000UL
#define ENC_INVERT 0

enum CaptureState { IDLE, ARMED, RECORDING };
CaptureState state = IDLE;
int32_t turnsTicks = 0;
int16_t lastRaw = 0;
bool haveRaw = false;
uint32_t sequenceNo = 0, i2cErrors = 0;
uint32_t armedAt = 0, startedAt = 0, lastSampleUs = 0;
QuietMotion quietMotion;
float previousTheta = 0, filteredSpeed = 0;

int readReg8(uint8_t reg) {
  Wire.beginTransmission(AS5600_ADDR); Wire.write(reg);
  if (Wire.endTransmission(false) != 0) return -1;
  if (Wire.requestFrom((uint8_t)AS5600_ADDR, (uint8_t)1) != 1) return -1;
  return Wire.read();
}

int readRaw() {
  Wire.beginTransmission(AS5600_ADDR); Wire.write(REG_RAWANGLE);
  if (Wire.endTransmission(false) != 0) return -1;
  if (Wire.requestFrom((uint8_t)AS5600_ADDR, (uint8_t)2) != 2) return -1;
  return ((Wire.read() << 8) | Wire.read()) & 0x0fff;
}

float updateAngle(int raw) {
  if (!haveRaw) { lastRaw = raw; haveRaw = true; }
  int d = raw - lastRaw;
  if (d > 2048) d -= 4096;
  if (d < -2048) d += 4096;
  turnsTicks += d; lastRaw = raw;
  float a = turnsTicks * (2.0f * PI / 4096.0f);
#if ENC_INVERT
  a = -a;
#endif
  return a;
}

void endCapture(const char *reason) {
  Serial.printf("END %s %lu %lu\n", reason,
                (unsigned long)(millis() - startedAt), (unsigned long)i2cErrors);
  state = IDLE;
}

void handleCommand(String s) {
  s.trim(); s.toUpperCase();
  if (s == "ARM") {
    state = ARMED; armedAt = millis(); startedAt = 0;
    quietMotion.reset();
    sequenceNo = i2cErrors = 0; filteredSpeed = 0; haveRaw = false;
    turnsTicks = 0; previousTheta = 0; lastSampleUs = 0;
    Serial.println("ARMED pull pendulum aside, hold briefly, then release");
  } else if (s == "STOP") {
    if (state == RECORDING) endCapture("host_stop"); else state = IDLE;
  } else if (s == "STATUS") {
    Serial.printf("STATUS %d %lu %lu\n", (int)state,
                  (unsigned long)sequenceNo, (unsigned long)i2cErrors);
  } else if (s == "HELP") {
    Serial.println("COMMANDS ARM STOP STATUS HELP");
  }
}

void setup() {
  Serial.begin(921600); Serial.setTxBufferSize(4096);
  Wire.begin(SDA_PIN, SCL_PIN, 400000); Wire.setTimeOut(20);
  delay(200);
  Serial.println("READY cartpole pendulum characterizer v2");
  Serial.println("QUIET <=1 degree peak-to-peak for 3 seconds; minimum capture 7 seconds");
  Serial.println("FIELDS D seq,t_us,dt_us,raw,ticks,theta,omega,agc,status,i2c_errors");
}

void loop() {
  while (Serial.available()) {
    String s = Serial.readStringUntil('\n');
    handleCommand(s);
  }

  // The hard timeout must also work when encoder reads fail continuously.
  if (state == RECORDING && (uint32_t)(millis() - startedAt) >= MAX_CAPTURE_MS) {
    endCapture("timeout");
    return;
  }

  const uint32_t periodUs = 1000000UL / SAMPLE_HZ;
  uint32_t nowUs = micros();
  if ((uint32_t)(nowUs - lastSampleUs) < periodUs) return;
  uint32_t dtUs = haveRaw ? (uint32_t)(nowUs - lastSampleUs) : periodUs;
  lastSampleUs = nowUs;

  int raw = readRaw();
  if (raw < 0) { i2cErrors++; quietMotion.reset(); return; }
  float theta = updateAngle(raw);
  float omega = (theta - previousTheta) / max(dtUs * 1e-6f, 1e-6f);
  previousTheta = theta;
  filteredSpeed += 0.12f * (omega - filteredSpeed);

  if (state == ARMED && fabsf(filteredSpeed) >= START_SPEED_RAD_S) {
    state = RECORDING; startedAt = millis(); quietMotion.reset(); sequenceNo = 0;
    Serial.printf("BEGIN %lu\n", (unsigned long)nowUs);
  }
  if (state != RECORDING) return;

  int agc = (sequenceNo % 25 == 0) ? readReg8(REG_AGC) : -1;
  int status = (sequenceNo % 25 == 0) ? readReg8(REG_STATUS) : -1;
  Serial.printf("D %lu,%lu,%lu,%d,%ld,%.7f,%.5f,%d,%d,%lu\n",
                (unsigned long)sequenceNo++, (unsigned long)nowUs,
                (unsigned long)dtUs, raw, (long)turnsTicks, theta,
                filteredSpeed, agc, status, (unsigned long)i2cErrors);

  uint32_t elapsed = millis() - startedAt;
  const bool quiet = quietMotion.update(turnsTicks, millis());
  if (elapsed >= MIN_CAPTURE_MS && quiet)
    endCapture("quiet");
}
