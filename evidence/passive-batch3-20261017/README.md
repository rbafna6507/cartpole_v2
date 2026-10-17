# Passive batch 3: completed training, interrupted validation

The six requested training releases were recorded successfully. The 180-second capture plus preflight/baseline contains 182.118 seconds of board data, 45,560 STATE records, and 8,871 camera frames. No logger records were lost. The encoder snapshot gap is at most 4 ms. Capture ended normally at its requested duration and confirmed STOP. The firmware's large cumulative `dropped` counter is distinct from the host logger's `records_dropped`; it is not a count of records lost in this file.

Validation contains five releases and stops at 100.605 seconds of board data, before the final right-side horizontal release. The camera repeated one source frame until its reported age reached 223.36 ms and flagged it stale. The collector preserved that failing packet and stopped. Its original report remains incomplete; the standard loader rejects it. STOP replies, disabled final telemetry and clean logger termination exist in the raw log, but the failed completion report does not claim `stop_confirmed`. No KeyboardInterrupt recovery or other admission override was applied.

A subsequent read-only camera health check found advancing frames, no reported read failures, and about 79 FPS delivery/tracking. The historical stall's underlying cause is not established; the stale packet proves the interruption trigger, not a permanent camera failure. There are also delayed collector receipts near the interruption. No service restart, hardware motion, parameter change or firmware upload occurred for this review.

## Measurement quality

All six training free-motion intervals pass the existing camera consistency and pixel-pivot screens, with about 98.2–99.9% supported time coverage. Relative hanging was measured independently for each sensor. Requested angles remain labels; measured camera poses are approximately 29.9° left, 31.3° right, 62.9° left, 56.7° right, 91.7° left and 90.4° right. Camera geometry is apparent image-plane angle, not absolute physical calibration.

Three pre-release poses fail their separate existing gates:

- Right 30°: encoder 95th-percentile deviation from its median is 2.46°, versus 0.15° for the camera.
- Right 60°: encoder deviation is 3.32°, versus 0.87° for the camera.
- Right horizontal: encoder reads −84.99° relative to hanging; camera reads −90.43°, a 5.44° disagreement.

These statistics use fixed pre-release windows, not a search for a passing subinterval. They show measurement disagreement/variability worth investigating, not proof of which sensor or fixture component is responsible. All six releases remain in the fit. Manual cart restraint and exact hand-clear time are not independently certified; the recordings contain geometry/telemetry, not a replayable movie.

## Historical comparison

The unchanged viscous weak-form fit gives effective length 0.16004 m and angular damping 0.37207/s, compared with 0.16138 m and 0.35141/s in batch 2. These are identified model parameters; the saved controller's `leff` and gains are unchanged.

The new fit predicts the prior batch-2 validation releases with 5.54° short-horizon RMS and 10.64° P95 error. The prior fit scored 5.64° and 10.74° on those same windows. Both exceed the unchanged 4.58° RMS / 8.59° P95 gates. Previous validation has already guided analysis, so reuse is explicitly a **development comparison**, not a fresh holdout.

Conversely, the frozen batch-2 model predicts the new training recording with about 5.04° RMS. This is consistent with a repeated measurement/model mismatch rather than a one-off bad recording. See `analysis/summary.json` for all model/source combinations and per-release short and uninterrupted forecasts.

The historical fit is rejected. No model was exported, no MuJoCo/Gym defaults changed, and no physical tuning parameters changed. Keep this training recording; another identical training batch is not the immediate priority. Investigate the stationary encoder/camera discrepancy and the sensitivity of the existing 11-sample initial-velocity estimate before revising the measurement/model method, then collect a fresh validation set. A repeated validation capture alone would fill missing coverage but would not resolve these existing failures.

## Artifacts and reproduction

- `original-recordings.tar.gz` and `original-manifest.json`: byte-exact originals and verified hashes.
- `training-annotations.json`: six windows frozen from raw encoder/camera traces before fitting/scoring.
- `analysis/training-camera-review/release-overlay.png`: held poses and free-motion sensor comparison.
- `analysis/historical-fit-review/recorded-vs-frozen-ode.png`: new fit on prior validation; development evidence.
- `analysis/old-model-on-new-data/recorded-vs-frozen-ode.png`: frozen prior model on the new recording.
- Generated forecast arrays are losslessly compressed in sibling `report.json.gz` files, with uncompressed hashes in `report-archive.json`.

These orange trajectories use the saved pendulum ODE and are labelled accordingly; they are not MuJoCo trajectories.

The analysis script only reads recordings and writes a new output directory. It never connects to the rig, changes source reports, fits the failed validation run, lowers gates, or exports a model. Run from the repository root after extracting the batch-3 archive into a new directory and restoring the already-reviewed batch-2 recovery sidecars alongside its originals (see the batch-2 README):

```sh
uv run --locked --extra id --extra plots python \
  evidence/passive-batch3-20261017/analyze.py \
  --raw-directory runs/passive-batch3-original \
  --historical-directory runs/passive-batch2-original \
  --output runs/passive-batch3-review-replay
```

Output directories must be new. The script rechecks original raw/camera hashes, standard source admission/rejection, disabled recordings, the historical recovery proofs, and numerical predictions. This review changes evidence and analysis only; the existing collector and simulation code are unchanged.
