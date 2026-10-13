# Vision3 baseline

Observe-only camera tracking, encoder comparison and display fusion. All files in
`pendulum_vision/` are unchanged from commit `1d48532`; future vision development
must copy the needed parts into a new directory outside this archived baseline.

## Run on Jetson

Only one process may own the camera. From this directory:

```bash
uv run vision3 --camera /dev/video0 --calibration-file last_calibration.json
```

Defaults preserve the existing setup: 960x600 capture, requested 80 FPS, 180-degree
rotation, 640-pixel detector width, port 3090, and 4000 kbit/s H.264. Requested FPS
does not establish achieved valid measurement throughput.

For encoder/fused traces, keep the balancing console open in another terminal:

```bash
uv run --project ../good_balancing_jetson cartpole-console --rate 100
```

It remains the only serial owner and publishes to loopback UDP port 3096. Vision3
never opens the Teensy. Use `--encoder-port 0` for camera-only operation, and
`--no-video` to omit H.264 encoding. `--help` lists the preserved options.

On the Mac, run `./archive/vision-tunnel.sh` from the repository root and open
**http://127.0.0.1:3095/**. The web server binds Jetson loopback port 3090.

## What the calibration file stores

`--calibration-file last_calibration.json` restores and saves:

- Camera frame width, height and rotation, which must match on restore.
- Hanging-angle reference and observed arm length in pixels.
- Optional two cart reference points and their physical separation in millimeters.

The included saved file contains an angle/arm-length reference. Its cart points
and span are null, so it does **not** provide a calibrated cart distance in meters.
Moving the camera or changing geometry requires a fresh calibration even if the
resolution still matches. Without the option, each launch starts uncalibrated.
This file neither changes the magnetic encoder reference nor affects motor gains.
Encoder sign and the configured vision-delay correction are separate launch
settings, not part of this calibration file.

## Dependencies

`uv` manages Python 3.11, NumPy, OpenCV headless and Flask. The H.264 helper continues
to run through `/usr/bin/python3`, with the Jetson's system GStreamer GI bindings.
It requires `gi`, GStreamer, `videoconvert`, `x264enc`, and `h264parse`.

Read-only prerequisite check on Jetson:

```bash
/usr/bin/python3 -c 'import gi; gi.require_version("Gst", "1.0"); from gi.repository import Gst; Gst.init(None); missing=[n for n in ("appsrc","videoconvert","x264enc","h264parse","appsink") if Gst.ElementFactory.find(n) is None]; print("Missing:",missing); raise SystemExit(bool(missing))'
```

For a fresh Ubuntu installation, the relevant system packages are
`python3-gi`, `gir1.2-gstreamer-1.0`, `gstreamer1.0-tools`,
`gstreamer1.0-plugins-base`, `gstreamer1.0-plugins-good`,
`gstreamer1.0-plugins-bad`, and `gstreamer1.0-plugins-ugly`.
They were not installed or changed on the Jetson during Phase 0.

## Tests and records

```bash
uv run --locked --group dev python -m unittest discover -s tests
node --test tests/*.test.cjs
```

The relative `console` symlink points to `../good_balancing_jetson/console` for
integration tests; it is not a second copy and is not needed by the vision app.
For the real GStreamer test on Jetson, with no competing benchmark workload:

```bash
VISION2_GST_TESTS=1 uv run --locked --group dev python -m unittest discover -s tests
```

The legacy environment-variable name is intentionally retained. Normal offline
test runs skip that one Jetson-specific test. Session outputs go under `runs/` and
are ignored by Git. Use `--record --duration 30` for a bounded recorded session.
Old runs are preserved locally; copying the repository through Git does not copy
them. Existing `VALIDATION.md` and `ENCODER_COMPARISON.txt` contain historical
measurements and limitations, not fresh Phase 0 live verification.

Fusion is for display comparison. Its timing assumptions, prediction horizon and
health gates have not been validated as an actuator-input contract.
