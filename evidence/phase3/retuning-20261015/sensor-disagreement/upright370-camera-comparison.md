# Raw camera / encoder geometry comparison at direct reference370

> **Latest conclusion:** The completed slow manual-turn record establishes strong angle-dependent disagreement while disabled, plus a+.04861rad encoder-versus-camera change between nearly matched stopped-down poses. Only one full direction was recorded, so no global calibration was accepted. See `manual-angle-map-assessment.md` for the current result; the preceding constant-reference preference is superseded.

> **Update: visible stationary upright now available.** `visible-upright-report.json` independently verifies50 raw camera frames, camera mean+.031898rad (std.002587), and752 encoder states with mean+.001479rad/range.003068. Reference370 remained unchanged. Camera-minus-encoder is therefore+.030419rad at stationary upright, versus+.195–.213rad at prior stationary hanging poses: a differential+.165–.182rad. This supersedes the earlier preference below for a constant reference/held-pose discrepancy. A constant zero/roll adjustment cannot reconcile both stationary poses. Sensor transfer, linkage, geometry or state dependence must be investigated; the pending release trace is the next evidence.

The rightward cart drift is physical. Raw camera pivot displacement agrees with emitted step position (correlation.9993–.9999 over the first seven corrected-reference runs). The angular sensors also have a substantial repeatable disagreement. No encoder reference, controller parameter, production file or hardware state was changed.

| Check | Result |
|---|---|
| Camera read-time relative lag | Encoder best matches camera orientation at camera timestamp minus21.5–24.7ms |
| Raw camera minus encoder during balance | +.127–.144rad (7.3–8.3deg) |
| Image cart-track normal relative to image vertical | +.012–.015rad (~.7–.9deg), robust line fits |
| Stopped pretrial camera minus encoder after track-normal subtraction | +.181–.200rad (10.4–11.5deg) |
| Horizontal pole crossings | 73 crossings; pooled median target±π/2 minus encoder +.123rad (7.0deg) |
| Horizontal-crossing empirical5–95% spread | .084–.277rad; this is spread, not a calibrated confidence interval |
| Fitted ellipse center relative to red pivot marker | .3–3.0px displacement, radii156–166px |
| Free-ellipse axis ratio | At most1.043 across seven runs |

## What the timing and angle fits establish

Camera orientation is recomputed solely as `atan2(bob_x-pivot_x,pivot_y-bob_y)`. Stored vision theta/rate is ignored. Board time is linearly mapped to the host clock, then camera latency is fitted on the first6seconds of swing and frozen for later swing/all balance. A per-run constant plus first/second angular harmonics describes possible angular disagreement, but the extra terms barely help heldout swing: pooled RMS .06656rad for a constant versus .06601rad for periodic terms (292 samples). Do not use these empirical harmonics as an encoder calibration.

Stopped initial poses are particularly useful. Raw camera orientation varies by only.00035–.00082rad across10–13 images, while encoder/camera disagreement is about.20rad before the small track-normal correction. Run5 maximum initial |omega| was.00856rad/s, so22ms timing error contributes less than.0002rad. Frame rate/lag cannot explain this static discrepancy. Retained camera samples are typically15Hz and have gaps; they cannot adjudicate10–20ms encoder chatter.

## Geometry discrimination

Image vertical alone is not gravity vertical. Oblique projection can keep the rail nearly horizontal while skewing the projected physical vertical; rail-normal correction alone does not rule this out. Horizontal pole crossings are stronger: if the red marker is the true hinge, the blue marker lies on the pole axis, and the pole moves in the cart/pendulum plane, a horizontal pole has its bob on the hinge's projected cart-track line regardless of camera roll/perspective. The corresponding encoder angle should be±π/2 relative to rail-normal upright. All73 observed residuals are positive. Direction-group medians are+.116 and+.139rad; within-run medians are+.101–.158rad. Linear-versus-local-cubic crossing interpolation changes the absolute angle by median.012rad and95th-percentile.019rad on22 eligible brackets. High-speed telemetry/camera noise still gives substantial scatter.

The free ellipse fits use only raw bob-minus-pivot pixel coordinates, with no encoder angle. Under weak perspective the inferred fixed pivot-marker error contributes at most roughly.002–.019rad. Explaining.13–.20rad solely through fixed marker displacement would require roughly21–32pixels over a160pixel radius, far above the fitted.3–3pixels. Near-circular ellipses also argue against large affine foreshortening/shear. These are conditional geometric diagnostics, not calibrated bounds: projective center displacement, out-of-plane motion, marker detector errors and camera geometry remain possible.

Before the newly visible stationary upright, the evidence favored a reference/held-pose discrepancy over timing or gross fixed marker displacement; that preference is now superseded by the update at the top. It does not identify a validated gravity-zero correction. Reference370 remains unchanged. A stationary visible pole aligned to an independently known vertical (or a level-verified rail normal), with simultaneous raw encoder and marker coordinates, is the next decisive observation. A hand-held pose called upright without an external vertical reference cannot resolve lean versus calibration.

## Reproduce and inspect

Run `python3 /tmp/cartpole-retune-20261015/upright_camera_compare.py`, then `python3 /tmp/cartpole-retune-20261015/upright_horizontal_geometry.py`, then the plotting script with `MPLCONFIGDIR=/tmp/cartpole-retune-20261015/mpl-cache`. Sources and generators are hashed in `upright370-camera-provenance.json`. Numerical results are in `upright370-camera-comparison.json`, `upright370-horizontal-geometry.json`, and `upright370-rail-and-rest.json`; the latter records stationary pretrial measurements. Raw camera files cover all12runs; matching full telemetry available locally covers runs1–7, which are the analysis population here.

`upright370-camera-geometry.png` shows stationary/near-up disagreement, the fitted marker-relative ellipse, and individual horizontal crossings. DC camera fusion must wait for common reference/extrinsic calibration; relative-motion checks can still inform diagnostics without writing a new zero.
