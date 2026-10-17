# Independent passive heldout result, 2026-10-16

**The frozen viscous candidate passes the declared aggregate statistical gates.** This supports an explicitly conditional passive-pole comparison profile. It does not validate the full cart/actuator model, global angle calibration or every individual release. Errors are uneven: the largest selected episode individually exceeds the aggregate RMS and p95 thresholds. The viscous+Coulomb primary remains rejected for its negative training damping.

No coefficient, phase offset, model choice, threshold or episode boundary was changed after scoring. The frozen training manifest SHA256 remains `04befe14b16a54e5288d4326a7ca5d826e8c5a169dc20206dd1108ea160aa744`; all eight artifact hashes were checked before importing the fitter. The evaluator calls the frozen numerical prediction/integral functions using exact stored coefficients; it never calls fitting.

## Source and annotations

The completed disabled-driver recording is `/home/rbafna/cartpole-v2-runs/system-id-20261016/manual-ringdown-heldout-01/`. Its662528-byte lossless `columns.json.gz` has SHA256 `183dc05f790630640cc22ae8a1e90c469cac9dc92faec26c80436f7b427e1a5f`. Original raw identities are:

| Source | SHA256 |
|---|---|
| `rig-1792183281283189743-703304915.jsonl` | `968cbd1ed2742a2121e18c974532663393f16e208082000d29c4c50f81f64f60` |
| `vision.ndjson` | `8b7515dc11dc01bb603d5000b3f208e23980067ffd26698897e9b1a3a1ca13e5` |
| `report.json` | `cc391181984d2fe98e9b66438e4fb747290bed4adad052a4cf09d3281d568f34` |
| `vision-report.json` | `321480816ebf7b9a601a83fd8ea375813efca2c0c947f23f2c1635de4a990886` |

The80.161s record contains20074 state rows, one verified identical board duplicate,4106 camera rows and no timestamp reversals. All states have flags205/fault0/mode0, with reference330 and home epoch14 unchanged. Counted x remains zero; it is not physical stationarity proof. The user confirmed holding the cart by hand throughout and completed the three requested alternating releases.

Free intervals were selected from raw motion/handling transitions and independently checked against the full-record plot **before any forecast or residual score**. `manual-ringdown-heldout-01-annotations.json`, SHA256 `8d26fa57c18055de73355657584cc3e2bd7b3e176c5dadb8c414691490c40d9b`, fixes31.0–36.4,44.8–51.2 and63.0–70.0s relative to first board `unwrapped_us=3834751050`. Included intervals are31.002–36.398,44.802–51.198 and63.002–69.998s, totaling4700 magnetic samples. Manual handling, first extrema/transients and final small/static suffixes remain excluded. No boundary was optimized against errors.

## Fixed-model scores

The selected magnetic model remains L=0.16073596568158666m, gamma=0.4631556778357131/s, Coulomb c=0 and fitted gravity-phase offset−0.11310915597373176rad. Linear coefficients `[A,gamma,B]` remain `[60.64177253375597,0.4631556778357131,6.8885413950367065]`. The phase offset is model-inferred in sensor coordinates, not an independently proven encoder correction.

| Model |0.5s forecast RMS, rad|p95 absolute error, rad|Integral NRMSE|Final statistical status|
|---|---:|---:|---:|---|
| Frozen magnetic viscous |0.07037925|0.13276841|0.09141581|pass aggregate gates|
| Frozen magnetic viscous+Coulomb |0.07204289|0.13182958|0.08416343|rejected: training gamma<0|
| Provisional raw-camera viscous |0.04993794|0.10166635|0.04133566|pass statistical gates; projection remains uncalibrated|

Magnetic validation covers35 half-second prediction windows,4375 predicted samples and51 weak windows; maximum selected angle span is1.91748rad. Thresholds remain RMS≤0.08rad, p95≤0.15rad, integral NRMSE≤0.15, at least3 predictions and heldout span≥0.15rad. Each forecast reinitializes angle and velocity from past raw-angle samples within its episode; its validated horizon is0.5s. Full-episode open-loop rollout accuracy remains unvalidated. Camera validation uses34 forecasts,826 samples and49 weak windows. The camera Coulomb candidate has no fitted training coefficients and remains rejected/unscored.

The aggregate result masks uneven errors. The following are supplementary diagnostics, **not a newly substituted acceptance rule**:

| Magnetic episode |Forecast RMS, rad|p95 absolute error, rad|Integral NRMSE|
|---|---:|---:|---:|
|1|0.06989|**0.17418**|0.11074|
|2|0.04609|0.10434|0.07625|
|3|**0.08728**|**0.17550**|0.09419|

Episodes1 and3 exceed0.15rad p95 individually, and episode3 also exceeds0.08rad RMS. These observations limit claims about amplitude-dependent accuracy and robustness. They are not repaired by refitting to this heldout record. A more detailed model would need a fresh training/validation split.

## Physical and camera limits

All three heldout raw-pivot diagnostics pass the unchanged pixel gates: valid coverage98.51%,100%,100%; radial p95 displacement0.311,0.283,0.439pixels; maximum0.425,0.417,0.478pixels; maximum valid-frame gap50.2,38.0,38.0ms. Handling-region false detections are outside the annotated episodes. These observations support the intended hand restraint, but do not prove metric/out-of-plane stationarity. The earlier training episode2 camera coverage failure remains part of the evidence and is not erased by this clean heldout result.

Camera angle remains the predeclared image projection `unwrap(pi-image_angle_rad)`, using original timestamps. Image arm lengths range about165–177pixels across the selected episodes. Applying only the two **frozen training phase offsets** for a cross-sensor diagnostic gives per-episode disagreement RMS0.0563,0.0658,0.0729rad. No heldout offset was fitted. Exposure/transport timing, projection and magnetic angular distortion remain confounded; no global reference or calibration update is justified.

For an opt-in passive MuJoCo comparison, effective length and angular damping may be used conditionally, with provenance and uncertainty retained. Hinge torque damping requires an assumed pivot inertia; for the existing uniform-rod surrogate, `I_pivot=0.75*m*L_eff²` and `hinge_damping=gamma*I_pivot`. Mass, cart friction, input gain, commanded-to-physical acceleration, actuator delay and force saturation remain unidentified. This assessment does not authorize a claim of a validated full-rig RL environment.

## Reproduction and verification

Six new evaluator tests pass, including exact agreement with the frozen validation math, proof that scoring makes no fitting call, unchanged parameters, static-heldout rejection, source independence, annotation admission and clock-reversal rejection. Existing training files were not edited. All predictions and diagnoses below are local/offline; no serial, service, motion or calibration command was issued by this analysis task.

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest discover \
  -s evidence/system-id-20261016/analysis/heldout -p test_evaluate_passive.py -v
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  evidence/system-id-20261016/analysis/heldout/evaluate_passive.py \
  --input /tmp/manual-ringdown-heldout-01-columns.json.gz \
  --annotations evidence/system-id-20261016/analysis/heldout/manual-ringdown-heldout-01-annotations.json \
  --output /tmp/fresh-heldout-assessment.json
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  evidence/system-id-20261016/analysis/heldout/diagnose_heldout.py \
  --input /tmp/manual-ringdown-heldout-01-columns.json.gz \
  --annotations evidence/system-id-20261016/analysis/heldout/manual-ringdown-heldout-01-annotations.json \
  --output /tmp/fresh-heldout-diagnostics.json
```

`manual-ringdown-heldout-01-assessment.json` preserves complete fixed-parameter scores, source pins and camera checks. `manual-ringdown-heldout-01-diagnostics.json` preserves the supplementary per-episode results. `pre-score-verification.json` pins the evaluator and annotations before scoring; `verification.json` pins the final heldout evidence separately from the unchanged training freeze.
