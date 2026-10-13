# Deployment starter design

User-authorized scope: a new deployment directory, firmware based on the working Ethernet rig, Python mini SDK, MuJoCo environment, and characterization workflow. Upload hosting and sensorshare are architecture work only in this iteration. No board flashing, physical motion, remote deployment, or public exposure is performed.

## Evidence and decisions

Source root: /Users/rbafna/projects/cartpole. Existing files are reference-only for this change. The checkout already contains extensive unrelated changes; add only deployment/. Stage/build separately and copy the finished directory there.

Teensy 4.1 on Copperhill, native QNEthernet 0.37.0, TCP 192.168.50.2:9000; Jetson peer .1. Cart STEP 2, DIR 3, Z STEP 4/6, shared active-low enable 8. Wire1 SDA17/SCL16, AS5600 0x36. 60T GT2 2 mm, 200 full steps, 16 microsteps gives 26666.666667 steps/m. Control 1 kHz; DDS 7 us. No direct cart encoder, limit-switch pinout, or IMU implementation found. Never synthesize hardware IMU readings. All cart observations from hardware must say position_source=commanded_steps.

The initial single-link profile follows the source's 125 mm arm, 0.01105 kg arm and 0.0117 kg tip masses. Archived free-decay fit: effective length 0.124454888 m and angular damping 0.913383 /s. The current assembly remains unconfirmed until measured. 175 mm historical geometry is not silently substituted. Cart mass, COM and actuator tracking remain provisional.

Use a new small trusted executor assembled from the existing tested motion geometry and motion governor, rather than exposing the legacy command parser with its enable, tuning, and automatic restart paths. Preserve the working source. V1 exposes cart acceleration/velocity/position targets, state/encoder streaming, explicit manual center-reference, arm/disarm and fault reset. Z movement and IMU are unsupported capabilities until their independent bounds/wiring exist. Shared enable still affects Z drivers; secure the vertical mechanism before hardware runs.

Owner ceilings for commissioning: speed 0.25 m/s, acceleration 2 m/s2, jerk 20 m/s3, rail half-span at most 0.15 m. These are development restrictions, not certified safe limits or proof of motor tracking. Command TTL 10..100 ms. Boot/disconnect/invalid active input/deadline/encoder fault disables pulses and latches fault where appropriate. Stop invalidates the manual home assertion. No auto restart or remote widening of limits. Independent hardware inhibit and direct position feedback remain commissioning prerequisites for unattended public motion.

## Shared Python API

Package cartpole_deploy, Python >=3.10. Root owns types.py, config.py, characterization.py, cli.py, package metadata and docs. Firmware agent owns firmware/ and tests/native. SDK agent owns protocol.py, hardware.py and tests/test_protocol.py/test_hardware.py. Simulation agent owns simulation.py, model.py, gym_env.py and tests/test_simulation.py plus models/ if useful.

Observation dataclass fields: time_us:int (MCU uint32 microseconds), mode:str (DISARMED/ARMED/RUNNING/FAULT), theta_rad:float (0 upright, positive top towards +x), omega_rad_s:float, x_m:float, v_m_s:float, a_m_s2:float, encoder_raw:int, flags:int, sequence:int, session:int, fault:str, position_source:str default commanded_steps. flags bit0 encoder_valid, bit1 homed, bit2 enabled. to_dict() serializes fields. Properties encoder_valid/homed/enabled expose flags.

RigConfig dataclass with validated SI scalars: arm_length_m=.125, arm_mass_kg=.01105, tip_mass_kg=.0117, effective_length_m=.124454888, damping_per_s=.913383, coulomb_rad_s2=0, com_m=.09464285714285714 (uniform arm + tip assumption), cart_mass_kg=.5, rail_half_m=.15, max_velocity_m_s=.25, max_acceleration_m_s2=2, max_jerk_m_s3=20, control_dt_s=.001, policy_dt_s=.01, encoder_counts=4096, encoder_upright_raw=0, sensor_noise_rad=0, actuator_time_constant_s=.01, actuator_force_limit_n=5, seed=0. Provenance is a dict; defaults explicitly provisional where unmeasured. total_pendulum_mass_kg, pivot_inertia_kg_m2 properties (I=mass*com*effective_length), load(path), to_dict(), save(path) methods. Known profile status/confirmation in provenance, not claims of current calibration. All physical positive values and step sizes finite, damping/friction/noise nonnegative; dt ratios integral.

Rig interface implemented by HardwareRig and SimRig:
- read() -> Observation
- home(rail_half_m:float=.15) -> None: manual center assertion while disarmed, no automatic movement
- arm(session:int|None=None) -> None: explicit, require valid home and encoder
- command(kind:str, value:float, ttl_ms:int=50) -> None: kinds acceleration/velocity/position, requires arming, fresh observation, increasing sequence; runtime never refreshes a stale action itself
- stop() -> None: disabled, home invalidated
- clear_fault() -> None: disarmed and unhomed, never motion
- close() -> None; context manager
- capabilities() -> dict
SimRig(config:RigConfig|None=None), reset(theta_rad=pi, omega_rad_s=0, x_m=0, v_m_s=0), advance(seconds:float)->Observation. read does not advance simulation time. HardwareRig(host='192.168.50.2', port=9000, timeout=1.0, serial_port=None), set_stream_rate(hz), iter_observations() optional. No opening network or moving on import. Hardware connection may request info/state but never silently enables. Commands never automatically retry after uncertain delivery. Explicit stop on close best effort; firmware TTL remains authority.

## Wire protocol v1

ASCII newline frames both directions: @PAYLOAD*HHHH\n. CRC16/CCITT-FALSE polynomial 0x1021, init 0xffff, no final xor. Maximum complete frame 256 bytes, parser discards oversized lines to newline. CRC is integrity, not authentication. Private cable only.

Requests payloads:
`D1 info`
`D1 state`
`D1 home HALF_SPAN_M`
`D1 arm SESSION_UINT32_NONZERO`
`D1 act SESSION SEQUENCE OBSERVED_US TTL_MS KIND VALUE` (KIND a/v/x)
`D1 stop`
`D1 clear`
`D1 stream HZ` (0..500)

State payload exactly:
`D1 S TIME_US MODE THETA OMEGA X V A RAW FLAGS SEQUENCE SESSION FAULT`
MODE one of DISARMED/ARMED/RUNNING/FAULT. FAULT a single token, none when absent.
Info: `D1 I 1 1000 500 60 26666.666667 0.15 0.25 2 20 encoder`
Acknowledgement: `D1 OK VERB` (act optionally includes accepted sequence; arm optionally session).
Error: `D1 ERR CODE` (single-token code, optional descriptive tokens).

Only D1 parser is exposed; legacy stop/off can be accepted as a local emergency override, no other legacy motion command. State timestamp references a MCU sensor sample. Reject future/stale observation references, old or duplicate sequences, wrong session, nonfinite values, out-of-bound targets, invalid TTL, extra tokens, and malformed active input. Act expiry is OBSERVED_US+TTL_MS*1000, NOT receive time, with uint32 wrap-safe comparisons. The SDK reads a fresh state before command if necessary. Arm also expires after 100 ms without first action. State/stream traffic cannot extend motion lease. Faults invalidate home/session and remain latched until clear, then explicit home and arm. Passive state-only clients never hold/enable motion.

## Simulation and identification

MuJoCo model has cart slide and pendulum hinge, correct SI units and theta convention. Preserve visible .125m geometry, explicit COM and inertia from the effective-length fit. Model acceleration intent through the same jerk/speed/rail governor and a bounded lagged velocity/force actuator; do not pretend to have identified drive friction, cart mass or missed steps. Model 4096-count angle observations, retain simulator ground truth separately, and flag actual vs pulse-derived cart position. Disabled cart in passive decay tests is mechanically clamped by an explicit simulation fixture mode, not an implicit promise for real hardware.

Provide Gymnasium wrapper with continuous acceleration action and fresh observations, reset and terminated/truncated semantics; low commissioning limits mean it is scaffolding for future training, not a validated balance benchmark. SDK scripts run both backends using the same home/arm/command/read interface. Sim time advances explicitly and action expiry works without further client calls.

Characterization CLI supports noise and passive decay capture, bounded position/sine drive capture, fit from explicit released-data interval, held-out validation, and export a NEW tuned config. Hardware drive requires --execute, measured half-span and explicit center/secured-Z acknowledgement; default CLI backend simulation and no actuation on connection. Always stop in finally, preserve partial CSV and metadata after failures. Timestamp samples, requested/applied actions, raw counts, flags, transport timing, source/backend, config, release window, and parameter provenance. Analyze gaps, invalid sensors and stationary cart assumptions; never infer actual cart mass/friction/tracking from commanded step count alone. Fit effective length and damping (optionally dry friction only if identifiable) using nonlinear integration, not noisy second differences. Train/validation are separate captures; export remains provisional without independent validation. Motor characterization records commanded response and optionally externally measured x for later identification; explicitly report what is not identifiable.

## Internet boundary

Proposed: browser/CLI obtains authenticated upload URL, writes immutable artifact to object storage, submits a manifest/hash to queue. Jetson makes outbound authenticated connection, leases one job, verifies/hash-checks and stages it, validates offline, runs bounded sandboxed controller through local SDK broker, reports results. Upload completion never means execution. No public raw Teensy TCP, unrestricted shell, direct firmware upload, or Python execution in the web handler.

Sensorshare: one local acquisition/broker process owns Teensy connection; read-only subscribers receive copied timestamped samples through a separate service/relay. Bounded queues drop old frames for slow readers, record sequence gaps, protect control scheduling. Distinguish encoder/derived state from actual IMU; do not invent IMU data. Public stream clients run on users' machines; Jetson hosts producer. Separate permissions read:sensors and run:experiment. Vercel may host UI/auth/job metadata; choose live transport based on verified current limits and do not couple it to motor deadlines.

## Validation

Native C++ tests for strict parsing, freshness/sequence/session, timeout and fault latch, governor rails and nonfinite inputs. Real Teensy compile with installed toolchain. Python tests with loopback TCP for CRC, fragmented streams, errors, timeouts and context cleanup; no device connection. Headless MuJoCo model, sign, free-decay, lease expiry, bounds, Gym API tests. Synthetic parameter recovery and separate validation trace; end-to-end CLI capture/fit/sim smoke. Final independent review. Physical timing, safety wiring, live sensors and model validation require supervised bench work and are not claimed here.
