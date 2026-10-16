# Recorded upright shadow demonstration

`visible-upright-source.json.gz` is the unchanged report compressed from the
existing direct, visibly upright stopped capture. Its uncompressed SHA-256 is
`ee030920d5c4a2ddcc9d1dd0b1b214c4bf5b1403a84764b3d36347935d1156ed`.

`recorded-shadow-config.json` anchors magnetic `theta` to its capture mean
0.0014789045545212766 rad and camera **calibrated `theta_rad`** to its capture mean
0.025411013337611914 rad. The separately reported raw image geometry mean was
0.03189767927432337 rad. Subtracting that raw mean from `theta_rad` would mix
coordinate conventions; the camera's existing home offset is
-0.006486665936711519 rad. No firmware or camera calibration is changed here.

The full camera calibration fingerprint is
`c6b106b0595f94032364cebf985f8a8661d36ea044f82fd434fb6561a602e4dc`.
Root checked that the running camera retained this calibration and native
960x600 geometry with rotation 180. Capture rate was benchmarked at 30, 60, and 80 Hz;
detector width 640 is separate from native camera geometry. Physical source
identity and the existing common angular sign convention are operator assertions,
not something established independently by this stationary capture.

`proposed-live-shadow-config.json` is ready for a **stopped, non-control** monitor
against encoder reference 370 and firmware `executor-v4-rehome`. Use a new unique
session ID per monitor process. A different firmware/reference is rejected until
explicitly reviewed and updated with a recomputed encoder-reference fingerprint.
The clock strategy explicitly assumes 22 ms serial receipt delay, declares 25 ms
uncertainty, permits 10 ms receipt residual and expires after 60 seconds. These
are approximate shadow budgets; none certify exposure timing or control validity.

`recorded-shadow-input.jsonl.gz` reconstructs the SDK mirror packet envelope from
original State and INFO and preserves original serial `received_ns`. Camera
snapshots retain original `receipt_s`, host-read `t` and derivative effective
times. Events are sorted by original host receipt. No synthetic sensor values or
reordered acquisition timestamps are introduced. The packet sequence is assigned
for this offline reconstruction because the historical recording predates the
new SDK UDP publisher.

`recorded-shadow-trace.jsonl.gz` and `recorded-shadow-summary.json` show 752 accepted
encoder updates and 50 accepted camera corrections. Six startup outputs are
invalid before the first camera correction; 796 subsequent software observations
are valid. This uses the **same stationary capture to anchor and demonstrate the
bridge**. It is not an independent accuracy test, dynamic calibration, validation
of angular signs, or approval for control. Nonlinear/history-dependent magnetic
error remains unresolved. Every packet is shadow-only and uncommissioned.

Replay without serial/network access:

```sh
python examples/sensing_shadow.py \
  --config evidence/phase3/retuning-20261015/sensing/recorded-shadow-config.json \
  --replay evidence/phase3/retuning-20261015/sensing/recorded-shadow-input.jsonl.gz \
  --output /tmp/cartpole-shadow-replayed.jsonl
```


## Actual stopped live verification

The single-owner mirror check published 3,443 packets in 20 seconds without
publisher errors or drops. All 414 sampled HTTP snapshots retained the correct
session and reference 370 metadata. After closing the Rig owner, the viewer
reported the encoder stale while vision continued.

The first latest-only HTTP shadow test failed: 452 camera frames could not find a
valid 30 ms encoder bracket. This failure is retained in
`live-shadow-latest-only-failure.json`. The monitor now retrieves bounded dense
encoder history incrementally and defers a camera update until real samples
bracket its timestamp. It does not extend the interpolation gap or extrapolate.
The repeated 25-second real-CLI test accepted 425 corrections, with 425 tracking
outputs and three startup-unavailable outputs, no history truncations, and no
pending queue drops. Viewer SDK and encoder status became stale after the owner
and monitor exited.

`live-shadow-batch-summary.json` records the result and final stopped, healthy,
homed state. The board remained executor-v4-rehome, raw reference 370, home epoch
1, x = 0, with both cart switch interlocks enabled. No motion or calibration
command was used. The approximately 0.118 rad hanging correction observed in
this run is an estimator output, not a validated calibration offset. No reference
was saved from this trial, and the observer remains uncommissioned and ineligible
for control.

The unchanged capture is preserved in `live-shadow-batch-capture.jsonl.gz`. It
predates a diagnostic naming fix separating original camera receipt from deferred
correction availability. Replaying it with the corrected implementation reproduces
425 accepted corrections, three rejected corrections, and the same final bias
within floating-point rounding. The diagnostic timestamp fields now distinguish
receipt and availability; the trace is therefore not byte-identical. Replay emits
one observation per input event, while the live monitor emits one per polling
cycle, so their observation counts differ. All replay observations remain
uncommissioned and ineligible for control. `live-shadow-batch-replay-check.json`
records the semantic comparison and source hash.


## Persistent stream follow-up

The later 25-second stopped test used the maintained `/api/sensing-stream`
transport and accepted 903 camera corrections (13 rejected), versus 593 accepted
with measurement-only HTTP polling. Post-warmup mean tracking rose from 28.488 to
38.235 FPS; stream camera capture averaged 75.320 FPS and encoded video 40.008 FPS.
The native 960×600 / rotation-180 profile requested 80 FPS capture, detector width
640, and 40 FPS video at 3000 kbps with one visible smooth-camera browser client.
The two runs provide 22 and 23 post-warmup service samples respectively.

No SDK encoder history truncation or pending-camera drop occurred. The final rig
was disabled/stopped at home, flags 205, reference 370. SDK and encoder feeds aged
to stale after close. Replay reproduces final diagnostics and final observation
values/timestamps exactly; only the observation sequence differs (917 live,
2748 replay) because replay emits after each recorded input event.

The durable measured summary and capture live in
`evidence/phase4/vision-service-20261015/`: see
`live-shadow-stream-performance.json`, `live-shadow-stream-summary.json`,
`live-shadow-stream-capture.jsonl.gz`, and `live-shadow-stream-replay-check.json`.
`monitor-http-performance-analysis.json` preserves the earlier full-state HTTP
baseline separately from this newer measurement-only HTTP/stream comparison.
This short stationary transport check does not resolve nonlinear magnetic error,
certify exposure timing, or authorize fused observations for control.
