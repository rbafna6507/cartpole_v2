// ============================================================================
//  i2c_scan.ino -- continuous AS5600 readout.
//
//  Streams forever so you can move the magnet with one hand and watch the
//  numbers with the other. Send any character to reset the span tracker.
//
//  arduino-cli compile --fqbn esp32:esp32:esp32 i2c_scan
//  arduino-cli upload  --fqbn esp32:esp32:esp32 -p /dev/cu.usbserial-0001 i2c_scan
//  arduino-cli monitor -p /dev/cu.usbserial-0001 --config baudrate=115200
//
//  WHAT TO AIM FOR
//    agc  : 128 is MAX GAIN - the chip is straining and the field is too weak.
//           Move the magnet closer. You want it to fall to roughly 40-90.
//           If it drops near 0, you are too close.
//    span : spin the magnet one full turn. span should cover 0..4095. If it
//           only covers part of that, the magnet is off-centre from the chip,
//           or it is axially rather than diametrically magnetised.
//    MD   : magnet detected.  ML = too weak.  MH = too strong.
// ============================================================================

#include <Wire.h>

#define PIN_SDA 21
#define PIN_SCL 22
#define ADDR    0x36

int rmin = 9999, rmax = -1;

int rd(uint8_t reg) {
  Wire.beginTransmission(ADDR);
  Wire.write(reg);
  if (Wire.endTransmission(false) != 0) return -1;
  if (Wire.requestFrom((uint8_t)ADDR, (uint8_t)1) != 1) return -1;
  return Wire.read();
}

void setup() {
  Serial.begin(115200);
  delay(800);
  Serial.println("\n=== AS5600 live ===");

  pinMode(PIN_SDA, INPUT); pinMode(PIN_SCL, INPUT);
  delay(20);
  Serial.printf("idle levels: SDA=%d SCL=%d (both should be 1)\n",
                digitalRead(PIN_SDA), digitalRead(PIN_SCL));

  Wire.begin(PIN_SDA, PIN_SCL, 400000);
  delay(50);

  Serial.println("scanning...");
  for (uint8_t a = 1; a < 127; a++) {
    Wire.beginTransmission(a);
    if (Wire.endTransmission() == 0) {
      Serial.printf("  device at 0x%02X%s\n", a,
                    a == 0x36 ? "  <- AS5600" :
                    a == 0x06 ? "  <- MT6701, different chip" : "");
    }
    delay(1);
  }
  Serial.println("streaming. move the magnet. any key resets span.\n");
}

void loop() {
  if (Serial.available()) {
    while (Serial.available()) Serial.read();
    rmin = 9999; rmax = -1;
    Serial.println("-- span reset --");
  }

  int hi = rd(0x0C), lo = rd(0x0D), agc = rd(0x1A), st = rd(0x0B);
  if (hi < 0 || lo < 0 || agc < 0 || st < 0) {
    Serial.println("no response");
    delay(500);
    return;
  }

  int raw = ((hi & 0x0F) << 8) | lo;
  if (raw < rmin) rmin = raw;
  if (raw > rmax) rmax = raw;

  // AGC as a bar, so you can see it move without reading digits
  char bar[9];
  int fill = agc * 8 / 128;
  if (fill > 8) fill = 8;
  for (int i = 0; i < 8; i++) bar[i] = (i < fill) ? '#' : '.';
  bar[8] = 0;

  const char *verdict = (agc >= 120) ? " MAX-GAIN, move magnet CLOSER"
                      : (agc <= 8)   ? " min gain, magnet too close"
                                     : " ok";

  Serial.printf("raw=%4d  ang=%6.1f deg  agc=%3d [%s]%s  span=%d..%d (%d)%s%s%s\n",
                raw, raw * 360.0 / 4096.0, agc, bar, verdict,
                rmin, rmax, rmax - rmin,
                (st & 0x20) ? "  MD" : "  NO-MAGNET",
                (st & 0x10) ? " ML-weak"   : "",
                (st & 0x08) ? " MH-strong" : "");
  delay(150);
}
