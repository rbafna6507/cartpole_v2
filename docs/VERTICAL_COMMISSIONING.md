# Standalone vertical screw commissioning

This is an operator-attended test, separate from `cartpole-console`. Source:
`firmware/vertical_commissioning/vertical_commissioning.ino`; host:
`scripts/vertical_commission.py`. It must replace the Teensy firmware temporarily
before use. It does not control/balance the cart, emit cart STEP pulses, read the
pendulum encoder, or run submitted policies. The normal executor currently blocks
Z pulses. Cart balancing during vertical disturbances comes later, after this
commissioning and explicit integration into the common executor.

The owner confirmed on 2026-10-23: both rails have 200 mm stroke, the bottom stops
can tolerate the requested timed bottoming, and the rail remains mechanically
supported with drivers disabled. The initial pose may be declared bottom by the
operator. Physical directions and step accuracy are still unverified.

## Wiring

These are **Teensy 4.1 digital GPIO numbers**, from the existing executor and PCB
wiring documentation, not Jetson GPIO or connector pad numbers. Verify the
assembled wiring matches before flashing.

| Function | Teensy GPIO | Driver connection |
|---|---:|---|
| Left screw Z1 STEP | D4 | Left/U4 STEP |
| Left screw Z1 DIR | D5 | Left/U4 DIR |
| Right screw Z2 STEP | D6 | Right/U5 STEP |
| Right screw Z2 DIR | D7 | Right/U5 DIR |
| Shared enable | D8 | All three drivers ENABLE, LOW = enabled |
| Cart STEP / DIR | D2 / D3 | Held LOW by this sketch; no cart pulses |
| Ground | GND | Common driver/controller logic ground |

MS1/MS2/MS3 are left in their existing hardware configuration. Big Easy Driver
unconnected defaults are 1/16 microstepping, per the
[SparkFun product specification](https://www.sparkfun.com/big-easy-driver.html).
The sketch does not drive these pins or change motor current. NEMA 17 specifies
frame size, not step angle: **verify 1.8°/200 full steps per revolution**; use
`--motor-steps 400` for 0.9° motors. The supplied 5 mm pitch is interpreted as
**5 mm travel per revolution (lead)**. Multi-start screws require actual lead.

D28/D29 are reserved candidate Z switch inputs, but this test does not use them:
no installed Z contacts, current sensor, stall detection or position encoder has
been commissioned. See [PCB wiring](pcb-switches.md).

## Scale and waveform

For 200 full steps/revolution, 16 microsteps and 5 mm/revolution:

- `steps_per_mm = 200 × 16 / 5 = 640`.
- Homing request: 40 mm/s = 25,600 pulses/s = 480 RPM; 5 seconds commands
  **200 mm**, including any time spent stalled against the bottom stops.
- Default sine: `z(t) = 25 + 20 sin(2πt)` mm when the envelope is fully raised.
  Both ends receive the same displacement and phase. “Amplitude 20 mm” means
  ±20 mm, **40 mm peak-to-peak**, spanning 5–45 mm above the declared bottom.
- Steady sine peak speed: `2π f A = 125.664 mm/s`, about 80,425 pulses/s and
  1,508 motor RPM. Peak acceleration: `(2πf)² A = 789.57 mm/s²`.
- The standalone 4 µs pulse timer has a theoretical 125 kHz ceiling; admission
  caps requests at 100 kHz including the envelope derivative. The production
  executor's 7 µs timer cannot supply the default sine's required pulse rate.
  Supporting pulse rate does **not** prove motor torque, tracking, or synchrony.

Before the sine, a quintic smoothstep moves both ends to the center at at most
10 mm/s. The oscillation amplitude then ramps in over 2 s and out over 2 s using
`e(t) = [1-cos(πr)]/2`, where `r=min(1,t/2,(duration-t)/2)`. The finite run ends
at the center with zero target velocity. Run duration excludes the center move.
For default settings: ~4.69 s transfer from bottom, then 10 s waveform.

Requests must stay at least 2 mm from declared endpoints, last 4–60 seconds, and
fit the pulse-rate budget. These bounds apply to commanded coordinates only.
Changing motors/microstepping can make the default waveform exceed the budget;
the firmware rejects it instead of silently changing amplitude or frequency.

## Build and stage — no automatic flashing

From the main repository:

```bash
arduino-cli compile --fqbn teensy:avr:teensy41:usb=serial \
  --build-path /tmp/cartpole-vertical-build firmware/vertical_commissioning
uv run python scripts/vertical_commission.py --help
uv run pytest -q tests/test_vertical_commissioning.py
```

The test package is staged on Jetson at `/home/rbafna/cartpole-vertical-test`,
including source, the compiled HEX and its SHA-256. Staging does not flash or move
anything. The existing operator deployment and firmware files are untouched.

Before changing firmware, stop the hardware worker and exit the normal cartpole
console/any other serial owner. Preserve the **matching current executor build**
and its restore procedure; do not assume an old `teensy_executor.ino.hex` found
elsewhere is the currently installed firmware. Standalone firmware removes the
normal balancing/encoder/portal hardware interface until the executor is restored.
Keep the rail supported during flash/reset, when D8 may be high-impedance.

For a deliberate test flash on Jetson, after that handoff:

```bash
cd /home/rbafna/cartpole-vertical-test
sha256sum -c SHA256SUMS
~/cartpole-v2-live/tools/loader-2.3/teensy_loader_cli \
  --mcu=TEENSY41 -w -v vertical_commissioning.ino.hex
# The loader may wait for the Teensy's physical program button.
```

The firmware starts disabled and moves only after explicit commands. The host
checks `VERTICAL-COMMISSIONING-1` before sending configuration; it refuses the
normal cartpole firmware.

## Run the direction checks first

On Jetson, using the existing operator Python environment (contains pyserial):

```bash
cd /home/rbafna/cartpole-vertical-test
~/cartpole-v2-live/active/.venv/bin/python vertical_commission.py \
  --port /dev/serial/by-id/usb-Teensyduino_USB_Serial_20242870-if00 \
  --travel-mm 200 --motor-steps 200 --microsteps 16 --lead-mm 5 \
  --bottom-stops-rated
```

Alternatively, locally from the repo, use `uv run python scripts/vertical_commission.py`
with the appropriate local serial device. Do not run two serial clients.

At the `vertical>` prompt, each probe moves only the selected end by a nominal
0.5 mm over 0.5 s, then holds. This intentionally introduces a tiny tilt; stop if
that is not mechanically permissible. `+` means DIR HIGH, not proven UP.

```text
probe left +
# Observe, wait for DONE. If this moves UP:
direction left +
# If DIR HIGH instead moves DOWN, use direction left -.

probe right +
# Observe independently. Choose + or - for whichever raw direction means UP:
direction right +
status
```

Use `probe left -` / `probe right -` for the reverse check and return movement.
For a variable distance, append millimeters: `probe left + 5`, `probe right - 10`,
or `probe left - 20`. The default remains 0.5 mm; allowed distances are >0 to
20 mm per command, with a quintic ramp and peak speed at most 2 mm/s. A 5 mm
probe takes about 4.69 s; 20 mm takes 18.75 s. These are raw directions, not
semantic UP/DOWN. They do not require a reference and cannot enforce absolute
travel bounds. Verify available clearance and permissible rail tilt before
larger single-end moves. Repeated probes can exceed the rail stroke; the limit
is per command, not an absolute position limit.
Every new probe invalidates that axis's direction confirmation, so issue
`direction ...` again afterward. Do not repeatedly probe one side into a large
tilt: there is no measured skew detection. Direction confirmations and settings
are volatile and reset on reboot/new configuration.

## Bottom reference and timed homing

Since the current starting pose is bottom, you can skip the timed routine **if
both ends are still physically at bottom after direction testing**:

```text
reference
# Type BOTH only after inspecting the two bottom positions and level rail.
```

Otherwise, after confirming both UP polarities:

```text
home
# Type BOTTOM to command DOWN at 40 mm/s for 5 seconds.
# Wait for DONE, inspect both ends, then:
reference
# Type BOTH.
```

`home` is a timed motor-bottoming operation, not sensed homing or automatic
squaring. It never detects which end hits first and does not stop one motor when
it contacts. Interrupted bottoming does not establish a reference. Completion
only reports that the pulse command finished; `reference` is a separate operator
assertion that both bottoms were reached. It zeros the issued-pulse counters.

## Paired disturbances

Start with a smaller test if needed, then use the requested waveform:

```text
sine 2 0.25 25 10
# Wait for DONE. Default requested ±20 mm, 1 Hz, centered at 25 mm, for 10 s:
sine
# Equivalent explicit command:
sine 20 1 25 10
status
stop
quit
```

`stop`, Ctrl-C or `quit` stop/request stopping pulses and leave holding torque
on while powered. STOP invalidates the bottom reference; inspect/return to the
bottom and explicitly reference again before another sine. A completed sine
retains its counted reference. `disable` separately prompts for `SUPPORTED` and
releases **all three** drivers via shared D8. This is permitted by the owner's
support confirmation, but it is never an implicit STOP side effect.

A 50 ms host heartbeat is required while moving. A 500 ms heartbeat gap, 5 ms
foreground stall, pulse-spacing violation, excessive command tracking lag or
motion deadline stops pulses in the timer ISR and latches a fault. It does not
automatically restart. `clear` acknowledges the fault; a new reference is required.
Enable remains unchanged on those stops. Loss of power/reset can release torque.
No firmware watchdog proves physical halt or detects missed motor steps.

## Commands and options

| Host command | Meaning |
|---|---|
| `probe left/right +/- [mm]` | Raw direction probe, default 0.5 mm, >0–20 mm, peak ≤2 mm/s |
| `direction left|right +|-` | Confirm which raw polarity raises that end |
| `home` | Prompt, then timed 40 mm/s × 5 s DOWN |
| `reference` | Prompt, then declare both current positions bottom/zero |
| `sine [amplitude_mm hz center_mm seconds]` | Defaults `20 1 25 10`; validates travel/rate, moves to center, runs finite waveform |
| `status` | Mode, latched fault, enable/reference, polarity/confirmation, counted positions |
| `stop` | Stop pulses, retain holding torque, invalidate reference |
| `clear` | Acknowledge fault; no automatic motion/reference |
| `disable` | Prompt, then release shared enable; invalidate reference |
| `help`, `quit` | Help or stop/request STOP and exit |

Numeric status modes: 0 idle, 1 probe, 2 timed bottoming, 3 center transfer,
4 sine. Faults: 1 host heartbeat, 2 foreground stall, 3 pulse spacing,
4 target tracking or motion deadline.

CLI options: required `--port`; `--travel-mm 200`; `--lead-mm 5`;
`--motor-steps 200|400` (default 200); `--microsteps 1|2|4|8|16` (default 16);
`--bottom-stops-rated` (enables the home prompt); `--log PATH` (new file only).
Default transcript is `runs/vertical-<timestamp>.jsonl`, with monotonic timestamps
and command/response events. It is not a physical position/acceleration recording;
use `status` for counted positions. There is no live integration with the camera
or the pendulum experiment recorder yet.

## Verification and remaining work

Native tests exercise the **actual sketch** with simulated time/GPIO: no cart
pulses, direction confirmation, independent direction inversions, synchronized
counts, full default sine/transfer, timed bottoming, STOP, explicit disable,
heartbeat and foreground-stall faults. Separate tests cover profile/travel/rate
validation, waveform endpoints and host command confirmation boundaries. The
Teensy 4.1 build passes. These checks are not measured pulse timing, motor torque,
stall tolerance or loaded travel verification; those require the user's physical
direction and motion checks.

After verification, integrate Z under the existing executor's shared enable,
cart safety, STOP, leases, fault/reference lifecycle, telemetry and timing budget.
A separate terminal cannot independently drive the same Teensy while cartpole
policies run. Do not simply remove the production Z pulse inhibit.
