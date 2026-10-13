# Validation and limits

Validated on 2026-09-24. This package has not been flashed or physically tested here.

- Arduino CLI compiled for `teensy:avr:teensy41:usb=serial`, Teensy core 1.62, toolchain 15.2.1. Final build: 68,244 bytes code, 37,048 bytes flash data; RAM1 variables 56,928 bytes.
- Nine Python unit/integration tests passed, including synthetic dynamics recovery, calibration limits, timestamp and sampling-gap rejection, capture persistence, and a mocked guided four-move experiment.
- Native mocked firmware tests passed: positive/negative motion settling, command bounds, missing home reference, host timeout, foreground stall, raw encoder loss, serial backpressure, shared-enable behavior, no Z pulses, hold/release detection and micros rollover.
- These mocks do not validate physical wiring, pulse timing on a scope, real USB buffering, actual motor torque, mechanical clearance, sensor accuracy or braking distance. The Teensy build validates compilation, not those hardware properties.

Reproduce Python tests from the directory above this package:

```bash
python -m unittest discover -s teensy_pendulum_characterization/tests -v
```

Reproduce native logic tests with a C++17 compiler:

```bash
g++ -std=c++17 -DARDUINO_TEENSY41 -DCHARACTERIZATION_NATIVE_TEST -Iteensy_pendulum_characterization/tests/native teensy_pendulum_characterization/tests/native/firmware_test.cpp -o /tmp/char_fw_test
/tmp/char_fw_test
/tmp/char_fw_test rollover
```

No policy has been trained with this package, no camera/Ethernet controller has been implemented, and no new physical parameters have been inferred before collecting your current assembly's measurements.
