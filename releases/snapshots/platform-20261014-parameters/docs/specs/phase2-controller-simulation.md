# Phase 2: Python reference controller and MuJoCo backend

The owner authorized Phase 2 on 2026-10-13, following the completed SDK foundation,
and previously authorized parallel chunked implementation with full autonomy.
Build and verify locally in cartpole_v2. Preserve all archived control, firmware
and vision algorithms. No Jetson commands, actuation, flashing or calibration.

## Outcomes

1. A readable Python port of the saved cart controller: estimator, tuned gains,
   startup pumping, approach/capture, balance/loss, rail/spin/upright recovery,
   response watch, and jerk/speed/rail governor. Keep demanded and governed
   acceleration separate. Preserve the exact 1 ms algorithmic step; do not claim
   equivalent behavior at the 100 Hz telemetry rate or hard real-time Python.
2. An independently compiled C++ reference exercising the archived firmware's
   actual controlTick and headers under local hardware stubs. Native-only source
   substitutions must be minimal, deterministic, asserted against exact original
   text, and documented. Never rewrite controller logic to match the Python port.
3. An optional MuJoCo physics backend and Gymnasium environment using the Phase 1
   contracts, with explicit acceleration-to-force conversion and sensor timing.
4. Runnable examples, deterministic rollouts/recordings and provenance that let
   the next hardware/safety and identification phases build on measured boundaries.

The Python port is an offline reference, not replacement safety firmware. The
simulator is an unvalidated surrogate, not a calibrated digital twin. Balance in
it does not establish hardware safety or transfer. Public policy isolation, broker,
MCU transport/safety and physical system identification stay in later phases.

## Common conventions and integration

SI units. x increases in positive cart motion. theta=0 is upright, theta=±pi
hanging; positive theta leans toward positive x. Controller plant convention is
alpha=(g*sin(theta)-cart_acceleration*cos(theta))/L_eff. Radians are wrapped using
atan2(sin,cos); raw firmware telemetry and internal estimated angle remain distinct.

The control core is fixed-step and accepts decoded angle/position with explicit
clock and encoder health. It retains the firmware's command-velocity state, which
is not independent measured velocity. Numeric agreement against float32 C++ uses
reported absolute/relative tolerances; discrete mode/guard comparisons must match
away from explicitly identified float boundary ambiguity. Do not advertise bitwise
or whole-board equivalence: I2C, pulse ISR, EEPROM, display and OS scheduling are
outside these local tests. Health/host timeout branches of the control tick must
still be exercised. Preserve the saved automatic pw=4.5 and upright-only bal_pw=4,
plus the remaining preset settings; source/hash the packaged preset.

The SDK wrapper explicitly selects angle/position channels and enforces the 1 ms
observation cadence. It resets once per session and fails closed on unusable
channels or gaps, without catch-up on one stale sample. It returns governed
acceleration for the Phase 2 simulator. A future hardware adapter must place the
motion governor exactly once; its final authority belongs in the Teensy. Expose
raw demand in controller diagnostics for that integration.

MuJoCo uses a cart slider and an unactuated hinge with named joints. The initial
rig config is explicit and provisional: effective length from the saved preset,
rail half-length from the saved preset, and assumed masses, damping and force
limit. A uniform-rod surrogate with length 1.5*L_eff matches the controller's
small-angle effective length; this is not a claim about the rig's geometric arm
length or mass distribution. Model/config metadata must identify those assumptions.
No silent reuse of old deployment geometry or unverified mechanical calibration.

Acceleration commands are not forces. At each physics step solve the unactuated
joint equation for its acceleration, then obtain the cart generalized force needed
for the requested cart acceleration, using MuJoCo's mass matrix, bias and passive
forces. Clip only to an explicit actuator-force bound and report requested/applied
force and achieved acceleration. The model has no active contacts before rail
termination. Force saturation, gravity/sign and free-hinge behavior need analytic
or finite-difference tests. No hidden pole torque or state teleportation.

The simulator exposes truth separately from policy observations. Simulated sensor
readings use source='simulation', explicit frame/method, validity, and distinct
acquisition/effective/receipt/availability times. Configurable sampling period,
delay, noise and dropout are seeded and bounded. Startup before delayed data is
available is unknown, never a valid zero. Observation sequence/time is monotonic;
older repeated samples keep their original effective time. A separate truth API
supports diagnostics without silently giving a policy ground truth.

Backend accepts SDK ActionRequest or None. Validate before changing state, including
session/clock/observation sequence, monotonic action sequence, expiry, magnitude and
lifetime. A new request replaces the active lease; None supplies no new request and
retains an unexpired lease. Expiration removes its acceleration demand (zero-demand
fallback in this provisional simulator), not a physical emergency-stop guarantee.
Recheck expiry at physics substeps. Reset clears leases/counters/history and reseeds
sensor randomness. Reject stepping after rail termination or episode truncation.

Gymnasium wrapper uses continuous scalar acceleration in m/s² and observation
vector [x, v, sin(theta), cos(theta), omega], with validity/age metadata available
in info. Invalid observation values must be represented explicitly (validity mask
in observation or clear finite placeholder plus mask, never hidden invalid zeros).
Use a Dict observation if needed for state plus validity/age. Rail crossing is
termination; finite time horizon is truncation. Seeded reset and step follow current
Gymnasium API and pass its environment checker. Rewards must be documented as an
illustrative upright/centering/control-cost objective, not a proven training target.

## Verification and packaging

Keep base SDK imports dependency-free. Put MuJoCo/Gymnasium/numpy in a locked optional
`sim` extra. Core/reference tests run without simulation dependencies; optional
simulation tests run explicitly with the extra. C++ compiler is a development/test
dependency, not needed to use the Python controller or an installed wheel.

Parity tests compile original firmware logic and compare primitive outputs plus
scripted stateful trajectories across startup, capture/loss, both rail directions,
spin states, upright stop/reject, host/encoder faults, response watch and governor.
Boundary tests include wrap, exact guards/deadlines, resets and invalid values.
Keep explicit coverage and numerical error reports. A second Python translation is
not an acceptable C++ oracle. Preserved-source hashes must still match all 70 files.

Simulator tests cover deterministic reset/rollouts, force semantics and saturation,
physical signs, sample aging/delay/dropout, action rejection/expiry, rail/horizon
ends, step-after-done, Gym check_env, and same-policy SDK integration. Build and
install a wheel outside the repository so packaged model/preset resources are
actually verified. End-to-end demos save model/config/seed/controller provenance,
observations and action/plant diagnostics. No result should be described as rig
validation. One independent final review covers the integrated implementation.
