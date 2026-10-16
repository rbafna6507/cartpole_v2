# Offline sensing and identification

The new identification package fits an acceleration-driven planar pendulum from
independent training and held-out runs. It never modifies firmware, calibration,
archived algorithms or the simulation model. A synthetic result establishes
mathematical/software behavior; a physical fit requires actual rig records.

For upright-zero angle in the SDK's positive cart +x rotation convention,

```
theta_ddot = (g / L_eff) sin(theta)
             - gamma theta_dot
             - (input_gain / L_eff) a(t - delay) cos(theta)
L_eff = I_pivot / (m_pole * COM_distance)
damping_ratio = gamma / (2 sqrt(g / L_eff))
```

`gamma` is angular damping per second. The damping ratio is dimensionless.
Neither quantity is a physical hinge torque damping coefficient without measured
inertia. Pole/cart masses and force gain cannot be identified from acceleration
and angle alone. The acceleration-driven equation follows the cart-pole equation
with cart acceleration substituted; see [MIT's Underactuated Robotics](https://underactuated.csail.mit.edu/acrobot.html).

With **commanded** acceleration, input gain and delay include the actuator,
step-motion discrepancies, timestamp/estimator timing and model mismatch. They
are composite effective parameters, not independently measured cart acceleration,
slip, force gain or physical motor delay. A measured acceleration record must come
from an independently calibrated source. Step count is not independent cart truth.

## Input and API

```python
from cartpole_sdk.identification import FitConfig, identify_pendulum
report = identify_pendulum(training_rows, validation_rows,
                          source='magnetic', acceleration_kind='commanded',
                          config=FitConfig(length_bounds_m=(0.05, 0.5)))
result = report.to_dict()
```

Canonical dictionaries require `t_s`, `theta_rad` and
`cart_acceleration_m_s2` in SI. Optional fields are `omega_rad_s`,
`omega_effective_t_s`, `valid` (bool), `run_id`, `calibration_id`, `frame_id`,
`clock_id`, `source`, and `acceleration_kind`. Use distinct actual `run_id`s;
metadata must describe the captured experiment, not a renamed copy. If omega is
provided it must represent row time. Earlier vision slope effective times must be
explicitly aligned, or omega must be omitted. Angular rate is used only to
initialize held-out prediction; regression does not need it.

Finite, strictly increasing timestamps are mandatory. Invalid rows may contain
`None` for unavailable angle/acceleration. An invalid row, excessive timestamp
gap, or changed run/calibration/frame/clock breaks a segment. Unwrap, delay
interpolation, regression and prediction stay within valid segments. An undetected
turn of more than pi between frames cannot be repaired by unwrapping; adequate
sampling is an experimental prerequisite. Joining independent clocks requires an
explicitly calibrated clock mapping before these rows are built.

CSV requires explicit names, even when column order appears obvious:

```sh
PYTHONPATH=src python examples/identify.py \
  --training train.csv --validation holdout.csv --format csv \
  --column t_s=seconds --column theta_rad=angle \
  --column cart_acceleration_m_s2=command \
  --column run_id=run --column calibration_id=calibration \
  --acceleration-kind commanded --source magnetic --output fit.json
```

`--format rows-jsonl` reads canonical dictionaries, one per line. The output file
must be new; the CLI never overwrites an earlier report. Exit 0 means the configured
quality checks accepted the report; exit 2 means rejected fit or invalid input.
Raw file hashes and canonical row hashes are recorded.

`sdk_run_rows` adapts explicit SDK run dictionary records containing `observation`
and caller-named time/acceleration fields. It requires a precise angle channel,
SI time scale, acceleration kind and run/calibration/clock identities. Angle
effective time must equal the acceleration time. SDK base recording v1 contains
observations only; it cannot reconstruct commanded or measured acceleration.
Export/join action records explicitly on a calibrated clock rather than guessing
an input from observation columns.

## Method and acceptance

On disjoint windows, a compact polynomial test function and its first derivative
vanish at both boundaries. Integrating the equation twice by parts moves angle
derivatives onto the test function. Only angle, sin/cos angle and delayed
acceleration need quadrature. Constant/linear angle terms are integrated
analytically to avoid numerical offset bias on irregular sample grids. This uses
the weak-form principle described by [Messenger and Bortz, Weak SINDy](https://pmc.ncbi.nlm.nih.gov/articles/PMC10795802/);
this package fits a fixed physical model rather than performing sparse model selection.

The finite delay grid is selected from training residuals alone. Training checks
include minimum windows, angle/input excitation, scaled regression rank and
condition, positive bounded length/input gain, nonnegative bounded viscous damping,
and integral residual limits. A delay at the maximum search boundary rejects the
fit. A training-only five-term nuisance regression adds gravity cos(theta) and
input sin(theta) terms to diagnose an angle zero offset. Both independently
inferred offsets must remain within `max_angle_zero_bias_rad` (default 0.02 rad),
and that diagnostic must itself be identifiable. A visible hanging-angle error
must not be absorbed into effective length, gain or damping.

`FitConfig.angle_offset_rad` can subtract an independently established fixed angle
zero offset before fitting; its value is saved in provenance. The software does
not establish or change live calibration. A physically hanging pole measured
roughly 0.13 rad from pi needs calibration investigation; a fit with that bias is
rejected. Nuisance estimates themselves are diagnostics, not commissioned corrections.

Held-out runs do not select parameters, delay or thresholds. They undergo fixed
parameter nonlinear RK4 prediction over nonoverlapping 0.5-second windows with
only initial angle/rate reset, plus independent integral residual checks. If rate
is absent, initialization uses only past samples from that same segment. Reported
RMSE and p95 are wrapped angular errors after initialization. At least three
prediction windows and configured residual limits are required. This is a bounded
prediction check, not a guarantee of long-horizon chaotic/unsteady control behavior.

Defaults: 20 training windows of 0.35 seconds, 0.05-second maximum gap,
0–0.1-second delay grid at 0.005-second resolution, prediction RMSE <=0.08 rad,
p95 <=0.15 rad and integral NRMSE <=0.15. Configure thresholds and length prior
before inspecting held-out results. OLS coefficient/length standard errors are
conditional regression uncertainty. They omit errors-in-variables, calibration,
clock bias, model bias and serial noise correlation. The near-optimal delay profile
(5% training loss band) is not a confidence interval or a claim that delay is
uniquely physically identified. An experiment should vary forcing frequencies,
amplitudes and pendulum energies and repeat independent trials.

`recommended_model` contains only effective length and only for accepted reports.
It does not apply a model or set a safety limit. A new physical model still requires
review of provenance, cart measurements, calibration and further validation.

## Vision provider

`VisionProvider` converts caller-supplied vision3 snapshot dictionaries. It never
consumes the dashboard's comparison/fused fields. Construct it with `Session`,
explicit `frame_id`, caller-approved calibration dictionary and
`ClockMapping(source_clock_id, session_clock_id, offset_ns)`; there is no implicit
Jetson/board/host alignment. The caller separately supplies local `received_ns`
and the snapshot source clock identity to `observation()`.

vision3 `t` is host-read completion: an acquisition proxy, not exposure time.
Mapped acquisition and angle effective time retain it, while angular/cart velocity
samples retain their own earlier effective timestamps. Methods identify causal
slope estimates; `last_timing` preserves source t, host-read-to-result duration,
clock mapping and calibration hash for caller evidence. Repeated/decreasing frames,
future mapped timestamps or result time, and unexpected calibration changes are
rejected. Reconstruct the provider with an explicitly approved new calibration
and session/frame identity after a reset. Angle/cart validity is independent;
missing cart metric scale always suppresses metric position/velocity. Stale
mapped acquisition/effective times suppress values even if snapshot flags say valid.

`VisionHTTPClient` is an isolated optional read-only urllib GET client with bounded
body and timeout, strict JSON and no calibration/control API calls. Snapshot
conversion tests use the archived real `vision3/evidence/live-measurement-samples.json`
fixture without touching the running server. HTTP decoding tests substitute a
byte-stream transport. No network/hardware commissioning is implied. No fused
control estimator is supplied; fusion requires calibrated clocks, frames,
uncertainty and a separately validated estimator.

## Current physical evidence

The original-controller `baseline-20261013T224303Z` trajectory contains 1021 samples
across 10.202 s, including swing-up and balance, 28 nonoverlapping regression windows
and nonzero commanded acceleration with 2.813 m/s² standard deviation. It therefore
clears the basic training coverage/rank checks. It is still rejected: integral
NRMSE 0.266 exceeds 0.15; prediction RMSE is 1.414 rad on an independent earlier auto
run and 0.164 rad on the recenter/passive run. The nuisance gravity/input offset
estimates (-0.0084/+0.4142 rad) disagree, so a single inferred angle calibration
correction does not explain the dynamic mismatch. No rejected candidate
parameter is recommended or applied. Installed reference 3485 remains preserved.

The complete report, raw-file/wire/report hashes, canonical row data and exact
reproduction command are in `evidence/phase4/fuller-physical-assessment.json` and
`evidence/phase4/assess_actual.py`. Planned next measurements are recorded in
`evidence/phase4/next-excitation-protocol.md`: independently establish zero/timing,
repeat passive decay, then distinct bounded frequency-rich forced and held-out
trials with independently calibrated cart measurement where available. Successful
swing-up/balance and successful physical model identification are separate results.

The later bounded executor characterization (`identification-20261013T231939Z`)
provides independent 20-second train/held-out multisine records at 250 Hz. Both
complete fault-free and disabled. Actual angular spans are only 0.047554 and
0.039884 rad, below the unchanged 0.15-rad excitation requirement. Raw-encoder
fitting rejects nonpositive gravity and integral residuals; a fixed pretrial
hanging-offset sensitivity also rejects. Short-horizon RMSE alone passes but does
not override physical coefficient, excitation or residual failures. See
`evidence/phase4/executor-assessment.md` and its reproducible assessment JSON.
The original compressed report and exact tested command procedure are preserved.

A larger bounded pair can materially improve signal and is not mathematically
unidentifiable solely because vision is unavailable: roughly proportional 4x
response would span about 0.19 rad. Acceptance remains conditional on actual
excitation, a physically established angle mapping and unchanged held-out checks.
No cart masses/force/slip or independent physical actuator delay can be inferred
from commanded acceleration and step-derived cart feedback. A local hanging offset
must be fixed from training pretrial reference data before validation, explicitly
labelled, and must not silently replace global upright calibration. If offset
consistency/residual failures persist with stronger verified motion, more amplitude
alone is insufficient; independent measurement/model investigation is required.

The completed 4x follow-up (`identification-20261013T232736Z`) improves actual
angular spans to 0.144194/0.101243 rad. A local offset is frozen from the training
pretrial's last 5 seconds only (-0.108911426 rad) and applied identically to the
separate held-out run. The resulting candidate passes held-out prediction and
integral checks, but still fails the unchanged training span (0.144194 <0.15),
training integral residual (0.174254 >0.15), and input zero consistency diagnostic
(-0.065503 rad versus a 0.02-rad limit). It remains unaccepted. Validation pretrial
reference differs by 0.004608 rad and is recorded only as stability evidence.
No calibration, model or acceptance threshold changed. Preserved sources,
procedure, reproducible hashes and specific next measurements are documented in
`evidence/phase4/executor4-assessment.md`.


## Native Rig JSONL recordings

`rig_log_rows(records, run_id=...)` returns canonical rows plus admission counts.
It reads the recorded session and preceding INFO reference/home metadata, uses
unfiltered `theta` and jerk-limited commanded `acceleration` at board
`unwrapped_us`, and leaves all inactive/unhealthy states as invalid boundaries.
It never substitutes pre-governor `demand`, filtered `angle_hat`, or filtered
`omega`. The latter's effective delay is not established. Duplicate identical
board snapshots are counted once; conflicting duplicates and clock/session
ambiguities fail. Host errors latch subsequent records invalid for this input.
The timestamps are acquisition-snapshot proxies, not verified sensor latency.

`examples/identify_rig.py --training INPUT --validation INPUT --output NEW.json`
accepts plain/gzip JSONL or `ARCHIVE.tar.gz::EXACT_MEMBER`. Archive members are
read without extraction. Source hashes, session/reference identities, excluded
counts, fitter/adapter hashes and the unchanged fit thresholds accompany the
report. A rejected fit returns status2 with `recommended_model:null`; it never
changes the simulator. Caller must still choose genuinely independent runs and
check installation/calibration provenance. Health flags cannot prove physical
accuracy or independent excitation.

The first current-reference assessment is preserved in
`evidence/phase4/paused-20261016/`. A candidate effective length0.152m was rejected
on both later recordings. The report describes calibration diagnostics, input
meaning, causal state-initialization uncertainty, and held-out prediction errors.
