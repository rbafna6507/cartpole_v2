# Phase 1: local policy contracts and deterministic replay

Authorized by the owner on 2026-10-13, following the architecture and Phase 0
baseline. Execute locally in cartpole_v2. Preserve archived control, firmware,
vision2 and vision3 source. No live policy, actuation, flashing or calibration.

## Outcomes and boundaries

A dependency-free Python SDK can describe observations, select sensor channels,
record/reload them, and run a trusted local policy against recorded observations.
The first adapters read preserved console CSV and vision3 states JSONL. Replay
never changes future observations in response to an action: it is useful for
integration, determinism and shadow comparisons, not closed-loop evaluation.
MuJoCo, a live broker, MCU command framing and the controller port follow later.

Use immutable dataclasses with strict construction and JSON validation, Python
3.11+, SI units and named cart/joint topology. No import opens a device or socket.
Unknown schema versions, non-finite values, bool-as-number, duplicate channels,
unknown joints, invalid ordering and inconsistent clocks must fail explicitly.

## Contract

Session identifies a unique recording/run, clock domain and cart/joint names.
Observation identifies that session, sequence and availability time in integer
nanoseconds. Each scalar sample names entity, quantity, source, frame, method,
value, validity and reason; acquisition, effective and receive times are separate
nullable fields in the session clock. Units are explicit and validated against
quantity (position m, velocity m/s, angle rad, angular velocity rad/s).

Sources include magnetic encoder, step integration, vision, fused estimate and
simulation. Validity is valid, invalid or unknown. Estimates and predictions are
labeled separately from measurements. A finite number alone does not establish
validity. Channel selection requires an explicit source and frame per quantity;
it rejects invalid/unknown, missing, stale or future effective times. It neither
silently substitutes sensors nor fuses data. Legacy coordinate frames stay
separate until measured alignment is supplied. Multi-joint topology is a data
contract, not a claim of commissioned double/triple hardware support.

Policy reset receives Session; act receives Observation and returns an
Acceleration intent in m/s² or None (no request, not zero acceleration or stop).
The trusted replay runner wraps intent in an expiring ActionRequest tied to the
session, clock and exact observation, with monotonic action sequence. Validation
checks finite values, configured magnitude, lifetime, observation age, session,
clock, sequence and strict expiration. Example limits are illustrative offline
settings, not physical rig limits. No Python validator is a safety substitute.

## Recordings, adapters and replay

A versioned JSONL recording has one session header, ordered observations and a
required count footer. Reader/writer reject incomplete or inconsistent sessions,
duplicate/non-increasing sequences and decreasing availability times. Writer
creates a new file and removes its partial file on an exception; no overwrite.
Deterministic output uses sorted keys, compact JSON and no wall-clock fields.

Console CSV requires the 12 baseline columns. t_ms is a 32-bit board emission
clock, not acquisition/host receipt. Wraparound unwraps; a smaller backward jump
starts a new session segment and must not be silently merged. Angle is raw;
angular velocity uses the firmware filter; cart values are step-derived. Sensor
health/calibration is absent: import marks those values unknown, preserving
numbers for analysis without making them policy-valid. No inferred host alignment.

Vision JSONL uses camera host-read t, frame seq, validity/status, and separate
velocity effective times. Sensor acquisition remains unknown. Availability is
host-read plus reported host_read_to_result_ms when available; the fallback is
explicitly labeled host-read proxy. Invalid/stale rows remain invalid even if
numeric fields are retained. Calibration changes/events are not fully in the
states file: the importer requires a caller-provided session and calibration/frame
identity, and documents that a file must represent one calibration epoch.
Never combine independently clocked logs by row number or guessed offset.

Replay uses recorded availability time with no sleeping and resets policy state
once per session. It logs issued requests or missing intent deterministically.
It does not import arbitrary policies from untrusted uploads; local examples are
trusted Python. Real archived snippets exercise both adapters; generated fixtures
exercise failures, wraps, gaps, timestamp skew and malformed schemas.

## Tunnel follow-up

With no explicit destination, discover current IPv6 through the authenticated
bootstrap SSH host `jetson` using only `ip -j -6 addr show scope global`. Filter
non-public, expired, deprecated, tentative and failed addresses; prefer stable
addresses over temporary ones and probe bounded TCP connectivity. Reuse bootstrap
SSH configuration/user and its effective host-key identity with Hostname and
HostKeyAlias overrides. Keep StrictHostKeyChecking enabled and never keyscan or
silently accept a new key. Authentication may still ask for the normal password.
A positional destination or JETSON_SSH_TARGET bypasses discovery, preserving the
manual/Tailscale escape hatch. No reachable address is a clear error explaining
that explicit fallback; do not silently select the known poor video route.
The shell remains a tiny launcher for a standard-library Python helper. Only
read-only discovery and temporary tunnel verification may contact the Jetson;
Phase 1 policies and all tests remain offline.
