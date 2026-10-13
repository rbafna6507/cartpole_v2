# Cart-pole: ESP32 firmware + Mac host console

## Manual cart frequency test

Use the [frequency-test GUI](frequency_test/README.md) to choose peak-to-peak
travel and frequency, preview position/velocity/acceleration/jerk, and run the
cart manually. It uses a separate ESP32 test sketch. Swing-up auto-tuning is
paused during these tests.

## Run the swing-up sketch (125 mm arm, 60T pulley, 300 mm travel)

**v34:** startup now uses the [full-span hardware tuning preset](analysis/v33_span_tuning/recommended_settings.json):
`ke=4`, `kpx=40`, `kdx=2`, `pw=6`, `pz=0.85`, `pc1=-3`, `pc2=-4`,
`bw=30`, `catch_a=0.25`, `catch_r=2`, and `catch_da=2`.
Motion defaults are `vmax=vmax_s=vmax_b=1.5`, `amax_s=amax_b=25`,
`jmax=150`, and `spin_trip_rad_s=150`. Normal operating travel remains 270 mm.
This preset achieved three 30-second holds, with variable capture latency;
it is the supported full-span preset, not the experimental compact-span candidates.
Manual upright mode retains `bal_pw=8` and uses the shared cart poles.
`bw` remains adjustable from 0.1–100 Hz while stopped.
Upload v34 manually to apply these defaults; this source update does not flash the board.

v32 added a bounded startup kick from centered hanging rest, subject to the same
jerk and rail protection. Physical tuning results and per-trial settings are in
`/Users/sajivshah/Documents/InvertedPendulum/autonomous_tuning/20260918_resume/`.
The 60T pulley, 125 mm arm, and cart STEP25/DIR26 mapping are retained. `params`
should report `pulley_teeth 60`, `cart_mm_per_rev 120`, and `cart_steps_per_m 26666.67`.

`swingup/swingup.ino` runs on the ESP32; `cartpole.py` is its Mac console.
The swing-up cart pins are **STEP = GPIO25, DIR = GPIO26**.
Z1 uses **STEP = GPIO18, DIR = GPIO19**; Z2 uses **STEP = GPIO16 (RX2), DIR = GPIO17 (TX2)**.
The older sketches below retain their own wiring.
Place the cart at the **physical center** before power-up/reset. Support the
pendulum as needed. Startup loads the saved upright reference and assigns `x = 0` there;
there is **no homing movement**. The sketch boots idle with **all drivers disabled** and these cart limits:

| Setting | Default |
|---|---:|
| Total physical travel | 300 mm (±150 mm from startup center) |
| Hard speed ceiling (`vmax`) | 1.5 m/s (750 RPM) |
| Swing / balance operating caps (`vmax_s` / `vmax_b`) | 1.5 / 1.5 m/s |
| Near-upright approach speed / capture speed (`approach_v` / `catch_v`) | 0.3 / 0.3 m/s |
| Swing-up acceleration limit (`amax_s`) | 25 m/s² (12,500 RPM/s) |
| Balance/braking acceleration limit (`amax_b`) | 25 m/s² (12,500 RPM/s) |
| Manual acceleration limit (`amax_m`) | 0.5 m/s² |
| Automatic jerk limit (`jmax`) | 150 m/s³ (75,000 RPM/s²) |
| Manual jerk limit (`jmax_m`) | 10 m/s³ |
| Keyboard jog speed (`vman`) | 0.05 m/s |

The 60T pulley and 2 mm belt pitch give 120 mm/revolution and 26.666667 steps/mm
at 1/16 microstepping. At `jmax 150`, acceleration changes by at most
0.15 m/s² per 1 ms tick, taking approximately 167 ms from zero to 25 m/s².
A 7 µs pulse timer supports up to 71,429 steps/s (2.679 m/s pulse ceiling);
the configured 1.5 m/s limit requires 40,000 steps/s.
Manual jogging keeps its gentler acceleration and jerk limits.
`stop`, `off`, and faults stop pulses and **disable all three drivers**.
Startup drives the shared active-low ENABLE pin HIGH before serial delays,
I2C initialization or encoder zeroing. Support the height assembly while
motors are disabled. Firmware cannot control GPIO during the earlier reset/bootloader interval.
There are no `fast` or `slow` profiles; motion commands use the current limits.

### v26: prepare for capture, independently of the hard speed ceiling

`vmax_s` and `vmax_b` independently cap swing-up and balance; both are bounded by
`vmax`. Raising an unused hard ceiling does not change pumping or capture.
Both operating caps start at 1.5 m/s: reducing the entire swing phase prevented
energy buildup in many modeled cases. The approach to upright has its own slower policy.

On the incoming arc, `approach_angle=0.8` rad (46°) begins blending the energy
pump into balance feedback and reducing planned speed toward `approach_v=0.3` m/s.
Capture additionally requires speed below `catch_v=0.3` m/s, balance demand within
`catch_da=2` m/s² of the current acceleration, and a feasible 180 ms forecast.
The forecast checks jerk, speed, rail braking and angular divergence. It is a
model-based gate, not a guarantee of motor tracking. Acceleration always passes
through the shared jerk limiter, including handoff and return to a lower mode cap.

Changes require `stop` first. For example, `set vmax_s 0.8`, `set vmax_b 0.8`,
`set approach_v 0.3`, and `set catch_v 0.3`. The v26 trial used
`ke=8`, `kpx=80`, `kdx=2`, `phase_soft=2`, `pw=7`, `pz=0.85`;
v34 startup gains are listed above.
[Evidence, validation and remaining limitations](analysis/v26/README.md).
**v26 uploaded; firmware, defaults, IDLE and disabled output verified over serial. No physical motion trial yet.**

### User-set motion ceilings (v34)

Firmware enforces maximums of `spin_trip_rad_s 150`, `jmax 150`,
`amax_s 25`, `amax_b 25`, and `vmax`, `vmax_s`, `vmax_b` all 1.5.
Boot defaults match these. `bw` defaults to 30 Hz and is independently
tunable. The trial runner reapplies and verifies its recorded settings before motion.
Lower values remain manually configurable while stopped.

Trials require a usable encoder magnet, a known cart origin, and supervision.
Keep one serial connection open between trials: opening this board's port resets
its pulse-based position origin. Re-establish the origin after a reset; `home`
sets the current position to zero and does not physically seek the center.
Cart position is inferred from pulses and cannot detect all missed steps.

### Adjustable spin recovery (introduced in v29)

**Uploaded and serial-verified: trigger 50 rad/s, resume below 10 rad/s, bw 30 Hz; IDLE with drivers disabled.**

```text
stop
set spin_trip_rad_s 50
set spin_resume_rad_s 10
params
```

v29 defaults were 50 rad/s to trigger recovery and below 10 rad/s to resume once centered and stopped. Both values use the magnitude of filtered pendulum rate. Changes require IDLE and `0 < spin_resume_rad_s < spin_trip_rad_s`. Runtime changes last until reset; v30 startup defaults are 150/10. Messages and `get`/`params` report the active values. Manual `bal` retains its separate fall-and-return behavior.

### Encoder rate filtering (v28, included in v29)

The default `bw` is now **30 Hz**, up from 10 Hz. The same wrap-aware observer
still updates at 1 kHz. Quantized-sine tests at 1–5 Hz show rate-estimate phase
delay falling from 28–30 ms to about **9 ms**. This is filter delay only, not
measured end-to-end motor response. Higher bandwidth increases rate noise.
The 25 Hz telemetry logs cannot validate millisecond-scale sensor noise.

```text
stop
set bw 30
params
```

v28 accepts `bw` only in **0.1–100 Hz**, while stopped, and resets the estimator
state in the control task after a bandwidth change. v27 accepted `bw 500`, which
made the estimator diverge in the September 18 12:33 recording; that setting
must not be used. If an older board has already diverged, stop and reboot it to
clear the state before applying a valid bandwidth. Re-establish physical cart
center before a reset because startup assigns x=0 without homing.

Firmware and simulator defaults both use 30 Hz. Saved historical presets retain
their recorded bandwidth. Gains, motion limits, encoder reference, and pins are
unchanged by this revision. This change is compiled and tested offline; hardware
balance performance remains unverified.

### Quick upright calibration (v27)

**v27 uploaded and serial-verified.** With the arm physically vertical, use:

```text
stop
upright
```

Keep it still until `encoder reference saved` appears (about 0.4 s of steady
readings, with a 5 s timeout). This records the present encoder count as
`theta=0` for balance, capture and telemetry, and resets the estimator.
It does not enable the motors. After the saved acknowledgment, `stat` should
show an angle close to zero. If the cart is physically centered, `home` then
`bal` starts an upright-only trial.

- `upright` averages a still vertical reading, handling the raw count wrap.
- `upright 3769` sets a known count directly; **3769 is only an example**.
  Counts must be integers from 0 through 4095.
- `zero` is for the arm **hanging down**. It records down and updates the
  upright target by half a turn (2048 counts), with the same stillness check.
  Do not use `zero` while the arm is upright; use `upright` instead.
- `home` resets cart position only.

Both reference commands stop and disable every motor. Support the height
assembly. Motion is blocked during capture and saving; `stop` cancels an
unfinished capture. Invalid encoder readings cannot complete calibration.
The saved target survives reset and startup does not overwrite it from the
arm's boot position. A board without a saved reference falls back to the old
3953 count calibration until you explicitly use `upright` or `zero`.
`params` reports the live `encoder_upright_raw` and `encoder_reference_saved`.
If saving fails, the acknowledgment says the reference is active only until reset.

`bal` rejection now reports the measured/estimated angles, angular speed and
cart position to identify a failed start condition. Uniform 4096-count scaling
remains; these commands change the offset, not encoder nonlinearity.
The [original four-pose readings](encoder_calibration/125mm_20260917/selected_calibration.json)
remain an unchanged historical record.

### Pendulum spin failsafe

**v24 trips immediately above |θ̇| = 35 rad/s and releases below 10 rad/s. Reflash to apply it.**
`params` reports `spin_trip_rad_s 35` and `spin_resume_rad_s 10`.

The filtered angular-speed magnitude **above 35 rad/s** latches
`SPIN_BRAKE → SPIN_CENTER → SPIN_WAIT` in either rotation direction.
It monitors automatic swing-up, automatic balance, and automatic rail recovery.
The upright-only `bal` trial retains its separate fall-return-stop behavior.
There is no full-turn requirement, pendulum-angle gate, or quiet-time delay.

Pendulum control pauses while the cart brakes, then returns to its original
center at up to **0.10 m/s**, with a **0.5 m/s²** return acceleration target and
the existing jerk limit. Braking still uses the normal motion/rail protections.
SWINGUP resumes only once the cart is within **±3 mm** of center,
|cart velocity| ≤ 0.005 m/s, |cart acceleration| ≤ 0.1 m/s², and a valid
encoder estimate has **|θ̇| strictly below 10 rad/s**. Exactly 10 rad/s keeps
waiting. The separate thresholds prevent repeated switching near the trip rate.
Waiting can continue indefinitely; failure to center within 10 seconds faults
and disables the motors. Ordinary edge recovery still only returns inside the
270 mm operating region; this rate failsafe specifically returns to center.

Drivers remain enabled to hold center during recovery. `stop`/`off` cancel it
and disable all drivers immediately. Repeated `auto`, `bal`, and jog commands
cannot bypass an active recovery. `stat` shows its phase, current rate, and
release threshold.
There is no homing or direct cart-position measurement; the center reference
still relies on commanded steps and can be wrong after physical slipping.

### Rail recovery

The physical ends are at ±150 mm from the startup center. Normal operation may
use the central **270 mm (±135 mm)**. Entering the last 15 mm at either end
starts `RAIL_BRAKE`: pendulum control pauses while outward motion decelerates.
Predictive braking can start earlier when velocity and acceleration require it;
it aims to stop before ±135 mm. At 0.8 m/s with zero acceleration and jerk
60 m/s³, stopping requires about **92.4 mm**, so braking cannot wait for the
last 15 mm at full speed.

Braking now finishes with both speed ≤0.005 m/s and acceleration ≤0.1 m/s²
before `RAIL_RETURN` requests an inward speed up to 0.15 m/s and
acceleration up to 1.5 m/s² (or lower configured limits), still jerk limited.
The stopping prediction includes the final ramp of acceleration back to zero.
Automatic operation resumes SWINGUP inside **±130 mm**, moving inward or
nearly stopped with inward acceleration, only once |speed| ≤0.155 m/s,
|acceleration| ≤1.5 m/s² and the braking latch has cleared. This prevents
handing swing-up a fast, strongly accelerating return from the rail.
There is no center-seeking or dwell. Recovery can finish farther inside if the
predictive stop completed there. A `# rail handoff` event records x, v and a.
[Recovery checks and compact swing-up tuning](analysis/rail_recovery_v22.md).
Manual recovery resumes MANUAL with a zero velocity target. Held jog commands
are ignored during recovery; `stop` always cancels recovery and disables all
drivers. Recovery never resets the position reference. It times out to a
disabled fault after 8 s.

The independent fault boundary remains ±140 mm. Position is inferred from
commanded steps, not sensed at the ends; missed steps or manual movement can
invalidate it. These are software margins, not physical endstop detection.

Close other serial programs before uploading. Reset/upload releases the shared
driver enable, so support the height assembly. From Terminal:

```bash
cd /Users/sajivshah/Documents/GitHub/cartpole_inverted_pendulum
python3 flash.py swingup
python3 cartpole.py --port /dev/cu.usbserial-0001
```

### Compile and flash any sketch

`flash.py` requires Python 3, `arduino-cli`, and the installed board core (see
setup below). It defaults to `swingup` and the `esp32:esp32:esp32` board. It
selects the single connected USB serial device; with multiple devices, specify
`--port`. Close the serial console or plotter first.

```bash
python3 flash.py                          # compile + flash swingup
python3 flash.py frequency_test           # any sketch in this repo
python3 flash.py characterize/characterize.ino
python3 flash.py swingup --port /dev/cu.usbserial-0001
python3 flash.py swingup --compile-only   # compile without accessing hardware
python3 flash.py /path/to/sketch --fqbn vendor:architecture:board --port PORT
```

You can invoke the script by its full path from any directory. Sketch names
resolve from the current directory first, then from this repo. Paths containing
spaces must be quoted. Use `--libraries DIR` for extra libraries or `--cli PATH`
for an Arduino CLI installation outside your PATH. The bundled FastAccelStepper
library is included automatically. `python3 flash.py --help` lists all options.

Every invocation builds in a fresh temporary directory and uploads that exact
build only if compilation succeeds. Temporary files are removed afterward.
The script does not open a serial monitor or send motion commands; the selected
firmware determines startup behavior after upload.

If Python dependencies are missing, install `pyserial` and `matplotlib` in your
Python environment. The port may change after reconnecting; check `/dev/cu.*`.
The [Arduino CLI guide](https://docs.arduino.cc/arduino-cli/getting-started)
describes the compile/upload commands.

Wait for `# ready`, then at the `>>>` prompt:

```text
params
mag
auto
```

`auto` enables the drivers, starts swing-up and switches to balance when eligible.
`stat` reports the ENABLE output: LOW means enabled, HIGH means disabled.
v9 fixes v8 GPIO initialization that could report energized while ENABLE stayed HIGH.
While plotting, type **`stop` + Enter in the terminal**, click **STOP / disable**,
or press **Space/Escape in the plot**. In the terminal, Escape or Space at an
empty prompt also sends stop immediately. `q` + Enter exits the plot and stops.
Other terminal commands, including `set`, work while plotting. A/D/W/S jogging
is available in the `control` plot window; terminal letters form commands.
Restart `cartpole.py` to load this console change. Reflash v15 for the serial fixes, calibrated upright, rail
behavior and limits. No profile command is needed.
After moving the disabled cart by hand, place it at physical center and issue
`home` before starting again; commanded steps cannot observe manual movement.
Height-axis limits remain 2 mm/s and 20 mm/s².

To change limits, first send `stop`, then for example:

```text
set vmax 0.8
set vmax_s 0.8
set vmax_b 0.8
set approach_v 0.3
set catch_v 0.3
set amax_s 12
set amax_b 12
set jmax 60
set rail 0.15
```

`rail` is **half** the total physical travel, in metres. These serial settings
last until reset. `home` only
relabels the stopped cart's current position as zero; use it only at the physical
center. It does not search for a limit switch.

Both JSON files record 300 mm total travel. The current arm is **125 mm / 11.05 g**
with **two 5.85 g end weights**, 22.75 g combined. The original 100 mm label
was incorrect; the user confirmed it referred to this same 125 mm arm.
JSON is reference metadata, not automatically loaded by the sketch.
The current controller uses **0.124 m effective length**, rounded from
**0.124455 m**, fitted from 20 same-side cycles at 5–20° across three of the
original pre-175 mm captures. Period is 0.707704 s; simulator equivalent
viscous damping is 0.913383 s⁻¹. Balance gains, energy normalization and
capture prediction all use the updated length. The pole choices and motion
limits remain unchanged. [125 mm fit and source records](pendulum_characterization/125mm_11p05g/2026-09-15/README.md).
The live encoder upright target is saved on the ESP32. Use `upright` after
re-indexing the shaft or encoder magnet.

The revised `swingup-175mm-20t-v15` firmware uses smooth phase feedback for energy
pumping, cart centering, a gentle startup bias, and a balance handoff that also
checks cart position, speed headroom, approach direction, and acceleration ramp time.
The capture window opens at 0.60 rad (34.4°), with angular rate below 3 rad/s;
balance acceleration applies on the handoff tick. The dropout angle is 0.80 rad.
The speed limiter anticipates velocity gained during acceleration ramp-down. It stops startup if it
commands over 30 mm cumulative travel for over 2 seconds without a 0.03 rad
pendulum response. This detects gross non-response; it does **not** detect every
missed step. Buzzing with little physical movement still needs a motor/driver
check and a fresh physical center reference. Verify manual motion first. Motion-limit regressions pass for this revision, but
recorded-state simulations remain imperfect: some cases settle in the ideal
model despite failing physically. See [current change assessment](analysis/rail_recovery_v10.md) and the earlier [v8 assessment](analysis/v8_assessment.md).

The console now saves `logs/run_<timestamp>_events.jsonl` alongside each CSV.
It records outgoing commands, firmware identity, parameter replies, diagnostic
messages and faults; `auto` and `bal` request a parameter snapshot before starting.
Cart position is inferred from pulses, and velocity/acceleration are commands.

### Ongoing log review

The five-minute Codex review is currently **paused for manual frequency tests**.
When enabled, it reviews new completed runs and updates
and tests repository candidates; applying settings and starting trials remain
manual. The controller does not learn online. See [tuning workflow and current
candidate](analysis/continuous_tuning.md). Keep Codex open and this Mac awake.

Host-side motion regression checks (no hardware movement):

```bash
clang++ -std=c++11 -Wall -Wextra -Werror tests/cart_motion_test.cpp -o /tmp/cart_motion_test
/tmp/cart_motion_test
clang++ -std=c++11 -O2 -Wall -Wextra -Werror tests/swing_controller_test.cpp -o /tmp/swing_controller_test
/tmp/swing_controller_test
python3 tests/test_console_events.py
```

## Free-swing recording: automatic stop

Recorded datasets are indexed in [pendulum_characterization/README.md](pendulum_characterization/README.md), grouped by physical configuration and date.

The `characterize` sketch ends with `END quiet` when the encoder stays within
**1° peak-to-peak for 3 seconds**, after at least 7 seconds of recording. It uses
unwrapped angle counts, so one-count encoder noise does not restart the quiet
timer. Motion above that band restarts the timer; missing samples or sensor
errors also restart it. The 45-second maximum capture remains a fallback.

Recompile and upload `characterize` to apply this change, then rerun the host:

```bash
arduino-cli compile --fqbn esp32:esp32:esp32 characterize
arduino-cli upload --fqbn esp32:esp32:esp32 -p /dev/cu.usbserial-0001 characterize
python3 characterize_pendulum.py --port /dev/cu.usbserial-0001
```

Close other serial consoles, support the height assembly, and keep the cart
fixed with motors off for the free-swing test. Start hanging, displace the
pendulum about 10–20°, and release. The Python recorder also sends `STOP` when
its own timeout expires or you press Ctrl-C.

Replay the two recordings that previously reached the 45-second timeout:

```bash
clang++ -std=c++11 -Wall -Wextra -Werror tests/quiet_motion_test.cpp -o /tmp/quiet_motion_test
/tmp/quiet_motion_test pendulum_characterization/175mm_14p2g/2026-09-15/pendulum_20260915_184743.csv pendulum_characterization/175mm_14p2g/2026-09-15/pendulum_20260915_184905.csv
```

With the new detector, those captures qualify as quiet at approximately
19.1 seconds and 25.1 seconds respectively. This is an offline replay, not a
new hardware measurement.

## Serial integrity and encoder recording (v15)

**Flash v15 and restart the updated console together.** They use **115200 baud**
and **25 Hz telemetry** (maximum 100 Hz). Replies carry a CRC-16 checksum,
including telemetry, raw encoder readings, parameters and STOP acknowledgments.
Dropped digits and minus signs are rejected even when the remaining text looks
like a valid number. Host commands remain newline-delimited text.

The console sends keepalives every 250 ms without depending on parameter replies.
Firmware disables active motion after 1.5 seconds without host commands. The
console sends STOP after a one-second telemetry gap, retries STOP/rate commands
once per second as needed, and requires a valid STOP acknowledgment and three
consecutive valid telemetry samples before permitting a new motion command.
It never replays a previous run. Startup follows the same STOP acknowledgment
check. A blocked `auto`/`bal` stays at the prompt instead of opening a dashboard.

Type **`link`** in the terminal (also while plotting) for the exact blocking
reason, valid sample rate, and checked/rejected frame counts. Malformed frames
and blocked requests are logged. Automatic recovery retries the same serial
path; a different port name needs a console restart with the new `--port`.
Check physical cart center after a USB reconnect/reset before restarting motion.

The 14:06–14:09 sessions show dropped characters, stale telemetry and one
`Device not configured` disconnect. Lower baud/traffic and chunked host reads
reduce serial load; checksums detect corruption rather than reconstruct missing
bytes. Physical USB reliability still requires a run on the hardware. See
[serial investigation](analysis/serial_integrity_v15.md).

For explicit diagnostics with old firmware only, the console accepts
`--legacy-serial --baud 230400` for v13/v14 (`921600` for older swing-up versions).
Unchecked legacy data cannot reliably detect dropped digits. The calibration
recorder now requires v15 checksummed replies, preserving the original captured
files. The live balance target is set by `upright` or `zero` in v27.

After flashing v15, close the console and run:

```bash
python3 calibrate_encoder.py --port /dev/cu.usbserial-0001
```

Hold the pendulum manually at each prompt and press Enter:

1. **0°** — hanging down.
2. **90°** — horizontal toward positive cart travel.
3. **180°** — upright.
4. **270°** — horizontal toward negative cart travel.

All motor drivers remain disabled. Each Enter records **one raw encoder reading**
and immediately saves it under `encoder_calibration/`. The JSON contains the
four reference angles and their raw counts, plus the original readings and
sensor diagnostic flags. Use `--samples 20` only if you want multiple readings
and a circular mean at each position.

The recorder does not reject motion, magnet flags, offsets, or quadrant spacing.
Unreadable serial replies are retried five times, then the same position prompt
remains available to retry. Earlier readings remain saved. These values form the
recorded calibration table; firmware correction is not automatically applied by the recorder. The current
v27 firmware can apply a recorded upright count with `upright <count>` as described above.
This serial update requires v15 firmware; older replies are rejected by default.

## Original cartpole_esp32 sketch

The remaining instructions describe the separate `cartpole_esp32` sketch,
including its older wiring and slow boot defaults. Its pulley conversion is also
60T; its linear limits are preserved. For the current 60T / 300 mm setup,
use the `swingup` commands above.

```
cartpole_esp32/cartpole_esp32.ino   flash this
cartpole.py                         run this
```

---

## 1. Wiring

Every STEP pin is deliberately in GPIO 0–31, because the firmware pulses all
three axes with a single register write. Don't relocate them above GPIO 31.

| ESP32 | Connects to | Notes |
|---|---|---|
| GPIO 25 | Cart driver — STEP | |
| GPIO 26 | Cart driver — DIR | |
| GPIO 16 | Z-left driver — STEP | |
| GPIO 17 | Z-left driver — DIR | |
| GPIO 18 | Z-right driver — STEP | |
| GPIO 19 | Z-right driver — DIR | |
| GPIO 27 | **ENABLE — all three drivers** | active LOW, wired in parallel |
| GPIO 21 | AS5600 SDA | |
| GPIO 22 | AS5600 SCL | |
| 3V3 | AS5600 VCC | module is a 3.3V part |
| GND | AS5600 GND **and its DIR pin** | DIR must not float |

Leave MS1/MS2/MS3 unconnected on **all three** drivers. The Big Easy Driver
pulls them high for its 1/16 default: 26.667 steps/mm on a 60T GT2 belt, 640
steps/mm on a 5 mm ball-screw lead.

The legacy sketch uses a 120 kHz configured timer and a 60T pulley. Its
configured fast profile remains 0.72 m/s and slow profile remains 0.05 m/s.
Use the swing-up sketch above for the current controller and safety settings.

All driver grounds tie to ESP32 ground. Motor power (24V) goes to **M+ only** —
the BED's VCC pin is a regulator *output*, not an input.

### Three things to do to the hardware first

**Solder the 3/5V jumper closed on all three Big Easy Drivers.** The A4988
needs V_IH ≥ 0.7×VDD, which is 3.5V when the board's logic rail is at its
default 5V. Your ESP32 drives 3.3V. It will half-work and drop steps
unpredictably, which is indistinguishable from a tuning problem.

**Set the current.** The BED uses 0.11 Ω sense resistors, so
`I = Vref / (8 × 0.11) = Vref / 0.88`. The ball-screw motors are 1.5A →
Vref = 1.32 V, measured at TP1 with the motor unplugged.

**Mind the air gap on the encoder magnet.** Aim for 1–2 mm, magnet rotation
axis exactly on the pivot axis. A 0.5 mm offset becomes a once-per-revolution
angle error the balancer will chase forever. The `mag` command reports AGC;
mid-range (~64) is good, railed at either end means bad gap or wrong magnet.

---

## 2. Flashing from a Mac, no Arduino IDE

```bash
brew install arduino-cli

arduino-cli config init
arduino-cli config add board_manager.additional_urls \
  https://espressif.github.io/arduino-esp32/package_esp32_index.json
arduino-cli core update-index
arduino-cli core install esp32:esp32
```

Find the board. The sketch folder name has to match the `.ino` name, which it
already does:

```bash
ls /dev/cu.*          # look for cu.usbserial-* / cu.wchusbserial-* / cu.SLAB_USBtoUART
```

Nothing there? You need the USB-UART driver for your dev board's bridge chip —
Silicon Labs CP210x or WCH CH34x, depending on which one it has. Check the chip
next to the USB connector.

Compile and upload:

```bash
arduino-cli compile --fqbn esp32:esp32:esp32 cartpole_esp32
arduino-cli upload  --fqbn esp32:esp32:esp32 -p /dev/cu.usbserial-0001 cartpole_esp32
```

If upload fails to sync, hold **BOOT** on the dev board, tap **EN**, release
BOOT, and rerun. Some boards need this every time; most auto-reset fine.

Watch boot output directly if you want:

```bash
arduino-cli monitor -p /dev/cu.usbserial-0001 --config baudrate=921600
```

---

## 3. Host console

```bash
pip3 install pyserial matplotlib
python3 cartpole.py
```

It finds the port itself. At the prompt:

| Command | What it does |
|---|---|
| `data` | live dashboard — angle, angular rate, cart position + velocity, commanded acceleration, pendulum energy, plus AGC / loop time / stream rate |
| `control` | **A** / **D** drive the cart left and right, **W** / **S** raise and lower the rail, **SPACE** stops, **Q** returns to the prompt |
| `auto` | swing-up, hands off to the balancer, dashboard open the whole time |
| `bal` | balance only — hold the pole upright and send this |
| `stop` | emergency stop |
| `slow` | crawl speeds — **the boot default** |
| `fast` | full speeds, needed for `bal` and `auto` |

Spacebar is a stop from inside any window, and it works whether the plot or the
terminal has focus. Ctrl-C at the prompt stops the board on the way out.

Every sample is written to `logs/run_<timestamp>.csv` automatically. `rate 250`
gives you a denser capture if you want to analyze a specific fall.

### Encoder angle crossings

The live angle plot keeps `0 = upright` and breaks its line at the ±π display
boundary. This avoids false vertical jumps when the arm swings past hanging
down. Telemetry and controller calculations are unchanged. Restart `cartpole.py`
to load the plotting fix; no firmware flash is required.

For a continuous angle plot and wrap-corrected angular-rate check from a saved
run (with its matching `_events.jsonl` sidecar):

```bash
python3 analysis/plot_encoder_run.py logs/run_<timestamp>.csv --output analysis/encoder_run
```

The report freezes the input files and saves PNG/SVG plots plus `summary.json`.
Unwrapping assumes less than half a rotation between samples and disconnects
gaps longer than 0.2 seconds. It does not correct sensor nonlinearity.

### How the keyboard driving is safe

Holding **A** doesn't latch a velocity. Each key repeat sends a fresh `v`
command, and the firmware zeroes the cart if it hasn't heard one in 250 ms. If
the host crashes, the USB cable pops out, or you just let go, the cart stops on
its own rather than driving into the end of the rail.

### Emergency stop keeps the motors energized

`stop` zeroes every velocity but leaves the drivers on. That's deliberate: the
SFU1605 screws are efficient enough to back-drive, so cutting ENABLE with the
rail raised drops it. Since all three ENABLE lines share GPIO 27, de-energizing
is a separate command — `off` — and you should support the rail before using it.

---

### Speed profiles

The board boots into `slow`: 0.05 m/s top speed, 0.02 m/s jog, 1 m/s² accel.
Everything creeps, and a direction error nudges the end of the rail instead of
hitting it. Do all of your wiring and calibration checks here.

Balancing will not work on the slow profile, and that isn't a tuning problem —
the cart has to accelerate out from under a falling pole, and 1 m/s² isn't
close. Send `fast` before `bal` or `auto`, and stand clear when you do.

Both commands e-stop first, so `slow` doubles as a panic button that also
prevents the next command from being quick.

## 4. First run, in order

1. **Current down, motors nowhere near the rail ends.** `python3 cartpole.py`,
   then `mag` — confirm the magnet reads healthy before anything moves.
2. `control`, tap **D**. Note which way the cart physically goes; that direction
   is +x. Backwards? Set `CART_INVERT 1` and reflash.
3. `home`, then drive the cart a known distance and compare the reported `x`
   against a ruler. Disagreement means your pulley or microstep constants are
   wrong — fix the constants, don't invent a scale factor.
4. **Measure L_eff.** Let the pole hang, give it a small push, time 10 swings.
   `L_eff = g·(T/2π)²`. Then `set leff <value>`. Every balance gain is derived
   from this one number, so measuring beats guessing.
5. Tilt the pole toward +x and check in `data` that theta goes **positive**.
   If not, `ENC_INVERT 1` and reflash.
6. Send `fast`. Everything up to here was on the crawl profile; balancing
   needs real acceleration. Then hold the pole upright and send `bal`. It should fight you. Tune live, no
   reflashing: `set pw 9` for a stiffer pendulum loop, `set pc1 -2` if the cart
   wanders into the rail, `set bw 12` if it buzzes.
7. `auto`.

## 5. When it misbehaves

**Lost steps look exactly like bad tuning.** After any crash, check whether the
reported `x = 0` is still the physical centre of the rail. If it drifted, you're
losing steps: lower `amax_s`/`vmax`, raise Vref, or raise the motor supply
voltage as appropriate for the driver and motor. The current 60T swing-up
default of 0.8 m/s corresponds to 400 RPM; the motor supply is 24V.

**Rotor inertia also matters.** For example, 87 g·cm² through the 60T pulley's
19.10 mm pitch radius reflects to about 0.024 kg of apparent cart mass. This
is an illustration; the actual motor and pulley inertia have not been measured.

**Swing-up stalls at a fixed amplitude** → check `v` in the dashboard before
touching gains. The energy pump does work at a rate proportional to the cart's
*acceleration*, so the instant velocity saturates at `vmax`, acceleration goes
to zero and pumping stops for the rest of that half-swing. A flat-topped `v`
trace means you're speed-limited and no gain will fix it.

**Swing-up never gets going at all** → raise `amax_s`, or lower `kpx`; the
centring term steals energy from the pump. **Flies past upright too fast to catch** →
lower `ke` so the pump eases off near the top, or widen `catch_r`.


## Interactive pendulum simulator

Open [Pendulum Lab](simulator175/index.html) in a browser to test acceleration, jerk, speed ceilings, and four stepper input styles against the current measured 125 mm pendulum model, with the archived 175 mm presets retained. Includes calibration overlays, recorded command-waveform replay, comparisons, parameter sweeps, and CSV/JSON exports.

See [simulator documentation](simulator175/README.md) for local serving, model assumptions, source provenance, and validation. Run `node simulator175/test.js` to check the model and firmware-equation parity.

## Manual upright tuning (v17)

Use **`bal` / START upright** after manually raising the pendulum. The new upright-only session accepts a stopped start near upright, aborts beyond **±50° from calibrated upright**, brakes, returns to center and disables. It never switches to swing-up or automatically restarts. Rail protection also ends the trial. Existing motion limits remain **0.8 / 12 / 12 / 60** (speed / swing acceleration / balance acceleration / jerk).

The controller is four-state feedback, not PID. `bal_pw=8` is the simulation-screened first candidate; `set bal_pw 7` restores the old angular response for comparison while stopped. See [upright tuning and hardware procedure](analysis/upright_tuning.md). Compile/upload v17 and restart the Python console before testing; no physical trial has been performed.

## v19 direction trial

After seven v18 upright trials aborted on predictive rail protection and the user observed motion away from the falling side, **v19 sets `CART_INVERT=0` (previously 1)**. `ENC_INVERT=0`, upright raw 3416, `bal_pw=8`, motion limits .8/12/12/60 and ±50° upright abort/centering are retained. `params` now reports `cart_invert` so logs identify the physical direction mapping. The driver writes DIR on the first command as well as reversals; otherwise a first positive command could retain the boot LOW pin level after this polarity change.

Place the cart at physical center before reset/upload; after upload confirm firmware v19 and `cart_invert=0`, then use `data` and **START upright** / `bal` for a near-vertical release. Expected corrective cart motion is toward the falling side. The separate possible 2.9° reference discrepancy is not applied in this trial. [Physical review](analysis/upright_review_20260916/review.md).
