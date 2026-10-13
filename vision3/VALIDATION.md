# Vision3 validation — 2026-10-13

Target: reliable **80 FPS moving-arm measurements**, with physical accuracy, dropout and latency established separately. The software is built and live at the user's subsequent request. That target is **not yet demonstrated with the physical moving arm**.

## Verification

- Jetson final complete suite passed **62/62**, including real GStreamer H.264 encode/decode and frame timestamps; see `evidence/jetson-final-tests.log`. The live session was launched after the initial 60-test run; the later exact-25-FPS floating-boundary fix is saved for the next launch so the user’s new calibration is not disturbed.
- Mac final Python suite: **61 passed, 1 Jetson-only skip**. Browser timing math: **2/2 Node tests**. Dashboard and video JavaScript syntax checks passed.
- Independent read-only code review found two evaluation issues and a derivative boundary issue; all were fixed. Camera sequence gaps now survive saved-video evaluation; unpaced source timeline FPS is labeled explicitly; the paced cache test no longer claims exact velocity truth; exact 25 FPS history cutoffs tolerate floating-point rounding.
- Both original directories remain unchanged by this work. No hardware, firmware, Teensy, exposure/gain or power-mode changes. Read-back power mode remained **25W**.

## Paired Jetson synthetic test

Evidence: `evidence/jetson-synthetic/report.json`, 160 identical 960×600 antialiased rotating-arm frames, 2 ms simulated exposure, alternating processing order, OpenCV two threads. The existing vision2 camera/video app was still running, so this includes competing workload. This run preceded the final moment/allocation optimization; retain it as an intermediate measured comparison, not a fresh isolated benchmark of the final app.

| Measurement | Vision2 | Vision3, 640 detection width |
|---|---:|---:|
| Median detector + estimator time | 18.33 ms | 10.63 ms |
| p95 time | 24.70 ms | 15.77 ms |
| Frames exceeding 12.5 ms | 160/160 | 41/160 |
| Detections | 160/160 | 160/160 |
| Synthetic angle RMSE | 0.0097° | 0.0279° |
| Synthetic angle absolute p95 error | 0.0184° | 0.0532° |
| Velocity RMSE at effective fit time | 0.00417 rad/s | 0.00664 rad/s |
| Velocity RMSE against current-frame truth | 0.1854 rad/s | 0.1246 rad/s |
| Normal effective velocity delay | 37.5 ms | 25.0 ms |

The faster, shorter-window version trades a little ideal-image noise for lower delay. These exceptionally small synthetic errors do **not** describe accuracy in the real camera image. Blur, lighting, calibration, lens distortion, oblique viewing and reference timing need physical validation.

Unpaced replay receives every saved frame, even when processing is slower than 80 FPS. Its source-timeline rates are not achieved live throughput. Service time and the paced test below expose that distinction.

## Saved real motion

Evidence: `evidence/mac-saved-motion/report.json`; source is `vision/evidence/live-motion/raw.avi` with the original host timestamp sidecar. Same 650 frames, full-frame acquisition, no external truth labels.

| Measurement | Vision2 | Vision3 |
|---|---:|---:|
| Detected geometry | 498/650 | 507/650 |
| Available velocity estimates | 448/650 | 491/650 |
| Missing velocities despite detected angle | 50 | 16 |

This is **43 additional velocity estimates**, with fewer extra warmups following missed detections. The sidecar contains another **six skipped camera frames**, so input coverage uses 656 frames. Reports and `*-states-corrected.jsonl` restore those authoritative sequence numbers; original logs with replay indices are retained for audit. Actual lighting/occlusion failures remain. In the initial width comparison, 640 width added 12 detections and lost 3 relative to 960; p95 paired angle difference was approximately **0.14°**, which measures agreement rather than physical accuracy.

## Paced synthetic engine + video

Evidence: `evidence/jetson-paced-video80/report.json`. An 80 FPS cached rotating arm fed the actual measurement engine and software H.264 tracking-overlay pipeline for eight seconds. The first second is excluded from steady-state statistics. Vision2 was still running concurrently; this is a contention test, not an isolated final capacity claim.

- Steady valid angle and velocity throughput: **65.25 FPS**.
- Every processed synthetic frame was detected and had valid velocity after warmup.
- **103 input frames were skipped** in the steady interval: input coverage **81.6%**.
- p95 host-publish-to-result time: **34.74 ms**.
- H.264 output: approximately **64.68 FPS**, no encoder error.
- No velocity accuracy claim for this test: cached angles are published with jittery scheduler timestamps. Analytic accuracy is measured by the separate synthetic test.

This result prevents claiming that offline detection success automatically establishes reliable 80 FPS under encoding load. After vision2 was stopped, vision3 was started with the physical camera for the user to test; avoid adding benchmark load during that test.

## Live launch check

Vision2 PID 23791 exited and released the camera. Vision3 PID 30032 started from the separate `vision3` directory. Chrome loaded it through the existing native SSH tunnel at `http://127.0.0.1:3094/`.

Observed initial values:

- Camera and processed frames: approximately **79 FPS**, zero camera read errors.
- Chrome decoded video: approximately **79 FPS**.
- Browser host-read-to-canvas age: approximately **63 ± 29 ms** in the captured view.
- Current scene was dark and had **no reliable arm geometry**. These rates therefore establish acquisition/transport operation, not valid moving-arm measurement throughput.

Use the new per-stage counters and independent reference CSV support for the next well-lit swing test. An 80 FPS camera produces a frame every 12.5 ms; the test should establish both near-80 valid angular-velocity updates and high camera-input coverage over sustained motion, with accuracy and timing limits stated explicitly.

After the user calibrated and selected the live overlay, 12 half-second samples were saved to `evidence/live-measurement-samples.json`. Median camera delivery was 78.08 FPS, processed frames 76.86 FPS and video output 76.89 FPS. Median valid velocity rate was only 5.55 FPS, ranging from 0 to 29.30 FPS, with median velocity coverage 7.05%. Worker, camera and encoder reported no errors. This was an uncontrolled interactive interval in the dim scene; it demonstrates that the current physical measurement target is still unmet. Do not substitute video/processing throughput for this validity result. The running session was preserved to avoid losing the user's calibration.
