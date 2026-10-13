# Phase 5 host controller and RL report

Implemented in `/Users/rbafna/projects/cartpole_v2`. No hardware, firmware,
archive, portal, rig or project dependency changes were made by this agent.
The existing `policies.py` became a package; its public
`AngularDampingPolicy` import remains available. No commits were created.

## Delivered behavior

- `cartpole_sdk.policies.HostRatePolicy`: separate handwritten energy-shaping
  and linear-feedback controller at explicit 100/250 Hz. Four exact ordered
  channels (position, velocity, angle, angular velocity), no hidden reference
  observer, no operator/device object, raw bounded acceleration output. Source,
  freshness, timestamp-skew, cadence and replay faults latch until Session reset.
- `cartpole_sdk.sim.executor.ExecutorSimulation`: wraps unchanged MuJoCoBackend
  with original binary32 motion.advance once per 1 ms tick. External demand is
  governed exactly once, with 1.5 m/s, 25 m/s², 150 m/s³ and .26 m rail defaults.
  Governor braking starts near .245 m; hard trip is .250 m and speed trip 1.502
  m/s. Expiry faults at its tick and cannot be revived without reset. A smaller
  raw request ceiling does not reduce emergency braking authority. Terminal
  faults do not model actual post-disable coasting. Default backend and strict
  1 kHz ReferencePolicy semantics remain unchanged.
- `cartpole_sdk.learning`: genuine cross-entropy episodic parameter-search RL
  using only episodic reward, with a disclosed strong handwritten controller
  prior. Ten positive gains/phase/kick parameters are optimized in log space.
  Structure, effective length, capture guards and safety limits are handwritten.
- Safe bounded JSON weights, fixed family/schema, finite numeric fields, no
  pickle/eval/executable artifact; loader and host policy run without NumPy or
  MuJoCo on the hardware host. `load_policy(path, channels=...)` returns the same
  SDK reset/act contract and retains the saved deployment rate.
- Working `examples/train_policy.py` and `examples/evaluate_policy.py`,
  `docs/policies.md`, and `evidence/phase5/` with exact command, seeds,
  configurations, candidate scores, baseline/learned weights, model/source
  hashes, dependency versions and per-episode outcomes.

## Actual training and held-out results

Command:

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

Training split: 3 seeds × hanging/upright, 10-second episodes. Five generations,
10 candidates including the cached incumbent, 46 distinct evaluations including
baseline = 276 episodes. Runtime approximately ten minutes on this host.
Training mean reward: **3.597891644 → 3.706169242**.
The frozen winner reproduced its training score exactly on independent replay;
all 14 recorded source hashes match. All six selected-policy
training episodes succeeded. The earlier development run was interrupted before
an artifact when the firmware hard-trip margin was discovered; final training
restarted from the original prior under corrected semantics.

Held-out split: **six unseen seeds × two initial-state families = 12 episodes**.
The artifact evaluator rejects overlap with training seeds. Neither weights nor
search configuration was changed using these held-out results.

| Metric | Pretraining handwritten | Learned |
| --- | ---: | ---: |
| Mean held-out reward | 3.449923410 | 3.704015435 |
| Final-second balance successes | 12/12 | 12/12 |
| Mean final continuous balance, hanging starts | 7.2733 s | 8.4967 s |
| Hanging trials invoking rail braking | 2/6 | 1/6 |
| Reported force saturation at control samples | 0 | 0 |

Success means all of the final second has |theta|<.15 rad, |omega|<1 rad/s,
|x|<.12 m, the full horizon completes, and no fault occurs. The exact shaped
reward is recorded in the artifact and docs; it is not a hardware criterion.

Hanging held-out episodes (both policies succeeded in every row):

| Seed | Before reward | Learned reward | Final dwell seconds before / learned | Peak absolute x metres before / learned |
| --- | ---: | ---: | ---: | ---: |
| 1001 | 3.1633 | 3.4500 | 7.86 / 8.62 | 0.1779 / 0.2232 |
| 1002 | 2.4097 | 3.4545 | 6.21 / 8.64 | 0.2450 / 0.2320 |
| 1003 | 3.1221 | 3.4258 | 7.74 / 8.55 | 0.2120 / 0.2287 |
| 1004 | 2.3587 | 3.2733 | 6.04 / 8.08 | 0.2450 / 0.2450 |
| 1005 | 3.1955 | 3.4221 | 7.96 / 8.54 | 0.1708 / 0.2357 |
| 1006 | 3.1526 | 3.4253 | 7.83 / 8.55 | 0.1844 / 0.2300 |

All near-upright held-out trials remained within the success bounds for the full
10 seconds. Every episode's actual initial and final x/v/theta/omega is in the
JSON. Across learned held-out end states, maximum absolute x was 5.77e-7 m,
v 1.80e-6 m/s, theta 5.63e-7 rad, and omega 2.38e-6 rad/s. Such small residuals
reflect this deterministic idealized plant, not physical precision.

**The learned policy improves reward and settling time, but it does not improve
success count in this small benchmark, and some cart excursions increase.**
Seed 1004 still reaches the .245 m governor braking margin. Do not translate this
into physical clearance or safety acceptance.

## Separate handwritten/reference validation

`host-rate-validation.json`: handwritten HostRatePolicy, seeds 501–503 × both
starts, 10 s, yielded 6/6 successes at each of 100 and 250 Hz. Scores 3.184442
and 3.577675 respectively. At 100 Hz all hanging trials used the .245 m margin;
at 250 Hz their peaks were .199–.238 m. These characterization seeds were never
used for CEM reward. They do not replace measured host timing/shadow/hardware
validation.

`reference-simulation-baseline.json`: unchanged strict 1 kHz reference with saved
parameters and leff .124 m, outputs directly to unchanged backend (no second
governor), 3/4 successes. Hanging seed501 remained swinging at 10 s:
x=-.0649323 m, v=-.758080 m/s, theta=1.906632 rad, omega=-10.552691 rad/s,
no fault. Saved gains therefore are not advertised as universally successful
in the provisional model.

## Verification and remaining acceptance

Fresh maintained suite: **301 passed, 5 skipped, 160 subtests passed** in 25.32 s
(`.venv/bin/python -m pytest tests -q`, `evidence/phase5/tests.log`). The policy
and learning subset has 23 tests, covering real raw/governed acceleration,
exact lease expiry, faults, wrong source/frame/session, stale/skewed state,
cadence, supplied measured rates, deterministic real rollouts, train/held-out
splits, safe JSON loading and actual balance. CLI help and `git diff --check`
also passed. The portal agent independently integrated this wrapper into its
SimulationBridge and its new tests are included in the full run.

A bare `pytest -q` earlier collected preserved historical archive test trees and
failed with 34 collection errors (missing cartpole, angle_plot, pendulum_vision,
cv2 and duplicate test-module names). The maintained suite command above is
clean; no archived source or dependencies were modified to mask those failures.

Still **hardware unvalidated**: actual USB timing, source latency/filtered-rate
behavior, shadow runs, staged bounded external controller trials, trained-policy
physical trials, switch/homing commissioning and identified plant acceptance.
The simulation's .124 m effective length and remaining parameters are provisional;
it models perfect acceleration tracking within a force cap, not motor/slip/ISR
or disabled stopping. Sensor noise/dropout are available but the retained
training/evaluation uses noiseless channels, 10 ms samples and zero transport
delay. Positive startup delay produces unknown channels and correctly fails
closed; these examples do not supply hidden truth or silently warm up a delayed
stream. This is an explicit limitation, not a measured zero-latency claim.

Usable artifact SHA-256:
`eb5bb1102986e775161338d5c5954ed67c21102bf706b2431d0f0bfae8db6936`

Primary paths: `src/cartpole_sdk/policies/`, `src/cartpole_sdk/learning/`,
`src/cartpole_sdk/sim/executor.py`, the two train/evaluate examples,
`tests/test_host_policy.py`, `tests/test_learning.py`, `docs/policies.md`,
`evidence/phase5/`.


## Single-file export and recorded-data shadow addendum

The learned delivery gap is closed: `examples/export_policy.py` exports the
existing artifact to `evidence/phase5/learned-policy-simulation.py`, a deterministic
**19,866-byte** portal source containing `create_policy()`.
Its source SHA-256 is `4e2ae15c38f61fbbcb8f43988d1760e8006b18e906e0ac109f907f8a6ca88125`. The exact original numeric
artifact, its digest and full provenance are embedded. It needs only stdlib and
the readonly SDK in the child; no external weight file, NumPy or MuJoCo. Seven
inference-source hashes are checked for compatibility. Explicit selected source
is simulation, frame sim:upright+x, ordered x/v/theta/omega, saved rate100Hz,
raw acceleration semantics. The weights and original training source hashes
were not modified. Four new export tests pass: deterministic source selection,
actual portal immutable submission, loaded nonzero inference without the weight
file, Python -I -S dependency-free import, required provenance, and tamper checks.

Reproduce:

```sh
.venv/bin/python examples/export_policy.py evidence/phase5/learned-policy.json \
  --source simulation --output evidence/phase5/learned-policy-simulation.py
```

Actual isolated target integration has been handed to the parent and SDK agent;
this agent performed no SSH/device activity. The SDK agent added the Linux-only
`tests/test_portal_worker.py::WorkerTests::test_real_isolated_learned_simulation_queue_worker`
regression using this exact export, real Sandbox, 10-second simulation, >=900
actions, nontrivial demand above .25, 10 seconds of simulated time and final
state fields. It must execute on Linux with Bubblewrap before that gate is
claimed passed. The parent's exact test command is:

```sh
python -m pytest tests/test_portal_worker.py::WorkerTests::test_real_isolated_learned_simulation_queue_worker -q
```

The trusted simulation ceiling is25 m/s²; the hardware default stays.25 m/s².
No submission field can raise either. The full local queue/worker command
without importing the source into the broker is documented in docs/policies.md.

The requested quick shadow used the real recording's complete MCU reference
interval (no state filtering/resampling within the interval), preserved SDK
magnetic/step source mappings, and handwritten HostRatePolicy at250Hz.
**2501/2501 intents** were produced without a source,
cadence, age or skew fault. All board intervals were4000µs. Host receipt intervals
were1.265–7.582ms (median3.995ms); this is not a measurement of inference timing or
mapped sensor latency. **5 shadow demands hit25 m/s².**
No outputs were sent to hardware. This establishes only source/board-cadence
compatibility on the recorded reference trajectory, never counterfactual control
quality or host/learned physical acceptance.

Shadow command:

```sh
.venv/bin/python examples/shadow_policy.py \
  evidence/phase3/live-recordings/executor-reference-20261013T231602Z/rig-1791933362677431132-3601744890.jsonl.gz \
  --rate 250 --output evidence/phase5/host250-reference-shadow.json
```
