# J7-only wiring revision

Encoder initialization, scanning, reads, writes, and recovery all use Wire1 on SDA17/SCL16. All nine microstep GPIO writes/configurations removed. Regression now checks that stepper initialization never touches any former MS pin, including the repurposed I2C pair. Existing motor/EEPROM and display mock tests pass. No target compile or hardware test was performed for this revision; the target-build limitation below still applies. LCD and controller tuning are retained.

# LCD revision validation

- Existing motor/DDS/EEPROM host regression checks: passed after the LCD addition.
- Mock LCD checks: disconnected and idle text, stale-character clearing, fault and lost-host display together, maximum one glyph per service, and no writes to unchanged cells: passed.
- Target compile for this LCD revision: **not completed**. The current environment has no installed Teensy core, and Arduino CLI core download failed because network access was unavailable. Compile locally using README commands. No old binary is included with this revision.
- No hardware upload, screen orientation check, SPI timing measurement, or motor trial was performed. The mock cannot validate the vendor library or interrupt latency. Controller helpers and tuning are unchanged by the LCD work.

The following records the earlier firmware build, before the LCD addition; it is not evidence of compilation of this revision.

# Validation

## Target build: passed

Built the complete sketch with Arduino CLI and official PJRC Teensyduino **1.62.0**, using the included Wire 1.0 and EEPROM 2.0 libraries:

```bash
arduino-cli compile --fqbn teensy:avr:teensy41:usb=serial,speed=600,opt=o2std --output-dir build swingup
```

Result: successful ARM compile and link. Memory report:

```text
FLASH: code:73300, data:15544, headers:8432   free for files:8029188
RAM1: variables:33568, code:70344, padding:27960   free for local variables:392416
RAM2: variables:12416  free for malloc/new:511872
```

The build environment emitted a missing Linux USB udev-rules warning. This does not affect compilation; no hardware upload was attempted. It is not a macOS installation requirement.

## Focused host regression checks: passed

`python3 tests/test_port.py` (requires g++) extracts the actual port's pulse-generator code and runs it with mocked GPIO, time, timer, and EEPROM APIs. It checks:

- DDS step counts on all three axes at the original 7 us tick.
- Direction output and signed counts on reversal.
- No pulses/count changes while disabled.
- Stall shutdown and rejection of re-enable while its fault is pending.
- Motion lockout if timer initialization fails.
- All nine microstep output levels HIGH.
- EEPROM valid/invalid records, range checking, and corruption detection.

This mock test does not establish physical pulse widths, interrupt latency, USB behavior, or I2C behavior on a Teensy.

All **eight** original helper headers were compared byte-for-byte with the uploaded archive and remain unchanged. No controller retuning was performed.

## Not hardware-tested

No Teensy, driver, motor, or encoder was attached. Flashing, GPIO waveforms, real control-loop timing, EEPROM retention through power loss, cable reliability, and swing-up/balance stability still require verification on the rig. The existing Python host was not included in this upload, so host compatibility is based on retaining the commands and telemetry format, not an end-to-end host test.
