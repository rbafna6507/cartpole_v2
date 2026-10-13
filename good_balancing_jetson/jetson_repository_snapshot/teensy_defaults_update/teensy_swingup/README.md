# Swing-up and balance — Teensy 4.1

Port of the supplied working `swingup.zip`, firmware v33. Open `teensy_swingup/teensy_swingup.ino`; keep every `.h` file in that same folder. The complete Copperhill CAN/Ethernet assembly still programs as **Teensy 4.1**. This firmware uses USB serial, not CAN or Ethernet.

## What changed

- Motor and encoder signal wiring below; see ../PCB_WIRING.md for the added PCB connections. Encoder uses Wire1 on GPIO17/16. No microstep-control GPIOs; Big Easy Driver onboard pull-ups retain 1/16 stepping.
- ESP32 hardware timer/register writes replaced by Teensy `IntervalTimer` and `digitalWriteFast`. The DDS period stays **7 microseconds**.
- FreeRTOS task replaced by a **1 kHz foreground scheduler**. I2C remains outside interrupt context. Missed full control periods during energization fault; the step interrupt independently disables the drivers after a foreground stall exceeding 5 ms.
- Serial output uses a bounded, nonblocking-service queue. On queue overflow it drops whole frames; `stat` reports dropped USB frames. Input parsing is bounded so incoming traffic cannot indefinitely starve control.
- ESP32 Preferences replaced by Teensy EEPROM emulation. Only the upright reference is persisted, in bytes 0–7, with a validity tag and complemented value. Writes occur with motion disabled. Other runtime settings remain volatile, as in the upload.
- DIR changes pause that axis's pulse generation briefly to respect pulse completion and direction setup timing.

All eight shared controller/helper headers now match the attached ESP32 firmware byte for byte; only parameter defaults changed relative to this Teensy port. Swing-up, capture, balance, rail/spin recovery, estimator, tuning, command names, and CRC16 output format are retained. Startup remains disabled, centered at the physical position at reset; no automatic homing is added.

The supplied configuration still uses a 60-tooth GT2 pulley, 200-step motors, 1/16 microstepping, 5 mm screw lead, 300 mm configured travel, and the original 1.5 m/s maximum setting. The earlier 400 mm rail discussion has NOT been used to enlarge travel. Preserve these bounds until physical clearance is verified. Changing to a 12 V motor supply can reduce tracking performance even with identical firmware.

## Wiring

GPIO numbers below are Arduino/Teensy pin numbers. Copperhill contact labels follow the schematic mapping you provided; verify connector orientation against the actual assembly.

| Signal | Teensy GPIO | Copperhill contact |
|---|---:|---|
| CART STEP | 2 | J7_4 |
| CART DIR | 3 | J7_5 |
| LEFT / Z1 STEP | 4 | J7_6 |
| LEFT / Z1 DIR | 5 | J7_7 |
| RIGHT / Z2 STEP | 6 | J7_8 |
| RIGHT / Z2 DIR | 7 | J7_9 |
| All driver ENABLE inputs | 8 | J7_10 |
| Encoder SDA | 17 (Wire1 SDA) | J7_13 |
| Encoder SCL | 16 (Wire1 SCL) | J7_14 |
| Encoder supply | 3.3 V | J7_2 |
| Encoder GND and DIR | GND | J7_3 |
| Driver logic ground | GND | J7_3, same common GND |

This upload originally assigned ESP32 Z1 to 18/19 and Z2 to 16/17. The new assignment follows the PCB naming: **Z1 is LEFT, Z2 is RIGHT**. Both screws still receive the same velocity command.

Close the Big Easy Driver 3/5V jumper for 3.3 V logic and retain APWR as planned. Teensy GPIO is not 5 V tolerant. Do not connect driver VCC outputs to the Teensy 3.3 V rail. All grounds share the common reference. Motor supply connects to driver M+, and the Copperhill's designated 12V_IN if supplying that assembly; never to the bare Teensy VIN, 3V3, or GPIO pins.

Leave all driver MS1/MS2/MS3 pins unconnected. Remove their GPIO traces and selection jumpers from the planned PCB. The firmware no longer configures or writes microstep pins. Keep 1/16 in the mechanics: removing microstep control does not select full stepping. GPIO16/17 are reserved for encoder I2C. The reviewed PCB routes J6 to four limit switches and the MPU connector, but this firmware does not read those devices. Copperhill J5 remains unused. PCB connector J5 is a different connector; see ../PCB_WIRING.md.

Route encoder SDA to J7_13, SCL to J7_14, 3V3 to J7_2, and GND to J7_3; keep encoder DIR tied to GND. Ensure SDA and SCL have pull-ups to 3.3 V (typically 2.2–4.7 kOhm, unless already fitted on the encoder module). J7_1 is 5 V, not the encoder supply.

Verified against the [Copperhill carrier schematic](https://copperhilltech.com/content/teensy41_triple_can_ETH_rev_A.pdf) and [PJRC Wire port table](https://www.pjrc.com/teensy/td_libs_Wire.html). All reads, configuration, scan, and bus recovery now use Wire1. Flash this revision when moving SDA/SCL; the previous firmware used GPIO18/19. These are wiring/firmware changes; the KiCad file itself has not been edited.

Firmware holds ENABLE HIGH once setup starts. For a defined disabled state during reset, bootloader operation, or unplugging the controller, use an appropriate external pull-up on ENABLE to the driver-side 3.3 V logic supply. Support the height assembly whenever all drivers are disabled.

## Flash with Arduino IDE 2 on macOS

1. Install Arduino IDE 2 and open **Arduino IDE → Settings**.
2. Add this to **Additional Boards Manager URLs**:

   `https://www.pjrc.com/teensy/package_teensy_index.json`

3. Open **Boards Manager**, search `Teensy`, and install the PJRC Teensy package. This port was built with version **1.62.0**.
4. Extract this archive. Open **teensy_swingup/teensy_swingup.ino**. All headers must remain alongside it.
5. Select **Tools → Board → Teensy → Teensy 4.1**. Set **USB Type → Serial**, **CPU Speed → 600 MHz**, and **Optimize → Faster** (the `o2std` option used for validation). No extra third-party libraries are required.
6. For the first flash, remove motor power and support the height mechanism. Connect a **USB data cable to the Teensy's programming USB port**, not Ethernet or a USB host connector. Follow the Copperhill board's USB/external-power provisions; do not assume external power and USB may be paralleled without checking its power arrangement.
7. Select the Teensy port when available and click **Upload**. Teensy Loader handles programming. If it cannot reboot the board, or there is no port on the first upload, compile/Verify, then briefly press the **Program** button with Teensy Loader in Auto mode. Do not hold it down for a restore operation.
8. Once the sketch runs, select its new serial port. On macOS it is typically `/dev/cu.usbmodem...`, rather than the old ESP32 USB-UART device. Select **115200** and **Newline** in Serial Monitor. Close your Python host while using Serial Monitor; close Serial Monitor before reopening the host.

Teensy's native USB serial does not use the baud setting as a physical UART bitrate, but retaining 115200 keeps the existing host configuration consistent. Opening the port does not necessarily reset this board; send `params` or `stat` to query it. Every reply is deliberately wrapped as `@payload*CRC16`; commands are plain newline-terminated text.

Official instructions: [PJRC installation](https://www.pjrc.com/teensy/td_download.html) and [PJRC upload/Program button](https://www.pjrc.com/teensy/td_usage.html).

## Flash with arduino-cli

From the extracted archive directory:

```bash
arduino-cli core update-index --additional-urls https://www.pjrc.com/teensy/package_teensy_index.json
arduino-cli core install teensy:avr@1.62.0 --additional-urls https://www.pjrc.com/teensy/package_teensy_index.json
arduino-cli compile --fqbn teensy:avr:teensy41:usb=serial,speed=600,opt=o2std --output-dir "$PWD/build_teensy" "$PWD/teensy_swingup"
arduino-cli board list
```

Copy the Teensy port reported by `board list`, then upload, replacing the example port:

```bash
arduino-cli upload --fqbn teensy:avr:teensy41:usb=serial,speed=600,opt=o2std --port usb:2100000 --input-dir "$PWD/build_teensy" --verbose "$PWD/teensy_swingup"
```

If automatic reboot is unavailable, use Teensy Loader and briefly press Program as described above. The ESP32 FQBN and ESP32 flashing tools are no longer applicable. Do not rely on the Copperhill Ethernet/CAN connections to upload this sketch.

## First run

1. Place the cart at physical center before reset. Support the height stage. Confirm motor wiring, current limits, and common ground before applying motor power.
2. With drivers stopped, send `stat`, `params`, `mag`, and `enc`. Verify the AS5600 is detected and healthy.
3. Send `stop`, hold the pendulum hanging still, then send `zero`. Alternatively, hold it upright and send `upright`. Wait for `encoder_reference_saved 1`. The ESP32's saved reference does not transfer. Reboot and query `params` to confirm persistence. A compile-time fallback exists, but do not trust its angle reference on the new installation.
4. With motor power available, verify a small positive cart jog and both screw directions before running control. Repeated `v 0.02` commands jog the cart slowly; a single command expires after 250 ms and decelerates. Send `stop` afterward. Check displacement scale against a ruler. If direction is wrong, check wiring and the existing `CART_INVERT`, `Z_INVERT`, and `ENC_INVERT` definitions rather than changing gains.
5. Test your existing `bal` command while holding the pole near upright at center, then test `auto`. Keep the original host running for heartbeats. Successful compilation does not establish stability on the new hardware.

**Keepalive matters:** your original 1500 ms host timeout is retained. The host must send `ping` (or another valid command) more often than that; 250 ms is a practical interval. Serial Monitor alone will not sustain `auto`/`bal` unless you keep sending commands. Manual `v` requires updates within its separate 250 ms velocity watchdog. Do not remove these timeouts to make a bench test run unattended.

Your existing host's command and telemetry layout is preserved, but select the new USB port. The host source was not supplied, so hard-coded ESP32 port detection/reconnect behavior has not been tested.

## Validation and remaining hardware checks

See VALIDATION.md. These are source/build and host-side checks, not a physical swing-up test. Verify pulse timing with a scope/logic analyzer if available (7 us HIGH pulses, DIR setup at reversals), encoder I2C reliability on your cable, actual cart/screw direction, position scale, and motor tracking at 12 V. No limit switches or position feedback have been added: cart position is still inferred from emitted steps.

Port API references: [IntervalTimer](https://www.pjrc.com/teensy/td_timing_IntervalTimer.html), [Wire pins](https://www.pjrc.com/teensy/td_libs_Wire.html), [EEPROM](https://www.pjrc.com/teensy/td_libs_EEPROM.html).

## LCD status display

Targets the 240x240 ST7789 IPS display used by the [SK Pang/Copperhill carrier demo](https://github.com/skpang/Teensy41_240x240_LCD_CANFD_test). Uses the ST7735_t3 / ST7789_t3 library distributed with Teensyduino. LCD GPIO: CS 10, DC 9, MOSI 11, SCLK 13, RESET 32, backlight 33. These are reserved for the LCD; they do not conflict with the motor/encoder assignment above. If your screen is a different hardware revision, verify its wiring before using this display configuration. Rotation is the `setRotation(0)` call in status_display.h.

States: DISCONNECTED, IDLE, MANUAL, SWINGING UP, BALANCING, CALIBRATING, FAULT, RAIL_BRAKE, RAIL_RETURN, SPIN_BRAKE, SPIN_CENTER, SPIN_WAIT, BAL_BRAKE, BAL_CENTER. Recovery labels are the controller's existing phases. A fault always takes precedence over the disconnected label. Driver enable and host link are separate fields: idle does not necessarily imply drivers disabled.

Host connection means a nonempty USB command was received within 1.5 seconds, matching the existing watchdog. USB power alone does not count. The host should continue its existing periodic commands/keepalive. Disconnect during motion retains the existing fault-and-disable behavior. Encoder health reports recent successful reads, not independent magnet alignment validation. Cart position is the controller's step-count estimate, not a separate position sensor.

Screen snapshots update at 5 Hz. Refresh writes at most one opaque 12x16 character per foreground service, and only starts with at least 600 microseconds until the next control tick. No full-screen clear runs during control. This reduces blocking but is not a hardware timing guarantee; existing timing fault guards remain in force. Startup initializes the screen with drivers disabled. The display sends no motion commands and changes no tuning.

First check: power by USB with motor supply off. Expect DISCONNECTED and DRIVERS: DISABLED. Send `stat` periodically to show the host link; connect the encoder to check its status. Confirm screen orientation. Check real control timing on hardware before powered motion; this LCD revision has not been flashed or measured here. Full fault messages remain available in the serial log (LCD shows the first 40 characters).

## Move existing ESP32 wires

| Function | Old ESP32 GPIO | Teensy GPIO / supply | Copperhill contact |
|---|---|---|---|
| Cart STEP | 25 | 2 | J7_4 |
| Cart DIR | 26 | 3 | J7_5 |
| Left Z1 STEP | 18 | 4 | J7_6 |
| Left Z1 DIR | 19 | 5 | J7_7 |
| Right Z2 STEP | 16 | 6 | J7_8 |
| Right Z2 DIR | 17 | 7 | J7_9 |
| Shared ENABLE | 27 | 8 | J7_10 |
| Encoder SDA | 21 | 17 | J7_13 |
| Encoder SCL | 22 | 16 | J7_14 |
| Encoder power | 3V3 | 3V3 | J7_2 |
| Common ground | GND | GND | J7_3 |

Move wires with USB and motor power disconnected. No MS wires or J5 connections are needed. Carrier 12 V input remains the separate designated power connection; J6/J7-only refers to the signal and encoder wiring, not feeding 12 V through these headers.
