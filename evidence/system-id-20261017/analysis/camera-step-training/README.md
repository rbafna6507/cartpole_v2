# Camera pixels versus counted cart motion

Four completed training runs only: signed10mm and20mm pulses. Reserved validation data were not read. Direct Rig STATE x/received_ns and raw vision.t/pivot_px are used; mirrored encoder, filtered cart/angle fields and old camera calibration are ignored. Raw decompressed and file hashes, completion report hashes and script hash are retained in analysis.json.

The visible pivot follows the counted pulse shapes in both directions. This is descriptive agreement in pixels, not independent metric cart gain, calibrated latency, or proof of no slip. Camera pose is not independently verified by a fixed background landmark in these recordings.

| Run | Zero proxy lag gain (px per counted m) | Zero proxy lag RMS (px) | Best same-run lag (ms) | Best-lag RMS (px) | Apparent return offset (px) | Pulse valid geometry |
|---|---:|---:|---:|---:|---:|---:|
| +10mm |1015.27|0.543|15|0.191|−0.109|100%|
| −10mm |995.92|0.513|15|0.153|0.000|94.3%|
| +20mm |985.56|1.039|20|0.212|0.000|100%|
| −20mm |998.17|0.941|15|0.174|−0.373|95.1%|

The zero-lag gain mean is998.73px/count-m, standard deviation10.67px/count-m (about1.1%). These are four different sign/amplitude conditions, not repeated trials under each condition; this measures cross-run consistency rather than statistical repeatability. Per-run pre-pulse baseline x spans506.08–506.59px. Counted final-minus-initial median x is0 for all four runs. The −20mm final hold window has only83.6% valid delivered geometry, with an88ms longest valid-frame gap; its return estimate needs that qualification.

Each run fits an affine board-snapshot→host-receipt proxy using its own direct STATE timestamps. Receipt residual P95 values are0.41,0.40,3.51,0.46ms in table order; short-run fitted slope includes receipt jitter/trend and is not an independently measured oscillator rate. Camera t is host read rather than exposure time. The reported15–20ms lag minimizes residual on these same samples and conflates timing proxies, camera pipeline, physical/count differences and detector error. It is not calibrated sensor or actuator latency.

Shape regression uses the fixed interval−0.1..1.1s around pulse start. Lag sensitivity is−100..100ms in5ms steps, always using identical common camera support. Missing camera points are never filled; counted x is linearly interpolated only between adjacent board snapshots separated by≤30ms. Baseline is−0.25..−0.05s; return is the last1s of the3s feedback hold. Geometry coverage means valid raw pivots among delivered unique camera frames, not coverage relative to a nominal camera rate.

Reproduce from the repository root, choosing a new output directory:

```sh
uv run --script evidence/system-id-20261017/tools/analyze_camera_step_pulses.py \
  --same-host-clocks \
  --run evidence/system-id-20261017/raw-pulse-training/pulse-pos10-short-01 \
  --run evidence/system-id-20261017/raw-pulse-training/pulse-neg10-short-01 \
  --run evidence/system-id-20261017/raw-pulse-training/pulse-pos20-short-01 \
  --run evidence/system-id-20261017/raw-pulse-training/pulse-neg20-short-01 \
  --output /tmp/camera-step-new
```

The same-host assertion is required: all vision.t and direct Rig received_ns must originate from one monotonic host clock. Use absolute script/run paths from another directory. --no-plot needs NumPy only. There are no hardware or network operations in the script. Its optional uv launcher can install the declared plotting dependencies; use an existing environment or offline cache when working offline.

Seven synthetic tests cover affine clock recovery, signed gain/known lag, equal-support lag comparisons, no gap bridging/extrapolation, raw-only camera use and missing geometry, plain/gzip source hash binding, and immutable JSON output with explicit same-host assertion. The production SDK, calibration, firmware and controller gains were not changed. This analysis does not alter the training/validation fit or promote a model.
