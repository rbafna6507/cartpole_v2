# Submitted-run recordings

Every claimed worker attempt creates a trusted recorder before connecting a backend. The submitted policy cannot access its files. If the recorder cannot initialize, the worker does not create or arm the backend. Setup errors, policy errors, cancellation, and successful runs all finalize a bundle when the worker remains alive. A process or power failure can leave a partial JSONL spool; it cannot guarantee a completed bundle. A job cancelled before a worker claims it has no experiment telemetry.

The worker stops/closes the backend and reports its outcome before packaging or uploading data. Artifact upload does not extend a motion lease or grant permission to run. A failed upload preserves the local spool and keeps `local_pending_upload` in both the queue and returned result. Automatic upload retry is not implemented. The portal's download endpoint checks job ownership; an operator may inspect all jobs. Worker uploads are bound to the original worker identity and lease token, even after the run has finished, to permit artifact delivery without renewed motion authority.

## Contents

`run.zip` contains exactly:

- `manifest.json`: artifact hash and run identity, outcome, recording counts and limits, SDK/Python versions, worker/recorder/sandbox source hashes, clock notes, coverage limitations, and telemetry SHA-256.
- `telemetry.jsonl`: session, initial backend diagnostics, complete SDK observations at control cadence, policy-call markers, requested acceleration and inference timing, optional sensing envelopes, and final outcome/backend diagnostics.

Each record has a worker-host `recorded_monotonic_ns`. Original observation clocks, sample timestamps, sources, calibration identifiers, validity, and filtered/raw channel labels are retained. Do not equate host monotonic time with a board or camera clock. The manifest includes a host wall-clock/monotonic pair for approximate external alignment; it does not claim hardware video synchronization.

Requested actions are not proof of physical actuation. Hardware records include the available board state, cached INFO, action limits, last accepted action, and timing. A cached INFO may be absent or older than the run. The worker does not issue extra serial queries to obtain a full gain/calibration snapshot. Simulation records include configuration and final executor/ground-truth diagnostics. No unavailable encoder counts, firmware samples, serial bytes, or applied force are fabricated.

## Bounds and failure behavior

The default telemetry budget is 12 MiB per attempt, with a 64 KiB maximum control record and an asynchronous scalar writer queue bounded by both 256 entries and 4 MiB. Optional sensing runs in a separate spawned process with its own 3 MiB spool and 1 MiB record limit. It shares no JSON parsing, serialization, or GIL with control. After the backend stops, complete sensing lines are appended within the overall budget; partial lines are discarded and reported. Scalar data takes priority, so sensing can consume at most 3 MiB and cannot displace the first 9 MiB of scalar data. The parent signals the child and uses bounded terminate/kill escalation after the run. Oversized records, queue saturation, and the byte ceiling increment `dropped_records`. Disk writing does not wait in the control loop. A nonzero drop count means the bundle is incomplete, even if the experiment succeeded. Write/flush failures are reported in the manifest. ZIP upload accepts at most 16 MiB, with only fixed, uncompressed members; the service never extracts supplied archives.

The persistent spool defaults to `<local queue root>/recording-spool` for local workers and `runs/portal-recordings` for remote workers. Override with `--recording-root PATH`. Each attempt has a unique private directory. Source spools and uploaded recordings are retained; automatic retention/garbage collection is not yet implemented. Monitor disk capacity during development. A worker crash may leave telemetry without a manifest; do not treat that as a complete bundle.

## Optional independent sensing capture

```sh
uv run --locked cartpole-worker --local-root runs/portal-dev/store \
  --rig-id sim --backend simulation --once \
  --sensing-url http://127.0.0.1:3090 \
  --recording-root runs/portal-recordings
```

`--sensing-url` is trusted worker configuration, never a submitted policy option. The spawned process subscribes independently to the new `/api/streams/ndjson` service at up to 30 Hz, preserving original envelopes, cursors, freshness and gap metadata. The service must have the developer-stream routes deployed. It does not support the old `/api/sensing-stream` endpoint. A camera connection failure is reported as unavailable and does not alter controller inputs or stop scalar recording. Sensing records are appended after scalar records rather than interleaved chronologically; use their preserved host timestamps for ordering. Sensing records share the telemetry budget; receipt counts do not prove every envelope was retained. Large envelopes may be dropped by the per-record limit.

Video files, camera RAW frames, user stdout/stderr archives, and synchronized video recording are not yet included. The portal live video tab is viewing, not recording. Optional reservation gating for a local worker is enabled with `--enable-reservations`; remote workers use the portal server's reservation configuration.
