# Cart frequency bench

Choose **total peak-to-peak travel** and **frequency**, preview the signal, then
run the cart yourself. This uses a dedicated ESP32 sketch; swing-up control is
not active during a test. The GUI never connects or starts motion on launch.

## Install and launch

Close `cartpole.py`, Arduino Serial Monitor, and any other program using the
board. Keep the height assembly supported during upload/reset because the
drivers share ENABLE. From the repository root:

```bash
cd /Users/sajivshah/Documents/GitHub/cartpole_inverted_pendulum
arduino-cli compile --fqbn esp32:esp32:esp32 --build-path /tmp/cartpole-frequency-build frequency_test
arduino-cli upload --fqbn esp32:esp32:esp32 --input-dir /tmp/cartpole-frequency-build -p /dev/cu.usbserial-0001 frequency_test
python3 frequency_test_gui.py
```

Python needs `pyserial` (already used by `cartpole.py`). The GUI opens at
http://127.0.0.1:8766. `--port 8767` selects another web port if needed;
select the **serial** port inside the GUI. `--demo` exercises the same UI with
simulated data and no serial access. The demo banner makes that explicit.

1. Select the board's serial port and click **Connect**. Wait for IDLE.
2. Place the cart physically at the middle of the rail. Tick the confirmation,
   then click **Set this position as center**. This only resets a coordinate;
   it does not move or home the cart.
3. Enter total travel and frequency. For example, 100 mm means −50 to +50 mm;
   0.25 Hz means one oscillation every four seconds.
4. Click **Run oscillation**. Set the ramp duration (default **2 seconds**, independent of frequency). The amplitude ramps up over that time, then the cart oscillates until you finish or stop.
5. **Finish smoothly at center** ramps the amplitude down over the same time.
   If pressed during startup, it waits for that ramp to finish first.
   **Stop now** or **Esc** stops pulses immediately. After an immediate stop,
   physically recenter and confirm again before starting another test.

Inputs are locked during motion. Finish/stop before changing them. No frequency
sweep or automatic gain tuning occurs. Closing/hiding the page, disconnecting,
or losing browser/board telemetry stops the test. Keep the page visible.

## What the plots mean

After startup, position is `x = A sin(2πft)`, where `A = total travel / 2`.
The four plots show reference position, velocity, acceleration, and jerk.
Peak cards show the full-amplitude steady sine:

- speed = `A × 2πf`
- acceleration = `A × (2πf)²`
- jerk = `A × (2πf)³`

The preview and board waveform include the derivatives of the quintic amplitude
ramp. The ramp can change instantaneous peaks; the firmware also validates a
conservative speed bound that includes the ramp. It generates the signal locally
at roughly 1 kHz and uses a 125 kHz step timer, rather than streaming velocity
samples over USB. There is no swing-up acceleration/jerk limiter distorting the
chosen waveform: the requested travel and frequency determine the demands.

The dashed position curve is inferred from generated pulses. **It is not a
physical cart encoder.** Inspect actual cart movement to identify buzzing,
missed steps, or reduced travel. This test does not assert a measured motor
bandwidth or guarantee tracking. The pendulum sensor is not used by this sketch.

## Travel and drive limits

- Physical rail: **300 mm**; retained end margin: **15 mm per side**.
- Maximum test excursion: **270 mm peak-to-peak**, centered at zero. Entering
  300 mm displays the signal but blocks Run with an explanation. It is never
  silently reduced to a different amplitude.
- Frequency input: **0.02–5 Hz**, additionally limited by required pulse speed.
- Pulse ceiling: **2.34375 m/s**, derived from 60T × 2 mm/rev, 200 full steps,
  1/16 microstepping and 62,500 step pulses/s. This is not a motor torque rating.
- The ISR independently stops pulses after a 750 ms host-heartbeat timeout or
  beyond ±140 mm inferred position. A control timing gap over 5 ms faults too.
- The Z STEP outputs remain low. Stop keeps the shared drivers energized.

V2 firmware requires its own handshake, a live heartbeat, idle state and a confirmed
center before Run. An old swing-up sketch cannot be accidentally run by this UI.

## Timing diagnostics (V2)

The GUI displays the observed waveform update frequency and maximum gap, step
timer frequency and maximum gap, emitted pulse count per second, and minimum
STEP HIGH/LOW times estimated from CPU timestamps around GPIO writes. These
values are logged once per second in the event JSONL. They measure software
scheduling, not driver input voltage or physical cart motion. The A4988 requires
at least 1 µs HIGH and LOW at its STEP input. An oscilloscope or logic analyzer
is needed to verify the electrical signal at the driver.

V1 incorrectly tied the ramp to two oscillation periods: 0.05 Hz caused a
40-second startup. V2 uses an explicit 0.5–30 second ramp (default 2 seconds).

## Logs and verification

Each connection writes CSV telemetry and JSONL commands/events under
`logs/frequency_test/`. These logs are separate from swing-up runs. They label
references, pulse-inferred position, and commanded velocity explicitly. Demo
sessions are marked in their event log.

The recurring swing-up tuning automation is paused for these manual tests.
The original `swingup` firmware is unchanged; re-upload it to return to swing-up.

Software checks (no hardware motion):

```bash
clang++ -std=c++11 -O2 -Wall -Wextra -Werror tests/frequency_motion_test.cpp -o /tmp/frequency_motion_test
/tmp/frequency_motion_test
PYTHONPYCACHEPREFIX=/tmp/cartpole-pycache python3 tests/test_frequency_gui.py
```

The optional Playwright test `tests/frequency_gui_browser_test.js` expects the
demo server at port 8766. It verifies previews, invalid travel, connection,
center confirmation, Run, smooth finish, immediate stop and mobile layout.
