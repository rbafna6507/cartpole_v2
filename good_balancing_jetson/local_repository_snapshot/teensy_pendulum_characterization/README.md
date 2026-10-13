# Teensy pendulum characterization

A separate characterization fork based on your supplied `teensy_defaults_update.zip`. Flash this sketch instead of the swing-up controller while collecting data. It preserves the source's cart wiring, 60T mechanics, 7 µs DDS pulse method, 1 kHz motion math and volatile AS5600 fast-filter setting. It adds guided experiments and timestamped raw logging. No physical hardware was tested here.

Start with `QUICKSTART.md`. `TRAINING_AND_TIMING.md` explains the subsequent MuJoCo, RL and vision stages. `VALIDATION.md` records software checks.

## What changed from the running firmware

| Component | Characterization behavior |
|---|---|
| Cart | STEP 2, DIR 3, CART_INVERT=0, shared active-low ENABLE 8; same source wiring |
| Encoder | Wire1 SDA 17 / SCL 16, 400 kHz, AS5600 0x36; same volatile CONF=0x0300 setting as source |
| Mechanics | 60 teeth, 2 mm pitch, 200 full steps/rev, 16 microsteps: 26.6667 pulses/mm |
| Motion | Source `cart_motion.h` used unchanged; bounded position-target experiments added |
| Pulse timing | Source-derived DDS at 7 µs, with independent foreground-stall cutoff |
| Sampling/control | 1 kHz; magnet diagnostics 20 Hz; nonblocking queued USB serial |
| Startup | Drivers disabled; NO assumed home, no automatic centering, no swing-up or balance |
| Z axes | STEP 4 and 6 stay LOW; no Z movement commands |
| Shared enable | Energizes/disables ALL three drivers. Secure/support vertical axes before testing |
| Rail | Measured during every drive session; original default is not trusted as a home reference |
| Limits/IMU/display/network | No limit-switch, MPU, LCD or Ethernet initialization in this build |
| Encoder reference | Raw counts retained; no EEPROM writes; original saved upright reference is untouched |

This collector replaces the previous sketch while flashed; it does not run alongside it. The original uploaded archive was not modified. The source's high 1.5 m/s, 25 m/s² and 150 m/s³ automatic limits are NOT used as characterization defaults.

## Install and flash

Install the PJRC Teensy board package in Arduino IDE or Arduino CLI. Board-manager URL: `https://www.pjrc.com/teensy/package_teensy_index.json`. Select **Teensy 4.1 / USB Type Serial**. Open `teensy_pendulum_characterization.ino` in this directory and upload. Close Serial Monitor before using lab.py.

CLI, from the parent directory:

```bash
arduino-cli compile --fqbn teensy:avr:teensy41:usb=serial teensy_pendulum_characterization
arduino-cli upload --fqbn teensy:avr:teensy41:usb=serial --port YOUR_TEENSY_PORT teensy_pendulum_characterization
```

A normal Teensy upload may need the program button if automatic reboot is unavailable. Use your existing working board installation and wiring. Do not move the AS5600 to the old standalone collector's 18/19 pins: THIS board uses **17/16 on Wire1**.

From this directory on your laptop or Jetson:

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
python3 lab.py ports
```

Substitute your actual serial device for PORT in subsequent commands. On macOS it is typically `/dev/cu.usbmodem...`; on Jetson usually `/dev/ttyACM...`. USB baud setting is 115200 for compatibility; native USB is not a 115200-bit UART. Run acquisition locally, not in Colab. Offline analysis and later training can run in Colab.

## First data collection session

### A. Record the actual hardware

```bash
python3 lab.py measurements
```

Enter measured bare arm mass, COM/balance point, complete rotating mass, tip-weight distance and moving cart mass. Unknown fields may be blank. The supplied controller comments say 125 mm, 11.05 g arm, two 5.85 g weights; `equipment.json` records these as unconfirmed current-assembly metadata. Old logs used earlier geometry; do not automatically combine hardware revisions. Edit supply voltage, driver/current setting and assembly note in equipment.json before capture. Every capture stores a copy.

### B. Stationary noise and encoder checks

Secure the rail/Z mechanics and physically fix the cart for passive experiments. Keep motor power off when manually repositioning parts if needed; the firmware also keeps enable disabled.

```bash
python3 lab.py --port PORT noise --seconds 10
python3 lab.py --port PORT static
```

Noise captures spread, drift, sample timing/gaps and magnet flags. For `static`, use a protractor or physical angle guide. Follow the requested DOWN, ±15°, ±30°, ±60°, ±90° poses and repeated approach directions. Hold each requested position BEFORE pressing Enter. The tool checks angle scale, nonlinearity and directional repeatability (including operator placement error).

It produces `static_report.json`, `static_plot.png` and, when monotonic/stable checks pass, `encoder_calibration.json`. Inspect before using. Applying the mapping is explicit via `--calibration`; outside-range samples are rejected, not extrapolated.

### C. Free decay, each side

```bash
python3 lab.py --port PORT swing --angle 20 --fit
python3 lab.py --port PORT swing --angle -20 --fit
```

Do three releases on EACH side at ±20°. Then two or three each at ±45° and ±75°. Each command:

1. Confirms the cart is fixed and automatic control off.
2. Records a hanging-still DOWN reference.
3. Asks you to position and HOLD the pole near the requested signed angle, then press Enter.
4. Detects 0.8 seconds of stable holding and tells you to release.
5. Marks detected motion on the MCU; stops after 3 seconds quiet (minimum 5 s post-release) or 60 seconds.
6. Saves raw data, metadata, diagnostics, period-versus-amplitude plots and optional friction/dynamics fit.

`--angle` records your intended physical starting angle; it does not actuate the arm. Do not move the arm into position after arming. Auto release is a motion threshold slightly after physical let-go. Fitting includes initial angular rate. Hand motion is preserved in raw data but excluded by the release event.

For calibrated reanalysis or collection:

```bash
python3 lab.py --port PORT swing --angle 45 --fit --calibration runs/STATIC_SESSION/encoder_calibration.json
```

Raw encoder counts always remain in the CSV. The firmware's filtered omega is ONLY used to detect hold/release/rest; it is not the production controller's alpha-beta observer. The raw recording can later be replayed through that observer to assess its noise/delay.

### D. Manual homing and first powered cart test

Remove the cart clamp. Secure the rail/Z mechanics: the driver's enable wire is shared across all axes. Ensure you can cut motor power. Software bounds use emitted step counts, so incorrect homing or lost steps remain undetectable without independent position sensing.

Start with a **5 mm, 10 mm/s one-way move**:

```bash
python3 lab.py --port PORT drive --distance 5 --speed 10 --accel 100 --jerk 1000 --single
```

The guide first disables drivers and asks you to:

1. Manually mark both usable CART-CENTRE endpoints, leaving clearance from mechanical impact.
2. Measure the span between those marks with a ruler.
3. Mark the midpoint, move the cart manually there, leave the pendulum hanging and remove the clamp.
4. Type MOVE to enable the drivers and execute the short test.

This is manual centre-reference homing, not an automatic end-stop search. It does not estimate span by counting pulses while you push an unpowered motor. Never push the cart after it energizes. `HOME span_mm` records your assertion of centre and the measured span; it cannot independently verify either.

Check actual direction and displacement against the ruler. After the test the drivers are disabled; enter measured final displacement only if the cart has remained at its stopped position. For a 5 mm target the nominal count is about 133.3 pulses, rounded through actual DDS stepping. If direction/scale is wrong, stop and correct the physical setup/firmware before larger tests.

Once that passes, collect a slow return/reversal sequence:

```bash
python3 lab.py --port PORT drive --distance 20 --speed 30 --accel 300 --jerk 3000 --repeats 2
```

Targets are +20, 0, -20, 0 mm, repeated twice. Each endpoint is held for 2 s before the next command. Homing is repeated at the start of the session. Do not assume power-off preserved the old reference. `MOVE_DONE` means the COMMAND profile reached its pulse-count target, not independent proof of cart arrival.

If these initial trials are repeatable, add separate trials at 50 and 100 mm/s, one change at a time, with the same 20 mm distance. These are optional experiments after verifying tracking; the package does not automatically search for the motor's failure limit. Record actual displacement/return error, supply voltage/current setting, load, temperature and observations.

| Bound | Value |
|---|---:|
| Default command speed | 30 mm/s |
| Default acceleration | 300 mm/s² |
| Default jerk | 3000 mm/s³ |
| Allowed speed ceiling | 250 mm/s |
| Allowed acceleration ceiling | 2000 mm/s² |
| Allowed jerk ceiling | 20000 mm/s³ |
| Python target magnitude | ≤50 mm |
| Firmware single target change | ≤100 mm |
| Target-to-entered-end margin | ≥30 mm |
| Motion braking boundary | 15 mm inside entered ends |
| Pulse-side count cutoff | 10 mm inside entered ends |

These are deliberately bounded command envelopes, not experimentally certified motor limits. Emergency pulse/enable cutoff can still leave mechanical coasting. Do not infer actual acceleration from the acceleration command alone.

### E. Communication timing

```bash
python3 lab.py --port PORT timing --count 200
```

With drivers disabled this measures USB host→firmware→host PING/PONG RTT, logging median/p95/p99/max and timeouts. It does not measure one-way delay, camera latency, physical motor response or Ethernet timing. Host and MCU timestamps have different clocks and must not be directly subtracted to claim one-way latency.

## What is saved

Each run gets a unique directory under `runs/`:

- CSV: raw AS5600 counts, unwrapped ticks, MCU read-midpoint time, sequence, diagnostics, error/gap counters, and host arrival time.
- Drive CSV adds signed emitted cart pulses, pulse-derived `x_command_m`, profile `v_command_m_s`, `a_command_m_s2`, motion ID and enabled/homed/moving flags. Count and position share one snapshot; the snapshot is taken after the angle read/control calculation, not at exactly the sensor's internal conversion instant.
- `_capture.json`: equipment snapshot, exact sent commands and host send times, MCU command-accept/done/fault/release events, stop reason.
- `_protocol.log`: original received lines and host arrival times.
- Passive `_lab_metrics.json`/`_lab_plot.png`: quality, separate same-side full-cycle periods, amplitude dependence, signed decay and asymmetry flags, optional normalized dynamics fit.
- Drive `plan.json`, `drive_report.json`, `drive_plot.png`: planned targets/limits, completion/fault, ruler entry and command traces.
- Timing `timing.json`; mass/geometry `measurements.json`; static calibration reports/plots.

CSV rows are written while acquiring. Interruptions retain partial files; STOP is sent on exit. If the host disconnects, firmware independently stops powered motion within 300 ms of the last parsed command/heartbeat. A foreground stall >5 ms is handled by the pulse ISR. Missed 1 ms control deadlines while energized, stale encoder data, bad/stale magnet diagnostics and step-boundary violations disable drivers and invalidate home. These are not substitutes for physical limit switches or independently measured position.

Send the **entire runs folder**, plus any photos of the angle/ruler fixtures. A plot alone omits timing and quality evidence.

## Analysis and simulation handoff

```bash
python3 lab.py analyze runs/SWING_SESSION/swing.csv --fit
python3 lab.py summary runs
```

New captures carry release/down-reference metadata. Legacy logs can be analyzed with an explicitly reviewed release time (`--release-s`) and optional `--zero-raw`; otherwise down-zero is inferred from the final two seconds and marked as an assumption. The raw input is not rewritten. Timestamp resets, large gaps and out-of-range angle mappings are rejected.

With measured total rotating mass and COM, `export-model` writes a parameter JSON compatible with the previous MuJoCo starter:

```bash
python3 lab.py export-model runs/SWING_SESSION/swing_lab_metrics.json --mass-g MEASURED_MASS --com-mm MEASURED_COM --output measured_model.json
```

Replace the uppercase placeholders with real numbers. Period identifies I/(m*g*COM); it cannot identify all three independently. Dry-friction and viscous coefficients are model-dependent estimates. Compare a selected parameter set against different recordings before applying it to training.

The new fork does not update MuJoCo with invented measurements. Once you return the runs, the work is: review quality/calibration → fit passive dynamics across repeats → reserve held-out releases → update mass/COM/inertia/friction → model the exact command integration/limits → compare driven trajectories → train. Pulse logs validate the command implementation; they do not identify actual motor tracking, missed steps, braking distance or torque. Ruler endpoints give coarse checks; later measured cart trajectories supply the missing dynamic validation.

## Protocol and support

Commands (newline terminated, uppercase): INFO, STREAM, ARM, GO, STOP, OFF, PING [id], LIMITS speed_mm_s accel_mm_s2 jerk_mm_s3, HOME measured_span_mm, MOVE id target_mm.

HOME is accepted only during streaming, with healthy fresh encoder/magnet data and disabled drivers. MOVE needs valid home, energized drivers and streaming. No automatic home/reference is restored after reset, STOP or a fault. LIMITS is rejected during a move. Invalid requests are explicitly reported. A MOVE times out at 20 s. Plain PING keeps the capture/drive lease alive; numbered PING returns a timestamped PONG for timing.

Do not run a second host program or Serial Monitor on the port. Ethernet control is an intended later integration, not a feature of this acquisition release. Return to your original firmware to use its swing-up/balance controller and LCD.
