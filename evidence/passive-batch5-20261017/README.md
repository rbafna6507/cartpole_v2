# Passive batch 5: cleaner capture, persistent model/measurement errors

Both `passive-training-5` and `passive-validation-5` completed normally using `done`, confirmed STOP, and reported zero lost logger records. Both camera captures completed without stale-frame or recorder errors. Each contains six releases, including both horizontal directions. All eight original files are preserved byte-for-byte in `original-recordings.tar.xz`; `original-manifest.json` records the independently checked Jetson hashes.

Training records 124.956 seconds after its measured hanging baseline; validation records 118.732 seconds. The full board recordings are 127.074 and 120.831 seconds, respectively, with a maximum 4 ms snapshot gap. Hanging encoder baselines differ by one encoder count (about 0.088°); this baseline repeatability does not establish global angular calibration.

## Measurement review

Annotations were frozen from raw encoder and clock-mapped raw camera traces before any batch-5 model scoring. All six releases in both datasets remain selected. The same model, numerical methods, camera limits and prediction gates were used. There is no video to independently prove the exact hand-clear time; hand restraint and free release follow the stated collection protocol. Camera geometry is an apparent projected angle, not absolute physical-angle calibration.

Five of six pre-release poses pass in each recording, improving on three of six in batch-3 training. The remaining failures are informative:

- Training right-horizontal hold: encoder −98.00° versus camera −90.46° relative to each sensor's initial hanging baseline, a 7.54° discrepancy. That free interval also narrowly fails the 5° camera/encoder RMS gate at 5.039°. Other training free intervals pass.
- Validation right-60° hold: encoder's 95th-percentile deviation from its median is 3.67°, versus 0.38° in the camera. This fails the unchanged 2° pose variability gate. All six validation free intervals pass their camera consistency/pivot screens.

These are disagreements to diagnose, not proof of which sensor or mechanical component causes them. Requested release angles remain labels. Camera pose magnitudes are approximately 38.3, 34.7, 59.8, 59.6, 90.9 and 90.5° in training; validation gives 35.6, 34.1, 59.4, 62.6, 92.0 and 91.5°. Nominal 30° releases were somewhat larger, which does not invalidate fitting at their measured range.

## Fixed-method identification and validation

The viscous fit on training 5 estimates effective length **0.16053 m**, angular damping **0.38026/s**, and local raw-angle gravity phase **−0.11329 rad**. These agree closely with batch 3's 0.16004 m and 0.37207/s. They are model quantities and do not modify the working controller's settings or saved encoder reference.

Batch-5 validation has short 0.5-second forecast RMS **6.22585°** and P95 **13.07036°**, above the unchanged **4.58366° / 8.59437°** gates. Four of six validation episodes fail at least one numerical gate. Per-release RMS values are approximately 3.66, 3.05, 3.70, 5.50, 9.27 and 6.23°; the horizontal releases remain problematic. Release 01 passes RMS but narrowly fails P95. Numerical results remain unrounded in the reports.

Comparing all frozen models on the **same batch-5 validation intervals** separates model changes from differences between recordings:

| Model fitted on | RMS | P95 |
|---|---:|---:|
| Batch 2 training | 6.328° | 13.140° |
| Batch 3 training | 6.223° | 13.117° |
| Batch 5 training | 6.226° | 13.070° |

The new fit is essentially unchanged from batch 3 on the same data. Comparing 6.23° here with 5.54° from the previous historical review alone would conflate different validation recordings. The same-source comparison supports saying that capture completion and several held poses improved, but predictive model accuracy did not materially improve.

The fit is **rejected** by both numerical validation and required measurement checks. No model was exported; no simulator, gains, saved reference, firmware or collector code changed. Keep this batch. Additional identical collections alone are not the immediate priority. Investigate the held-pose sensor disagreement and forecast-initialization sensitivity using the existing recordings before changing the measurement/model method; any method revised using these scores needs a fresh holdout afterward.

## Artifacts and reproduction

- `analysis/training-camera-review/release-overlay.png` and validation counterpart: raw sensor overlay and selected poses/free intervals.
- `analysis/fit-review/recorded-vs-frozen-ode.png`: measured validation trajectories and frozen model predictions. Orange is the fitted passive ODE, not MuJoCo.
- `analysis/passive-fit.json`: full unchanged-method fit, provenance, rejection reasons and per-release gates.
- `analysis/summary.json`: completion checks, camera results and same-source cross-model comparisons.
- `analysis/fit-review/report.json.gz`: lossless full forecast arrays, with original and compressed hashes in `report-archive.json`.

After extracting the archive into `runs/passive-batch5-original`, run from the repository root:

```sh
uv run --locked --extra id --extra plots python \
  evidence/passive-batch5-20261017/analyze.py \
  --raw-directory runs/passive-batch5-original \
  --output runs/passive-batch5-review-replay
```

The output directory must be new. The script rechecks raw/camera hashes, standard source admission, disabled recordings, existing annotation hashes, and saved-fit numerical reproducibility. It never opens hardware, modifies originals, changes gates, or exports a model. Earlier model reports remain required for the comparison and are committed in their original evidence directories.
