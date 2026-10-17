# Read-only encoder telemetry and SDK shadow fusion

The operator console mirrors its accepted encoder state to loopback UDP 3096 by
default. `--no-vision-telemetry` or `--vision-telemetry-port 0` disables it. SDK
applications opt in with `Rig(..., vision_publisher=EncoderPublisher())`, importing
`EncoderPublisher` from `cartpole_sdk.sensing.telemetry`. The existing serial
reader remains the only owner. Submission replaces one snapshot reference; JSON
and nonblocking UDP run on a separate worker. A disconnected reader stops
publishing, and the camera viewer must age the last packet. No viewer can arm or
send commands through this transport.

The version-1 packet keeps the existing camera comparison format and adds
`sdk_state`, `sdk_info`, `board_clock_id` and `host_clock_id`. Health comes from the
**current executor state**, including fault and calibration flags. INFO contains
last-read diagnostics and the upright reference; it does not establish current
magnet health. `upright` and `sdk_info` remain null until the serial owner reads
INFO. The console reads INFO while stopped on startup; SDK applications call
`get_info()` explicitly. The old viewer comparison is display-only. After any encoder calibration
attempt, the mirror withholds reference metadata for the rest of that Rig session.
V4/V5 state frames have no reference generation, so queued angles cannot safely be
paired across a reference change. Close and reopen the console/SDK connection to
establish the new reference. INFO itself remains available for operator diagnosis;
a running shadow observer requires a fresh explicit session/configuration.


`examples/sensing_shadow.py` defaults to one persistent NDJSON connection to
`/api/sensing-stream`. Each envelope carries the measurement-only camera snapshot
and a dense incremental encoder batch. The service samples the camera, releases
its lock, then fetches encoder history; it retains at most 2048 packets and five
seconds for the current session/reference. Repeated camera snapshots arrive with
fresh encoder batches at least every 100 ms if the camera stalls. They retain
original source timestamps and do not apply a second camera correction.

The client bounds each line to 4 MiB, reads in bounded chunks, and applies an
absolute duration deadline to response reads, including HTTP header and chunk
framing. Transport disconnects/timeouts are logged and retried with a bounded
50–200 ms backoff and the last accepted encoder cursor. The same observer and
clock mapping survive reconnects; calibration/source changes and malformed or
oversized records fail visibly. An outage ages the existing measurements normally.
The default `--poll-hz 100` is a stream rate ceiling, not a claim of 100 camera FPS.

`--transport http` selects the earlier polling baseline: camera first at
`/api/state?measurement=1`, then `/api/encoder?after_seq=...&session=...`.
Both paths preserve calibration, frame dimensions, source/effective timestamps
and stale semantics. The example targets the maintained runtime and does not
open serial. With explicit calibration and timing JSON it emits actual SDK
`Observation` objects, records replayable input/flush/output events, and sends
`cartpole-sdk-shadow-v1` packets to loopback UDP 3097. The viewer exposes these
separately from its old comparison. `--replay` deterministically processes a
capture offline and never publishes into the live viewer.

Stream records distinguish receipt from availability: `vision_queued.received_ns`
is the event's processing time and `source_received_ns` is the original client
receipt used in the camera sample. Encoder batch events also retain
`transport_received_ns`; every packet retains its serial owner's earlier
`sdk_state.received_ns`. Thus multiple envelopes from one socket read can share a
transport receipt while acquiring sequential processing availability. Replay
uses these explicit times; older captures without `source_received_ns` retain
their earlier receipt interpretation.

```sh
python examples/sensing_shadow.py --config runs/shadow-config.json \
  --output runs/shadow-capture.jsonl --duration 60
python examples/sensing_shadow.py --config runs/shadow-config.json \
  --replay runs/shadow-capture.jsonl --output runs/shadow-replay.jsonl
```

## Required configuration

The following is a schema illustration, **not a commissioned rig calibration**.
Replace every measured value and identity from the same physical setup before
using it. Fingerprints are `calibration_fingerprint(dictionary)` from
`cartpole_sdk.sensing.vision`. The calibration JSON is the complete camera
`/api/state` calibration object. Its fingerprint must match the source alignment.
A camera anchor is the `theta_rad` reading at a directly verified stationary
upright pose in that same camera calibration, not a raw image angle in another
coordinate convention. Both angular signs must be verified, and both reference
IDs identify the same physical upright pose and positive rotation convention.

```python
from cartpole_sdk.sensing.vision import calibration_fingerprint

# Fill these from explicit observations; do not copy nominal example values.
reference = {'upright_raw': verified_encoder_upright_raw,
             'firmware': verified_firmware_identity}
camera_calibration = verified_full_camera_calibration
config = {
    'schema_version': 1, 'session_id': unique_shadow_session,
    'clock_id': 'local-monotonic',
    'encoder_reference': reference,
    'vision_calibration': camera_calibration,
    'encoder_alignment': {
        'source': 'magnetic', 'source_id': verified_encoder_identity,
        'source_frame_id': 'encoder-zero',
        'source_calibration_id': calibration_fingerprint(reference),
        'target_frame_id': shared_upright_frame,
        'reference_id': direct_upright_capture_id,
        'zero_rad': measured_encoder_zero_rad, 'sign': verified_encoder_sign,
    },
    'vision_alignment': {
        'source': 'vision', 'source_id': verified_camera_identity,
        'source_frame_id': 'camera-native',
        'source_calibration_id': calibration_fingerprint(camera_calibration),
        'target_frame_id': shared_upright_frame,
        'reference_id': direct_upright_capture_id,
        'zero_rad': measured_camera_theta_rad_at_upright,
        'sign': verified_camera_sign,
    },
    'encoder_clock': {
        'strategy': 'receipt-anchor',
        'receipt_delay_ns': explicitly_assumed_or_measured_serial_delay,
        'uncertainty_ns': declared_clock_uncertainty,
        'max_receipt_residual_ns': allowed_receipt_jitter_and_drift,
        'valid_for_ns': bounded_clock_mapping_lifetime,
    },
    'vision_clock': {
        'source_clock_id': camera_host_clock_identity,
        'session_clock_id': 'local-monotonic',
        'offset_ns': measured_camera_to_local_host_offset,
    },
    'fusion': {},  # FusionConfig defaults; changes are fingerprinted in output.
}
```

The encoder map anchors the first board time to its recorded serial receipt minus
the explicitly supplied delay. It records that offset and the declared
uncertainty, checks later receipt residuals, and expires after its configured
lifetime. It does not estimate drift or infer synchronization across hosts. The
camera timestamp remains a host-read acquisition proxy; an approximately 22 ms
receipt-delay estimate does not certify camera exposure time. The SDK never
subtracts that estimate from camera time automatically. Run this bridge on the
serial/camera host or provide a genuinely calibrated common host clock.

AngularAlignment applies `wrap(sign * (angle - zero_rad))`; angular velocity only
gets the sign. It verifies original source frame and calibration identity before
changing values and frame names. Fusion consumes the resulting shared frame.
Board session, reference generation, source identity, camera calibration or clock
rollback changes latch a reset requirement. No automatic re-anchoring follows.

## Estimator behavior and limitations

The magnetic angle supplies fast motion. Delayed vision is compared to wrapped
linear interpolation of already received magnetic history at its own effective
time, with no extrapolation across missing history or large gaps. A complementary
correction slowly adjusts magnetic bias, bounded by innovation, correction rate
and absolute bias limits. Every output keeps original source timestamps and an
estimated fused angle at the latest magnetic effective time. Buffers are bounded.
Camera loss, stale encoder state and missing alignment make the fused channel
invalid; they do not silently substitute another source. Short rejected camera
outliers leave a recent accepted correction usable only within its age limit.
A slow HTTP poll does not downsample the encoder history used for interpolation.
Each history sample keeps its original serial receipt, while the HTTP batch time
is its availability to the shadow observer. Camera observations can wait in a
bounded 32-frame queue until a real encoder bracket arrives. Their original
receipt is preserved and correction availability is the later processing time.
Pending frames expire under the existing vision-age bound; true missing encoder
intervals still fail the unchanged interpolation-gap check. A stale history batch
cannot make the current fused output fresh. Capture logs include these queue and
batch events so offline replay follows the same causal order.

Rates are not fused: source rate estimates have different effective times and
filter delays, and angle-bias correction does not establish a valid derivative.

This simple estimator is inspectable and requires fewer unverified noise/dynamics
assumptions than an EKF. Its limitation is consequential: the measured magnetic
error is nonlinear and history-dependent (including roughly 16 degree slow-turn
error and several degree changes after rotation). A slow additive correction
cannot repair that behavior over the full motion range. Timing error during
motion can also resemble bias. Raw, aligned and fused traces plus diagnostics
must be evaluated on held-out real recordings before any control use.

All shadow packets set `commissioned: false` and `control_eligible: false`.
Software tests establish wrap/timing/staleness/provenance behavior only. Neither
these tests nor an attractive overlay commission sensor fusion or the separate
100/250 Hz host policy. No existing policy source selection changes.


## Measured stream performance

A stopped 25-second run on 2026-10-15 compared the persistent stream with the
measurement-only HTTP baseline. The profile used native 960×600 capture at a
requested 80 FPS, rotation 180°, detector width 640, and a 40 FPS / 3000 kbps
smooth-camera feed with one visible browser client.

| Measurement | HTTP polling | Persistent stream |
| --- | ---: | ---: |
| Accepted camera corrections | 593 | 903 |
| Rejected camera corrections | 3 | 13 |
| Mean tracking FPS after warmup | 28.488 | 38.235 |
| Mean camera capture FPS after warmup | 74.988 | 75.320 |
| Mean encoded video FPS after warmup | 35.740 | 40.008 |

The rate means omit the first two service samples: 22 HTTP samples and 23 stream
samples remain. These are separate short runs of a stationary pole, not guaranteed
rates under other scenes or client counts. The stream had zero encoder-history
truncations and zero pending-camera drops. The final rig was disabled and stopped
at home (`x=0`, flags 205, reference 370); SDK and encoder status became stale
after their producers closed.

Offline replay exactly reproduced final diagnostics and all final observation
values and timestamps. Only the observation sequence differed: 917 live versus
2748 in replay, because replay emits after each input event. See the
[measured results](../evidence/phase4/vision-service-20261015/live-shadow-stream-performance.json),
[replay check](../evidence/phase4/vision-service-20261015/live-shadow-stream-replay-check.json), and
[baseline and transport analysis](../evidence/phase3/retuning-20261015/sensing/monitor-http-performance-analysis.json).
The unchanged 30 ms interpolation-gap gate, explicit clock uncertainty, source
calibration requirements and shadow-only control status still apply. This test
establishes transport performance and reproducibility, not dynamic sensor accuracy.

## Neural policy sensor bindings

The development neural runner now shares the SDK provider, angular alignment and
fusion with `RigCartpoleEnv`. This is separate from the display-only shadow
packet. Train/export with an explicit modality, then use
`scripts/run-neural-policy --sensing-config PATH` for vision/fused actors.
The command defaults to stopped shadow inference. A camera binding is required
before opening serial; it never fabricates an upright reference from hanging.

The binding has this structure. The identifiers/measurements below must come
from the current setup; this is a construction guide, not a ready calibration:

```python
from cartpole_sdk.sensing.vision import calibration_fingerprint

reference = {'upright_raw': measured_saved_upright_raw,
             'firmware': actual_firmware_identity}
config = {
    'schema': 'cartpole-neural-sensing-v1',
    'stream_url': 'http://127.0.0.1:3090/api/sensing-stream',
    'vision_calibration': complete_camera_calibration,
    'encoder_reference': reference,
    'vision_alignment': {
        'source': 'vision', 'source_id': verified_camera_identity,
        'source_frame_id': 'camera-native',
        'source_calibration_id': calibration_fingerprint(complete_camera_calibration),
        'target_frame_id': 'physical-upright',
        'reference_id': direct_upright_capture_id,
        'zero_rad': measured_camera_theta_at_upright, 'sign': verified_camera_sign,
    },
    'encoder_alignment': {
        'source': 'magnetic', 'source_id': verified_encoder_identity,
        'source_frame_id': 'encoder-zero',
        'source_calibration_id': calibration_fingerprint(reference),
        'target_frame_id': 'physical-upright',
        'reference_id': direct_upright_capture_id,
        'zero_rad': measured_encoder_theta_at_same_upright,
        'sign': verified_encoder_sign,
    },
    'clock': {
        'source_clock_id': camera_host_clock_identity,
        'source_to_client_offset_ns': measured_camera_to_runner_host_offset,
        'source_mapping_established_ns': local_monotonic_time_when_checked,
        'source_mapping_valid_for_ns': chosen_bounded_lifetime,
        'board_receipt_delay_ns': declared_serial_transport_delay,
        'max_board_residual_ns': allowed_serial_receipt_jitter_and_drift,
        'max_camera_transport_ns': allowed_camera_publication_to_receipt_delay,
        'uncertainty_ns': measured_source_clock_mapping_uncertainty,
    },
}
# For vision-only angle/rate, encoder_alignment may be None. The rig's saved
# reference/configuration health remains checked for all motor execution.
```

Obtain a valid camera hanging calibration first, then record its `theta_rad`
while the pole is at the same directly measured upright reference used for the
magnetic anchor. Verify angular signs with a small manual rotation while the
motor is disabled. Changing camera calibration/geometry or the encoder reference
invalidates the binding. Existing natural-upright measurements are useful only
if their exact camera calibration and physical setup still match.

Run the reader on the same Jetson as the camera where possible: both processes
then share the host monotonic clock, making the source-to-client offset zero
under that explicit same-host/same-boot condition. A remote reader needs measured
clock mapping, for example bounded HTTP round-trip anchors; never reuse an old
host offset across boots. The source mapping expires within at most one hour.
The SDK anchors board time to the current session's serial receipt and checks
subsequent residuals. Source uncertainty plus allowed board residual must fit
within20ms. Those bounds delay camera eligibility and reduce effective freshness
conservatively; nominal camera timestamps remain unchanged for interpolation.
Camera publication/receipt checks also include source-clock uncertainty. None
of this establishes the camera's true exposure time from a host-read timestamp.

A bounded background stream reader prevents HTTP waits in the control loop.
Clock rollback, invalid calibration, changed source identity, stale data, queue
overflow or expired mappings fail explicitly. Vision mode never substitutes
magnetic angle/rate. Fused mode keeps a recent accepted bounded angle correction
on current magnetic data only until its age budget expires; rates remain magnetic.
All exported actors remain `hardware_accepted: false`.
