# Vision3

Observe-only camera tracking, with a faster detector, more continuous measured angular velocity, and explicit measurement coverage and latency. It never sends Teensy commands. `vision/` and `vision2/` are preserved.

## Encoder and fused angle comparison
See [ENCODER_COMPARISON.txt](ENCODER_COMPARISON.txt) for the three toggleable traces,
console telemetry, timing assumptions, calibration and verification limits.
The current Mac tunnel uses **http://127.0.0.1:3095/** (Jetson port 3090).
Use the latest console bundle so encoder health is published.
Vision calibration starts fresh unless you provide --calibration-file;
moving the camera still requires a fresh calibration.

## Start a later session

Stop the currently running app first using Ctrl+C in its terminal. For the background instance started here, verify its identity and stop it on the Jetson:

```bash
ps -p "$(cat /tmp/pendulum-vision3.pid)" -o pid=,args=
kill -INT "$(cat /tmp/pendulum-vision3.pid)"
```

Run these commands on the Jetson, one line at a time:

```bash
cd /home/rbafna/cartpole_inverted_pendulum/vision3
../.venv/bin/python -u -m pendulum_vision.live --camera /dev/video0 --width 960 --height 600 --fps 80 --rotate 180 --port 3090 --detector-width 640 --video-fps 80 --video-bitrate 4000
```

Dependencies are already installed. If rebuilding the environment, use uv rather than pip inside the environment:

```bash
uv pip install --python ../.venv/bin/python -r requirements.txt
```

H.264 uses the Jetson's existing `/usr/bin/python3` GStreamer runtime and software x264 encoder. The regular vision virtual environment handles tracking.

If the Mac tunnel is no longer open, run this in a Mac terminal and leave it open:

```bash
ssh -N -o UserKnownHostsFile=/tmp/jetson-vision-known-hosts -o StrictHostKeyChecking=yes -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 -L 127.0.0.1:3095:127.0.0.1:3090 rbafna@2601:408:c402:c85f:acc2:faf9:770:a44
```

This uses the native IPv6 route and the previously verified host-key file from this session. If the Jetson address or that temporary file changes, resolve that before reconnecting; do not disable host-key checking. Do not add `-6`: that previously prevented the IPv4 loopback listener from binding. Normal Chrome needs no SOCKS flags with this tunnel.

Only one vision app can own the camera. To return to vision2, stop vision3, change into the sibling `vision2` directory, and use its original command. The browser/tunnel ports remain the same.

## Controls for comparing performance

Append or change these options on the launch command:

| Option | Purpose |
|---|---|
| `--video-fps 60` | Keep measurements at 80 FPS while reducing video encoding load. |
| `--no-video` | Disable H.264 to isolate tracking cost; no main canvas stream in this mode. |
| `--detector-width 960` | Original detection resolution for an accuracy/throughput comparison. |
| `--detector-width 480` | Experimental faster detection; smaller pivot details may be lost. Validate against references before relying on it. |
| `--record --duration 30` | Record a bounded validation session, including processed raw frames and their timestamp sidecar. Recording adds work. |

The default is 640, selected after saved-motion and fixture comparisons. Segmentation still scans the whole image; it does not assume the arm stayed near its previous location. Green thresholds, circular bob fit, pivot-hole detection, ambiguity rejection and calibrated length checks remain in place. No pose is invented through occlusion.

## What changed

- Native OpenCV segmentation and moment calculations replace large NumPy image allocations. Full-resolution mode preserves the original segmentation exactly and the saved fixture geometry to numerical precision.
- Angular velocity normally uses a 50 ms causal fit, with about 25 ms effective delay at 80 FPS. At lower/jittery rates the window can extend to 120 ms to retain four observations. The UI reports actual delay. A short missed frame is invalid, but recent measured history remains available for recovery. Gaps over 75 ms, invalid geometry, timestamp reversal and calibration changes reset angular history.
- Camera, processing, detected geometry, calibrated angle and valid velocity are counted separately. Coverage includes skipped camera sequence numbers. Uncalibrated velocity coverage is unavailable, not zero-quality calibrated tracking.
- JPEG fallback encoding runs outside the tracking thread. H.264 avoids repeated overlay work for unchanged frames and unnecessary full-frame byte copies. Encoding pauses when there are no viewers.
- The dashboard shows p95 computation and host-read-to-result time. Host-read-to-canvas age uses clock probes and exposes round-trip uncertainty. This is **not** exposure-to-screen latency; sensor/readout/USB time before host read and display scanout are not measured.

See [VALIDATION.md](VALIDATION.md) for evidence and limits, and [TRANSPORT.md](TRANSPORT.md) for alternatives to SSH.

## Tomorrow's validation

1. Improve steady lighting so both the dark pivot screw and green bob rim are distinct without motion blur. Keep the camera square to the motion plane. Do not change calibration while the arm is moving.
2. Set hanging zero; check 25 consecutive stable samples. Let the arm swing freely through the intended range. Watch **valid angular velocity FPS** and **velocity coverage**, not just video smoothness. Coverage includes startup and actual loss; rolling statistics cover two seconds.
3. Save a 30-second recorded run. `raw.avi` contains the frames actually processed, with `raw_times.jsonl`; it does not contain frames skipped by the tracker. `states.jsonl` preserves input sequence numbers and all per-frame timings. Compare video80, video60 and no-video in separate otherwise identical sessions to distinguish compute competition.
4. Evaluate the log (replace the session directory):

```bash
../.venv/bin/python -m pendulum_vision.evaluate log runs/SESSION/states.jsonl --out runs/SESSION/measurement-report.json
```

5. Measure physical angle against an independent reference, not the detector's own output. Suggested check: stationary known angles plus timestamped encoder data through free swings, or independently annotated pivot/bob centers from recorded frames. Reference CSV columns are `t,image_angle_rad` and optionally `image_omega_rad_s`; times must use the same origin as the log. Image angle is `atan2(bob_x-pivot_x,bob_y-pivot_y)`, zero down, positive toward image-right. Optional reference angular velocity uses that same sign; it is opposite the dashboard's theta velocity. Synchronize any encoder clock explicitly.

```bash
../.venv/bin/python -m pendulum_vision.evaluate log runs/SESSION/states.jsonl --reference reference.csv --out runs/SESSION/accuracy-report.json
```

Reference interpolation will not bridge gaps over 100 ms or extrapolate beyond reference data. The report gives angle RMSE/bias/p95/max and velocity error both at its effective fit time and at the current frame time. Regression fit residuals are diagnostic noise estimates, not calibrated physical uncertainty.

## Offline tests and reproducible benchmarks

```bash
../.venv/bin/python -m unittest discover -s tests -v
node --test tests/timing.test.cjs
VISION2_GST_TESTS=1 ../.venv/bin/python -m unittest discover -s tests -v
../.venv/bin/python -m pendulum_vision.evaluate benchmark --baseline ../vision2 --frames 320 --out evidence/new-synthetic-trial
../.venv/bin/python -m pendulum_vision.pipeline_benchmark --seconds 10 --video-fps 80 --out evidence/new-paced-trial
```

The GStreamer and paced-video tests are for the Jetson. Synthetic benchmarks never open a camera. Avoid benchmarking while assessing the live app: extra benchmark load competes for the same CPU/power budget. Use a new output directory each time.
