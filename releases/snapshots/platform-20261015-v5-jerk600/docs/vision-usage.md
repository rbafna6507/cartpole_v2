# Persistent camera viewer

The optional SDK camera runtime lives in `src/cartpole_vision`. It preserves the
vision3 portal, raw camera / tracking overlay / mask views, calibration controls,
metadata, and plots. The archived sources remain unchanged. This process never
opens serial or sends motor commands.

## Run locally

```sh
uv run --extra vision cartpole-vision --camera /dev/video0 --fps 60
```

The HTTP and legacy encoder UDP endpoints bind loopback at 3090 and 3096.
GStreamer H.264 encoding runs in a separate system-Python helper, using the
Jetson's installed GI and x264 plugins. The optional dependency extra installs
Flask, NumPy, and OpenCV; it does not install system GStreamer packages.
The default capture rate is deliberately 30 FPS until the connected camera is
benchmarked. Requested, delivered, processed, encoded, decoded, and displayed
rates are separate measurements.

## Persistent Jetson service

Install the checkout at `~/cartpole_v2`. Use an isolated virtual environment so
normal console commands cannot remove the viewer dependencies:

```sh
cd ~/cartpole_v2
UV_PROJECT_ENVIRONMENT=.venv-vision ~/.local/bin/uv sync --locked --extra vision --no-dev
scripts/install-vision-service.sh
loginctl enable-linger
```

The unit is `cartpole-vision.service` in the user's systemd manager. It launches
`.venv-vision/bin/cartpole-vision`, restarts after five seconds on exit, and shuts
down on SIGTERM. A camera stall lasting two seconds or a failed tracking/encoding
worker exits the runtime so the supervisor can recover. `loginctl enable-linger`
was successfully applied on the Jetson; no reboot was performed.

Configuration: `~/.config/cartpole-vision/runtime.env`. Supported environment
settings are listed in `scripts/run-vision-service.sh`; retain native camera
geometry when using an existing calibration. Calibration is stored at
`~/.local/state/cartpole-vision/calibration.json`. The original reference was
copied unchanged from
`~/cartpole-v2-runs/vision-motor-tests-20261014/calibration.json`: 960×600,
180-degree rotation, home angle −0.006486665936711519 radians, home length
150.33427350884477 pixels, cart scale unset.

```sh
systemctl --user status cartpole-vision
systemctl --user restart cartpole-vision
systemctl --user stop cartpole-vision
tail ~/.local/state/cartpole-vision/runtime.log
```

No unattended raw recording occurs. Each normal session retains at most four
8 MiB state files, four 8 MiB comparison files, and two 1 MiB event files.
Only the four newest runtime-marked session directories are kept (approximately
264 MiB total plus small metadata). Runtime diagnostics retain four 2 MiB files.
Unrelated directories are never removed. Explicit `--record` sessions are
excluded from automatic session pruning: their raw AVI and timestamps require
the operator's own disk budget and cleanup. HTTP access logs are disabled.
Systemd lifecycle records follow the host journal's retention policy.

## Private viewing

The deployed remote view binds only the Jetson tailnet address
`100.126.59.18:3091`, enabled by `VISION_VIEW_BIND=100.126.59.18`.
It blocks calibration changes; view selection remains available. It never binds
0.0.0.0 and does not use Tailscale Funnel or expose a public endpoint.

WebCodecs requires a secure browser context. Run the local proxy on any computer
already connected to the same tailnet, then open its localhost URL in Chrome:

```sh
python3 scripts/vision-view.py --host 100.126.59.18 --port 13090
```

Open **http://127.0.0.1:13090**. The proxy binds only localhost and forwards each
connection independently over the encrypted Tailscale network. Stop it with
Ctrl-C. Direct HTTP at the tailnet IP is useful for API diagnostics, but browsers
do not enable WebCodecs on that insecure origin.

For calibration through the original loopback endpoint, an SSH tunnel remains
available:

```sh
scripts/vision-tunnel.sh jetson 13091
```

Open **http://127.0.0.1:13091**. Verify the SSH host key normally on a new machine.
Initial tests found SSH video multiplexing and large uncompressed history
responses could stall the portal. The direct tailnet proxy, gzip JSON, bounded
chart initialization, and incremental histories avoid those stalls. Tailscale
Serve was attempted but denied the current user's admin rights; the supported
proxy route needs no privileged changes.

## Sensor and SDK interfaces

- `GET /api/sensing-stream?max_hz=100`: the default SDK transport is one persistent
  NDJSON connection. Each `cartpole-sensing-stream-v1` line contains `vision`
  (the lightweight source snapshot), `encoder` (the incremental batch below),
  `stream_seq`, and server emission `host_t`. Source acquisition/effective/receipt
  timestamps are never replaced by emission time. Optional `after_seq` and
  `session` resume the encoder cursor per connection. The server waits for new
  processed frames and emits a repeated-camera/fresh-encoder heartbeat within
  100 ms during a camera stall. `max_hz` accepts 10..100 (default 60) and is a
  ceiling; the SDK client requests 100 to consume every available latest frame.
  There are at most four subscribers, no producer queue, a 4 MiB line bound,
  an explicit truncation flag, a 32 KiB requested socket send buffer, and a
  five-second write timeout. Linux may double the socket-buffer allocation.
  Slow consumers skip intermediate camera frames; bounded encoder history and
  original sample timestamps remain available. The endpoint is never gzipped.
- `GET /api/state?measurement=1`: source measurement, calibration, source timing,
  and worker error only. The SDK monitor uses this path to avoid diagnostic
  computation and comparison IPC.
- `GET /api/state`: original full dashboard API. `history=1` enables
  incremental plotted samples; `history_limit=120` bounds initialization.
- `GET /api/encoder?after_seq=N&session=S`: the original latest raw encoder
  packet plus an ordered `packets` batch, `session`, `oldest_seq`,
  `latest_seq`, `reset`, and `history_truncated`. History retains at most
  2048 schema-accepted packets and five seconds, including invalid health
  packets. It clears on session, reference generation, upright reference, or
  detected board reboot changes. No new timestamps replace serial timestamps.
- UDP 3097: loopback-only genuine `cartpole-sdk-shadow-v1` observations, with
  session/clock/frame/calibration identity. These observations remain explicitly
  uncommissioned for control.
- `GET /api/sdk-state?compact=1&after=N&session=S`: separate SDK shadow status
  and incremental bounded history. Producer time determines freshness.
  Duplicate-time fused corrections replace the earlier plotted point.
- The legacy purple display filter is explicitly labeled and never presented as
  SDK control fusion. Calibration changes invalidate old measurements before
  new calibration metadata is published.

## Measurements and limits

Initial 20-second camera-only trials, with an active local tracked H.264 consumer,
used unchanged 960×600 geometry and camera readbacks exposure 5 / gain 168.
Median steady-state values (warm-up excluded):

| Capture request | Detector width | Delivered | Tracked | Encoded | Valid angle coverage |
|---|---:|---:|---:|---:|---:|
| 30 FPS | 640 | 29.94 | 29.94 | 29.97 | 100.0% |
| 60 FPS | 640 | 59.74 | 59.28 | 59.32 | 99.2% |
| 80 FPS | 640 | 77.46 | 60.20 | 59.67 | 77.4% |
| 80 FPS | 480 | 78.37 | 69.62 | 69.11 | 87.9% |
| 80 FPS | 320 | 79.07 | 76.12 | 75.80 | 85.4% |

Coverage includes skipped capture frames. These static-pole trials do not
establish dynamic angle accuracy or physical velocity accuracy. Smaller detector
images can change marker precision. A higher capture request can provide fresher
latest frames even when processing skips some frames. Browser throughput is a
separate limit, and video quality must be judged from the encoded view, not
server-side FPS alone.

Evidence: `evidence/phase4/vision-service-20261015/`; full Jetson trial artifacts
are under `~/cartpole-v2-runs/vision-service-20261015/`. Reports' connection-refused
entries at the final sample coincide with deliberate duration-based process
shutdown; each benchmark runtime exited successfully.

## Deployed quality profile and transport findings

The selected profile keeps the physical calibration geometry at 960×600 rotated
180 degrees, requests capture at 80 FPS, detects at width 640, and encodes smooth
camera video at 40 FPS / 3000 kbit/s. In the final configuration file:

```sh
VISION_FPS=80
VISION_VIDEO_FPS=40
VISION_VIDEO_BITRATE=3000
VISION_DETECTOR_WIDTH=640
VISION_VIEW_BIND=100.126.59.18
VISION_VIEW_PORT=3091
VISION_VIEW_TCP_MSS=1000
```

The detector processes the newest available frame. It is expected to skip
capture frames, and requested 80 FPS does not mean 80 valid measurements per
second. Viewer-only trials measured roughly 50–60 tracked frames/s in this scene.
The final simultaneous SDK-observer and visible-viewer test averaged 39.14
tracked frames/s; use that measured concurrent rate for planning. Smooth camera
video is independent of tracking. Overlay and mask use actual processed frames.
The 30 FPS installation defaults remain conservative for an unmeasured camera.

The initial degraded path delivered only 0.58 Mbit/s for a bounded raw snapshot,
with TCP congestion windows of 2–4 segments and heavy retransmissions. With the
viewer paused, repeated nine-second private TCP probes gave 3.32/3.02 Mbit/s
with default segments, 6.16/5.93 Mbit/s at MSS 1000, and 5.09 Mbit/s at MSS 800.
These are path-specific observations, not a general recommendation for all
networks. The optional MSS setting applies to the private listener before its
SYN negotiation; it changes no global network configuration. Streaming handlers
also use TCP_NODELAY. Temporary benchmark listeners expired automatically.

A second bottleneck was browser scheduling: several complete frames can arrive
in one network chunk. The old synchronous loop reset the decoder when six
frames were queued, before asynchronous decoding could run. The player now
waits briefly for decoder capacity, with abort/visibility cleanup and a bounded
250 ms stall timeout. It retains keyframe startup and reconnects if transport
falls behind. No invalid delta frames are silently used after a reset.

With those fixes, the visible browser achieved approximately 59 decoded / 57
painted FPS at 4 Mbit/s and 60 video FPS, with estimated host-read-to-canvas age
55 ± 30 ms. Capture was 78.4 FPS and tracking 47.8 FPS in that sample. The clock
uncertainty is shown explicitly; this is not a sensor-exposure latency claim.
The final 3 Mbit/s / 40 FPS profile reduces encoding load and leaves bandwidth
headroom while retaining substantially better quality than the rejected
500 kbit/s trial. It has more bits per video frame than 4 Mbit/s / 60 FPS.

The cap comparison at 4 Mbit/s measured these medians with one viewer:

| Video cap | Delivered capture | Tracked | Encoded | Slow disconnects during trial |
|---:|---:|---:|---:|---:|
| 60 | 78.13 | 51.89 | 52.03 | 3 |
| 40 | 79.71 | 59.93 | 27.33 | 2 |
| 30 | 78.74 | 57.74 | 30.03 | 1 |

Those short runs include reconnects, and the initial 60 FPS view mode was not
controlled consistently; they demonstrate load sensitivity, not a precise
causal ranking. Subsequent profiles explicitly select smooth camera mode.
Stage fields `lock_wait_ms`, `detection_ms`, and `comparison_ms` distinguish
work from contention. Under a full 4 Mbit/s / 60 FPS viewer, a 30-sample check
measured mean 27.9 ms processing, 26.1 ms detection, 1.2 ms lock wait, and 0.18 ms
comparison submission. The six-core host was at 25 W mode, 1.344 GHz and about
46–47°C; no privileged power or network settings were changed.

## Precision and source image limitations

A same-frame comparison on an earlier 650-frame moving MJPEG recording found
480-versus-640 angle disagreement with mean +0.0205°, standard deviation 0.1195°,
and absolute 95th percentile 0.1860° (503 jointly detected frames). However, a
60-frame burst from the current geometry was materially worse at width 480:
640 detected 60/60 with 0.0353° static angle scatter; 480 detected 59/60 with
0.3971° scatter and −0.9814° mean disagreement from 640. Width 320 detected
49/60. Therefore 640 is retained for this scene. Neither detector is angle
ground truth, and static scatter does not prove dynamic accuracy.

The raw uncompressed snapshot already contains visible grain. Original control
readbacks were auto exposure 0 (Auto Mode), inactive exposure value 5, and gain
168, the minimum exposed gain setting. An inactive exposure readback is not a
measurement of the automatic shutter time. Explicit manual exposures 5/10/20
produced no valid detections in 24 frames per setting: a fixed wall region had
mean luma 0.42/1.16/1.62 on a 0–255 scale, versus 115.43 in the automatic burst.
Original automatic controls were restored in a finally block and verified.

The standard V4L2 exposure-absolute unit is 100 microseconds, so those requested
values correspond to 0.5/1/2 ms, without independently measuring the shutter.
See the [Linux camera control reference](https://docs.kernel.org/userspace-api/media/v4l/ext-ctrls-camera.html).
No longer, motion-blurring exposure was promoted from static evidence. Better
scene lighting is needed to improve short-exposure source quality. The runtime
does not blur or temporally smooth images to make angle precision look better.

## Concurrent SDK load and rejected tuning

The complete stopped SDK-plus-visible-viewer test with the lightweight HTTP
polling path accepted 593 camera corrections in 25 seconds, without encoder
history truncation or pending-queue drops. Tracking nevertheless averaged
28.49 FPS under that workload, compared with roughly 50–60 FPS when displaying
the camera alone. A controlled phase comparison showed the slowdown already
occurred when the observer polled but did not publish SDK viewer telemetry.
Detector wall time increased while engine lock waiting remained a smaller cost.

A one-millisecond Python scheduling experiment produced 27.94 tracked FPS and
563 accepted corrections, so it was rejected. The service uses the interpreter's
normal scheduling; the experimental tuning option was removed. The persistent
NDJSON source stream replaces repeated HTTP connection/thread creation while
preserving the exact source/fusion contracts. With the same 80 FPS capture,
640-pixel detector, 40 FPS / 3 Mbit/s video profile, and one visible viewer, the
25-second stream test accepted 903 camera corrections (902 tracking outputs,
13 rejected updates) with no history truncation or pending-queue drops.
Post-warmup means were 75.32 FPS capture, 38.24 FPS tracking, and 40.01 FPS
video. The rig remained disabled and homed; both encoder and SDK data became
stale after the observer closed. This is an improvement over the 593-correction
HTTP test, but it does not sustain 60 tracked FPS under the full concurrent
workload. The HTTP, scheduling, and stream results are archived for comparison.

The final detector change skips external contours with fewer than three points,
whose polygon area is exactly zero, and computes the unchanged area thresholds
once per frame. All pose fields, detection reasons, candidate counts, and mask
pixels matched the prior detector exactly on 650 saved moving frames and five
stills. Local alternating timings improved the noisy current still median from
2.751 to 2.554 ms; moving replay median gains in the last two passes were only
about 1–2%, so this is not evidence of a large live throughput improvement.
The earlier 60-frame current burst saved all pose rows but only its first and
last raw images; equivalence was not tested on unavailable raw burst frames.
The evidence includes the baseline source, replay script, and measured results.

The final stopped 25-second test after that optimization accepted 898 camera
corrections, with 29 rejected updates, no history truncation or pending drops,
and no camera/video errors. Post-warmup means were 75.65 FPS capture, 39.14 FPS
tracking, and 39.98 FPS video; mean detector time was 27.24 ms and engine lock
wait 2.18 ms. The viewer stayed in smooth camera mode throughout. The small
difference from the previous 903-correction / 38.24 FPS trial does not establish
a causal live performance gain. Final hardware state was disabled, homed, and
fault-free, and source freshness expired correctly after the observer closed.
No further camera, detector-width, or encoding profile changes were made.

## Focused verification

```sh
uv run --locked --extra vision --group dev python -m pytest tests/vision_runtime
node --test tests/vision_runtime/*.test.cjs
```

Camera-runtime tests skip as a package when the optional Flask/NumPy/OpenCV
packages are absent. The SDK's source contracts and replay tests remain usable
without camera dependencies. Hardware/camera access is not needed for these
focused tests; live performance evidence is recorded separately.
