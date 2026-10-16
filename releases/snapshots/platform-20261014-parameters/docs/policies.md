# Host policies and reproducible policy search

`HostRatePolicy` is a separate handwritten controller for explicit **100 or 250
Hz** observations. It consumes SDK `Observation` and returns SDK `Acceleration`;
`reset(Session)` clears its state and fault latch. It receives no device or
operator object. The archived `ReferencePolicy` remains a strict 1 kHz adapter
and its outputs already include a governor. These are distinct control paths.

The channel tuple is ordered cart position, cart velocity, pole angle, pole
angular velocity. Every channel must name its entity, source and frame. A rig
factory can select the established `step/cart-step-home` position and commanded
velocity channels and `magnetic/encoder-zero` angle and filtered-rate channels.
Cart step counts remain estimates rather than independent travel measurements.
Frame names select channels; they do not transform coordinates. This controller
assumes upright angle zero and positive angle leaning toward positive cart x.
It uses the selected rate directly, with no hidden 1 kHz observer.

```python
from cartpole_sdk import Channel
from cartpole_sdk.policies import HostRatePolicy

channels = (
    Channel('cart', 'position', 'step', 'cart-step-home'),
    Channel('cart', 'velocity', 'step', 'cart-step-home'),
    Channel('pole', 'angle', 'magnetic', 'encoder-zero'),
    Channel('pole', 'angular_velocity', 'magnetic', 'encoder-zero'),
)
policy_factory = lambda selected: HostRatePolicy(selected, rate_hz=100)
```

This is a factory example, not an instruction to arm the apparatus. Hardware
execution belongs to the trusted rig runner, which establishes physical state,
bounds acceleration and duration, and stops in `finally`. A policy output may
exceed that runner's conservative commissioning ceiling; the runner must reject
it rather than silently expand the ceiling. Neither host policy is hardware
accepted by the evidence in this document.

## Controller structure and faults

The handwritten prior uses pole energy relative to upright, bounded tanh phase
feedback, cart centering and a brief conditional startup kick. Near upright it
blends into linear state feedback; capture/release guards provide hysteresis.
Initial balance gains derive from the saved controller parameter JSON with
`leff=.124 m`; this does not import historical encoder calibration. It does not
invoke the archived controller or its tick/observer machinery.

Missing, invalid, unknown, stale, wrong-source or wrong-frame channels return
no request and latch the policy fault until reset. Effective time determines
freshness. Channels may differ by at most one control period. Observation
sequences must increase; they need not increase by one because real sequences
are MCU ticks. Interarrival time must stay within 50% of the configured 4 or
10 ms period; this tolerance is configurable downward. A wrong session/clock
raises validation failure. `None` is not a physical stop: the trusted runner
must stop and/or the unchanged MCU lease must expire.

## Raw versus executed acceleration

The host and learned policies return **raw demanded acceleration**. The new MCU
external mode applies its original binary32 `cart_motion` governor once at
1 kHz, with speed 1.5 m/s, acceleration 25 m/s², jerk 150 m/s³ and commissioned
rail configuration (currently .26 m half-range). Leases do not renew themselves;
expiry faults and disables the executor.

`MujocoBackend` intentionally retains its earlier direct/executed-acceleration
semantics, including zero demand after expiry. New `ExecutorSimulation` wraps
it with one governor update per 1 ms physics tick and independent host control
intervals. The wrapper checks raw action/session/sequence/TTL before mutation,
records raw and executed demands separately, holds a still-live lease for
`None`, and latches a terminal fault at the exact expiry tick. The firmware hard trip at `rail_half_m-.010` (currently .250 m), or speed
above 1.502 m/s, terminates the rollout; the governor starts braking earlier.
A lower raw-action ceiling does not reduce its emergency braking authority. Fault termination does **not** predict physical motion
after motor disable. It does not simulate ISR scheduling, pulse quantization,
backlash, missed steps, motor saturation, homing or switch circuits.

Plant and sensor defaults are provisional assumptions. The simulation includes
an acceleration servo with a force cap, a free damped pole, source=`simulation`,
seeded noise/dropout, and configurable sample period and delay. It has no model
of the MCU magnetic filter's dynamics. A positive startup sensor delay initially
produces unknown channels, which the policy rejects; the training/evaluation
examples currently record that as a failed episode rather than supplying truth
or silently warming up the controller. The selected evidence therefore records
zero transport delay. This is not a measured USB-latency model.

## Reinforcement-learning method

`cartpole_sdk.learning.train` performs cross-entropy episodic policy search over
ten positive parameters in log space. Candidate policies run complete MuJoCo
SDK episodes. Their only optimization signal is mean episodic reward on a fixed
training split; no expert action labels are supplied. Elites update the search
mean and standard deviation, and the incumbent remains a candidate. This is a
simple parameter-search RL method initialized with an explicit strong controller
prior. The policy structure, capture guards, model effective length and safety
limits are **handwritten**, not learned. The default host controller remains
separate and unchanged by training.

Every training seed generates one near-hanging and one near-upright initial
condition: cart x in ±.015 m, cart v in ±.025 m/s, angle offset in ±.07 rad and
pole rate in ±.15 rad/s. The random stream uses `(seed, initial-state family)`;
sensor randomness has the episode seed. Held-out evaluation rejects overlap
with the saved training seeds and never updates the weights.

Reward per decision is `cos(theta) - .3*(x/rail)^2 - .001*omega^2 -
.0002*raw_acceleration^2`, plus 2 while `abs(theta)<.15 rad`, `abs(omega)<1 rad/s`
and `abs(x)<.12 m`. The episode score is the mean over the full requested
horizon, assigning -3 to every uncompleted decision, plus final continuous
balance time divided by horizon. Success requires **the entire final second**
within all three balance bounds, the complete horizon, and no fault. This is
an explicit benchmark definition, not a physical acceptance criterion.

```sh
.venv/bin/python examples/train_policy.py \
  --output evidence/phase5/learned-policy.json \
  --seed 20261013 --training-seeds 11 12 13 \
  --generations 5 --population 10 --seconds 10 --rate 100 \
  --sensor-period-ms 10

.venv/bin/python examples/evaluate_policy.py evidence/phase5/learned-policy.json \
  --seeds 1001 1002 1003 1004 1005 1006 \
  --output evidence/phase5/heldout-100hz.json
```

Install the existing `sim` extra for local NumPy/MuJoCo training and evaluation.
The host controller and numeric weight loader do not require those dependencies
on the hardware host. Torch is not required. Runtime
scales with generations × population × seeds × two start families × horizon;
the default example is deliberately small. All commands are local simulation.

The artifact is bounded JSON with a fixed policy family, finite numeric weights,
rate, simulator/sensor configuration, baseline weights, train seeds, complete
candidate score history, objective, model hash, source hashes and package
versions. No pickle, Python module path, executable graph, dynamic import or
`eval` is loaded. `load_policy(path, channels=...)` creates a normal SDK policy
with explicit deployment channels; source mapping is never inferred from the
training artifact. Artifact provenance describes training and does not grant
hardware acceptance. Evaluation reports include artifact SHA-256, evaluation
code/model hashes, seed-specific initial/final states, success, final dwell,
peak cart excursion, score and fault. Compare aggregate and per-seed outcomes;
a higher reward is not proof of robust swing-up.

For an explicitly staged trusted runner, learned weights use the same source
selection and policy boundary:

```python
from cartpole_sdk.learning import load_policy

policy_factory = lambda selected: load_policy(
    'evidence/phase5/learned-policy.json', channels=selected)
```

The saved rate remains part of the artifact: a different stream cadence faults
instead of silently retiming a trained policy. The evaluator's explicit `--rate`
override is a separate sensitivity experiment; it does not modify this saved
deployment rate.

See `evidence/phase5/` for the reproducible experiment and reported limitations.

## Single-file portal export

The portal accepts one source file with `create_policy()`. Export the frozen
numeric artifact with an explicit source mapping:

```sh
.venv/bin/python examples/export_policy.py evidence/phase5/learned-policy.json \
  --source simulation --output evidence/phase5/learned-policy-simulation.py
```

The retained export is 19,866 bytes, below the 65,536-byte portal limit. It embeds
the exact numeric artifact and its original provenance; no external weight file,
NumPy or MuJoCo is needed in the isolated child. It verifies the embedded SHA-256
and seven SDK inference-file hashes before returning `LearnedPolicy`. These are
compatibility/integrity checks, not a replacement for the portal sandbox. The
source mapping is fixed to all four `simulation/sim:upright+x` channels and its
saved rate is 100 Hz. Wrong sources fail closed. `--source magnetic-step` can
produce a separate explicit magnetic/step mapping; it does not authorize physical
execution or alter the artifact's hardware-unvalidated status.

The exporter manifest records source and artifact digests, byte count, source
selection, cadence, action semantics and exporter hash. The original weights
and their training hashes remain unchanged. The exported source digest is
`4e2ae15c38f61fbbcb8f43988d1760e8006b18e906e0ac109f907f8a6ca88125`.

For a Linux target with the real sandbox installed, stage an isolated local
simulation without importing the submission into the broker:

```sh
python - <<'PY'
from pathlib import Path
from cartpole_sdk.portal.queue import Store
source = Path('evidence/phase5/learned-policy-simulation.py').read_bytes()
job = Store('/tmp/cartpole-learned-queue').submit(
    'local-validation', 'learned-simulation-v1', source,
    'learned-policy.py', 'simulation', 10.0)
print(job['id'])
PY
python examples/portal_worker.py --local-root /tmp/cartpole-learned-queue \
  --worker linux-validation --rig-id learned-simulation \
  --backend simulation --max-acceleration 25 --once
```

The 25 m/s² ceiling is trusted simulation-worker configuration; a submission
cannot choose it. The physical worker's conservative default remains separate.
Actual Linux isolation execution and its terminal trajectory must be recorded
before claiming isolated learned-policy acceptance. The local export tests alone
do not establish that gate.

## Recorded-hardware shadow

`examples/shadow_policy.py` replayed every recorded state in the ten-second MCU
reference interval at 250 Hz using the handwritten host controller and exact
magnetic/step source mappings. It produced 2,501 intents for 2,501 states without
a stream fault; all 2,500 board intervals were 4,000 µs. Five shadow intents hit
the 25 m/s² raw ceiling. No output was sent to a device. This establishes only
source and board-cadence compatibility on that recording, not counterfactual
control quality, host inference latency, or physical policy acceptance. Effective
timestamps retain the SDK's board acquisition-snapshot proxy; they do not measure
magnetic filter or USB delay. Details and hashes are in
`evidence/phase5/host250-reference-shadow.json`.
