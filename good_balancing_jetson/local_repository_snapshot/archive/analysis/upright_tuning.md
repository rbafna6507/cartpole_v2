# Manual upright tuning — v17

The upright controller is pole-placed **four-state feedback**, not PID. It uses angle error from calibrated upright, angular velocity, commanded-step cart position and commanded cart velocity. There is no integral term. The pendulum target remains raw AS5600 count **3416** (the measured 180° pose), independent of the hanging zero.

## Trial behavior

- Boot remains stopped with drivers disabled. Move the pendulum upright by hand.
- `bal` or the dashboard's **START upright** button is a one-shot start request. The control task accepts it only when stopped, the raw and estimated angle errors are within ±10°, estimated angular rate is at most 1 rad/s, and the cart is within 30 mm of the established center and stopped. Rejection never arms later capture. Start as close to vertical and stationary as possible; ±10° is an admission bound, not a demonstrated catch range.
- During an upright trial, raw calibrated angle error **greater than 50° in either direction** aborts balance. This corresponds to outside **130–230°** on a 180°-upright convention. The dashboard plots error in radians, so upright is 0 and the red bounds are ±0.872665 rad.
- Abort brakes through the existing jerk governor, returns to the existing center, and disables all drivers once within 3 mm, velocity ≤5 mm/s and acceleration ≤0.1 m/s². Return speed is capped at 0.1 m/s and return acceleration at 0.5 m/s²; braking retains the existing 12 m/s² limit. There is no swing-up or automatic restart. Another explicit `bal` is required.
- Predictive rail protection also ends the upright trial and returns to center. Existing 270 mm operating range, ±140 mm hard fault, 300 mm physical travel, encoder fault, host watchdog, and immediate `stop`/off behavior remain. A hard fault disables immediately rather than attempting a return. Return timeout is 10 seconds.
- Center is still inferred from commanded steps, not measured cart position. If steps are missed or the cart is moved while disabled, re-establish physical center before `home`.

## First candidate

Keep **vmax=0.8 m/s, amax_s=amax_b=12 m/s², jmax=60 m/s³**, the 20T pulley, and measured effective length 0.166 m. Change only the upright angular pole frequency from **7 to 8 rad/s**, exposed as `bal_pw` (default 8). `pz=0.85`, `pc1=-0.8`, `pc2=-1.2` and estimator bandwidth 10 Hz remain unchanged. `auto` still uses its original `pw=7`; the new setting is specific to `bal`.

`params` reports `bal_pw`, `bal_k1..bal_k4`, and start/fall bounds. `k1..k4` refer to the automatic controller. Changing gains requires stopped mode. Host requests a parameter snapshot before each `bal` so accepted starts have settings in the event log. The console refuses `bal` until the firmware advertises the new behavior.

| 5° stationary release at center, simulated | Baseline 7 | Candidate 8 |
|---|---:|---:|
| Maximum cart excursion | 122.3 mm | 108.8 mm |
| Settling within 2°, 10 mm and 0.02 m/s | 6.02 s | 5.21 s |
| Peak acceleration | 2.06 m/s² | 2.37 m/s² |
| Peak speed | 0.194 m/s | 0.194 m/s |
| 20-second screening cases settled | 18/18 | 18/18 |

Screening includes signed ±2°/±5° releases, ±3° with outward 0.2 rad/s rate, ±10 mm initial cart offsets, added encoder delay plus actuator lag, 95% tracking plus lag, and each of the three measured length/damping fits. This is candidate selection, not independent validation or a motor torque model. Settings 9–11 also passed the screen with more acceleration demand; 12 failed two cases. Candidate 8 is a modest first hardware change. The ±10° release tests reach rail protection and return to center, so start the first real trials within roughly 2–3° and nearly stationary.

Evidence: [upright_tuning.json](upright_tuning.json). Reproduce from the repository root with `node analysis/tune_upright.js`. The simulator's **Manual upright** preset uses the same limits and gains. Simulated initial states bypass the hardware start gate to allow explicit fall/rail recovery tests.

## Run on hardware

Source and compiled firmware are prepared; **no upload or physical trial was performed** in this task. Close any program holding the serial port before uploading. Shared ENABLE disables the height drivers too, as before; keep the height assembly supported when disabled.

```sh
cd /Users/sajivshah/Documents/GitHub/cartpole_inverted_pendulum
arduino-cli compile --fqbn esp32:esp32:esp32 swingup
arduino-cli upload --fqbn esp32:esp32:esp32 -p /dev/cu.usbserial-0001 swingup
python3 cartpole.py --port /dev/cu.usbserial-0001
```

Use the actual connected port if different. Establish the cart at physical rail center, then:

```text
stop
home
params
data
```

Raise the pole manually and click **START upright** when ready, or type `bal` + Enter in the terminal. Look for `# BALANCE`; a rejected request prints its reason. `stop`, Space/Esc, and **STOP / disable** remain immediate stops and cancel centering.

For a matched baseline trial, while stopped send `set bal_pw 7`; for the candidate send `set bal_pw 8`. Keep the other parameters and starting position unchanged. Collect several similar releases per setting; compare sustained upright time, angle error, cart excursion, return trigger, and any tracking issues. `log` identifies the CSV; the adjacent `_events.jsonl` records commands and settings. No further gain increase is justified from simulation alone.

## Validation

- C++ upright tests cover both signed fall boundaries, start rejection, gain isolation, jerk/speed/rail bounds during centering, timer rollover, timeout, and reset.
- Simulator tests cover gain and motion parity with compiled C++, latched signed fall recovery, and rail abort without swing-up.
- Host tests cover start-button/stop controls, legacy-firmware rejection, parameter snapshots, serial integrity/recovery and driver disabling. New recovery states are included in host-timeout tests.
- ESP32 compilation passes. Physical tracking and balance remain unverified.
- The full Python suite has one unrelated failure in the unchanged frequency-test GUI test `test_serial_handshake_center_run_and_lease_stop`: its stop wait can match an earlier connection-time stop before the lease expires. Upright-related tests pass.

Browser visual regression could not run in this sandbox: Chrome exited during launch. The simulator preset and JavaScript syntax were checked directly; the Matplotlib START/STOP callbacks pass their host test.
