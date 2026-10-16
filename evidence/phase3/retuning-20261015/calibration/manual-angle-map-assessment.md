# Slow manual angle-map assessment, 2026-10-15

The recorded camera/encoder relationship is strongly angle dependent and changes with history or operating state. A constant zero correction cannot reconcile the evidence. The cart drift in automatic trials is physical (camera tracks step position), while the pole-angle measurement chain is not yet sufficiently characterized for a global encoder correction. Direct reference370 was preserved throughout. This analysis made no hardware, network, parameter, or production edits.

## Most discriminating measurements

- In the separately recorded visible stationary upright, raw camera mean is+.031898rad and encoder mean+.001479rad: difference+.030419rad. The raw image is visibly near upright; reference370 was retained.
- Prior stopped hanging poses give camera-minus-encoder+.195–.213rad. Relative to the stationary upright this is an additional+.165–.182rad (9.5–10.4deg), independent of constant image roll or a constant encoder-zero shift.
- In the slow manual turn with motor disabled, near-up disagreement averages+.00469rad (60 moving samples with |encoder angle|<.15rad), while bins near encoder−1.83rad average+.277rad. Changing assumed camera lag by±50ms changes the near-up mean only to+.00135–.00858rad, so latency cannot explain the overall shape.
- Initially versus finally stopped down: encoder changes+.04303rad, while raw camera changes−.00558rad. The encoder-minus-camera differential is+.04861rad (2.79deg). Camera scatter within the two long rests is about.003rad, much smaller than this differential. This supports history-dependent disagreement, but does not isolate sensor nonlinearity, shaft/linkage motion, marker geometry, or true mechanical hysteresis.

## What the actual record covers

`manual-angle-map-compact.json.gz` contains120seconds,7490 decimated telemetry states (~62.5Hz) and1896 usable camera poses (~15Hz). All states remain disabled, mode0, x0. Reference370 is identical at start and end; no faults/misses are reported.

The useful manual motion occurs around40–74seconds. Both encoder and camera unwrap show one complete negative traversal (encoder net−6.240rad), with small local reversals. There is no complete opposite-direction traversal. The user's requested two-direction experiment is therefore not fully represented in this saved record, and direction-heldout validation is unavailable.

A descriptive first/second-harmonic map reduces moving-data residual RMS from.1064rad (constant) to.0324rad. This is not a validated correction: it is fitted to one traversal, cannot explain the same-pose return discrepancy, and does not transfer cleanly to automatic near-upright balance, whose camera-minus-encoder mean is+.127–.144rad. Do not install its coefficients as a calibration table.

## Camera geometry and timing checks

The slow-turn raw bob-minus-pivot path fits a centered ellipse with radii166.74/164.50pixels (axis ratio1.01363), center[.89,1.71]pixels relative to the red marker, and normalized radial RMS.00859. This is a clean, nearly circular trajectory. Under weak perspective, it argues against the very large image shear or20–30pixel fixed marker displacement needed to explain.13–.20rad angular discrepancies. Exact projective calibration and physical marker-center placement remain assumptions; the fitted center is not a metrology uncertainty bound.

Independent horizontal crossings from the automatic batch give positive rail-relative-minus-encoder disagreement:73 crossings, median+.123rad. Raw cart-track normal is only+.012–.015rad from image vertical. Timing fitted on early swing gives camera read-time minus21.5–24.7ms. Stopped disagreement remains while motion is negligible, which rules out frame rate/latency as the sole cause.

Camera orientation always comes from raw bob/pivot coordinates, ignoring stored vision theta/rate. The visible stationary upright now provides a useful local camera zero anchor; it does not by itself establish full-angle geometry or validate global camera/encoder fusion. Camera sampling cannot resolve the10–20ms encoder chatter seen during automatic control.

## Practical conclusion

Preserve370 and diagnose the angle-transfer/mechanical chain before treating native gain sweeps as plant-model tests. The strongest remaining discriminators are repeated opposite-direction slow traversal with stationary stops at common camera poses, and a comparison of identical supported poses before/after manipulation. Independent inspection of the magnet's centering/gap and the rigidity of shaft-to-pole coupling would help distinguish magnetic transfer error from linkage slip. These are recommendations for the parent operator, not actions performed here.

Near-upright vision can provide an independent angle observation after using the visible upright as its reference and accounting for latency/quality. A global static encoder map or uncalibrated DC averaging would conceal unresolved state-dependent disagreement. A separate comparison at matched physical poses and matched motor/fixture state is needed to establish why automatic near-up disagreement is larger than the slow/stationary observations.

## Evidence and reproduction

Run `python3 /tmp/cartpole-retune-20261015/analyze_manual_angle_map.py`; its JSON retains synchronized camera/encoder pairs, bins, lag sensitivity, static-window statistics and fitted geometry. Run `MPLCONFIGDIR=/tmp/cartpole-retune-20261015/mpl-cache python3 /tmp/cartpole-retune-20261015/plot_manual_angle_map.py` for the figure. Sources/generators are hashed in `manual-angle-map-provenance.json`.

- `manual-angle-map-analysis.json`, `manual-angle-map-analysis.png`, `manual-angle-map-analysis-output.txt`
- `visible-upright-independent-check.json`
- Earlier independent checks: `upright370-camera-comparison.json`, `upright370-horizontal-geometry.json`, `upright370-rail-and-rest.json`, `upright370-camera-geometry.png`

The old270-reference tuning/zero interpretations remain superseded. The independent encoder/camera full-cycle period result~.825seconds remains useful because constant zero does not affect cycle duration; its equivalent-length interpretation retains the friction/perspective/amplitude caveats already documented.
