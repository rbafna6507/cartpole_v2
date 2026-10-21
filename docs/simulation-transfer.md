# What offline success can establish

A frozen policy can become a well-tested candidate for a bounded hardware
experiment. Simulation cannot establish that it will work on this rig while
physical cart tracking, angular calibration and current timing remain unmeasured.
Keep `hardware_accepted=false` and `deployable=false`, even if every scenario passes.

The current model is useful evidence, with a narrower scope than full swing-up.
The unchanged batch-6 passive candidate predicts 47 independent releases in
batches 8 and 9 with pooled half-second forecast RMS/P95 of 2.356°/4.940°.
All release short-forecast numeric and coverage gates pass. Once-initialized
continuous predictions have RMS/P95 3.312°/6.528° after a 0.5 s history; camera
and held-pose qualification failures remain included. These observations cover
decays around hanging, approximately 30°, 60° and 90° excursions. They do not
validate upright balance or forced full rotations. See
[the frozen validation evidence](../evidence/passive-batches8-9-20261017/README.md).

## What is represented

`RigCartpoleEnv` uses 1 ms physics and one binary32 motion-governor update per
tick. A policy acts at 100 Hz with a 20 ms lease anchored to the observed board
snapshot. The governor includes jerk, acceleration, speed and predictive rail
braking limits. The recorded profile has jerk 150 m/s³, speed 1.5 m/s,
acceleration 25 m/s² and rail half-range about 0.309 m. These are a recorded
executor snapshot, not a current hardware readback.

The 20261021 encoder profile applies an explicit forward sensor error law before
4096-count quantization, runs the causal bandwidth-10 Hz observer at 1 kHz, and
exposes raw angle plus estimated angular rate. Nominal error coefficients are
zero; training varies constant bias and upright-anchored periodic shape terms.
Older profiles retain their saved bandwidths. This exercises coupled angle/rate
errors, unlike the older actor-input-only bias stress. Cart
position is an ideal pulse-count estimate; velocity and acceleration are command
states. Shared observation encoding supplies state, validity and age features.
The nominal profile adds 0.001 rad Gaussian encoder noise. The explicit
`observation-config.json` and `randomization.json` determine execution and are
retained in every new Colab recipe. See [the refresh evidence](../evidence/simulation-refresh-20261021/README.md).

Transport age is hidden from encoder age features: SDK timestamps use board
snapshot proxies. The simulator preserves that limitation. Camera/fused modes
use the causal camera provider and fusion assembler, but require explicit
calibration and clock bindings for physical operation.

## Important gaps

The plant computes the force required to achieve commanded cart acceleration,
then clips it at an **assumed 20 N**. Below that ceiling it is an ideal servo.
Mass and cart damping variation alone therefore largely cancels out of motion;
it is not an effective substitute for testing tracking error. Force saturation
terminates as unsupported tracking. Step interrupts, direction setup, missed
steps, backlash, belt compliance, motor force versus speed, disabled-motor
motion, collisions and hard-stop dynamics are absent. The governor uses physical
simulated position, whereas firmware uses pulse count.

Hinge friction is `-c*tanh(omega/0.05)`, with normalized nominal
`c=1.6268943 rad/s²` and viscous damping `0.006892/s`. The smoothing width is a
fixed model choice. Its local friction slope adds about **32.54/s** of damping
near zero velocity. Static stiction and possible history dependence are absent.
A useful later model-form stress is width 0.025 and 0.1 rad/s, explicitly labeled
as assumed; the current finite suite does not implement that variation.

The passive local phase `-0.112972 rad` is not a global encoder calibration and
was deliberately not applied to the plant. Historical camera/encoder records
show angle-dependent and history-dependent disagreement, with different saved
references and operating states. They establish a mechanism to investigate,
not a present global error envelope. See the
[manual angular-map assessment](../evidence/phase3/retuning-20261015/sensor-disagreement/manual-angle-map-assessment.md)
and [resting-window shifts](../evidence/phase3/retuning-20261015/calibration/micro-motion-screens/README.md).

The raw/filtered neural runner checks that the saved reference is healthy, but
does not require independently qualified physical upright/angular mapping
evidence. Offline scripted preflight accepted reference values 0, 123, 330,
2048 and 4095 for the same actor when other metadata matched. Any of those raw
values could be correct after a genuine physical upright recalibration: a
numeric reference pin alone cannot certify vertical and should not prohibit a
legitimate recalibration. Camera mode has an explicit reference binding. The
remaining requirement is a measured, current angular mapping/anchor with its
uncertainty, before interpreting successful inference as physical parity.

Nominal telemetry/command delays of 3/1 ms are declared assumptions. Older
250 Hz hardware recordings contain action expiry after a 22.314 ms host
interval even with zero demand, and a separate AUTO failure with 22.870 ms from
last act completion to failure recording. Those are evidence of real timing
failure mechanisms, not a current 100 Hz distribution or a measured transport
write duration. See the [timing audit](../evidence/python-control-id-20261016/timing-audit/report.md)
and [AUTO expiry reconstruction](../evidence/python-control-id-20261016/timing-audit/auto-1792181042331498776-report.md).

## Frozen-policy stress suite

Run both the stress suite and actual SDK export/inference comparison against a
trusted archived swing run with the offline command:

```sh
scripts/swing-transfer-check runs/local-swing-20261018/curriculum-seed17 \
  --output runs/local-swing-20261018/stress-curriculum-seed17-repeat \
  --seeds 54000 54001 --seconds 25
```

This reproduces the retained seed-17 candidate screen on the same seeds; those
seeds are no longer an independent final holdout after its results are inspected.
Choose fresh, uninspected seeds for a final candidate gate. The output directory
must not exist. The default checkpoint is the last recorded checkpoint; use
`--checkpoint STEPS` to select an earlier recorded one.

The command verifies recipe, report, source archive, checkpoint and demonstration
hashes, rejects overlap with recorded training/development/demonstration seeds,
and loads the checkpoint with the original archived source/dependency guards.
It runs the two separately hashed current evaluators against that frozen runtime
without modifying the training archive. It verifies inputs, tool sources and
loaded policy weights again before copying the staged results to the new output.
It does not install dependencies or contact hardware or cloud services. These
are integrity checks for a trusted local run, not authentication of untrusted
Python or checkpoint archives.

Inspect `report.json` for stress results, `parity/report.json` for actual SDK
inference agreement, and `transfer-provenance.json` for the binding between the
checkpoint, both evaluation tools and their reports. A zero command exit status
means the checks completed and reports were written; it does not mean either
`scenario_gate_pass` or `emission_parity_pass` is true. Failures remain in the
reports. Neither result grants hardware approval.

`learning.transfer_checks.run_suite` evaluates the supplied predictor without
optimization. Its caller must validate and load the checkpoint, verify source
compatibility, and choose seeds independent of training and inspected model
selection. The function records the caller's provenance and checkpoint digest;
it cannot independently prove that an arbitrary in-memory object came from the
named checkpoint. It hashes actual policy weights, evaluation dependencies and
source, verifies weights/source did not change, and preserves Python, NumPy and
Torch CPU RNG state and policy training flags.

```python
from cartpole_sdk.learning.transfer_checks import run_suite, source_identity

# model and experiment must already be loaded and validated by the caller.
report = run_suite(
    model, experiment, "runs/frozen-policy-stress",
    seeds=(48000, 48001, 48002, 48003), seconds=25,
    checkpoint_sha256=verified_checkpoint_sha256,
    source_binding={"validated_recipe": validated_recipe_binding,
                    "evaluation_source": source_identity()},
)
```

The output directory must be new. `recipe.json` freezes the experiment, scenarios,
seeds, runtime, weight digest and caller binding. Per-episode JSONL traces retain
actor inputs, physical truth, candidate and actual executor actions, faults and
timestamps. `report.json` hashes each trace. A failed evaluator leaves its recipe
and any completed traces without a completed report. No model admission or
source evidence is overwritten.

The finite matrix applies one perturbation at a time, to both upright and hanging
starts for each seed:

| Scenario | Values | Evidence status / expected outcome |
| --- | --- | --- |
| Nominal | Supplied frozen profile | Development model, no physical approval |
| Effective length | 0.95× and 1.05× | Engineering sensitivity; torques scale with inertia |
| Coulomb friction | 0.8× and 1.2× | Engineering sensitivity, not a fitted interval |
| Encoder noise | Gaussian σ=0.003 rad, then 4096-count quantization | Assumed noise stress |
| Fixed delays | Telemetry 8 ms, command 2 ms | Exact renewal boundary; expect task success if robust |
| Observed angle bias | −1° and +1° | Assumed actor-input bias; no true-state or zero change |
| Lease fault | Telemetry 9 ms, command 2 ms | Expect terminal lease expiry, not balance |
| Invalid telemetry | Dropout probability 1 after the guaranteed initial sample | Expect terminal invalid-input detection |

Successful-task rows require the complete requested horizon, no fault, and the
successive 100 Hz post-step ground-truth samples over the final five seconds
satisfying `abs(theta)<0.15 rad`, `abs(omega)<1 rad/s`, `abs(x)<0.12 m`. This is a
sampled hold criterion; it does not inspect every intermediate 1 ms physics tick.
Runs shorter than five seconds cannot pass that gate. Reports also retain first
one-second capture, longest dwell, final
window completeness, maximum cart excursion, action variation and angle-bias
command sensitivity. Initial states remain the existing small seeded envelopes:
x ±15 mm, velocity ±0.025 m/s, angle ±0.07 rad about upright/hanging and angular
rate ±0.15 rad/s. This does not test a wider balance capture region.

Fault-response rows check terminal detection and stop evaluating the episode.
They do **not** test a physical STOP command, cart stopping distance, or continued
hardware safety. Invalid-input detection in `TrainingEnv` ends before the next
plant step. The exact neural/host/firmware runner replay remains explicitly
`outstanding` in the stress report. Its note that numeric export parity was not
performed refers to that evaluator alone; the CLI's separate `parity/report.json`
contains the actual candidate-specific export/inference check described below.
A mock runner pass is never substituted.

The 8+2 ms case has no timing margin. Current offline zero-demand probes pass
at combined fixed delay 10 ms and expire at 11 ms, with the latter fault at
20 ms. For a final candidate, retain all failures, use fresh seeds, rerun the
60-second balance regression, and add selected combined corners after this
screen. These engineering ranges are independent stress choices, not a sampled
physical posterior, and cannot justify a hardware success probability.

A bounded follow-up tested six observed-state linear balance laws on development
poses 58000/58001 for 25 seconds, with nominal and ±1° actor-angle bias. All
24 biased cases failed the final hold; eight of twelve nominal cases passed.
Increasing position gain from 1 to 12 reduced the biased mean cart offset to
about ±0.06 m, but oscillations still exceeded the ±0.12 m hold region. No law
qualified for the predeclared fresh-pose confirmation. See the retained
[centering-bias diagnostic](../runs/local-centering-bias-20261018/README.md).
This isolates a control-law sensitivity within the same model; it does not
measure the rig's angular error or qualify a replacement controller.

## Actual SDK export and inference parity

`learning.candidate_parity.check_candidate` uses the real `learning.ppo.export_actor`
to write `parity/actor.json`, then loads those numeric bytes with the real SDK
loader and calls `NeuralPolicy.reset` and `act` on `RigCartpoleEnv` observations
with all six explicit channels. It verifies identical encoded observations for
the SB3 comparison. At every evaluated decision it compares the actual returned
raw acceleration against deterministic SB3 output clipped to its normalized
action limits and multiplied once by the saved physical action scale. The SDK
actor's actual raw action drives the unchanged governed simulator; the SB3
comparison action does not drive it.

`emission_parity_pass` requires at least one compared action in every episode,
no SDK input rejection and a maximum absolute raw discrepancy of at most
`1e-5 m/s²`. This allows float32 versus Python numeric arithmetic differences.
It establishes agreement only on the observations actually sampled, including
clipping when encountered. It does not certify all possible inputs. A simulator
fault can end a trajectory whose emitted actions all matched; parity can pass
while `full_horizon_complete` and `hold_success` fail. Read the episode faults,
comparison count and separate task metrics, using the same sampled five-second
hold criterion above.

The seed-17 screens demonstrate why these results must remain separate. On
poses 54000/54001, curriculum-17 held from hanging in 0/2 nominal SB3 trajectories
and 2/2 actual SDK trajectories; balance-17 produced 1/2 versus 0/2. Their initial
inputs and physical states matched exactly, and initial raw command differences
were about `1e-6 m/s²`. By decision 500, curriculum pose 54000 differed in cart
position by 0.281 m. Same-observation emission parity still passed. This is
evidence that capture outcomes are sensitive to numerical precision, rather
than evidence of an inference contract defect. Anchored-17 held in 2/2 hanging
cases through both paths on those poses, a small-sample result that does not
establish general robustness. Retain both closed-loop outcomes alongside the
conditional action comparison.

The parity recipe/report pin the original experiment, checkpoint assertion,
before/after policy weight digests, evaluator/runtime sources and actor hashes.
JSONL traces retain full SDK and encoded observations, both proposed raw actions,
their discrepancy, actual executor actions, physical truth, faults and inference
timings. Both Python/NumPy/Torch CPU RNG states and policy modes are preserved.
CPU and wall-clock timings measure actual `NeuralPolicy.act`, including validation
and encoding with the first call included. **Mac only, not Jetson deadline
guarantee**: these timings do not cover the live host loop, transport, scheduler
load or firmware arrival deadlines.

The numeric artifact remains `DEVELOPMENT_ONLY` with `hardware_accepted=false`;
the parity report also states `deployable=false`. The actual SDK inference check
does not call the full host runner, serialize live transport commands, replay
firmware or issue STOP. `host_firmware_stop_replay.status` remains `outstanding`.

## Remaining offline gates and physical evidence

Before proposing a bounded rig experiment, extend the candidate-specific numeric
comparison to deliberately constructed clipping boundaries and recorded or
scripted fault inputs beyond its nominal trajectory sample. Exercise the real
runner with scripted
replayed timestamps, duplicate/out-of-order frames, 20–25 ms host stalls, invalid
channels, session/reference changes and expiry. Verify no stale action renews
the lease and STOP/fault behavior is observed through the actual runner contract.
The retained training artifacts have no deployment approval; the separate parity
actor is an offline development artifact.

Useful numerical checks are native C++/Python governor and observer parity;
same-input ODE/MuJoCo short-trajectory agreement; and convergence at 1, 0.5 and
0.25 ms plant integration while retaining the 1 ms governor and 100 Hz decisions.
The last test needs a dedicated substep adapter: simply changing the current
environment timestep violates its control contract. Replay passive predictions
without refitting, and keep their local-angle mapping separate from policy truth.

New physical evidence must still establish a current upright/angular mapping,
actual cart motion against pulse count across the intended speeds/accelerations,
and end-to-end renewal margins under realistic host load. Small-pulse camera
shape agreement and rejected command-domain driven fits do not supply those
bounds. These are the experiments that can turn an offline candidate into
evidence about the rig; no amount of additional nominal training replaces them.
