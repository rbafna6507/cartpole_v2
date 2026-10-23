# Read-only developer streams and dataset collection

`cartpole-collect` (`python -m cartpole_sdk.sensing.collect`) writes original source values and timestamps to stdout or a **new** JSONL file. It never sends motion, calibration or configuration commands. CLI entrypoint: `cartpole_sdk.sensing.collect:main`.

## Existing running service: collect without restarting the camera

With the existing observation service forwarded to localhost:3090:

```sh
cartpole-collect --legacy-sensing --duration 30 --output capture-v1.jsonl
cartpole-collect --legacy-sensing --duration 10 | jq -c '.encoder.packets[]'
```

Explicit legacy mode reads `/api/sensing-stream` and preserves its v1 envelopes unchanged. It includes vision and board telemetry only, **not SDK shadow**. Stream selection and new cursor maps are unavailable in legacy mode. Existing `/api/sdk-state` remains a separate read-only SDK snapshot/history source. No automatic silent fallback or service restart occurs.

## New endpoint (requires deploying this service version)

`GET /api/streams` returns the capability catalog. `GET /api/streams/ndjson` returns `cartpole-developer-stream-v1` envelopes with selected `channels` and resumable `cursors`.

```sh
curl -fsS http://127.0.0.1:3090/api/streams | jq
cartpole-collect --streams vision.raw,vision.processed,board.telemetry,sdk.shadow --duration 30 --output run.jsonl
cartpole-collect --streams sdk.shadow --duration 30 | jq -c '.channels["sdk.shadow"].samples[]'
```

| Selectable channel | Actual data and retention |
| --- | --- |
| `vision.raw` | Latest image-space angle, pivot/bob, length, confidence, detection/cart-template state; camera `seq` and original host-read `t`. This is detector output, not raw sensor pixels. |
| `vision.processed` | Complete latest estimator result: calibrated angle, cart position, fitted rates, effective rate timestamps, fit uncertainty, validity, timing and diagnostic fields. The angle is calibrated geometry; do not assume a separate low-pass angle filter. |
| `board.telemetry` | Original decoded publishing packets including all optional raw/filtered angle, rate, position, motion/governor and health fields actually present. Up to 2048 packets/5 seconds. Includes optional `sdk_info` diagnostic `encoder_raw` counts with `diagnostic_received_ns` provenance, when present. Those diagnostics are not per-state encoder measurements. No native counts are invented. |
| `comparison.encoder` | Sign-adjusted angle after board-clock mapping, with gap markers; legacy display comparison, not SDK control fusion. |
| `comparison.fused` | Legacy display fused angle/source at its original fusion timestamp; shares comparison history up to 4096 rows/15 seconds. |
| `sdk.shadow` | Complete original SDK observation packets, source-explicit samples, filtered/fused outputs and diagnostics; up to 2048 packets/15 seconds. Keeps session, clock, sample availability/effective times and commissioning flags unchanged. |

Image resources are separately cataloged: `/snapshot.png` is the latest **undecorated decoded frame**, PNG encoded; `/preview.jpg` is a lossy presentation preview; `/preview.jpg?mask=1` is a lossy detector mask preview; `/video.h264` is encoded presentation video with the existing configured overlays. They are separate binary resources, not base64 NDJSON channels. None is sensor-native Bayer/RAW. PNG snapshots have a freshness gate and no timestamp/sequence pairing contract, so they cannot establish a synchronized image dataset by themselves. Original serial bytes and per-state native encoder counts are unavailable in this service. An upright count/reference is not a native-count observation stream.

## Bounds, cursors and limitations

The HTTP stream accepts `streams` (comma-separated catalog ids), `duration` (.001–3600 seconds, default 30), `max_hz` (1–100, default 30), `limit` (1–128 rows per channel/envelope), and `cursors` (JSON object, at most 4096 characters). Copy the final envelope's `cursors` into `--cursors '…'` to resume. Cursors are per channel, include source identity and sequence, and reset on identity changes. SDK identity includes calibration/frame identifiers; board identity includes generation/upright reference. Empty heartbeat batches do not become fake measurements.

Each channel is bounded to 512 KiB per envelope; excess retained samples remain pending (`more: true`) until subsequent pulls. Four subscribers share the existing sensing connection budget; a fifth receives HTTP 429. Serialization and network output occur outside acquisition locks. Requests read bounded histories and latest state; no subscription adds work to the control loop. Slow subscribers can miss data when source histories expire.

`reset` means the cursor identity/history position cannot be continued; `gap` marks a sequence discontinuity against the oldest retained sample. Vision uses latest-only sampling: missed frames cannot be recovered, even though the dashboard retains a reduced chart history. Comparison sequences share a counter with other updates: their `gap` is null (unknown) and `sequence_discontinuity` only reports skipped numbers, never proven sample loss. Camera channels report present `age_s` and stale status separately from the untouched original observation; comparison channels retain their complete producer status. SDK or board sequence gaps can originate upstream. This interface is **not lossless** and makes no transport completeness claim. Channel status can be `no_samples`, `stale`, `not_configured` or a producer SDK status; validity and health in original samples remain authoritative.

CLI additionally bounds output by `--max-records` (default 100000) and `--max-bytes` (default 256 MiB). It never truncates an existing output file, fabricates missing channels, automatically retries or rewrites clocks. HTTP response/header reads use an absolute run deadline. Output to a blocked stdout/file can still block; consumers must drain their pipe. Broken pipes terminate collection. Zero complete records exits nonzero with a no-data message; a short duration may expire before a large initial legacy history envelope arrives. On disconnection, inspect the final complete record/cursor and explicitly resume; expiration cannot reconstruct dropped history.

These are read-only endpoints under the observation service's existing access boundary. They introduce no authentication bypass, public exposure or arbitrary URL proxy. The collector's URL is a client-side service origin.
