# Live rig platform: remaining phases

Owner authorization (2026-10-13): implement all remaining phases, operate the
Jetson/rig, test and identify the plant autonomously. Acceptance is an SDK-backed
cartpole.py that commands real swing-up/balance, with external Python policies
validated separately. Hardware unchanged; cart physically centered; switches not
yet installed. Switch/homing behavior is requested now, based on the PCB nets.

Preserve archive algorithms and current hardware calibration. All new firmware,
providers and applications live outside archive. A single parent operator owns
hardware during development; agents perform local implementation/tests only.
Write explicit evidence for each completion, not implied by another phase.

## Phase 3: executor, SDK and operator console

Copy the proven controller/driver implementation to firmware/teensy_executor.
Retain the original inner 1 kHz controller and ISR timing as an operator reference
mode while adding a distinct bounded external-acceleration mode. A new framed
protocol owns commands, exclusive host sessions, telemetry, action age/expiry,
experiment lifetime, faults and physical reference state. Malformed, stale,
replayed or wrong-session actions must never refresh a lease or arm motion.
Heartbeat cannot renew an acceleration. Halt on an expired external lease;
foreground stalls retain the independent ISR cutoff. No implicit restart.

Telemetry carries board tick/time, raw and filtered angle/rate, step-derived cart
position and commanded velocity/acceleration, health, mode, limits, fault and last
accepted action. Replies and commands are CRC-protected. Use USB first; transport
semantics permit private TCP later, without changing command meaning. Measure
100/250/500/1000 Hz in a stopped state before selecting a host control rate.
Emit latest telemetry rather than draining a stale historical FIFO.

The SDK owns serial exclusively, performs explicit session negotiation, and never
arms on connect/reconnect. A trusted broker separates operator home/arm/mode
operations from policy observation/acceleration. Its policy runner records clocks,
requests, acknowledgments and termination, and stops in finally on exceptions,
timeouts, invalid output or stale state. The operator CLI is examples/cartpole.py;
board-reference auto/balance and external policy modes are visibly distinct.
Physical centering confirmation can establish a temporary manual home while no
switches exist. It is not persistent across reboot or a fault losing position.

The new firmware's switch profile follows verified schematic AND PCB nets. An
explicit no-switch commissioning profile remains separate. Enabled switch mode
must fail closed on the electrically detectable unplugged/broken-wire states.
Homing uses a bounded low-speed seek, immediate edge stop, release/backoff, slower
repeat approach, valid edge coordinate and controlled centering. Every stage has
time/travel limits and handles active-at-start, stuck-active, absent-trigger,
contradictory switch and disconnect/stop. Physical switch polarity/direction and
stop distance still need commissioning after soldering; software tests cannot
certify the assembled circuit. Shared Z-enable effects must be understood before
changing shared driver state or assuming a switch can be backed off.

## Phase 4: sensing and identification

Consume existing vision3 observations through a new provider without modifying
vision3. Preserve validity, calibration identity and distinct effective times.
Never hide vision loss or claim step counts independently measure cart travel.
Collect synchronized magnetic and vision records where available; identify
pendulum effective length/damping and input delay using train/held-out trials.
Cart scale/slip/actuator parameters require independent cart measurement. Fit only
identifiable parameters and keep uncertain quantities explicit. No generated fit
becomes a commissioned safety limit. Characterization motions use bounded low
amplitude/velocity/duration after executor faults and stopping have been tested.

## Phase 5: actual policy acceptance

First prove the SDK console can run the preserved on-board reference controller
with its saved gains. Then test external acceleration with benign bounded
policies and staged magnitude/rate, recording host timing and MCU acceptance.
The strict Phase2 1ms reference wrapper cannot silently be run at100Hz. Any new
host-rate controller/observer is a separate policy and requires simulation,
shadow evaluation and physical validation. RL policy tooling uses the same SDK
contract and records model/config/training provenance; simulation success alone
never marks a policy hardware accepted.

## Phase 6: submission, queue, isolation and viewer

Provide upload/queue/result services with authentication, immutable artifacts,
bounded sizes and durable run state. Run untrusted Python only in an independently
restricted container (no device, Docker socket, host credentials or network;
nonroot, readonly filesystem, CPU/memory/pid/wall limits). The trusted runner alone
owns the broker and accepts bounded JSON policy outputs. A queue must recover
stale claims, never duplicate an active hardware lease, and record interruptions.
The portal is a separate service; the Jetson pulls approved work outbound.
Do not expose a public listener or label isolation commissioned until the target
runtime and adversarial tests pass. Any missing infrastructure remains an explicit
operational blocker while all independent software work proceeds.

## Interactive MuJoCo viewer

An actual native MuJoCo GUI displays the SDK-driven simulation, using1ms physics
and render pacing independent from control. Pause/reset/status and explicit
fault/end states are required; GUI editing must not corrupt backend/controller
state. macOS uses the official mjpython launcher. No canned animation or hardware
motion is involved in the viewer.

## Evidence and progression

Unit/native protocol+fault tests, real Teensy compile, stopped hardware handshake
and rate measurements, expiry/disconnect tests with constrained motion, bounded
reference runs, identification/held-out residuals, and adversarial sandbox/queue
tests are separate acceptance gates. Preserve a recoverable known-working build
and live calibration before flashing. Never claim phases complete where an
actual physical or deployment prerequisite remains unmet. Owner autonomy replaces
repeated approval gates; missing physical facts are requested while independent
work continues.


## Sensing integration update, 15 October 2026

`executor-v5-calmodel` retains v4 INFO/rehome and adds stopped-only
`V2 CALIBRATE sid hanging offset_counts` with a bounded signed integer correction.
Model capture quality and cancellation are specified in `docs/executor.md`.
The physical board is still v4; compiling v5 is not evidence of deployment.

`EncoderPublisher` mirrors the sole SDK serial reader over loopbackUDP3096.
The maintained viewer and source-explicit shadow observer consume this feed;
neither opens serial. Actual SDK fusion uses loopbackUDP3097 and is visibly
separate from the legacy display comparison. Missing/stale sources invalidate
the estimate. Explicit source/calibration/frame/clock identities are required;
reference changes do not silently reset a running observer. Runtime capture,
processing, encoding and browser display rates are measured separately. All
current fusion packets remain uncommissioned and ineligible for control.
