# Cartpole vision

A standalone, observe-only tracker for this green pendulum arm and cart. Default capture is **960×600 at 80 FPS**, rotated 180° for the current mounting. It sends no motor commands.

## Run

From `/Users/rbafna/projects/cartpole/vision`:

```sh
../.venv/bin/python -m pendulum_vision.live
```

Open **http://127.0.0.1:3090**. Camera access must be allowed for the terminal/application. Close other camera applications first. Use `--camera 1` if index 0 is a different camera, or `--rotate 0` for an upright camera.

For a fresh environment (Python 3.10+):

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m pendulum_vision.live
```

Do not install both opencv-python and opencv-python-headless in the same environment. The app needs no OpenCV GUI windows.

## Calibration

1. Detection starts automatically. The green shaft, screw and circular weighted end must be visible. `Select pivot` is optional initial disambiguation and clears calibration; it does not permanently restrict cart travel.
2. Let the arm hang still. Click **Set hanging zero** after 25 consecutive stationary observations. Upright is θ=0; positive rotates from upright toward image-right. Hanging is ±π. Pixel positions and image angle are available before homing; calibrated θ and ω are not.
3. Hold the cart stationary at reference A and click **Record A**. Move to B, enter the **measured separation**, hold still, and click **Record B**. Position zero is the midpoint; positive goes A→B. Physical position/velocity remain unavailable until both references exist.
4. Optionally drag **Select cart patch** around a textured area rigidly attached to the cart. Keep the arm pivot visible and cart stationary during selection. Exclude the pendulum and stationary background. This provides a separate cart observation during arm occlusion. A template that disagrees with the visible pivot is disabled until reselected.

The camera must remain fixed, with its optical axis approximately perpendicular to the pendulum's motion plane. These are image-plane angles and an affine cart scale; lens distortion/perspective are not calibrated out. A new camera pose, zoom or resolution requires recalibration. Resolution changes reset references automatically. Calibrations are saved in the session for auditing but intentionally not restored automatically after restart.

## What the measurements mean

`GET /api/state` supplies JSON. Full-rate states are also written to `runs/<session>/states.jsonl`; the browser polls at about 10 Hz and is not a control interface.

| Field | Meaning |
|---|---|
| `angle_valid`, `cart_valid` | Independent measurement validity; always check these |
| `image_angle_rad` | Uncalibrated atan2(image dx, image dy); zero points down |
| `theta_rad` | Calibrated angle, radians, zero upright, positive toward image-right |
| `theta_down_rad` | Angle from hanging zero, positive toward image-right |
| `omega_rad_s` | Filtered derivative of `theta_rad`, rad/s |
| `cart_x_m`, `cart_v_m_s` | Calibrated cart position and filtered velocity in SI units |
| `pivot_px`, `bob_px` | Detected image points; may still be present when calibration rejects geometry |
| `cart_pivot_px`, `cart_source` | Accepted position observation and its source |
| `t` | Monotonic host time just after the camera read completes, seconds |
| `omega_effective_t`, `cart_velocity_effective_t` | Effective sample times of the velocity fits |
| `angular_window_s`, `cart_window_s` | Actual derivative fitting windows |
| `confidence` | Geometric quality heuristic, **not** a probability or error bound |
| `cart_extrapolated` | Position lies outside A–B; references are not rail end stops |
| `stale` | No measurement newer than 150 ms; angle/cart values are cleared |

Velocities use causal local linear regression over up to **80 ms**, needing at least four samples and 40 ms of data. This reduces differentiation noise but adds roughly 20–40 ms of effective delay. The effective-time fields expose that delay; do not treat velocity as an instantaneous sensor sample. Angle and position themselves are unsmoothed current observations. Missing measurements, gaps, repeated/reversed timestamps and position-source changes reset derivative history. No predicted pose is silently substituted for a measurement.

For control integration, import `ArmDetector` and `StateEstimator` in a dedicated process or add a suitably timestamped transport. This Flask dashboard is a diagnostic tool. Establish encoder-referenced accuracy, actual camera-to-host latency and required control bandwidth before closing the loop.

## Frame rate and recordings

Acquisition reports requested mode, backend acceptance, driver readback, **measured camera delivery FPS**, measured tracking FPS, timing tails and skipped camera sequence numbers. “Target met” requires a measured rate within 5% of the request over the rolling window; it does not certify unique sensor exposures or hard real-time behavior. Camera and tracking run independently, with the tracker taking the latest frame rather than building latency in a queue.

```sh
../.venv/bin/python -m pendulum_vision.probe --seconds 10 --out runs/probe-80
../.venv/bin/python -m pendulum_vision.live --record
```

`--record` saves unannotated **MJPEG** video (`raw.avi`, not Bayer/raw-sensor data) and `raw_times.jsonl` containing actual host times and camera sequence numbers for every saved frame. The bounded recording queue never blocks tracking; recording drops and errors are reported separately. It records processed frames, not necessarily every camera-delivered frame. Video is constant-rate; **the timestamp sidecar is authoritative**. Recording uses substantial disk space (roughly 0.5–0.7 GB/min in this scene).

Replay a capture:

```sh
../.venv/bin/python -m pendulum_vision.replay runs/SESSION/raw.avi \
  --timestamps runs/SESSION/raw_times.jsonl --out runs/replay-SESSION
```

Replay the supplied screen recording:

```sh
../.venv/bin/python -m pendulum_vision.replay \
  '../pendulum_camera_quality/Screen Recording 2026-10-03 at 3.06.44 PM.mov' \
  --out runs/screen-replay
```

Each replay writes `states.jsonl`, `summary.json`, an annotated `overlay.avi`, and `contact.jpg`. Output directories must be new. Use `--home-angle RADIANS` only when you know the image angle of hanging zero. Screen recordings have preview resampling and cannot validate sensor rate, exposure or velocity accuracy.

## Exposure and camera setup

80 FPS specifies a 12.5 ms frame period, **not** a 12.5 ms exposure. A global shutter avoids rolling-shutter skew but still blurs during exposure. The AR0234 B0495 family lists 960×600@80 FPS and 1920×1200@50 FPS; full resolution is not the 80 FPS mode. [Manufacturer datasheet](https://www.arducam.com/downloads/datasheet/B0495_AR0234_Global_Shutter_USB3.0_Camera_Module_Datasheet.pdf)

The current footage has significant motion blur. First test bright, steady illumination and a short fixed exposure, initially around **0.5–1 ms**, then check brightness, gain noise and tracking while swinging. This is a proposed tuning range, not a measured camera setting. Blur approximately obeys `blur_px = image_speed_px_per_second × exposure_seconds`: at a 210px arm radius and 10rad/s, a 1ms exposure smears the tip about 2.1px.

OpenCV/AVFoundation on this Mac reports exposure and gain as zero without usable units. The application logs this and does not claim they are zero exposure or zero gain. Optional `--exposure-raw`, `--auto-exposure-raw` and `--gain-raw` use backend-specific values and log set acceptance/readback. They are not microseconds and have no portable meaning. Do not guess values. Use a supported UVC control application, or Linux `v4l2-ctl --list-ctrls` to inspect the actual device's control names/ranges before setting exposure. Tune focus at the real arm distance and use a direct USB 3 connection.

A different camera is not yet justified by these measurements: the existing camera delivers the requested rate. Short-exposure motion quality and latency remain to be established.

## Tests and limits

```sh
../.venv/bin/python -m unittest discover -s tests -v
```

Tests cover full rotations, clutter, real-image reflections, ambiguous arms, reacquisition, cart-template translation/occlusion, source conflicts, calibration, irregular timing, wraparound, staleness, API errors, recording sidecars and replay. `docs/validation.md` records observed results and remaining gaps.

This detector is specific to a green rigid shaft with a wider circular weighted end. Severe blur, hands, clipping, lookalike arms and lighting changes can cause rejection. It does not certify “ironclad” operation or accuracy under arbitrary scenes; it exposes failures and provides reproducible evidence for improving them.
