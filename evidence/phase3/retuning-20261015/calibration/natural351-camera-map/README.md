# Natural-upright 351: camera-relative map feasibility

The user-selected natural resting upright is the working reference. This analysis
uses that choice directly; a gravity/metrology calibration is not a prerequisite.
Camera geometry changed before this second assisted capture, so no prior camera
anchor is reused. No production model, reference, timing gate, or controller was
changed by this analysis.

## Result

A simple empirical correction transfers to the later two ABBA trials, but a fixed
angle-only map does not reconcile the stationary working upright with the dynamic
measurements. It is useful as an offline diagnostic, not a promoted correction.

| Frozen model | Training RMS / p95 absolute error | Heldout RMS / p95 absolute error |
| --- | ---: | ---: |
| Raw angle, fitted effective timing only | 7.20° / 13.64° | 7.45° / 12.92° |
| Constant offset | 3.99° / 8.16° | 3.65° / 8.00° |
| Two harmonics constrained to preserve upright zero | 4.16° / 7.79° | 4.42° / 8.17° |
| Constant plus two harmonics | 3.14° / 6.23° | 3.38° / 6.86° |
| Upright-preserving harmonics plus rate-sign term | 4.04° / 7.23° | 4.42° / 8.42° |

The best dynamic fit has a **+4.076° intercept at native angle zero**, whereas the
passive working upright defines zero. Native angles within ±5° of upright have
median camera-minus-encoder differences of 4.12°, 2.56°, 6.57°, and 5.68° in
chronological ABBA order (14, 14, 4, and 15 samples respectively). The third run's
small near-upright sample count matters. The constant-only correction is +5.896°;
its larger error shows some reproducible angle structure, but the shape model's
heldout advantage is modest: 3.65° to 3.38° RMS.

Before the four runs, settled native raw medians are 2318, 2297, 2298, 2305 while
current-camera angles relative to upright are 180.034°, 180.522°, 180.477°,
180.411°. The first-to-second resting encoder/camera difference changes by about
2.33°. This and the passive/dynamic inconsistency argue against one permanent
scalar offset. They do not establish a unique cause: encoder/mechanical history,
angle-dependent camera geometry, dynamic tracking error, and varying acquisition
latency can all contribute.

## Anchor and time semantics

The camera anchor is the median theta in the final ten seconds of the second
assisted capture, bounded by the last native host receipt:
`[187638.719224778, 187648.719224778]` host-monotonic seconds. It is
**-0.009445365634260372 rad (-0.5411795868010273°)**. There are 421 valid camera
frames and 2361 native states; native raw min/median/max is 350/351/352. Camera
relative 5th/95th percentiles are -0.231°/+0.341°, with full range
-0.833°/+2.343°. These are observed dispersion, not confidence bounds or an
independence claim. No square-root-of-N uncertainty reduction is used.

The direct reference write subsequently changed native upright from 370 to 351.
For this analysis, native theta is the unfiltered STATE theta under reference351.
Current camera angle is computed from raw marker geometry:

```
image_down = atan2(bob_x - pivot_x, bob_y - pivot_y)
camera_working = wrap(pi - image_down + old_service_home_angle - new_anchor)
old_service_home_angle = -0.006486665936711519
```

The old service home angle is retained solely to reproduce its theta convention;
subtracting the new anchor removes that old zero. The new camera frame is anchored
to the second capture, not to the old geometry or a claimed gravity truth.

Each native board clock is mapped to host time using that run's first percentile
of `(serial_received_s - unwrapped_board_us / 1e6)`. The comparison interpolates
unwrapped native theta at `(camera_host_read_t - effective_lag)` and wraps the
result. It uses only actual neighboring states with gaps at most30ms; it does
not resample telemetry or extrapolate. Camera receipt is retained separately.
The empirical best effective lag is 19–21ms, consistent across leave-one-training-
run-out fits. It absorbs unknown camera capture/read and serial timing effects:
**it is not an exposure timestamp calibration or a change to SDK clock gates**.
The same first-percentile clock-mapping rule is applied independently to each
heldout session; model coefficients and effective lag are never refitted there.

A ±5ms timing perturbation with the best shape coefficients held fixed changes
training RMS from3.14° to4.01° or3.66°; ±10ms gives5.60° or5.04°. Timing therefore
remains material. Serial receipt outliers reach18–23ms above the lower envelope
in the training logs. This offline aggregate mapping does not invalidate the
separate online SDK residual failure or certify online alignment.

## Fit and heldout discipline

Only the first eight seconds after each report's motion-start receipt are used.
Training runs are auto45a then auto60a. Later auto60b and auto45b are held out.
The passive upright provides only the coordinate anchor. The initial balance
trial is not a fitting input. Reported metrics are ordinary sample-level circular
RMS/quantiles, not uncertainty intervals.

Admission requires detected marker pairs, confidence at least0.8, apparent arm
length115–155px, healthy neighboring native states, and a native bracket gap no
larger than30ms. These are explicit exploratory analysis filters, not production
threshold changes. Training has185 admitted pairs (93+92); heldout has181 (84+97
in acquisition order). Model fitting uses a 5° Huber objective, and a shared
-80..120ms lag grid in1ms steps. Models use constant and/or the basis
`sin(theta), 1-cos(theta), sin(2theta), 1-cos(2theta)`; the constrained versions
omit the constant. Residuals are wrapped. No residual observations are discarded
from reported validation metrics.

All coefficients were frozen before heldout contents were opened. The original
training-fit JSON SHA256 is
`d88f35559693208ac9451dbc0c257490c7152d265b4f65a8ec77c4100000c0ad`.
`frozen-training.json` and `heldout-evaluation.json` retain complete coefficients,
lag conventions, metrics, and source hashes. `manifest.json` records lossless
preserved inputs.

## Camera quality and practical next step

Camera snapshots were collected only about14Hz despite the faster detector.
Active-window detection coverage is83.0%,86.2%,75.4%,85.8% in ABBA order. Some
30° angle bins have only one or two observations, so a detailed full-turn lookup
table is unsupported. Several detected arm lengths are implausibly short/long.
A stricter125–145px/confidence0.85 sensitivity check does not improve residuals,
so those obvious quality outliers do not explain the whole discrepancy. The
camera logs omit full per-frame calibration/angle-valid/status fields; source
seq/t are unique and receipt ages are recorded, but this is a lighter provenance
contract than the SDK stream. Preserved passive source includes full calibration
and frame geometry. Native health is valid throughout heldout logs.

The already-started high-rate source stream is the bounded next measurement:
retain current natural-upright reference351 and geometry, capture dense source
camera timing/quality with native ticks, and examine innovations by angle, rate,
and direction on an untouched subsequent segment. No extra full-angle model or
new reference operation is needed to proceed with practical tuning. A bounded
camera-relative bias observer is a reasonable candidate to test in shadow; these
results do not show that bias is always slow enough, nor distinguish sensor
history from image geometry. Preserve source freshness, calibration identity,
innovation/dropout gates, and original measurement timestamps. Do not promote
this offline fit into control or reuse the old reference370 SDK configuration.

Source integrity validation found repeated native board ticks in three logs
(6, 5, and 2 duplicates). All repeat the identical unfiltered theta; most occur
during startup, with one6ms after motion start. Removing these duplicates with
the frozen time map changes every compared angle by exactly zero. There are no
board-time rollbacks, all source health/fault checks pass, serial receipts
increase, and camera sequences/timestamps are unique/increasing. Duplicate
native packets are not treated as independent calibration observations.
