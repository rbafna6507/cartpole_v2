# Read-only camera measurement review — 2026-10-17

The first preflight JPEG does not reproduce an arm detection failure offline. Current maintained `ArmDetector` accepts it at both 640 and 960 processing widths. Runtime reports supplied by the primary show intermittent raw-geometry loss, not total loss: approximately 84% recent coverage, 23/155 frames with `no reliable arm geometry`, otherwise stable raw pivot/bob detections. Calibration fields are null; this makes metric/zeroed fields invalid but does not cause raw detector rejection.

The fresh image still has the intended green shaft with a wider circular weighted end and dark pivot screw. The detector is designed for this connected silhouette, not two disconnected fiducials. Broad green color alone is not a shape mismatch.

At 640 processing width the saved preflight JPEG yields native-image pivot (501.325,203.425), bob (496.929,380.710), length177.339px, image angle−0.0247906rad and heuristic confidence0.901871. Its geometric margins are healthy: shaft support30/30, circular rim residual/radius0.0103 versus0.12 allowed, end counts740/433 versus1.15 asymmetry required, one pivot candidate. These are observations on this JPEG, not measurements of a rejected raw frame.

`PreviewWorker` publishes a 1Hz quality80 annotated JPEG from a source tuple. A preview can show a prior lost frame while current state already detects; JPEG compression can also change segmentation and dark-hole pixels. The overlay and a separate `/api/state` response must not be assumed to describe the same frame. `/snapshot.png` is lossless raw image content, but its endpoint supplies no source sequence/timestamp header. State reads bracketing a snapshot provide a source interval only.

## Physical camera movement supersedes the first view

The primary then reported camera movement between trials. Visual inspection of `/tmp/cartpole-id-20261017-data/after-negative.jpg` confirms a major different viewpoint: pole far left, left rail clipped and rail tilted. Primary state reports pivot about(132,153), length about200px, versus(501,203),177px in preflight. Absolute pixels, ROI coordinates and any earlier scale cannot be compared across these views. The maintained calibration check detects dimensions/software rotation changes, not physical camera pose changes. No detector tuning can resolve that coordinate-frame mismatch.

Treat each fixed camera pose as a separate measurement session. A physically fixed, adequate field of view and visible stationary rail landmarks are needed before quantitative cart comparisons. Prefer invalidating a moved-camera interval over fitting a camera motion correction from the cart trace. No camera/service/calibration change was made by this reviewer.

## Precise next diagnostic

Use a small saved sequence from the existing service's `/snapshot.png`, with before/after `/api/state` brackets, preserving raw image hashes and source sequence intervals. Do not open another capture device. Run `/tmp/cartpole-python-id-20261016/diagnose_camera_frames.py` locally on the PNGs. It traces current production detector rejection gates at640/960, records selected geometric margins and source hashes, and verifies identical output with tracing disabled. It does not modify thresholds, camera settings or code. Initial JPEG results are in `preflight-camera-gates.json`.

Classify actual loss by contour eligibility, elongation, end ambiguity, rim fit, pivot-hole eligibility, rigid-shaft support or width limits. Record gate margins alongside success/failure; do not broadly relax thresholds based on visible pole presence. Current generic runtime status does not expose those internal reasons. Evaluate lighting/exposure only after raw loss fixtures identify the failing geometry; reported gain168/exposure5 does not establish the actual automatic shutter time.

## Independent cart pixel recovery

1. Existing `pivot_px` and `cart_pivot_px` already provide raw camera cart position on accepted arm frames even when `cart_valid=false`. The latter requires metric cart anchors. For a bounded same-view pilot, compare settled-window medians with timestamp interval, spread, coverage and longest gap. Preserve missing frames; do not differentiate sparse pixels as if uniformly sampled or infer pixel scale from commanded steps.
2. Existing `CartTemplate` can follow one fixed textured rigid-carriage patch without requiring the full arm silhouette. It uses unchanged correlation>=0.80, best-versus-second margin>=0.06, bounded vertical search and no self-updating template. The patch must exclude the rotating green shaft/bob, stationary rail/belt/idlers and background. Runtime template selection needs one accepted arm pose to anchor its offset; later missing-arm frames can retain raw cart pixels without metric calibration.
3. For source-consistent offline ID, track that same fixed template separately on saved raw frames and retain score, ambiguity margin and measured point for every frame. `Engine` currently prefers the accepted arm pivot, so its combined `cart_pivot_px` can switch between arm and template sources. Do not hide those source changes in a physical derivative estimate. Validate two distinct rigid-carriage patches against each other and verify stationary rail landmarks to detect camera motion.
4. In the now-superseded first JPEG, gray side patches (476,215,18,28) and(511,212,17,32) had texture std38/48 and initial best-second margins0.220/0.174. Matching the selection image to itself proves only acquisition uniqueness, not motion robustness. These coordinates must not be used after camera movement.
5. A metric cart measurement additionally needs independently measured physical separation, fixed camera pose, sufficient pixel baseline and a held-out position check. Counted/commanded step displacement is not independent camera-scale calibration. Camera host-read timestamps remain separate from sensor exposure and board acquisition clocks.

No edits to maintained vision source, archived vision3, service, detector thresholds or calibration. No SSH, serial or hardware commands were issued by this review.

## Complete raw samples inspected

The primary stopped an incomplete archive transfer. Only the completely extracted `camera-partial/03.png` and `04.png` were inspected; their accompanying 03/04 state brackets were not available, so there is no exact frame-state or inter-frame timing claim. The incomplete archive must not be treated as a complete dataset or committed evidence.

Both PNGs are in the original preflight view and both pass unchanged detector gates at640 and960. At640, native-image pivot moves from(500.758,202.914) to(500.798,202.758), with length177.439→177.496px. Each has30/30 shaft support, one pivot candidate and circle residual/radius approximately0.016 against the0.12 rejection limit. Thus the two available raw samples do not reproduce the sporadic rejection, and no particular failing gate can be responsibly named yet.

Fixed gray-side templates selected on03 also accept04: left score0.992665/margin0.237123; right score0.996174/margin0.174270. The measured changes are about0.02–0.05px. This supports static acquisition only in the superseded first view; it does not establish motion tracking, calibration or high-rate coverage. Reports: `raw-camera-gates-20261017.json` and `raw-camera-template-check-20261017.json` beside this audit.

The primary supplied `reframed.jpg` after restoring a fixed full-rail view. It is a third camera pose, visually inspected, and must have its own template/reference identity. No templates or calibration were applied. Current conclusion remains: intermittent runtime geometry loss is real but not reproduced in these two raw samples; capture an actual raw rejection before choosing a detector fix. For ID now, preserve valid raw pivot pixels and missing intervals within one fixed camera pose, and restrict claims to measured pixel displacement until independent metric/timing validation exists.
