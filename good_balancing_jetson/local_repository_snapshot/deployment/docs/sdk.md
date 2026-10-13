# Python mini SDK

`HardwareRig` implements the shared `read/home/arm/command/stop/clear_fault/close`
interface. Python 3.10 or newer is required. Importing the package opens no
connection. Constructing a hardware rig opens its transport and requests `info`;
it never enables drivers, homes, starts a heartbeat, or sends movement.

```python
from cartpole_deploy.hardware import HardwareRig

# Read-only inspection on the private Teensy–Jetson cable.
with HardwareRig(host="192.168.50.2", port=9000, timeout=1.0) as rig:
    print(rig.capabilities())
    print(rig.read().to_dict())
```

The default transport is a direct TCP connection with `TCP_NODELAY`. This wire
protocol has CRC integrity, no authentication or encryption; it belongs on the
private rig link. A local broker should own the connection and provide sensor
copies or bounded control access to other processes. A passive SDK context does
not send `stop` on close; firmware disconnect policy still applies to whichever
transport/session owns the rig.

USB is optional: install the package's serial extra (or `pyserial`), then use
`HardwareRig(serial_port="/dev/ttyACM0")`. The import is lazy and USB is not
opened unless `serial_port` is supplied. Baud rate is 115200; the same framed D1
protocol runs in both directions. USB device behavior requires bench verification.

## Explicit commissioning sequence

Manual home is a human assertion that the cart is at the mechanical center. It
performs no automatic movement or switch search. Before using this sequence,
complete the bench checklist, secure the vertical mechanism affected by shared
enable, measure the travel span, and place the cart at its center.

```python
with HardwareRig() as rig:
    rig.clear_fault()             # remains disabled; invalidates prior home
    rig.home(rail_half_m=0.10)    # measured half-span, 0.03..0.15 m
    rig.arm()                    # new random nonzero uint32 session
    rig.command("acceleration", 0.10, ttl_ms=50)
    print(rig.read().to_dict())
    rig.stop()                   # disable and invalidate home
```

`command` accepts `acceleration` in m/s², `velocity` in m/s, and `position` in
metres relative to the asserted center. Client checks mirror commissioning caps:
0.25 m/s, 2 m/s², position magnitude at most the asserted half-span minus
0.015 m. The MCU also enforces jerk, rail margins, driver state, sample freshness,
session, increasing sequence, and its local caps. No client setting can widen
these limits. A session cannot reuse the previous session number; a sequence
cannot wrap. Stop and clear require explicit home and arm before more motion.

Every command requests state immediately before sending its action. The state
roundtrip, action write and acknowledgement must all finish within the smaller
of the configured transport timeout and the action TTL (integer 10..100 ms).
Pending telemetry is drained within a bounded budget before that state request;
a backwards MCU clock is rejected, with uint32 timestamp wrap permitted.
The exact MCU sample timestamp is transmitted as the action reference. Its
expiry is **sample time + TTL**, never receive time. Already delayed packets can
still be in transit, so the MCU is the final authority on actual sample age and
acceptance. The initial arm acknowledgement is limited to 100 ms as well.

There is no autonomous heartbeat, background thread, action renewal, or retry.
Reading state and streaming cannot extend a movement lease. If Python stalls or
stops sending actions, the MCU expires the lease. Plan the policy timing and
transport margin accordingly; a successful ACK is not a measurement of physical
motor tracking.

Closing a client that successfully armed makes one best-effort stop attempt,
bounded to 100 ms or the configured timeout, then closes the transport. A
rejected arm does not acquire stop ownership. A timeout or malformed reply closes
the connection immediately because delivery/response alignment is uncertain;
firmware disconnect and TTL handling are the fallback. A context manager preserves
an exception from its body even if cleanup cannot obtain a stop acknowledgement.

## Observation and streaming

`read()` requests a sample and returns `Observation`. Hardware `x_m`, `v_m_s`,
and `a_m_s2` describe issued step pulses/governed targets, with
`position_source="commanded_steps"`. They cannot establish actual cart position,
missed steps, actuator tracking, or cart mass. `theta_rad` uses zero upright and
positive angle toward +x; `encoder_raw` is the AS5600 12-bit reading. Angular
velocity is derived. Flags expose `encoder_valid`, `homed`, and `enabled`.
Capabilities truthfully report an encoder, no IMU, and no Z movement. The
stream contains no fabricated accelerometer or gyroscope data.

```python
with HardwareRig() as rig:
    rig.set_stream_rate(100)      # integer 0..500 Hz; zero disables
    samples = rig.iter_observations()
    for _ in range(100):
        print(next(samples).to_dict())
    rig.set_stream_rate(0)
```

The iterator sends no requests or actions. It is synchronous and not a
multi-subscriber broker. Parse buffers are bounded to 256-byte frames, at most
64 pending messages, and a finite request deadline. Excessive backlog or broken
frames fail the connection instead of letting old telemetry accumulate.

## Failures and recovery

- `DeviceError`: a CRC-checked `D1 ERR` rejection; inspect `.code` and `.detail`.
  No request is repeated. Read state to establish the MCU's fault/mode.
- `ProtocolError`: bad CRC, malformed/oversized frame, unknown reply, invalid
  schema, clock rollback, or queue overflow. The transport is closed.
- `TransportError`: timeout, peer disconnect or I/O failure. Delivery may have
  occurred; the transport is closed and the command is never retried.
- `ValueError`: local invalid argument or an observation that does not permit
  the requested arm/action.

Recover deliberately: establish why the lease/fault failed, reconnect if needed,
inspect state, clear a latched fault, manually re-center/home, then arm a new
session. Reconnection itself cannot restart motion.

The loopback test suite uses real localhost TCP servers, fragmented frames,
interleaved state replies, malformed CRC, peer close, delayed responses, session
and sequence checks, timestamp wrap/rollback, and context cleanup. No test
connects to Teensy or moves hardware. Live Ethernet/USB timing, actual sensors,
physical stop distances, shared-enable behavior and model tracking remain bench
validation work.
