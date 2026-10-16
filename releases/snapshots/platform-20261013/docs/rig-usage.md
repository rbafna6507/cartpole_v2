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
`manual [seconds]`, `velocity m/s [ttl_ms]`, `stop`, `center`, `home`,
`switches on|off`, `status`, `clear`, `rate hz`, and `quit`.
`balance` aliases `bal`. Durations are bounded to 1ms..60s. The board's watchdog
and duration cutoff remain active while the prompt waits for input.

`auto` and `bal` run the preserved controller **on the board** at its original
1kHz. The host telemetry rate does not change its controller period. `manual`
starts with zero demand; each `velocity` command is one expiring lease, limited
to 0.15m/s during commissioning. The prompt does not silently renew that lease.

The physical switch profile is enabled by default in firmware. `home` runs the
bounded physical switch routine only with that profile enabled. For the current
rig with no installed switches, `switches off` explicitly selects commissioning
mode, and `center` asserts that the operator has physically centered the cart
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
run stops in `finally`, including Ctrl-C and exceptions. The script requests
STOP slightly before the MCU duration cutoff (up to 10ms, bounded to one quarter
of very short runs), which keeps ordinary completion separate from the board's
hard duration fault. `--command bal` requires the board's upright start conditions. `--command home` waits for healthy homed disabled completion; `--duration` bounds this wait (default 60s; explicit shorter timeouts are honored). Timeout, fault and interruption stop in finally.

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
`observation()`, `wait_state(after_tick=None, timeout=1)`, `center()`, `home()`,
`configure_switches(bool)`, `start(mode='auto', duration_s=10)`,
`arm(duration_s=10)`, `set_acceleration(value, ttl_ms=20)`,
`set_velocity(value, ttl_ms=50)`, `step(ActionRequest | None)`, `stop()`,
`clear_fault()`, `set_rate(hz)`, and `close()`.

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
