# Phase 2: reference controller and simulation

Phase 2 adds the saved 1 kHz controller in Python, an independent native firmware
oracle, and a headless MuJoCo/Gymnasium backend. Everything here runs locally.
The Teensy executor, live Jetson broker and physical identification are next.

## Run the saved controller in MuJoCo

From the repository root:

```bash
mkdir -p runs/phase2-demo
uv run --locked --extra sim cartpole-v2 simulate runs/phase2-demo/swingup --steps 10000
uv run --locked --extra sim cartpole-v2 simulate runs/phase2-demo/upright --start upright --steps 10000
```

Each command uses a new directory. `auto` starts hanging; `upright` starts at
x=v=omega=0, theta=0.04 rad. `--state X V THETA OMEGA` overrides that initial
condition. Units are meters, seconds and radians; theta=0 is upright, positive
theta leans toward positive cart position. `--seed` controls simulated sensors.
The runner advances simulation time without waiting for wall time.

Outputs:

- `run.json`: exact model/sensor settings, seed, initial state, policy parameters,
  library versions, model hash and termination/fault reason.
- `model.xml`: the actual generated MuJoCo model for the run.
- `observations.jsonl`: SDK recording, including the initial and final observations.
- `trace.jsonl`: actual closed-loop action requests, resulting plant truth,
  controller mode/demand/governed acceleration and force diagnostics. Its header
  explicitly identifies simulation; this is different from fixed-input replay.

Force/acceleration diagnostics describe the final physics substep in an interval;
truth describes the state after stepping. Longer control intervals therefore do
not expose every substep through this trace. A rail end or horizon completes a
run; a reference-policy fault saves the bundle and returns CLI exit code 2.

## Write a Python policy or use Gymnasium

```bash
uv run --locked --extra sim python examples/simulate_policy.py runs/phase2-demo/my-policy
uv run --locked --extra sim python examples/gym_rollout.py --steps 200 --seed 7
```

Edit `MyPolicy` in the first example. It implements the same `reset(Session)` /
`act(Observation) -> Acceleration | None` contract used by replay. It demonstrates
bounded cart damping, not balancing. The second example exercises the RL
interface with random actions; it does not train an agent or save a trained model.

```python
from cartpole_sdk.sim import SimulationConfig, SensorConfig
from cartpole_sdk.sim.gym_env import CartpoleEnv

env = CartpoleEnv(
    SimulationConfig(control_steps=10, max_steps=1000),
    SensorConfig(sample_every_steps=2, delay_steps=1, angle_noise_std=0.002),
)
observation, info = env.reset(seed=7)
# An RL library can use env here. env.close() when finished.
```

Gym actions are a one-element continuous array of acceleration in m/s², bounded
by the configured acceleration limit. The Dict observation contains:

| Key | Values |
| --- | --- |
| `state` | `[x, v, sin(theta), cos(theta), omega]` from simulated sensors |
| `valid` | Five corresponding 0/1 validity flags |
| `age_s` | Five effective ages in seconds; -1 means unknown |

Unavailable values have zero placeholders and validity=0. Delayed valid readings
retain their older effective time. Ground truth is separate in `info`, alongside
force diagnostics. Reward is `cos(theta) - (x/rail_half_m)**2 - 0.001*action**2`,
computed from truth as an illustrative training objective. Rail crossing is
termination; the time horizon is truncation. The default Gym interval is 10 ms;
the default SDK simulation/reference interval is 1 ms. Rendering is not included.

## Model and sensor assumptions

The surrogate uses a free pole hinge and cart slider. Saved effective length
0.124 m and rail half-length 0.26 m come from the preserved preset. The uniform
rod is 1.5 times the effective length, matching the controller equation's inertia
ratio; it is not a measured representation of the actual arm and weights.

Cart mass 0.35 kg, damping coefficients and 20 N force ceiling are assumptions.
Pole mass 0.02275 kg derives from historical component comments and is unconfirmed.
Backlash, belt compliance, pulse quantization, missed steps, friction nonlinearities
and motor speed/force curves are not identified or modeled. A constant force
ceiling is a provisional actuator approximation. See
[model provenance](../evidence/phase2/model-provenance.json).

The SDK requests **acceleration**. At each physics step, the backend solves the
coupled mass/bias/passive-force equations for cart force while leaving the hinge
unactuated, then applies the configured force limit. It reports the achieved
acceleration, which differs when saturated. Physics has no contact before rail
termination. MuJoCo numerical instability raises an error and requires reset;
the backend disables MuJoCo's automatic state reset.

`--model-config model.json` and `--sensor-config sensors.json` accept partial JSON
objects matching `SimulationConfig` and `SensorConfig` fields. CLI `--steps` sets
the horizon even if the JSON also has `max_steps`. For example:

```json
{"cart_mass_kg": 0.4, "max_force_n": 8.0, "cart_damping": 0.08}
```

Sensors expose configurable acquisition period, delay (both in physics ticks),
independent Gaussian noise per quantity, and packet-level dropout probability.
All sensor channels are explicitly source=`simulation`. This does not certify a
particular magnetic/vision/fused estimator. Delayed startup is unknown; a strict
reference run stops immediately if required input is unavailable.

## Reference fidelity and limits

`cartpole_sdk.control.ReferenceController` ports the archived controller's
estimator, gain formulas, swing-up/approach/capture, balance, rail/spin/upright
recovery, health/response faults and motion governor. It loads the saved preset
(`pw=4.5`, `bal_pw=4.0`), not untuned firmware-header defaults. Historical encoder
calibration and Z settings are metadata only and are not applied to the model.

`cartpole_sdk.control.policy.ReferencePolicy` selects explicit angle and position
channels. Their coordinate conventions must already agree with the controller;
frame names do not perform a transformation. The port retains its own angle
observer and commanded cart velocity, just as the firmware does. It does not
substitute the simulator's angular or cart velocity truth.

The wrapper requires consecutive observations exactly 1 ms apart. Missing,
invalid, unknown, stale or mismatched channels latch a fault until explicit reset.
Its default maximum sample age is 2 ms. This is a 1 kHz reference implementation,
not evidence that the same controller works over existing 100 Hz telemetry.
Python execution here has no real-time deadline guarantee. Cadence is enforced
against the input clock, not an OS scheduler.

The wrapper emits governed acceleration for simulation. A future hardware path
must apply the motion governor exactly once and retain final authority in the
Teensy. Raw controller demand remains in diagnostics. `None` is no new request,
not zero acceleration; the backend retains an unexpired request. After expiry,
the simulator requests zero acceleration, which can require nonzero force.
That fallback is not a hardware emergency-stop implementation.

The native oracle compiles the complete original sketch and headers with stubbed
peripherals and four asserted source substitutions for host compilation and input
injection. It executes the original control tick and command handling, rather
than a second translation of the state machine. Its tests cover all 12 modes and
primitive/health/timer scenarios. Float agreement is tolerance-based; specific
motion arithmetic retains binary32 rounding because a settling guard amplifies
otherwise tiny differences. These checks exclude I2C/electrical behavior, pulse
ISR timing, board scheduling, persistent calibration and physical motion.
See [oracle details](../tests/native/README.md) and
[controller provenance](../evidence/phase2/controller-provenance.json).

## Verification and next step

```bash
uv run --locked --extra sim python -m unittest discover -s tests -v
uv run --locked python -m unittest discover -s archive/tests -v
```

The base SDK remains dependency-free. Without `--extra sim`, the core, reference
and native tests run and optional simulation tests skip. Native tests require a
C++17 compiler (`CXX` may select it); installed SDK use does not. `uv` may remove
optional dependencies when syncing without the extra; include it for simulator
commands. The lock was verified with Python 3.11, MuJoCo 3.15 and Gymnasium 1.4.

The next phase should establish the new Teensy executor and exclusive Jetson
broker, including command leases, bounded motion, independent watchdogs, limit
switch integration and motor-disabled bench tests. Then collect synchronized
magnetic/vision/cart measurements for model identification and held-out validation.
The portal and untrusted-policy execution remain later work.

API references: [MuJoCo dynamics](https://mujoco.readthedocs.io/en/stable/computation/),
[Gymnasium environment interface](https://gymnasium.farama.org/api/env/).
