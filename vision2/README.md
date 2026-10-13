# Vision 2 — continuous H.264 preview

A separate copy of the observe-only pendulum tracker. `vision/` is unchanged.
The camera and tracker run independently of the H.264 encoder and browser.
No motor or Teensy commands are sent.

## Run on the Jetson

The existing repository virtual environment is already usable. If recreating its Python dependencies, use `uv pip install --python ../.venv/bin/python -r requirements.txt` from this directory. The video helper uses the Jetson's existing `/usr/bin/python3`, GStreamer GI, x264, h264parse, and videoconvert. Nothing needs installing on the tested Jetson.

Stop any other vision process using the camera first. Then:

```bash
cd ~/cartpole_inverted_pendulum/vision2
../.venv/bin/python -u -m pendulum_vision.live --camera /dev/video0 --width 960 --height 600 --fps 80 --rotate 180 --port 3090 --video-bitrate 4000 --preview-fps 1
```

Keep that terminal running; Ctrl-C stops it cleanly. `--preview-fps` controls only the legacy JPEG snapshot cache, not H.264 video. `--fps` requests camera delivery and the encoder's nominal rate; actual timestamps are retained when frames are missed. `--video-bitrate` is the H.264 target in kbit/s. The default is 4000; try 2500 for a slower network. Reducing video bitrate does not change tracking input resolution.

## Mac tunnel and Chrome

Use the existing native SSH tunnel, then open **http://127.0.0.1:3094/** in Chrome. Keep one video tab active on this connection; each viewer consumes additional bandwidth.

This was the working native-IPv6 tunnel during the October 13, 2026 session:

```bash
ssh -o UserKnownHostsFile=/tmp/jetson-vision-known-hosts -o StrictHostKeyChecking=yes -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 -L 127.0.0.1:3094:127.0.0.1:3090 rbafna@2601:408:c402:c85f:acc2:faf9:770:a44
```

The temporary known-hosts file was populated using the host key obtained through the authenticated Jetson connection. Its path and the Jetson's IPv6 address are session-specific. If either changes, verify the current address and host key before reconnecting. Do not add `-6`: that prevented the IPv4 loopback listener from binding on this Mac. No Chrome proxy flags are needed for this local forward. The previous Tailscale SSH path was too slow for large images in this session.

## Views and rates

- **Smooth camera:** latest camera frames, without annotations. This is the fastest view, independent of detector speed.
- **Tracking overlay:** only processed frames, with the pose measured on that exact image. No stale pose is drawn over a newer camera frame.
- **Green mask:** the mask from processed frames.

The View selection applies to the shared encoder, so all connected viewers receive the same view. Tracking and calibration continue in every view. Select pivot/cart patch using the same controls as the original app. Set hanging zero again after an app restart, and recalibrate if the camera moves.

The dashboard reports camera delivery, tracking, received/decoded video, and browser canvas updates separately. Canvas updates depend on display refresh, browser scheduling, and network jitter; decoded FPS is not a claim about physical display refresh or sensor-to-screen latency. The browser draws the latest decoded frame each animation tick, reconnects if transport falls behind, and stops video requests in a hidden tab.

## Implementation

`stream.py` feeds one encoder process from the latest available frame, independently of tracking and HTTP clients. `gst_encoder.py` uses the system GStreamer runtime to produce H.264 constrained-baseline access units with no B frames and a keyframe every half second. Host frame timestamps supply presentation timestamps; missing frames are not replaced with fabricated observations.

`/video.h264` carries length-prefixed Annex-B access units over one HTTP response. Each frame has a 13-byte network-order `!IQB` header: payload length, presentation timestamp in microseconds, keyframe flag. New clients wait for a complete keyframe including SPS/PPS. Each client has a bounded queue; lagging clients disconnect and reconnect rather than blocking camera capture. `video.js` decodes through Chrome WebCodecs. See the [WebCodecs AVC registration](https://www.w3.org/TR/webcodecs-avc-codec-registration/) and [GStreamer x264 encoder](https://gstreamer.freedesktop.org/documentation/x264/index.html).

Measurements remain at `/api/state`; video encoder statistics are in `video`. Legacy `/preview.jpg` and `/snapshot.png` remain available. `/api/video-mode` accepts `camera`, `tracked`, or `mask`.

## Verification

On the Jetson:

```bash
cd ~/cartpole_inverted_pendulum/vision2
VISION2_GST_TESTS=1 ../.venv/bin/python -m unittest discover -s tests -v
```

On the Mac, omit `VISION2_GST_TESTS=1`; the system-GStreamer integration test is skipped. Tests include complete real H.264 encode/decode, missing-frame timestamp preservation, truncated packets, oversized packet rejection, slow-client disconnection, and exact-frame overlay selection, plus the original tracking/calibration tests.

The original tests `test_live_calibration_and_reset` and `test_video_creates_finite_measurements_and_summary` also failed in the unchanged `vision/` directory on this Jetson. The copies in `vision2` now timestamp synthetic frames when they are processed and evaluate the replay's average measured velocity rather than one raster/codec-sensitive endpoint. Production measurement math and detector thresholds remain unchanged.
