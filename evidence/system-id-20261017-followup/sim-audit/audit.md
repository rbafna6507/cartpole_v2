# Simulator, actuator and SDK observation audit

Offline review against repository `f849312` and the final stopped inspection at
`evidence/system-id-20261017/raw-final-inspection/final-inspect-01/report.json`.
No hardware, network, serial, calibration, controller setting or frozen evidence
was changed by this review. The new adapter is a software fidelity improvement;
it does not make the provisional physical model an accepted rig model.

## Concrete findings

The frozen `sim/gym_env.py:28` constructs `MujocoBackend` directly. Its action
means executed acceleration with an assumed force cap. The physical SDK sends
raw acceleration intent (`rig/client.py:728`), which external firmware mode
governs every 1 ms (`teensy_executor.ino:831`). These are different plants for
an RL agent. Existing CEM `learning/rollout.py:37` already uses
`ExecutorSimulation`; it was not bypassing the governor.

The final live readback is firmware `executor-v6-measuredrail`, reference 330,
home epoch 15, measured span 16505 steps, nominal half-rail 0.3089625 m,
speed 1.5 m/s, automatic acceleration 25 m/s², jerk 150 m/s³ and observer
bandwidth 6 Hz. The governor's normal boundary is approximately ±0.2939625 m,
its independent hard trip ±0.2989625 m, and recovery threshold ±0.2889625 m.
The old default normal boundary ±0.245 m is 48.96 mm narrower at each end.

`ExecutorSimulation` faithfully selects the external path's scalar limits:
`vmax=min(vmax,max(vmax_s,vmax_b))`, `amax=max(amax_s,amax_b)`, configured
`jmax`, rail margin and fault margin, one binary32 motion update per 1 ms.
`control/motion.py` ports `firmware/teensy_executor/cart_motion.h`. The motion
recurrence is shared in meaning, including acceleration slew, anticipated speed
limit, jerk-aware stopping distance and braking latch. The wrapper is not a
simulation of pulse interrupts, physical motor tracking or scheduler jitter.

An offline MuJoCo check from rest at hanging with a raw +25 m/s² request gave:

| Interval | Direct acceleration v | Governed v | Governed a | Direct x | Governed x |
| --- | ---: | ---: | ---: | ---: | ---: |
| 4 ms | 0.100 m/s | 0.001500 m/s | 0.600 m/s² | 0.250 mm | 0.0030 mm |
| 10 ms | 0.250 m/s | 0.008250 m/s | 1.500 m/s² | 1.375 mm | 0.0330 mm |
| 20 ms | 0.500 m/s | 0.031500 m/s | 3.000 m/s² | 5.250 mm | 0.2310 mm |
| 50 ms | 1.250 m/s | 0.191250 m/s | 7.500 m/s² | 31.875 mm | 3.3150 mm |

At 150 m/s³, acceleration changes only 0.15 m/s² per tick. A formal 0→25 ramp
takes 166.7 ms before considering speed and rail limits. Jerk-aware stopping
distances at a=0 are 28.87 mm from 0.5 m/s, 81.65 mm from 1 m/s, and 150 mm
from 1.5 m/s. At v=1 m/s and outward a=10 m/s², the stopping distance is
207.19 mm. Raw action reversal is therefore very different from executed
acceleration reversal.

## Sensor and timing fidelity

`Rig.observation()` uses raw magnetic angle, firmware-filtered omega,
step-derived cart position and commanded velocity. `Rig.control_observation()`
adds filtered magnetic angle, commanded acceleration and brake direction.
The current `HostRatePolicy` selects raw angle; `ExecutorFeedbackPolicy` uses
the filtered-angle channel. Neither receives true angular velocity.

The firmware observer is the causal 1 kHz recurrence in
`swing_controller.h:65`, already ported as `control.reference.estimate()`:
innovation = wrapped(measured angle − estimated angle), followed by angle and
rate updates using w=2π·bw. Raw AS5600 quantization is 2π/4096 = 0.001534 rad.
The default simulation's true omega plus independent noise does not reproduce
this dynamics. A common sensor delay cannot substitute for it because angle
and rate have different transfer functions.

The discrete recurrence at live bw=6 Hz has these sinusoidal rate responses:

| Input frequency | Estimated/true rate amplitude | Rate phase lag | Equivalent phase delay |
| --- | ---: | ---: | ---: |
| 1 Hz | 0.9740 | 18.39° | 51.10 ms |
| 1.41561 Hz (nominal pendulum) | 0.9492 | 25.81° | 50.65 ms |
| 3 Hz | 0.8061 | 51.72° | 47.89 ms |
| 5 Hz | 0.5994 | 77.65° | 43.14 ms |

At 1.41561 Hz the estimated angle gain is 1.0477 with only 0.76° lag.
The older bw=30 Hz estimate would have about 9.10 ms rate phase delay at this
frequency. These are mathematical responses of the documented recurrence,
not measured total magnetic/USB latency.

The firmware accepts an action only when its observed board tick is no older
than 20 ms and the action has not expired; expiry is observed tick + TTL, never
arrival + TTL (`executor_core.h:120`). The trusted runner normally uses 20 ms
leases. MCU observer/control runs at 1 kHz while host policy runs at telemetry
rate. The pulse timer is 7 µs, step resolution 37.5 µm. Telemetry combines
sampled angle/x with the newly computed commanded v/a; these within-tick
timestamps are proxies, not simultaneous physical measurements.

`Rig._observation()` assigns board snapshot time to available/acquired/effective/
received timestamps. Thus SDK age features do not reveal USB transport delay.
The new adapter preserves that limitation; actual simulated transport age is
diagnostic only. Constant telemetry and command delays are explicit assumptions,
not measured random-delay models. Initial reset runs causal zero-demand ticks
until the first delayed healthy snapshot arrives, bounded by the 20 ms ARM
lease. This keeps a 3 ms delayed 100 Hz stream's decisions at t=3,13,23... ms,
rather than artificially introducing a full-period age and lease gap.

## Physical identifiability

For a rigid pole with COM distance c, pivot inertia I and viscous hinge torque
b·omega, prescribed cart acceleration a gives

    theta_ddot = (g*sin(theta) - a*cos(theta))/L_eff - beta*omega
    L_eff = I/(m*c), beta = b/I.

The simulator explicitly solves for the force that produces requested cart
acceleration (`backend.py:162`). Before its force cap binds, cart mass and
cart damping are canceled by this ideal servo. Pole mass also cancels from
the angular equation when normalized hinge damping beta is held fixed.
The surrogate rod uses length=1.5·L_eff, giving pivot inertia
I=0.75·m·L_eff². Its default I is 0.000262353 kg·m² and beta is 0.38117 s⁻¹.

An offline 500-tick test multiplied cart/pole masses by four, multiplied hinge
damping by four and changed cart damping tenfold, using a nonbinding force cap.
Maximum differences in [x,v,theta,omega] were approximately
[4.24e-22,1.08e-19,0,0]. Those masses are not identified by fitting this
acceleration-controlled trajectory. The assumed default force cap is 20 N;
the static horizontal-pole force for 25 m/s² is only 9.32 N with default masses.
It does not establish motor force or missed-step performance.

Raw cart telemetry is generated step position plus commanded v/a. Fitting
those signals can validate the governor implementation and commanded trajectory,
but cannot establish physical tracking, friction, inertia, backlash or force
saturation. Independent cart position/acceleration is needed for that claim.
With trusted physical a, pole recordings can identify combinations L_eff,
beta, normalized Coulomb friction, local angle offset and possibly input scale/
delay under sufficient excitation. They do not separately identify m,c,I,b.
Pole input scale/delay can trade off with encoder mapping and tracking error.
Use independent geometry/mass/COM measurements or suitable force/position
measurements before claiming individual physical parameters.

## Additive implementation and exact policy I/O

New `sim/rig_gym_env.py` provides `RigCartpoleEnv` using the existing
`ExecutorSimulation` once per physics tick. It requires an explicit complete
`ControllerParameters`, 1 ms physics and 100 Hz decisions. The frozen
`backend.py`, `model.py`, `config.py` and `gym_env.py` are unchanged.

New dependency-free `policies/rig_observation.py` supplies one shared encoder
for simulation and real SDK observations. It has no MuJoCo/Gym/device import.
Schema `cartpole-rig-observation-v1` has dict fields `state`, `valid`, `age_s`,
each length seven, with state order:

1. step-derived x (m)
2. commanded velocity (m/s)
3. sin(selected angle)
4. cos(selected angle)
5. firmware-filtered omega (rad/s)
6. commanded acceleration (m/s²)
7. brake direction (−1,0,+1)

`rig_channels(angle_source='raw')` explicitly maps the corresponding six SDK
channels; angle is duplicated only for sin/cos. Filtered angle requires the
explicit `filtered` option. Deployment needs `Rig.control_observation()` to
obtain acceleration and brake state even when selecting raw angle. No source
or frame conversion is inferred. The policy output remains raw physical
acceleration in m/s², passed to SDK `Acceleration`/`ActionRequest`; a learned
normalized action must be scaled once by its saved physical bound.

Missing values use zeros with mask=0; no true state fallback exists. Numeric
Gym actions with unusable telemetry send no request and cannot renew a lease;
expiry returns a terminal fault. A trusted real runner may stop immediately on
its freshness/validity checks. True state exists only for reward/evaluation
diagnostics, outside the actor observation and shared encoder. The trusted
deployment wrapper must still reject unusable/stale/replayed input.

The new environment exposes commanded ideal pulse counts, not physical x, to
the actor. Exact ISR phase/direction setup and missed steps remain unmodeled.
The reused governor itself still consumes physical simulated x; while the ideal
servo tracks, this differs from command counts by quantization. Force saturation
terminates the new environment with an explicit unsupported-tracking reason
so training cannot exploit invented command/physical divergence.

## Verification and remaining gates

`tests/test_rig_gym_env.py` covers a single governor, 100 Hz decisions, live jerk/
speed/rail limits, native observer parity, zero observer-rate initialization,
raw/filtered selection, quantization, seed reproducibility, shared actual-SDK
encoding, no true-rate fallback, snapshot/command delay, observation-anchored
lease expiry, invalid telemetry no-send, force-cap termination and Gym API.
Initial tests failed before the new adapter existed; timing tests reproduced
and then guarded the reviewed age and decision-phase bugs.

The physical model is still unaccepted. Next evidence must distinguish encoder
angle geometry/nonlinearity, hinge dissipation, actual cart tracking and actuator
delay. The observer is a software-known dynamic and should be modeled directly,
not fitted away into pole length/damping. Train only with an explicit model
scope, controller snapshot, input schema, delay assumptions and source hashes;
label experimental models separately from models passing fresh validation.

Frozen source SHA-256 at audit completion:

- backend.py: `1eadad422f96d8003b652bd43e5fec84b530acec75801737bc8be6b6a081b34f`
- model.py: `090842af8212c34579ebf9653eab34a9ded7772a21fdbead3f2f938a52898d62`
- config.py: `48863494088e95a806cbe66fcf74d6e247d1406dad24807f819edbda55e7cb91`
- gym_env.py: `1bca5929575464e6ba14da384a3c7d46854b4866fcc78f8da1fa941d06d97883`
