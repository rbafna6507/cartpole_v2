# Four stopped/resting micro-motion screens, 2026-10-15

Four bounded cart excursions completed: positive1, negative1b, positive2, and
negative2. The earlier negative1 attempt aborted during baseline on the separate
shadow clock-residual guard, before motion. Raw files, configurations and
summaries are preserved under `captures/`; JSONL compression is lossless and
`manifest.json` retains original and saved hashes. `analysis.json` gives complete
metrics and source hashes. No hardware or production code was touched by analysis.

## Resting-window repeatability

Each baseline/after window covers approximately five seconds. All recorded native
states in these eight windows are healthy, disabled and at counted x=0, with
unique ordered source ticks. Every window spans at most one native count; all
first/last-quarter raw medians have zero drift. Camera first/last-quarter image
angle median drift is at most0.014 degrees. Nonetheless, settled encoder means
move between windows and stay at their new levels until the next excursion.

| Cart excursion | Raw mean before → after | Encoder change ° | Aligned camera change ° | Change in encoder minus camera ° |
| --- | ---: | ---: | ---: | ---: |
| positive1 | 2333.935 → 2328.210 | -0.5031 | -0.0535 | -0.4496 |
| negative1b | 2328.295 → 2325.612 | -0.2358 | +0.1666 | -0.4024 |
| positive2 | 2325.648 → 2321.765 | -0.3413 | -0.2684 | -0.0729 |
| negative2 | 2321.791 → 2325.000 | +0.2821 | +0.3007 | -0.0187 |

The camera sign is explicit: image-down angle is atan2(bob_x-pivot_x,
bob_y-pivot_y), and aligned vision change is its negative. Camera calibration
is unchanged across the captures. Adjacent completed after→next-baseline means
differ by only0.026–0.085 encoder counts; the aborted baseline also retained the
post-positive1 level. Recorded settling spans are0.848–0.888 seconds, followed
by stable five-second windows. This supports changes associated with excursion
and settling history rather than continued drift within the recorded rest.
It does not identify which mechanical or sensing component caused the changes.

From the first baseline to the final resting window, the encoder changes
-8.9349counts (-0.78525°), while aligned camera changes +0.14167°. The relative
encoder-minus-camera change is **-0.92691°**. Removing250ms from both ends of
common host-time overlap changes it only to -0.92543°. The overlap check uses
serial host receipt and camera host-read proxies; it is not a new clock mapping
or a dynamic sensor-alignment claim.

## Dispersion and physical uncertainty

No standard error, square-root-of-N reduction, or independent-sample assumption
is used. Each source retains its full observed range. Independent extrema give
this conservative initial-to-final observed difference envelope:
**[-1.26639°, -0.58427°]**. Adding ±one encoder count for the two half-count
quantization terms widens it to **[-1.35428°, -0.49638°]**. These are empirical
sample envelopes, not independently calibrated physical error bounds. Unknown
camera systematic error, out-of-plane pose, fixture alignment and physical
reference uncertainty remain outside them. Each individual excursion's full
extrema envelope includes zero; the cumulative comparison is stronger than a
claim that each separate excursion proves a sensor error.

Counted home is exactly x=0 in every resting state and final report. The eight
resting-window mean image pivots span only0.1983px horizontally and0.0784px
vertically. This corroborates repeatability in the recorded views, but the
camera cart-position channel is uncalibrated: no submillimeter physical-home
accuracy can be inferred. Native reference370, configuration768 and home epoch1
remain unchanged; initial/final I2C error and recovery counts remain zero.

positive2 explicitly reports invalid shadow fusion after its receipt residual
failure. Its raw native/camera data remain available and are analyzed separately.
positive1 predates the `shadow_valid` report field, but its successful summary
contains no source errors. The aborted negative1 is retained and excluded from
before/after comparisons.

## Consequences for the next upright capture

A stable window by itself is insufficient evidence for a stable hanging-to-upright
offset. Capture a new physically supported upright window and a new hanging
window for every eligible pair, with independently justified physical-reference
uncertainty. Keep reference370 unchanged while collecting. Preserve an extra
post-movement hanging window as a repeatability check; do not reuse one upright
as multiple training pairs. Bracket and record the full approach/settling history
so shifts before and after the upright movement remain visible.

The positive/negative labels here denote **cart excursion direction**, not the
monotonic raw-count approach direction required by CalibrationProfile. All these
rest windows are hanging observations, so this dataset supplies zero eligible
upright/hanging calibration pairs. It neither validates nor conclusively rejects
a paired scalar-offset model without fresh upright measurements. Do not derive
an offset from an old upright370 and an average of these different hanging
states, and do not convert the new upright capture into a reference write or
control-commissioning claim.
