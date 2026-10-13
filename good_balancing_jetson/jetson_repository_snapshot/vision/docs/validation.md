# Validation — 2026-10-03

## Final implementation

- 33 automated unittest tests pass: real image fixtures, full synthetic rotation, clutter, ambiguity, reacquisition, cart template conflicts, calibration, angle wrapping, irregular timestamps, velocity effective time, API validation/staleness, video timestamps, replay and asynchronous recording.
- Independent source review found three important issues (fixed with failing-then-passing regressions): selected pivot prevented later cart travel; a conflicting cart template could be reused during occlusion; rejected arm geometry could leak into cart position/calibration. A source switch now also clears cart velocity history.
- Bright live footage exposed open rim gaps around screws and bob holes. Endpoint localization now uses convex support plus a fit to the exposed circular rim. This fixes saved bright/horizontal frame regressions. Original shaft pixels still provide geometric support checks.

## 80 FPS

Requested 960×600@80, AVFoundation, 180° software rotation. Driver accepted width/height/FPS, reported80 FPS and delivered960×600. Buffer-size request was rejected; exposure/gain readback was0 with unknown support/units.

| Measurement | Result |
|---|---:|
| Initial ten-second camera/detector probe, ending camera rate | 79.748 FPS |
| Initial ten-second probe, detected / processed | 780 / 780 |
| Final45-second full app, full-session tracking average | 79.286 FPS |
| Final app, ending camera / tracking rolling rates | 79.740 / 79.728 FPS |
| Final app, detected / processed stationary frames | 3571 / 3571 |
| Final app, skipped camera frames / recorder queue drops | 8 / 0 |
| Final app, median / p95 processing time | 5.362 / 6.091 ms |

Full app included JPEG/mask preview, JSONL logging, browser requests and asynchronous unannotated MJPEG recording. A prior synchronous-recording version averaged67.87FPS and was replaced. The first asynchronous one-minute trial averaged77.54FPS, including transient host slowdowns; this is not hard real-time capture. Logs expose rate degradation instead of hiding it.

Host arrival times do not establish unique exposures, exposure duration, sensor drops or camera-to-control latency. `evidence/final-live-report.json` and `evidence/final-live-states.jsonl` preserve the final full-app result.

## Supplied screen recording

- Original detector, manually re-seeded per decoded frame: **0 / 215** accepted.
- Initial replacement:196/215 accepted, but real live tests exposed inaccurate endpoint localization under rim gaps.
- Final replacement: **186 / 215** accepted. Stricter circular-end geometry rejects more heavily blurred frames. Most failures occur during hand occlusion and the early fast swings. See `evidence/final-swing-replay/contact.jpg`, `overlay.avi`, `summary.json` and `states.jsonl`.
- Source is an approximately12-second variable-rate screen recording of a10FPS preview. This is detection coverage, not angular accuracy or a sensor-rate measurement. No independent ground-truth angles were supplied.

## Additional live motion capture

A60-second unannotated capture contained mostly a stationary arm and swings near the end (approximately±97° image angles). The initial detector accepted4018/4658 processed frames. Reanalysis with final reflection/rim handling accepted **4416/4658 (94.8%)**. These totals include stationary frames and therefore must not be interpreted as swing-only reliability. The retained motion excerpt and timestamps are in `evidence/live-motion/`; original frame numbers/source details are in its metadata. Camera framing/brightness differed from the initial fixture.

## Remaining work before controller use

- Set and verify a short manual exposure with supported UVC controls and adequate steady lighting. OpenCV/AVFoundation has not established usable exposure control here. Proposed starting trial:0.5–1ms; do not interpret raw backend values as microseconds.
- Repeat fast swings, full rotations, cart travel, occlusion/reacquisition and lighting variations while recording unannotated camera frames and timestamps.
- Calibrate actual measured cart A–B separation. Physical cart accuracy has synthetic tests but has not been validated against real measured travel in this session.
- Compare vision against an independent encoder/position reference; quantify error by speed and angle, false positives and recovery times.
- Measure sensor-to-host latency with a timed LED/trigger or equivalent reference. Account for the velocity estimator's20–40ms effective delay, explicitly reported via effective timestamps.
- Check lens distortion/perspective across full travel. Present geometry assumes the camera approximately faces the motion plane; there is no intrinsic calibration/homography correction.

The resulting app is a working tested measurement/diagnostic system, not a certification of closed-loop control readiness or arbitrary-scene robustness.
