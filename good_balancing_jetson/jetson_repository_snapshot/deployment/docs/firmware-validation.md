# Firmware validation

Validation performed 2026-10-03 without a board connection, flashing or physical motion. Reference firmware under `/Users/rbafna/projects/cartpole/teensy_swingup_ethernet` and `/Users/rbafna/projects/cartpole/teensy_pendulum_characterization` was read only. Changes are confined to the new deployment output.

## Native behavior tests

Command: `sh tests/native/run.sh`, using host C++17, `-Wall -Wextra -Werror -pedantic`, AddressSanitizer and UndefinedBehaviorSanitizer. Observed exit 0. Output:

```
executor tests: 9 groups passed
hardware integration tests: boot/home/arm, DDS watchdog/lease, encoder, CRC, TCP ownership/budget and EEPROM passed
```

Executor groups exercise:

- No home/enable on boot, home without energizing, separate arm, stop invalidation and clear without restart.
- Observation-anchored expiry instead of receive-time renewal, latched deadline fault, and unchanged lease during state/info/stream traffic.
- Adversarial finite/range checks, uint32 overflow/sign syntax, invalid TTL, unknown kinds/legacy commands, extra/missing tokens, old/duplicate sequences, wrong session and future/stale/unemitted sample references.
- Ownership, passive readers, disconnect, encoder-invalid/stale rejection and immediately repeated-session rejection after stop/clear.
- Microsecond timestamp wrap, saved-reference-compatible theta coordinate, encoder angle wrap and bounded omega estimate.
- Six-second acceleration trajectory with repeated fresh actions, governed speed/acceleration/rail bounds, nonfinite carriage state fault, positive velocity target and convergent position target, and per-tick jerk bounds.
- Independent CRC fixture (`D1 state` CRC 0x3372), corruption, oversized discard/recovery, NUL and CR rejection.

The sketch integration harness includes the real `.ino`, executor and motor code with simulated GPIO, Wire, EEPROM, Ethernet and IntervalTimer at hardware boundaries. It observes zero boot pulses and no Z pulse throughout; home leaves enable HIGH; arm enables shared GPIO8; real DDS generates cart pulses only; pulse-side lease and stall cutoffs stop without another `loop()` call; pulse-side rail checking prevents the boundary pulse; raw-read failure and malformed active CRC stop; USB/TCP owners disconnect safely; a second TCP client is rejected; RX work stays within 128 bytes per loop; an active owner's full reply queue faults; failed encoder configuration prevents encoder validity; timer allocation failure remains locked against clear; and existing EEPROM reference loads at boot without overwrite. Transport stubs verify application logic; they do not measure the real network stack.

Tests were authored before the new core/sketch existed and first failed on the missing implementation. During integration, the independent stall watchdog correctly fired before a longer action deadline when foreground execution stopped. The expiry scenario was tightened to stall within 3 ms of a normally serviced deadline so it exercises the distinct lease cutoff rather than the earlier stall cutoff.

## Actual Teensy build

Command:

```
arduino-cli compile --fqbn teensy:avr:teensy41 \
  --build-path /private/tmp/cartpole-deployment-teensy-build \
  --output-dir /private/tmp/cartpole-deployment-teensy-output \
  firmware/deployment_executor
```

Installed toolchain: Arduino CLI 1.5.1, Teensy core 1.62.0, QNEthernet 0.37.0. Observed exit 0; native Ethernet and actual Teensy headers/linker were used. Memory report: flash code 145172 bytes, flash data 20664, headers 8240; RAM1 variables 30048, code 139864, padding 23976, free locals 330400; RAM2 variables 55744, free malloc/new 468544. Build artifacts remain under `/private/tmp` and are not required in the deployment source tree. `sh firmware/build.sh` reproduces compilation in a fresh temporary directory.

## Physical validation still required

There are no claimed bench measurements of 1 kHz execution jitter, worst-case QNEthernet/I2C work, interrupt latency, DIR/STEP widths, AS5600 noise/status/sign or fault-pin timing. A supervised logic-analyzer test must establish actual enable/STEP behavior, lease and stall reaction and Z pulse absence. Confirm active-low shared enable, external inhibit and enable pull-up through power/reset. Secure Z, confirm the current upright reference/polarity and center, measure the rail, verify carriage tracking with independent position feedback and confirm commissioned limits at progressively small commands.

Carriage state remains commanded_steps; missing steps/slip/backdrive cannot be detected. Disabling may allow coast or loss of Z holding torque. Software reserves do not prove physical stopping distance. No limit switches, cart encoder, IMU, Z travel bounds, internet exposure, remote authentication or unattended motion safety have been added. Retained fallback calibration/provisional assembly geometry require confirmation. Successful compilation and native tests do not validate physical hardware or the model.
