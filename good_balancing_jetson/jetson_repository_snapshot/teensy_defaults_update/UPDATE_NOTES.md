# Teensy default-parameter update

Based on the uploaded working Teensy package and uploaded ESP32 swingup firmware. The working Teensy pin assignments, stepping implementation, encoder transport, EEPROM reference store, command protocol, and screen implementation are preserved.

| Default | Previous Teensy | Updated, from ESP32 |
|---|---:|---:|
| pw | 7 | 6 |
| pc1 | -0.8 | -3 |
| pc2 | -1.2 | -4 |
| catch_da | 4 | 2 |
| ke | 8 | 4 |
| kpx | 80 | 40 |
| catch_a | 0.60 | 0.25 |
| catch_r | 3 | 2 |
| bw | 50 | 30 |
| jmax / default_jerk | 100 | 150 |

All eight shared controller/helper headers match the uploaded ESP32 versions byte for byte. Six were already identical. Only swing_controller.h and cart_mechanics.h needed replacing. The sole .ino edit corrects an obsolete microstep-control comment; executable .ino code is unchanged. README wiring notes were clarified.

The ESP32 header comment mentions a 270 mm span, but its actual rail default is 0.150 m (300 mm total travel). This update copies the actual numeric values; it does not infer a different rail limit from that comment. Verify available physical travel before running.

Validation passed: existing host motor-port and display regression suites. Screen source unchanged. No Arduino CLI or Teensy toolchain was available here, so target compilation and hardware operation are not claimed. Run the commands below locally. Query `params` after reboot; host commands can override startup defaults.

## Build and upload

From this extracted package directory (containing the teensy_swingup subdirectory):

```sh
arduino-cli compile \
  --fqbn teensy:avr:teensy41:usb=serial,speed=600,opt=o2std \
  --output-dir "$PWD/build_teensy" \
  "$PWD/teensy_swingup"

arduino-cli upload \
  --fqbn teensy:avr:teensy41:usb=serial,speed=600,opt=o2std \
  --port usb:2100000 \
  --input-dir "$PWD/build_teensy" \
  "$PWD/teensy_swingup"
```

If the Teensy port changes, obtain its current value with `arduino-cli board list`.

IMPORTANT: this is a defaults update. The new limit switches and MPU6050 are documented in PCB_WIRING.md but are not implemented in this firmware. Physical switches will not stop motion with this version.
