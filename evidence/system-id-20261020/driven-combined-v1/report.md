# Encoder-only driven assessment, 2026-10-20

**The unchanged model fails both independent native AUTO validation trials at the original 0.5 s horizon.** Several near-hanging training trials pass the limited checks under a local resting-angle anchor, but that does not establish global angle calibration, physical cart dynamics, or transfer readiness. The model, firmware parameters, reference 330, pinned training profiles and original scoring gates were not changed. No parameter was fitted.

This assessment combines the complete gentle training campaign, the completed portion of standard training, and two completed native AUTO validation trials. The failed standard −20 mm trial and failed standard-validation quiet trial remain excluded. Their failures are preserved as execution failures, not used as physics evidence. All inputs are sealed local recordings; the analyzer verifies their hashes and declared roles before reading. Vision was excluded as requested.

## Fixed model and original checks

The model is `qdd=(9.81*sin(q)-a_MCU*cos(q))/0.160303873 - 0.006891975*omega - 1.6268943*tanh(omega/0.05)`. The input is a left-held 100 Hz **MCU commanded acceleration state**, with unit gain and zero modeled delay. Physical acceleration, intersample 1 kHz ramps, masses and actuator tracking are not measured here.

Each 0.5 s prediction reinitializes from raw encoder angle and a quadratic derivative using seven past/current samples. The future recorded command history supplies forcing. Recorded firmware omega is a separate comparator. These are conditional short-horizon forecasts, not full-episode free-running validation. Errors are circular angular differences. Continuity gaps reaching 20 ms reject a trajectory; failed trials cannot pass by using their earlier tail.

Both predeclared phases are retained: raw firmware reference (zero offset), and a pertrial quiet hanging anchor `wrap(initial_hanging-pi)`. The latter represents resting equilibrium, which friction may displace from true vertical; it is not an upright/global encoder correction. No offset is fitted from either training or validation residuals.

Limited checks require ≥3 forecasts, encoder span ≥0.15 rad, commanded-input RMS ≥0.05 m/s², forecast RMS ≤0.08 rad and absolute-error p95 ≤0.15 rad. They do not replace the original full-model residual/calibration/physical-validity gates. `hardware_accepted=false`, `recommended_model=null`, and the original full-rig limitations remain.

## Training coverage and prediction

| Completed training excitation | Encoder span (rad) | Raw-phase RMS (rad) | Local-anchor RMS / p95 (rad) | Local limited checks |
|---|---:|---:|---:|---|
| Gentle +10 mm pulse | 0.12272 | 0.09589 | 0.00774 / 0.02208 | Insufficient span |
| Gentle −10 mm pulse | 0.13039 | 0.10126 | 0.01964 / 0.04818 | Insufficient span |
| Gentle +20 mm pulse | 0.32827 | 0.10926 | 0.01988 / 0.04473 | Pass, training only |
| Gentle −20 mm pulse | 0.31907 | 0.11722 | 0.03586 / 0.09874 | Pass, training only |
| Gentle +20 mm reversal | 0.70256 | 0.13188 | 0.03407 / 0.07705 | Pass, training only |
| Gentle −20 mm reversal | 0.69029 | 0.12612 | 0.02367 / 0.04406 | Pass, training only |
| Standard +10 mm pulse | 0.11812 | 0.10010 | 0.01202 / 0.03441 | Insufficient span |
| Standard −10 mm pulse | 0.12272 | 0.10539 | 0.02061 / 0.04853 | Insufficient span |
| Standard +20 mm pulse | 0.31140 | 0.11841 | 0.02958 / 0.07610 | Pass, partial training only |

All completed actuator trials fail the raw-phase error checks. The two static timing trials lack excitation and cannot validate dynamics. The complete gentle run's six actuator trials have zero reported policy clamps/jerk-limit events; this does not independently prove physical tracking or reveal all 1 kHz governor ramps. The prior [gentle report](../driven-gentle-v1/report.md) includes command RMS and excitation-only errors, avoiding quiet-hold averaging. The standard campaign stops with executor fault 1 during the −20 mm trial; the separate standard-validation campaign stops during its quiet trial on the 20 ms cadence guard. Neither incomplete campaign is accepted as a whole.

The native training trial fails strongly: raw/local RMS 0.79796/0.84841 rad. This signals that near-hanging results cannot be generalized to native swinging/upright motion under the present input and sensor assumptions.

## Independent native validation

Each 25 s trial supplies 49 original 0.5 s forecasts (2,450 predicted samples). Both completed normally and returned to disabled state. Their completion is an execution result, not a model-validation pass.

| Native validation | Raw-phase RMS / p95 (rad) | Local-anchor RMS / p95 (rad) | Recorded-omega RMS, raw / local (rad) | Original result |
|---|---:|---:|---:|---|
| 001 | 0.82681 / 2.02224 | 0.81863 / 1.95987 | 0.70658 / 0.80226 | Reject |
| 002 | 0.71342 / 1.67567 | 0.69847 / 1.65114 | 0.80170 / 0.82513 | Reject |

Changing the initialization comparator alone does not rescue the 0.5 s predictions. The exact failure is a conditional forecast-gate failure, **not proof of an incorrect physical length, motor fault, lost steps, or any unique mechanism**. Input reconstruction/physical tracking, observation mapping, rate initialization, friction approximation and model error remain confounded.

## Post-hoc convention and horizon diagnostics

These checks were declared in `posthoc-plan.json` **after the original validation failures were observed**. They are development diagnostics, not renewed unseen validation. The primary assessment remains unchanged.

The checked-in firmware documents theta positive toward +x (`teensy_executor.ino:350`), with CART_INVERT and ENC_INVERT both zero (`:39–42`). Native and external paths share `cart_motion::advance` and store its output in `acc_cmd` (`:831–852`); telemetry transmits this acceleration separately from demand (`:912`). The SDK parser keeps that ordering, and the controller's own forecast uses the same minus-cosine input sign (`control/reference.py:87`). No source-level native-only sign/frame switch was found. This source audit does not independently establish the physical wiring or tracking.

The finite hypotheses were input signs ±1 and causal delays 0/10/20 ms. Selection was predeclared as minimum equal-trial mean squared error across completed non-timing training trials, separately for each existing phase. `training-choice.json` was written before diagnostic validation scoring. The raw-phase choice remains +1/0 ms. Under local hanging phase, the numerical choice is −1/20 ms, driven by the much larger native training error; it **worsens** reused validation RMS to 0.89373/0.78607 rad versus original 0.81863/0.69847.

Actuator-only training provides the contrary and clearer local sign evidence: pooled equal-trial local-anchor RMS is 0.02425 rad at the original +1/0 ms, versus 0.05465–0.05689 rad for reversed sign. Positive 10/20 ms delays give 0.02535/0.02668 rad. Thus the global post-hoc minimum does not justify reversing the input convention or changing delay. No diagnostic hypothesis is promoted.

A separate fixed **100 ms** diagnostic preserves the original +1/0 ms input and both phase baselines, with no fitting or new acceptance gate:

| Native record | Raw RMS / p95 (rad) | Local-anchor RMS / p95 (rad) |
|---|---:|---:|
| Gentle training | 0.16060 / 0.34980 | 0.15940 / 0.35586 |
| Validation 001, reused post-hoc | 0.15372 / 0.35102 | 0.15251 / 0.34625 |
| Validation 002, reused post-hoc | 0.16559 / 0.37733 | 0.16352 / 0.37880 |

For the nine actuator training trials, 100 ms local-anchor RMS ranges from 0.00439 to 0.02180 rad. Native errors shrink substantially at the shorter horizon but remain sizeable. Upright instability can amplify small state/input errors over 0.5 s; these horizon results are consistent with amplification contributing, without isolating its cause or establishing usable upright prediction. Full per-mode diagnostic errors are retained in `input-horizon-diagnostic.json`.

## Actual balance intervals

Mode-duration accounting avoids counting everything after first capture as balance. The intervals below are measured from each trial's first active state and are approximately 10 ms quantized. Angle metrics use enabled mode-3 snapshots only.

| Record | Mode-3 intervals (s) | Total observed balance | Balanced samples | Raw balance RMS / p95 (degrees) |
|---|---|---:|---:|---:|
| Gentle native training, 15 s | 2.51–3.51 | 1.00 s | 100 | 4.976 / 8.095 |
| Native validation 001, 25 s | 1.90–2.02; 6.00–7.39 | 1.51 s | 151 | 12.122 / 27.026 |
| Native validation 002, 25 s | 2.47–5.08 | 2.61 s | 261 | 5.064 / 8.965 |

All three subsequently return to swing before the duration limit, then normal return and disabled state; no fault is recorded in these native segments. Maximum absolute counted positions over native/return are 0.2932875, 0.2938875 and 0.2932125 m respectively. Counted position is not an independent physical displacement measurement. Full mode intervals and source pins are in `native-summary.json`.

## Artifacts and reproduction

The representative near-hanging plot is [gentle +20 mm](training-1-4-prediction.png); the representative independent failure is [native validation 001](validation-1-1-prediction.png). Both show raw and local-anchor baselines with causal/recorded initial-rate comparisons. The plots were visually inspected. `analysis.json` retains source hashes, live parameters, exact baselines, continuity, window initial states and pointwise predictions. `summary.json` is the compact version; `verification.json` pins artifacts, source files and sealed inputs.

The analyzer's 18 focused tests passed. The post-hoc default sign/zero-delay computation reproduces every non-timing training primary RMS to 1e-12 before alternative scores are considered. No SDK, pinned profile, source recording or original assessment was modified for the post-hoc checks.

From the repository root, reproduce the original assessment into a new output directory:

```sh
MPLCONFIGDIR=/tmp/cartpole-id-matplotlib PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m cartpole_sdk.identification.driven_validation --training runs/id-live-20261020/gentle-train-02 --training runs/id-live-20261020/standard-train-01 --validation runs/id-live-20261020/coupled-validation-01 --validation runs/id-live-20261020/standard-validation-01 --allow-partial --output /tmp/driven-combined-reproduction
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python evidence/system-id-20261020/driven-combined-v1/summarize_native.py runs/id-live-20261020/gentle-train-02 runs/id-live-20261020/coupled-validation-01
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/test_driven_validation.py -q -p no:cacheprovider
```

`diagnose_inputs.py` reproduces the explicitly post-hoc supplemental JSON files in this directory. Preserve the primary `analysis.json` and declared plan while reproducing it. Additional near-hanging independent data would still be required to validate that local regime; an encoder-only campaign cannot establish metric actuator tracking or a globally correct angle map.
