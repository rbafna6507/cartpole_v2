# Simple Arduino sine-wave cart motion

Open `cart_sine.ino` in Arduino IDE. Keep `SineMotion.h` beside it.
Select **ESP32 Dev Module** (Espressif ESP32 core **3.3.2**) and install
**FastAccelStepper 1.2.8**. The bundled
[`FastAccelStepper-1.2.8.zip`](../third_party/FastAccelStepper-1.2.8.zip) can be installed through **Sketch → Include
Library → Add .ZIP Library**. Upload, then open Serial Monitor at **115200 baud**
with **Newline** selected.

Place the cart at the physical middle of the rail before powering the motors.
The sketch enables holding torque at startup but waits for your commands to move.
Send these two lines separately:

```text
center
run 25 0.5
```

This moves **±25 mm from center at 0.5 Hz**: 50 mm peak-to-peak, one cycle every
2 seconds. `center` declares the current position; it does not find or move to
the rail midpoint. You can use `run` alone for the defaults near the top of the
sketch, or send `run <amplitude_mm> <frequency_hz>` for other values.

- `stop` smoothly reduces amplitude to zero and finishes at center in about
  2 seconds. During startup it first finishes ramping up (up to about 4 seconds
  total). You may then start another run without setting center again.
- `!` immediately aborts queued pulses, without needing Enter. This may lose
  steps; physically recenter and send `center` before running again.
- Stop before changing amplitude or frequency. Motion continues without a USB
  connection until you stop it or the board resets; there is no host heartbeat.

## Increasing speed and acceleration limits

The initial **1000 mm/s** and **5000 mm/s²** are chosen commissioning limits,
not measured motor ratings or limits imposed by microstep counts. They only
decide whether a requested waveform is accepted. Raising them does not change
the waveform until you also change its amplitude or frequency.

After uploading this version, use these commands while stopped:

```text
limits
limits 1250 7500
check 25 2.4
```

`limits` displays the current caps. The second line changes them to 1250 mm/s
and 7500 mm/s² (625 RPM and 3750 RPM/s). `check` reports steady peak speed,
acceleration, pulse rate, and ramp-inclusive bounds for the proposed amplitude
and frequency **without moving**. Use `run` with your chosen amplitude/frequency
when ready. Settings reset to 1000/5000 on reboot. Changes are rejected during
motion; malformed settings leave both caps unchanged.

There are three distinct constraints:

1. Configurable speed and acceleration caps: your test envelope. No independent
   pulse-generation acceleration ceiling is imposed by this timed-queue mode.
2. Pulse generation: the sketch retains its 100-pulse-per-1-ms-segment guard.
   That is nominally 100,000 pulses/s, or 3750 mm/s with this pulley. Reserving
   one pulse for rounding permits a speed-cap setting of at most **3712.5 mm/s**.
   The sketch also reads the active library backend's minimum step interval and
   lowers this ceiling if necessary. FastAccelStepper documents up to
   [200,000 pulses/s on ESP32](https://github.com/gin66/FastAccelStepper), but
   that is an electrical scheduling capability, not a loaded motor rating.
3. Mechanics: available motor torque at speed, driver current, supply voltage,
   motor and load inertia, and friction determine whether actual motion follows.
   Missed physical steps are not detected by this program.

Test from a known working waveform, keeping amplitude fixed and increasing
frequency in small increments. A 10% frequency increase demands 10% more peak
speed and **21% more peak acceleration**. Finish each test normally and check
that the physical center has not drifted; after a stall or lost steps, restore
the physical center and issue `center` before another run. The 135 mm amplitude
and 5 Hz frequency bounds remain in force.

## Hardware and tracking

This standalone sketch retains its **60T pulley** calibration. The repository's
`swingup` sketch now also uses **60T** calibration; their wiring and commands still differ.

The current sketch's pin settings are **STEP 18, DIR 19, shared ENABLE 27
(active LOW)**, 200 full steps/revolution, 1/16 microstepping, 60T GT2 pulley.
This gives **26.6667 pulses/mm**. Only the configured cart STEP pin receives pulses.
All three drivers retain holding torque, including after stopping. Upload/reset
can interrupt holding torque, so support the height assembly during upload.

The steady waveform is `x(t) = A sin(2πft)`. A two-second quintic amplitude ramp
avoids an instantaneous velocity jump on startup and brings position, velocity
and acceleration back to zero on a normal stop. A hardware pulse queue executes
1 ms position segments using FastAccelStepper's
[timed-move interface](https://github.com/gin66/FastAccelStepper/blob/1.2.8/src/FastAccelStepper.h).
Targets are rounded absolute positions, so fractional steps do not accumulate
into position drift. Timing remainder is carried into the next segment.
There is approximately 16 ms of queued motion; an underrun stops the test.

The code accepts amplitude 0.5–135 mm and frequency 0.02–5 Hz, and rejects
combinations above the configured ramp-inclusive software bounds (initially
1000 mm/s and 5000 mm/s²). It does not silently alter the requested waveform. The ±135 mm
limit assumes a correctly centered 300 mm rail with a 15 mm margin at each end.
Steady peak speed is `2πfA`; peak acceleration is `(2πf)²A`.

Start with `run 10 0.25`. These limits are not measured motor capabilities:
reduce amplitude/frequency if the motor stalls or skips steps. This is open-loop
step control, not measured cart-position feedback. The AS5600 measures pendulum
angle and cannot detect missed cart steps. Segment timing, microstep rounding,
driver reversal timing and mechanical compliance limit tracking accuracy.

## Software verification

From the repository root:

```sh
./scripts/build_cart_sketches.sh
./scripts/test_cart_sine.sh
```

Compilation and waveform tests do not establish physical tracking accuracy.
