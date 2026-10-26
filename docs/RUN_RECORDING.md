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

The default telemetry budget is 32 MiB per attempt, with a 64 KiB maximum control record and an asynchronous scalar writer queue bounded by both 2048 entries and 4 MiB. Optional sensing runs in a separate spawned process with its own 3 MiB standard or 8 MiB detailed spool and 1 MiB record limit. It shares no JSON parsing, serialization, or GIL with control. After the backend stops, complete sensing lines are appended within the overall budget; partial lines are discarded and reported. Scalar data takes priority: it is written first and sensing is appended only within the remaining overall budget, capped at 3 MiB standard or 8 MiB detailed. The parent signals the child and uses bounded terminate/kill escalation after the run. Oversized records, queue saturation, and the byte ceiling increment `dropped_records`. Disk writing does not wait in the control loop. A nonzero drop count means the bundle is incomplete, even if the experiment succeeded. Write/flush failures are reported in the manifest. ZIP upload accepts at most 40 MiB, with only fixed, uncompressed members; the service never extracts supplied archives.

The persistent spool defaults to `<local queue root>/recording-spool` for local workers and `runs/portal-recordings` for remote workers. Override with `--recording-root PATH`. Each attempt has a unique private directory. Source spools and uploaded recordings are retained; automatic retention/garbage collection is not yet implemented. Monitor disk capacity during development. A worker crash may leave telemetry without a manifest; do not treat that as a complete bundle.

## Optional independent sensing capture

```sh
uv run --locked cartpole-worker --local-root runs/portal-dev/store \
  --rig-id sim --backend simulation --once \
  --sensing-url http://127.0.0.1:3090 \
  --recording-root runs/portal-recordings
```

`--sensing-url` is trusted worker configuration, never a submitted policy URL.
Both modes retain the mandatory scalar trace and use the collector when configured.
`recording="standard"` (default) preserves existing latest-sample capture with limit 1
and a 3 MiB sensing cap. `recording="detailed"` requests up to 128 history samples
per stream per envelope with an 8 MiB cap, and adds cached decoded board-state
records on each observed hardware tick without extra serial queries. A missing
source is explicitly reported in manifest coverage. The spawned process subscribes independently to the new `/api/streams/ndjson` service at up to 30 Hz, preserving original envelopes, cursors, freshness and gap metadata. The service must have the developer-stream routes deployed. It does not support the old `/api/sensing-stream` endpoint. A camera connection failure is reported as unavailable and does not alter controller inputs or stop scalar recording. Sensing records are appended after scalar records rather than interleaved chronologically; use their preserved host timestamps for ordering. Sensing records share the telemetry budget; receipt counts do not prove every envelope was retained. Large envelopes may be dropped by the per-record limit.

Video files, camera RAW frames, user stdout/stderr archives, and synchronized video recording are not yet included. The portal live video tab is viewing, not recording. Optional reservation gating for a local worker is enabled with `--enable-reservations`; remote workers use the portal server's reservation configuration.

Decoded board records retain raw/filtered angles, cart estimates, demand, governor
feedback, fault/missed/dropped counters, and board/host timestamps available in
STATE telemetry. Cached INFO snapshots can contain native encoder counts and
configuration, but may be absent/stale and are not full-rate encoder capture.
A complete gain/parameter snapshot is not cached by the Rig client and is not
invented. These recording changes do not resolve USB link reliability or establish
hardware timing acceptance. The first post-arm policy observation is recorded
before its policy-call marker, including when the call subsequently fails.


## Export a downloaded bundle for replay and analysis

```bash
uv run --locked python -m cartpole_sdk.portal.dataset run.zip --output runs/dataset-001
# Optional external integrity pin and declared expected observation period:
uv run --locked python -m cartpole_sdk.portal.dataset other.zip --output runs/dataset-002 --sha256 EXPECTED_SHA256 --expected-period-ns 10000000
```

Output paths must be new. The exporter validates fixed ZIP members, limits, telemetry digest, recording counters and SDK session/observations. It preserves `manifest.json` and original `telemetry.jsonl`, writes normalized `observations.jsonl` for the SDK replay runner, a long-form `samples.csv` with each channel's units/source/validity/timestamps, `transitions.jsonl` with original action IDs/timestamps and next recorded observations, and `dataset.json` with coverage and outcome.

Identical latest-state duplicates are counted and collapsed only in replay/sample output; conflicting or reordered observations are rejected. Missing observations and time gaps are labelled rather than interpolated. An action is a request; subsequent motion is not proof that it was applied. Rewards, per-transition termination labels and physical applied-action certainty remain unspecified. A successful run with recording drops or errors is still incomplete. Failed setup can export metadata without a replay file when no session exists. This is a loss-aware analysis export, not automatically a valid offline-RL dataset.

`policy-inputs.jsonl` selects the observations referenced by actual `policy_call` markers, excluding preparation and terminal-only snapshots. Use this file for replaying the controller input sequence. `observations.jsonl` and the CSV retain all unique observations for analysis. Older traces without call markers fall back to action-request references and are explicitly not exact call replay; missing, repeated or reordered inputs are counted in `dataset.json`.

Detailed `board_state` events are independent latest cached snapshots. The reader
can receive a newer board tick after the SDK observation was selected.
`nearest_observation_sequence` is a nearby reference, not a guaranteed pairing;
`snapshot_matches_observation` compares that reference with `state.unwrapped_tick`.
Join only matching board ticks within the same session and preserve the state's
original `received_ns`/board timestamps. A mismatch is retained as evidence, never
relabeled or interpolated into the earlier observation.
