# Live rig SDK and operator console

The V2 executor owns the physical limits and the final action lease. The SDK
provides an exclusive serial owner, stopped session negotiation, bounded writes,
source-explicit observations, recording, and an operator console. Installing or
importing the SDK never connects or arms a board.

Install the optional serial dependency, then use the stable device path:

```sh
pip install -e '.[hardware]'
python examples/cartpole.py --port /dev/serial/by-id/usb-Teensy_example --rate 100
```

The interactive commands are `auto [seconds]`, `bal [seconds]`,
`manual [seconds]`, `velocity m/s [ttl_ms]`, `stop`, `center`, `home`, `rehome`,
`upright`, `hanging`, `switches on|off`, `status`, `info`, `clear`, `rate hz`,
`params`, `get key`, `set key value`, `save path`, `load path`, and `quit`.
`balance` aliases `bal`. Motion durations are bounded to 1ms..60s; physical
homing has a separate 75s deadline. The board's watchdog
and duration handling remain active while the prompt waits for input.

`auto` and `bal` run the preserved controller **on the board** at its original
1kHz. The host telemetry rate does not change its controller period. `manual`
starts with zero demand; each `velocity` command is one expiring lease, limited
to 0.15m/s during commissioning. The prompt does not silently renew that lease.

The physical switch profile is enabled by default in firmware. `home` runs the
bounded physical switch routine only with that profile enabled. The current rig has cart switches 1/2 installed. Only for explicit
switchless bench commissioning, `switches off` selects commissioning mode, and `center` asserts that the operator has physically centered the cart
**now**. It sets a step origin without commanding a homing movement. `center`
is rejected while the switch profile is enabled. A reference invalidated by a
hard fault requires a new physical home or centering after `clear`.

A bounded recorded reference run is:

```sh
python examples/cartpole.py --port /dev/serial/by-id/usb-Teensy_example \
  --command auto --duration 5 --switches off --center-confirmed \
  --log-dir runs/reference
```

Use `--center-confirmed` only when the cart is physically centered. Each script
run stops in `finally`, including Ctrl-C and exceptions. On `executor-v4-rehome`, normal `auto` duration expiry starts a bounded return
to the existing counted home; the script waits through that return before its
final STOP. On older firmware, and for `bal`/`manual`, the script requests STOP
slightly before the MCU duration cutoff (up to 10ms, bounded to one quarter of
very short runs), keeping ordinary completion separate from a duration fault. `--command bal` requires the board's upright start conditions. `--command home` waits for healthy homed disabled completion; `--duration` bounds this wait (default and maximum 75s; explicit shorter timeouts are honored). Timeout, fault and interruption stop in finally.

## Saved tuning candidate, 2026-10-16

On the Jetson:

```sh
cd ~/cartpole-v2-live/releases/platform-20261015-v6-tunable
uv run --locked --extra hardware cartpole-console \
  --port /dev/serial/by-id/usb-Teensyduino_USB_Serial_20242870-if00 --rate 250
```

The console loads and reads back the preserved 40-setting bandwidth-10 profile
while stopped, before displaying the prompt. With the rig homed and clear, run:

```text
info
status
auto 25
```

Use `--keep-board-params` to retain the board's current settings, or
`--startup-profile profiles/experiment.json` to select a different profile.
Interactive `set` and `load` changes remain active for that console session;
opening a new default console restores this saved baseline. Diagnostic CLI
commands such as `--command info` and `--command status` do not load it.
Noninteractive `--command auto` and `--command bal` do load it.
A faulted interactive connection defers loading until an explicit successful
`clear`; it does not clear faults or start motion automatically. Other firmware
requires `--keep-board-params` or an explicit compatible profile.

The packaged default is `src/cartpole_sdk/control/tuned-20261016-bw10.json`,
byte-identical to `profiles/candidate-20261016-bw10.json`. It includes motion
limits and rail fractions/margins, but excludes the measured `rail` value and
encoder reference. Bare SDK `Rig` sessions do not load a profile implicitly.

The candidate uses native 1 kHz AUTO, `bw=10`, `pw=3`, and jerk 150 m/s³.
It preserves measured rail geometry and does not home or calibrate the encoder.
The exact comparison used saved reference 330, an experimental constant trim;
a full hanging calibration model is still pending. A lost home requires normal
physical `home`; do not reinterpret an unhomed position as valid.
Two 60-second AUTO trials held continuously for about 57.5 seconds after capture,
but one other candidate attempt still entered the failed-catch swing-up loop.
The latest long run also completed automatic return. This is the best current
candidate, not unconditional stability acceptance. See the
[tuning evidence](../evidence/phase3/retuning-20261016/README.txt).

## Optional smoothing candidate, 2026-10-16

`profiles/candidate-20261016-smoother-bw8.json` changes only observer bandwidth
from 10 to 8 Hz. Two 25-second trials and one 60-second confirmation completed
with continuous balance after capture and full return. Fast command variation
was lower, but capture sometimes took about 3.3 seconds rather than 2.5.
The preserved bandwidth-10 profile remains the default. To try the candidate
while stopped, run `load profiles/candidate-20261016-smoother-bw8.json`, then
`auto 25`. Reopening the default console restores bandwidth 10. See the
[jitter comparison and limitations](../evidence/phase3/jitter-20261016/README.txt).

## Python interface

```python
from cartpole_sdk.rig import Rig

with Rig(port='/dev/serial/by-id/usb-Teensy_example', rate_hz=100,
         log_dir='runs/live') as rig:
    # Context entry negotiates a stopped session. These are explicit operations.
    rig.configure_switches(False)
    rig.center()  # operator assertion: cart physically centered now
    rig.start(mode='auto', duration_s=5)
    state = rig.wait_state(after_tick=rig.state.tick, timeout=1)
    print(state.theta, state.x, state.received_ns)
    rig.stop()
```

`RealRig` aliases `Rig`. The public API includes `session`, immutable `state`,
`observation()`, `wait_state(after_tick=None, timeout=1)`, `center()`, `home()`, `rehome()`,
`configure_switches(bool)`, `calibrate_encoder(pose='upright')`, `get_info()`, `start(mode='auto', duration_s=10)`,
`arm(duration_s=10)`, `set_acceleration(value, ttl_ms=20)`,
`set_velocity(value, ttl_ms=50)`, `step(ActionRequest | None)`, `stop()`,
`clear_fault()`, `set_rate(hz)`, `get_parameter(name)`, `get_parameters()`,
`set_parameter(name, value)`, `save_parameters(path)`, `load_parameters(path)`,
and `close()`.

The rate choices are 0/100/250/500/1000Hz. Rate zero stops periodic telemetry;
the SDK requests bounded STATUS snapshots for stopped commands and refreshes stale stopped preconditions. Motion and physical homing require a positive streaming rate; rate zero is also unsuitable for the host policy runner.
No implicit reconnect or rearm occurs. A parse/read/write failure or board fault
latches `rig.error` and requests STOP. `clear_fault()` is explicit, requires a
disabled board, never arms, and clears the host latch only after the board
confirms a zero fault. STOP/HELLO retain disabled mode 4 when a fault is latched;
CLEAR returns the board to healthy idle. A stopped faulted board can be connected
for inspection and explicit clearing. Transport failures require a new Rig
object/session after the physical connection is restored.

## Clocks and sensing

`Session.clock_id` is `teensy:<session-id>`. Observation sequence unwraps the
board's uint32 control tick, and observation/sample timestamps unwrap the board's
independent uint32 acquisition microseconds. The availability basis is explicitly
`board acquisition snapshot proxy`: the state frame does not provide a separate
board publication timestamp. Sample `received_ns` therefore also uses that board
snapshot proxy. **Actual host monotonic receipt is `State.received_ns` and the
JSONL diagnostics**, never mixed into a board-clock Sample.

The magnetic pole angle is raw decoded radians with frame `encoder-zero`; its
angular velocity uses `filtered_magnetic_rate`. An unhealthy encoder produces
invalid magnetic samples with `None` values and an explanation. `State.angle_hat`
retains the filtered angle diagnostic separately. Cart position uses the `step`
source, `cart-step-home` frame, `step_count` method and `estimated` kind. It is
invalid until the board has a physical reference. Cart velocity uses
`commanded_velocity` and `estimated` kind. Step counts and commanded velocity do
not independently measure physical cart travel or slip. Vision/fusion providers
must use their own explicit source/frame/time contracts.

The host rejects receipt ages above 100ms. An action also has a stricter 20-tick
board observation budget. Conservative host elapsed time since receipt reduces
that budget. The MCU independently checks actual tick age and anchored expiry;
serial latency cannot extend the board lease.

## External policies

External acceleration is a distinct explicit mode 12. `arm()` requires healthy,
homed idle, starts at zero demand, and requires the first action within 20 ticks.
The default acceleration TTL is 20ms, anchored to the observed board tick. PING
renews only the 200ms host watchdog; it does not renew an action or experiment.
A/V sequence numbers strictly increase within the lease, without uint32 wrap.
The board echoes its **accepted** `last_seq` in state; a successful host write
alone is not a board acceptance acknowledgment.

`step()` validates the requested session, board clock, original observation,
sequence, issue/expiry, magnitude, anchored TTL and both freshness budgets before
any action write. It retains a bounded observation history to validate a recent
policy observation even when a newer frame arrives concurrently. `step(None)`
returns the latest observation and does not renew a lease.

The benign host example explicitly selects magnetic and step channels:

```sh
python examples/cartpole.py --port /dev/serial/by-id/usb-Teensy_example \
  --command policy-zero --source magnetic-step --duration 1 \
  --switches off --center-confirmed --log-dir runs/external-zero
```

This policy requests zero acceleration; it does not swing up or balance. Arbitrary
**trusted** operator policies use an explicit callable and channel tuple:

```python
from cartpole_sdk.contracts import Acceleration, Channel
from cartpole_sdk.rig.policy import run_policy

class MyPolicy:
    def __init__(self, channels):
        self.channels = channels
    def reset(self, session):
        pass
    def act(self, observation):
        return Acceleration(0.0)

channels = (Channel('pole', 'angle', 'magnetic', 'encoder-zero'),
            Channel('cart', 'position', 'step', 'cart-step-home'))
# Inside an established healthy, homed Rig context:
run_policy(rig, MyPolicy, channels=channels, duration_s=1)
```

The trusted runner selects exact channels, validates `Acceleration` output,
limits demand to 0.25m/s² by default, records requests, and always stops in
`finally`. It waits for fresh telemetry; a callback delay cannot renew a stale
board action. It never imports a submitted module or path. Untrusted policies
must execute in a separate restricted process/container behind the trusted
broker; they must never receive a Rig or transport object. The original strict
1ms Python reference policy is not silently selected at 100Hz.

## Recording and transport

Each `log_dir` run creates a unique `rig-<time>-<session>.jsonl`, with session,
commands, board replies, full state including host receipt, policy requests,
errors and termination. Action acceptance is inspected through state `last_seq`.
The latest state, observation history, in-memory diagnostic records, line buffer
and asynchronous recording queue are bounded. `records_dropped` records queue
loss; it must be zero before claiming a complete timing trace. These diagnostic
logs are separate from the SDK's strict replay-recording format.

The default adapter lazily imports pyserial, requests POSIX exclusive ownership,
uses a 5ms read timeout and a 50ms write timeout, and serializes complete frames
under one mutex. A second Rig for the same canonical device path is also refused
within the process. The reader/heartbeat thread uses interruptible Event waits;
closing stops heartbeats before STOP and its final STATUS confirmation. Pre-HELLO old frame tails/replies are discarded within the negotiation timeout; after a matching HELLO, corruption is strictly latched. Trusted tests or future private
TCP adapters can inject `transport_factory(port)`, implementing bounded
`read(size)`, `write(bytes) -> count`, and `close()`.

Local acceptance tests use real PTYs and independent fake firmware, with no
physical motion. Run `python -m unittest discover -s tests -p 'test_rig*.py'`.
These tests establish software behavior only. Real stopped rate measurements,
physical stop behavior, on-board reference runs, and external-policy hardware
commissioning are separate acceptance gates.

## Installed cart switches (2026-10-14)

The `executor-v2-cart2` firmware expects switch 1/D26 at the left end and
switch 2/D27 at the right. Both use NC-to-SIG and COM-to-GND: `closed` while
released, `open` when pressed or disconnected. Inputs 3/4 are uninstalled and
may read `open`; this build reports them but does not require them. Z pulses
are disabled. Use `info` to distinguish this build from `executor-v1`, which
incorrectly required the two uninstalled inputs for this rig.

`status` now expands the raw flags into `switch_inputs`, `homed`,
`drivers_enabled`, `encoder_healthy`, and `switch_checking_enabled`.
With switches enabled, `center` is deliberately rejected: it only declares
an operator-selected origin in explicit switchless commissioning. Physical
`home` measures both cart ends and moves to the midpoint, then stops disabled.
First validate input transitions with motor power off, and confirm direction
and usable travel before the first powered homing attempt.

A rejected firmware command latches the SDK error and sends STOP even when
`fault` is zero. After correcting the cause, `stop` then `clear` recovers the
session; `clear` still requires healthy required inputs and does not home or
start motion. Do not use `switches off` to work around an installed cart switch.
Firmware uploads and Teensy resets require motor power off (see `executor.md`).

## Encoder calibration

The updated firmware and console support two explicit stopped-only commands:

- `upright`: hold the pole physically vertical **up**, then enter the command.
- `hanging`: let the pole settle freely vertical **down**, then enter the command.

Either command needs 400 consecutive healthy samples spanning at most four
encoder counts (about 0.35 degrees) and allows up to five seconds to obtain them.
The console waits for the firmware to verify the EEPROM save, then prints the
new upright raw reference. It does not start a controller, move the cart, change
switch checking, clear a fault, or replace cart homing. A hanging capture stores
the opposite encoder count as upright. `status` should subsequently show theta
near zero when up and near plus/minus pi when down. Verify both poses before a
powered run; a save acknowledgement alone does not establish physical alignment.

Use `stop` first. If a previous rejection is latched, correct its cause and use
`clear`. Keep the selected pose still until the console reports the saved count.
Ctrl-C or SDK `stop()` cancels an unfinished capture; loss of heartbeat, encoder
health, failure to settle, or EEPROM verification failure does not report success.
The new reference survives reboot, and `info` reports it and `reference_saved`.
The previous live reference remains in use until the new save verifies. A failed
EEPROM write can invalidate the persistent record and is reported as an error.

The same commands work noninteractively with `--command upright` or
`--command hanging`, and through `rig.calibrate_encoder('upright'|'hanging')`.
No ordinary motion command's transport timeout is extended. Calibration has a
six-second host wait for the board's bounded five-second operation. Old
`executor-v1` boards are rejected locally with an update instruction.

The combined release is `~/cartpole-v2-live/releases/platform-20261014-cart-switches`.
With motor supply OFF, USB left connected, and all serial consoles closed:

```sh
cd ~/cartpole-v2-live/releases/platform-20261014-cart-switches
~/cartpole-v2-live/tools/loader-2.3/teensy_loader_cli \
  --mcu=TEENSY41 -w -v artifacts/executor-v2-cart2.hex
```

Press the Teensy program button when the uploader waits for the board. Keep
motor supply off through programming and verify the disabled state afterward.
Then start the new console from the same release directory:

```sh
uv run --locked --extra hardware cartpole-console \
  --port /dev/serial/by-id/usb-Teensyduino_USB_Serial_20242870-if00 --rate 100
```

Confirm `info` shows `executor-v2-cart2`, perform one of the calibration commands,
and check both physical poses. Commission the left/right switch transitions and
homing direction before powered `home` and `auto` tests. The archived firmware
and the previous release remain unchanged.


## Encoder diagnostic release (2026-10-14)

The active firmware still identifies as `executor-v3-encguard`. The latest paired
SDK/firmware release includes PARAM and 750 mm homing; use its matching
console from `~/cartpole-v2-live/releases/platform-20261014-parameters`:

```sh
cd ~/cartpole-v2-live/releases/platform-20261014-parameters
uv run --locked --extra hardware cartpole-console \
  --port /dev/serial/by-id/usb-Teensyduino_USB_Serial_20242870-if00 --rate 100
```

Only one console or test runner may own the port. This release was uploaded
with motor supply off and verified disabled afterward. `info` now includes
actual AS5600 configuration readback: expected control bits are 0x0300 (decimal
768 when other bits are zero), with `encoder_conf_valid: true`. The saved angle
reference remains 270. The motor gains have not been retuned. The 750 mm homing and parameter build passed stopped hardware checks, including
all 30 parameter defaults and reversible profile operations. Its first physical
HOME was stopped after 5.13 s: commanded motion was steady at -30 mm/s, but the
camera showed negligible cart movement and the owner reported jitter. Motor
tracking and full physical homing are not yet validated; see
`evidence/phase3/motor-tracking-20261014/`. Do not treat the pulse counter as
measured cart motion. A power-off connection/mechanical inspection is pending.


## Live parameter tuning and host profiles

The console can read and tune all 30 controller parameters while the executor
is stopped. Reads remain available on a stopped faulted board for diagnosis.
Writes require healthy idle, no fault, and no encoder calibration in progress.
The SDK validates names, numeric values and bounds before writing; firmware
also enforces its limits. Every successful set prints the actual board readback,
verified against the requested float32 value. A wrong-name reply or mismatched
value cannot count as a successful change.

For example, from the interactive console:

```text
stop
params
get ke
set ke 3.5
get ke
save trial.json
load trial.json
```

`params` reads all current values from the board. `save` writes those verified
live values to the specified host JSON file. `load` accepts a complete profile
or a nonempty subset of parameters, validates the entire requested update
before any write, and leaves unspecified values unchanged. Spin trip/resume
changes are ordered so the intermediate pair remains valid. A rail change must
also fit the current measured homing clearance when the cart is homed.

Profile application is a sequence of board writes, not an atomic transaction.
If a later write fails, the SDK requests STOP and reports the confirmed changed
keys and any unconfirmed key that may have changed. Inspect the live parameters
before retrying. No profile operation starts motion, homes, centers, or clears
a fault.

The deployed v6 update exposes the motion settings through the existing stopped
`params`, `get`, `set`, `save` and `load` commands. Actual boot speeds, acceleration,
jerk and recovery behavior keep their previous values. A larger accepted setting
is an operator tuning capability; it is not a measured motor performance claim.

| Setting | Default | Purpose |
|---|---:|---|
| `vmax`, `vmax_s`, `vmax_b` | 1.5 m/s | Overall, swing-up and balance speed |
| `amax_s`, `amax_b` | 25 m/s² | Swing-up and balance acceleration |
| `jmax` | 150 m/s³ | Automatic motion jerk |
| `manual_speed_max` | 0.15 m/s | Trusted manual velocity commands |
| `amax_m`, `jmax_m` | 0.5 m/s², 10 m/s³ | Manual acceleration and jerk |
| `rail_fraction` | 0.95 | Fraction of measured travel available before normal stopping boundaries |
| `rail_margin`, `rail_fault_margin` | 15 mm, 10 mm | Normal stopping and independent fault margins inside the nominal rail |
| `rail_hysteresis` | 5 mm | Inward distance before releasing rail recovery |
| `rail_recover_v`, `rail_recover_a` | 0.15 m/s, 1.5 m/s² | Inward rail-recovery motion |
| `rail_recover_s` | 8 s | Rail-recovery timeout |
| `rehome_v`, `rehome_a`, `rehome_j` | 0.08 m/s, 0.5 m/s², 10 m/s³ | Settled return to the saved midpoint |

Speed validation follows the pulse-generation ceiling, approximately 2.68 m/s
for the current 7 µs timer, 60-tooth pulley and 1/16 microstepping. The supported
operator ranges extend acceleration to 200 m/s² and jerk to 10,000 m/s³. The
motor's achievable performance can be lower. The initial tuning comparison
retains 1.5 m/s, 25 m/s² and 150 m/s³ while changing only the rail envelope.

Rail settings are coupled: the fault margin must be smaller than the normal
margin with at least 1 mm between them, and the remaining rail must accommodate
recovery hysteresis. Geometry changes are validated while stopped and use the
measured physical span. An explicit smaller `rail` preference continues to win.
Automatic return first brakes using the active automatic motion limits, then
uses the separately configured gentle rehome settings.

For example:

```text
stop
params
get rail_fraction
get rail
get jmax
save baseline.json
set jmax 200
get jmax
save jerk200.json
load baseline.json
```

Changing a setting does not start the rig. Values remain RAM-only and profiles
are loaded only when explicitly requested. Physical switch handling, encoder
health, pulse timing and command-expiry guards remain active. Homing seek/latch
speeds and spin/upright-fall recovery are separate fixed paths in this update.

Tuning changes live in board RAM. They do **not** write EEPROM and revert to the
compiled defaults after reset. Host profiles are never loaded automatically on
connection or startup. The encoder calibration's persistent EEPROM reference is
separate from these controller settings. A minimal profile is:

```json
{
  "schema_version": 1,
  "parameters": {
    "ke": 3.5,
    "kpx": 40.0
  }
}
```

A saved profile may also contain optional `source_firmware` metadata. That
identity is descriptive. The connected firmware identity selects the supported
parameter catalog (30 legacy fields or 41 v6 fields); each actual value is
verified through PARAM readback.

The same operations work noninteractively:

```sh
cartpole-console --port /dev/serial/by-id/usb-Teensy_example --command params
cartpole-console --port /dev/serial/by-id/usb-Teensy_example --command get --param ke
cartpole-console --port /dev/serial/by-id/usb-Teensy_example --command set --param ke --value 3.5
cartpole-console --port /dev/serial/by-id/usb-Teensy_example --command save --profile trial.json
cartpole-console --port /dev/serial/by-id/usb-Teensy_example --command load --profile trial.json
```

Within an established stopped `Rig` session, the matching Python methods return
actual readback values:

```python
values = rig.get_parameters()
actual_ke = rig.set_parameter('ke', 3.5)
rig.save_parameters('trial.json')
loaded = rig.load_parameters('trial.json')
```

The updated homing routine accepts a switch-to-switch span of at most **750mm**,
represented by **20,000 commanded steps** at the configured geometry. Its total
deadline and the console's default HOME wait are **75s**, including both seeks,
slow latches, backoffs and the return to the midpoint. On v6, successful HOME
also derives the operating envelope from that measured travel, reserving at least
5% overall (and at least 15 mm per end) before normal stopping boundaries. The
previous fixed 0.26 m nominal cap remains for no-switch commissioning. Position
and span still come from commanded steps; camera checks help detect lost motion.
Other motion commands retain their 60 s maximum.

An explicit `rail` value is a nominal half-envelope: normal stops are 15 mm inside
it and the hard fault is 10 mm inside. A profile containing an old `rail: 0.26`
will deliberately retain that narrower envelope even after HOME. Omit `rail`
when restoring only gains and wanting the default measured envelope on the next
fresh boot/HOME. Use `info` and `get rail` to inspect the applied result. V6
firmware and matching SDK must be installed together; see `docs/executor.md`.


## Return to an existing home

`rehome` and `Rig.rehome()` require `executor-v4-rehome` or `executor-v5-calmodel`, an already established
home, healthy stopped state, and streaming telemetry. They move only the cart
to its existing counted zero, then disable. They do not seek either switch,
change the home epoch/span/reference, or recover a lost physical position.
Use physical `home` after a hard fault or suspected lost steps. Step counts are
an estimate of cart position; reaching counted zero does not prove physical
centering when the motor has lost steps.

On this firmware, normal `auto` duration expiry enters mode **14** and returns
to that same counted home, even if auto is currently balancing or recovering.
It never begins another swing-up after return. Explicit `bal`, `manual`, and
external policies retain their existing duration behavior. `status` identifies
mode 14 with `returning_to_existing_home`; `info` retains the same 17-token
encoder and home diagnostics as v3.

The board bounds each return to **15 seconds**, retaining its host heartbeat,
encoder, switch, rail and control timing guards. STOP, quit, Ctrl-C, connection
loss or any fault cancel it. Faults are never cleared automatically, and STOP
does not schedule a later return. `Rig.rehome()` and interactive `rehome` return
asynchronously so STOP remains available at the prompt:

```text
rehome
status
stop
```

The one-shot command waits for healthy, homed, disabled idle at counted x=0 and
always requests STOP in finally:

```sh
cartpole-console --port /dev/serial/by-id/usb-Teensy_example --command rehome
cartpole-console --port /dev/serial/by-id/usb-Teensy_example --command auto --duration 5
```

For one-shot `rehome`, `--duration` bounds the host completion wait (default and
maximum **15.25 seconds**; explicit shorter waits are honored). For v4 `auto`,
`--duration` still means the requested swing-up/balance run duration, at most
60 seconds. The SDK discovers v4 through stopped INFO before starting auto and
uses a total host guard of run duration + 15 seconds + 250ms for completion
confirmation. This margin does not extend the firmware's motion deadline.
Interactive auto keeps heartbeat and telemetry monitoring active through return;
one-shot auto waits for completion before its final STOP. The host latches a
failure if this finite budget expires or return stops away from counted zero.
V1/v2/v3 auto retains its original host deadline and early final STOP; no return
is inferred for older firmware. Encoder calibration remains available on v4.


## Current sensing deployment (15 October 2026)

The maintained viewer is `cartpole-vision` in `src/cartpole_vision`, copied from
the preserved archive. `archive/vision3` remains unchanged. The Jetson user service
runs independently of the console and never opens the Teensy serial port.
The latest SDK console is installed in `~/cartpole_v2` on the Jetson:

```sh
cd ~/cartpole_v2
uv run --locked --extra hardware cartpole-console \
  --port /dev/serial/by-id/usb-Teensyduino_USB_Serial_20242870-if00 --rate 250
```

Console startup reads INFO while stopped and mirrors accepted encoder snapshots
to the viewer by default. Closing the console makes encoder telemetry stale;
camera acquisition continues. Do not run another serial owner to feed the viewer.
SDK clients opt in with `vision_publisher=EncoderPublisher()`. The publisher is
best effort and cannot write commands. See `docs/vision-usage.md` for access and
`docs/sensing.md` for source-explicit observations and actual SDK shadow fusion.

Bare `hanging` now refuses an unchecked ideal-half-turn recalibration. Choose an
approved measured model and a separately asserted current installation identity:

```text
hanging model.json installation-identity.json
```

This requires v5 firmware. The physical board still runs v4; current real evidence
does not yet validate a model. `upright` remains a direct capture on v4/v5.
`hanging ideal` explicitly requests the old half-turn assumption; on the current
rig that assumption disagrees with the verified upright and should not replace
reference370 during tuning. One-shot equivalents use `--command hanging` plus
`--hanging-model MODEL --calibration-identity IDENTITY`, or the explicit legacy
`--ideal-half-turn` option. The SDK retains legacy `calibrate_encoder('hanging')`
for compatibility; model application uses `hanging_model` and
`calibration_identity` keyword arguments. No unapproved model falls back to the
legacy operation.


## Saved operator comparison profiles, 2026-10-15

The active Jetson release is `~/cartpole-v2-live/releases/platform-20261015-v6-tunable`.
Launch with `uv run --locked --extra hardware cartpole-console --port /dev/serial/by-id/usb-Teensyduino_USB_Serial_20242870-if00 --rate 250`.
At the stopped prompt, `load profiles/last-observed-20261015.json` restores the
last actually executed AUTO trial and `params` confirms values. Its overall
speed cap is1.0m/s, pw3.5, pz.85, pc1=-5, pc2=-6, jmax150 and bw30. It is an
experimental profile:6.044s continuous balance, then rail recovery and a later
encoder communication fault. The owner reported liking that run.

`profiles/original-working-20261012.json` holds the exact archived cart tuning
(pw4.5, pc1=-3, pc2=-4, catch_a.6, approach_v.3, vmax1.5). Its new comparison
was blocked before AUTO began. Both runnable profiles omit explicit rail
half-span so physical HOME determines the current travel envelope; the exact
last-run snapshot is preserved separately. Neither profile changes the saved
upright reference330. Load the desired profile explicitly after a reboot;
profiles are not applied automatically. `auto` and `bal` execute on the Teensy
at1kHz; the console uses the PythonSDK for commands and telemetry.

Powered testing is paused pending investigation of recurring encoder I²C errors,
three of which occurred around12cm left of home. Do not use these profiles to
bypass that unresolved check.
