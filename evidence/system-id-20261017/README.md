# System identification — October 17, 2026

System identification remains open. These measurements do not yet justify moving to physical RL transfer or replacing the simulator's default plant. Live firmware, gains, saved reference 330 and archived working releases were not changed. The user-operated console established home epoch 15 and bandwidth 6 before the new short-pulse batch; the collectors preserved those settings. Jerk remained 150 m/s³.

## What ran

The new `scripts/system-id` workflow ran on the Jetson in `/home/rbafna/cartpole-v2-live/staging/system-id-20261017`. It is independent of the native operator release. See [operator commands and model/Gym workflow](../../docs/system-identification-workflow.md).

- A 5 mm left pulse verified the integrated collector, followed by four signed 10/20 mm training pulses and a separately reserved signed 30 mm validation pair. Each used a 0.65 s reference followed by 3 s active cart hold at 100 Hz. Every new short pulse completed, had zero logger drops/faults, and confirmed disabled STOP at counted home. These are bounded trials, not long-duration control commissioning.
- Each 30 mm run clipped exactly two requested samples at the ±3 m/s² test limit. The raw governor acceleration is retained; the ideal analytic waveform is not substituted for it. Clipping remains an explicit protocol deviation.
- The user's new 180 s hand-restrained recording contains 45,063 STATE records, no faults, zero requested/applied cart acceleration and confirmed disabled STOP. Nominal 30° left / 60° right / 60° left instructions are not claims of measured pose. Free intervals were frozen from unscored raw-motion previews before evaluating predictions.
- Earlier failed attempts are preserved. One exposed tiny nonzero acceleration text underflow in the production Teensy float parser; the SDK serialization fix has native-parser regression coverage. Two longer negative 5 mm attempts stopped on the existing timing / 20 ms lease protections. Those limits were not relaxed and failed recordings are not fitting inputs.

Raw data, source hashes, live parameters, reference/home identity, failures and STOP outcomes live under `raw-initial/`, `raw-negative5/`, `raw-pulse-training/`, `raw-pulse-validation/` and the new manual evidence. `preservation.json` manifests verify decompressed exact raw content and stored compressed bytes. The full Jetson run directories are retained.

## Frozen model comparison

[Recorded swings versus the frozen MuJoCo model](analysis/comparison/recorded-vs-predicted.png) shows the independent October 16 manual recording. The left column resets forecasts every 0.5 s; the right initializes once and runs continuously for each selected release. Initialization uses preceding angle samples only. A local fitted hanging-region phase is applied to the comparison; it is not a global encoder calibration.

| Release | Continuous MuJoCo RMS | 95th-percentile absolute error |
| --- | ---: | ---: |
|1|2.90°|5.06°|
|2|3.27°|5.50°|
|3|7.82°|13.30°|

The frozen passive candidate has effective length 0.160736 m and viscous angular damping 0.463156/s. Its existing 0.5 s aggregate RMS is 4.04° in MuJoCo. Aggregate scores hide the larger error on the third release. Original training/validation artifacts are unchanged. Further exploration of those old validation data is development, not a new independent test.

Run the self-contained plot command from any directory:

```sh
/path/to/cartpole_v2/evidence/system-id-20261017/tools/plot_passive_comparison.py \
  --repo /path/to/cartpole_v2 --output /path/to/NEW-comparison
```

The executable uses `uv` and its declared dependencies. PNG, PDF and exact numerical comparisons are saved; source/model/annotation hashes are checked.

## Fresh manual repeatability check

[Full assessment and reproduction commands](analysis/manual-repeatability/README.md) · [Recorded versus predicted plot](analysis/manual-repeatability/frozen-model-comparison.png) · [Camera versus encoder plot](analysis/manual-repeatability/camera-encoder-comparison.png).

The new recording tests the unchanged October 16 candidate with three independently selected free-motion intervals. These intervals were frozen from an unscored motion preview before running predictions. The cart was restrained by hand, with the motor disabled throughout.

| Nominal release instruction | Continuous MuJoCo RMS | 95th-percentile absolute error | Short-forecast fixed gates |
| --- | ---: | ---: | --- |
|30° left of hanging|2.93°|6.48°|Pass|
|60° right of hanging|3.81°|6.45°|Pass|
|60° left of hanging|7.78°|13.28°|Fail|

The aggregate short-forecast RMS is 4.31°, but its 95th-percentile error is 9.80° and fails the unchanged 0.15 rad threshold. The large left-release mismatch repeats; the model cannot be promoted from a favorable aggregate RMS. The predeclared training-only Coulomb alternative makes only mixed small changes and also fails.

Camera geometry coverage during those selected moving intervals was 81.3%, 82.2% and 88.6%; maximum gaps were 88, 138 and 75 ms. Pivot radial 95th-percentile variation stayed below 0.46 pixels. Camera/encoder periods were approximately 0.82–0.83 s. Camera-versus-encoder disagreement is largest on the right-side release, whereas model error is largest on the left-side release. This does not establish a unique sensor or friction cause. Same-run angle gains/offsets and receipt-time alignment are descriptive diagnostics, not independent calibration.

A separate [initial-state sensitivity diagnostic](analysis/manual-turning-point-initialization-development-v1.json) keeps the frozen physics coefficients and compares both initializations on the same later samples. A fixed rule selects the first clear turning point; scoring begins only after the samples used to estimate that point. On the large left release, frozen-ODE RMS falls 7.80° → 3.91°; the small left release barely changes, and the right release worsens 3.76° → 5.69°. Initial-state estimation explains part of the large-release error but is not a general correction. This is development analysis after seeing the primary results, not a replacement acceptance test. No coefficients or original scores changed.

## Cart response and driven fitting

The [camera comparison](analysis/camera-step-training/README.md) independently checks visible pulse shape. The four training runs have diagnostic scales 986–1015 pixels per counted meter, zero-proxy-lag residual RMS 0.51–1.04 pixels and return offsets 0 to −0.37 pixels. A same-run timing sweep minimizes errors at 15–20 ms with 0.15–0.21 pixel RMS. These fitted scales and lags are not independent metric or exposure-time calibration. Negative 20 mm tail tracking coverage is 83.6%; per-run gaps are retained.

The analysis protocol was frozen before collecting signed 30 mm validation. It pins the four training sources, numerical gates, source code, zero-offset primary comparison and the historical-phase secondary diagnostic. See `analysis/pulse-batch-protocol-20261017.json` and [batch reproduction instructions](tools/README.md).

| Comparison | Training integral NRMSE | Reserved 0.5 s prediction RMS | Result |
| --- | ---: | ---: | --- |
|Raw upright reference, no phase offset|0.5117|36.98°|Rejected; nonphysical fitted coefficients and several failed gates|
|Historical local phase −0.113109 rad|0.2528|1.57°|Rejected; training residual and angle/input-bias diagnostic fail|

The secondary result has effective length 0.174957 m, commanded-input gain 1.40903 and viscous damping 1.43619/s. Its heldout 95th-percentile error is 3.33°. These are conditional command-domain estimates, not accepted physical parameters. The fitted gain can include actuator, sensing, timing and model error; counted acceleration is not an independent physical acceleration measurement.

A training-only regularized dry-friction extension was evaluated on the 30 mm development recordings. It changes training NRMSE only 0.2528 → 0.2477 and prediction RMS 1.568° → 1.556°, and remains rejected. It does not resolve the mismatch. `analysis/driven-friction-development-v1.json` preserves its explicit assumptions and constraints. No coefficients were copied into the live controller or default MuJoCo configuration.

## Software and acceptance scope

The reusable workflow covers inspection, disabled manual capture, guarded pulse capture, source-bound annotation, independent fitting, rejected-fit preservation, scoped export and 100 Hz Gym loading. A synthetic fit→export→Gym chain verifies software execution; synthetic evidence is kept separate from physical recordings.

Raw/filtered/command channels remain distinct. Fitting uses direct raw magnetic `theta` and sampled MCU governor `acceleration`, not filtered omega, requested demand, mirrored encoder packets or fused angle. Camera-enabled collection publishes the current encoder session to the existing portal, while camera recording runs in a separate process.

Static validation cannot establish dynamic accuracy. Both the new batch analyzer and packaged `fit-driven` wrapper enforce existing angle-span/input-excitation minima on validation, preserving the untouched base fitter result. Rejected fits cannot export. Unsupported nonzero friction, non-unit gain or delay are rejected by model export rather than silently dropped. Masses, force authority and unmeasured actuator dynamics remain explicit assumptions.

## Remaining identification work

The new manual release assessment repeats the larger-left-release discrepancy seen in the prior recording, but one release per requested condition does not establish a repeatability distribution. The initialization diagnostic isolates one contributor without resolving the discrepancy. Resolve the remaining angle/input diagnostic and dynamic residuals before accepting a plant. Independently calibrated cart distance and timing, broader driven excitation and upright/full-swing measurement validation remain necessary for strong transfer claims. The available small-pulse data do not establish motor force limits or masses. No RL training or hardware RL policy execution was started in this work.

## Verification and final hardware state

The final local suite passed **1040 tests and 390 subtests**, with 8 optional/environment skips. The plot-enabled independent focused review passed 33 tests. The first sandboxed suite attempt could not bind localhost sockets; rerunning the same suite with loopback access passed. See `verification/final-verification.json` and the full log for source hashes and exact commands. All 88 preserved raw files across six manifests passed stored-byte and decompressed-content hash checks. Final gzip replay exactly reproduces the manual prediction arrays and scores.

The final Jetson inspection confirmed idle mode, motor disabled, zero fault, zero cart position/velocity/acceleration/demand, saved reference 330 and home epoch 15. Live controller settings and the operator release are unchanged. The cumulative I2C counter remained at five, with zero recoveries; there was no new I2C fault in these completed collections. The rig was left stopped at counted home.
