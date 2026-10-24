# Deployed portal and interchangeable frontends

The API owns authentication, uploads, SQLite job/reservation state, immutable artifacts and run bundles. Independent Jetson workers pull jobs over authenticated HTTP on loopback. The browser never talks to serial or launches containers. Uploaded code runs only in the Bubblewrap child after namespace, seccomp and resource restrictions are installed.

## Hosting topology

Today `https://jetson.tail6f8113.ts.net` forwards through Tailscale Funnel to the loopback API on port 8780. That API also serves static UI assets. The independent frontend repository is https://github.com/rbafna6507/cartpole-portal.

For Vercel, import that repository with root `.`, build `node build.mjs`, no install command and no output-directory override. Set `CARTPOLE_API_ORIGIN=https://jetson.tail6f8113.ts.net`. Add the exact Vercel/custom HTTPS origin to `~/.config/cartpole-portal/service.json` on Jetson and restart `cartpole-portal.service`. Never put a bearer token in Vercel environment variables or compiled assets. Browser camera/API requests go directly to the authenticated API; video does not run through a Vercel function.

**No new database is needed when moving only the frontend.** SQLite remains durable on Jetson, and workers retain their loopback API address. Funnel is the API transport as well as the current UI host. To remove Funnel entirely, provide another HTTPS reverse proxy for this API or move the API/queue/artifact storage to a persistent hosted backend. Vercel static hosting alone cannot replace those services.

## Current validation status

All three upload formats pass public HTTPS simulation execution and ZIP download checks. Network access and infinite-loop submissions fail closed and return diagnostic recordings. The portal regression suite passes 211 tests locally (15 platform/explicit realtime-supervisor skips), with actual Linux sandbox checks performed separately.

On 2026-10-24 the persistent system hardware worker was installed and started, with boot-time enablement deliberately still off. The operator's realtime test completed five isolation/abuse checks and three numeric-actor reset checks; each reset verified the inference hard/soft RTTIME limits were 500 ms. The worker SDK now matches executor-v7-vertical and the current deployment actor runtime pins.

Physical one-second smoke tests passed for all upload types:

| Upload | Job | Actions | Maximum inference | Result bundle SHA-256 |
| --- | --- | ---: | ---: | --- |
| Python zero-controller | `64a0f738afc04ec8a2788a86d7ac898e` | 96 | 2.40 ms | `796eb8f9519b78920065e2ededd0761e0653c662d6cd7178680e02499c36e54d` |
| ZIP zero-controller | `255dbad31e1142319cfd4212af2c0d8a` | 96 | 2.42 ms | `ceb047f8eb750c2320865ab9728332ccaa3eac75f791b1ae4738d00fe519daa1` |
| Current working numeric actor | `1a82c666f67a4b42a721b5bd2469529a` | 91 | 3.28 ms | `a15d9091657a6545a793f38e7909d7db9ffce772c827ce00f5865b3ca717693b` |

Every run confirmed STOP, ended without a board fault, and uploaded a downloadable ZIP with zero dropped records. ZIP and actor submissions/downloads traversed public HTTPS with the Vercel origin. The hardware queue returned idle and unblocked. These establish bounded end-to-end execution, not long-duration balancing performance or general acceptance of arbitrary controllers. Result metadata intentionally retains `physical_acceptance: false`; no firmware deadline was relaxed. The numeric test stopped the cart at approximately +0.193 m rather than automatically returning it to center.

The exact Vercel deployment origin is allowlisted; authenticated API and camera-preview requests from that origin pass. The deployment currently redirects anonymous visitors to Vercel sign-in. Browser UI execution behind that protection has not been independently verified. API authentication remains required regardless of frontend hosting.

## Installed paths and services

- Source/runtime: `/home/rbafna/cartpole-portal/source`, `.venv` underneath.
- Private configuration: `~/.config/cartpole-portal/service.json`, `credentials.json`, `submit-token`, `operator-token`, `worker-token` (0600).
- Queue/artifacts/bundles: `~/.local/state/cartpole-portal/store`.
- Private recording spools: `~/.local/state/cartpole-portal/{simulation,hardware}-recordings`.
- Services: `cartpole-portal.service`, `cartpole-worker-simulation.service`, `cartpole-worker-hardware.service`.

```bash
# On Jetson, from the source directory:
uv sync --locked --no-default-groups --extra sim --extra hardware --extra inference
.venv/bin/python deploy/portal/install-user-service.py --python "$PWD/.venv/bin/python"
.venv/bin/python deploy/portal/install-worker-service.py --python "$PWD/.venv/bin/python" --backend simulation --enable --start
# Use the commissioned system unit for the realtime hardware worker.
# Disable any previous user worker; never run both against the serial device.
systemctl --user disable --now cartpole-worker-hardware.service
sudo install -m 644 deploy/portal/cartpole-worker-hardware.service /etc/systemd/system/cartpole-worker-hardware.service
sudo systemctl daemon-reload
# Prepare the stopped/homed rig with commissioned switches before approving jobs.
sudo systemctl enable --now cartpole-worker-hardware.service
systemctl --user status cartpole-portal.service cartpole-worker-simulation.service
systemctl status cartpole-worker-hardware.service
sudo tailscale funnel --bg 8780
tailscale funnel status
```

The worker installer accepts `--python`, `--backend simulation|hardware`, hardware `--port`, `--start`, `--enable`, trusted `--max-acceleration`, `--numpy-root`, `--sandbox-cpu` and `--sandbox-realtime`. Start and boot enablement are separate. Worker `Restart=no` deliberately avoids an automatic retry after uncertain lease/rig state. The installer defaults to a conservative 0.25 m/s² demand ceiling; this is suitable for acceptance/data collection, not swing-up. The deployed worker is explicitly configured with `--max-acceleration 25` to support the existing learned actors, matching the existing firmware demand limit. Operators can set a validated ceiling up to 25 m/s² in trusted service configuration; submissions cannot override it. Firmware safety remains enforced.

## Submit, approve, execute and download

Retrieve the submit token privately with `ssh rbafna@jetson 'cat ~/.config/cartpole-portal/submit-token'`. Connect in the portal, select a format/source/duration and upload. Simulation jobs become eligible immediately. Hardware jobs require the separate operator token and approval of the exact artifact hash, source and duration. The worker never homes, clears faults, changes gains or disables switches for submitted code.

Supported formats:

| Format | Limit | Entry point |
|---|---:|---|
| UTF-8 Python `.py` | 64 KiB | `create_policy()` returning `reset(session)` / `act(observation)` |
| ZIP project `.zip` | 8 MiB uploaded, 32 MiB expanded, 256 entries | Root `policy.py`, same interface; local helper modules/data allowed |
| Numeric actor `.json` | 1,000,000 bytes | Existing validated Cartpole actor export, raw/filtered encoder input |

Storage admission also limits each owner to 512 lifetime jobs and 256 MiB of distinct uploaded artifacts, the store to 2 GiB/8192 artifact files, and preserves 256 MiB free disk before new uploads. Reusing the same artifact hash does not duplicate its byte charge. Quota rejection never deletes prior work.

ZIPs cannot contain links, special files, duplicate paths, traversal, encrypted entries or unsupported compression. Dependencies are the supplied Python standard library, SDK and explicitly mounted NumPy runtime; no `pip install`, shell commands or network dependency resolution occurs. PyTorch pickle/checkpoint and arbitrary model formats are not accepted. Numeric model shape/content validation is data-only; execution occurs inside the isolated process. Artifact inspection displays the file manifest or actor metadata, and operators can download exact submitted bytes for review.

Every attempted worker run creates a bounded recording, including failed runs when recording initialization succeeds. Download bundle contains `manifest.json` and `telemetry.jsonl`: original observation channels/timestamps, requested actions, inference durations (including failed policy attempts), backend diagnostics, outcome, software hashes and explicit coverage/drop information. Telemetry is capped at 32 MiB and ZIP at 40 MiB. The bounded writer queue holds up to 2,048 records so short storage stalls do not immediately discard control samples. Dropped records remain explicit in the manifest; a larger cap is not a guarantee of lossless capture. Camera-derived measurements require a configured compatible developer-stream service; full video, serial bytes and firmware-internal samples are not included. A local spool survives upload/network failures; a missing remote bundle is not silently presented as complete.

## Reserved development and recovery

Reservations gate eligible physical jobs to their owner's time window; they do not grant SSH or bypass isolation/operator approval. For direct console experiments, stop the hardware worker first, and close the console before starting it again:

```bash
sudo systemctl stop cartpole-worker-hardware.service
# From the operator release directory:
uv run cartpole
# Exit console, leave rig healthy/homed/stopped, then:
sudo systemctl start cartpole-worker-hardware.service
```

An expired lease or unconfirmed STOP blocks the rig queue. Inspect the physical rig before operator recovery; restarting the service alone does not clear a blocked queue. Preserve private recording spools for diagnostics. Back up SQLite with its transactional backup mechanism plus artifacts/bundles; do not copy only a live database while ignoring WAL state. Configure retention before broad public enrollment: the current deployment uses invite tokens, bounded jobs/artifacts and local storage, not self-service accounts or unlimited archival storage.

## Realtime hardware worker

The hardware worker needs predictable scheduling to keep observation-anchored 20 ms actions fresh. The target unit in `deploy/portal/cartpole-worker-hardware.service` runs the trusted worker as `rbafna` with SCHED_RR priority 10 on CPU 4. Submitted processes default to SCHED_OTHER. The explicit trusted `--sandbox-realtime` option instead requires a broker running exactly at RR10 on one CPU and a distinct dedicated child CPU; the launcher assigns the child RR1 and a hard priority ceiling of 1. The child remains unable to change scheduling or CPU affinity through the seccomp filter. The isolated child is assigned CPU 5 with `--sandbox-cpu 5`, separating it from the realtime broker. The camera and API are assigned CPUs 0–3. Simulation does not require realtime scheduling.

Realtime Python and ZIP children receive a hard 500 ms `RLIMIT_RTTIME` limit from the external launcher before Python starts. Data-only numeric actors receive a bounded 1.25 s startup ceiling; after loading and warming the actor, the trusted harness blocks for 1 ms to reset uninterrupted CPU accounting and permanently lowers both limits to 500 ms before reset acknowledgement. No uploaded Python executes under the larger allowance. The broker startup deadline remains 1.5 s. This limits uninterrupted realtime CPU use; blocking can reset that kernel accounting, so it is not a per-call wall limit. The trusted broker independently enforces the unchanged 10 ms policy-response deadline, startup deadline, total execution budget and process cleanup. Uploaded code cannot raise the externally installed hard limits. Firmware observation-anchored 20 ms expiry remains unchanged.

The child uses system Python; its NumPy wheel must match that interpreter, independently of the API virtualenv. On this Jetson:

```bash
uv pip install --python /usr/bin/python3 --target /home/rbafna/cartpole-portal/sandbox-packages numpy==1.26.4
```

`--numpy-root /home/rbafna/cartpole-portal/sandbox-packages` mounts only NumPy and its bundled libraries read-only. Numeric actors retain the ordinary loader's provenance checks and use the existing prepacked float64 NumPy backend. No Torch or pickle is loaded.

For persistent realtime scheduling, install the staged system unit with administrator permission, after stopping any user/test hardware worker. Never run two hardware workers against the same device. The system unit is a target-specific template; review account, paths, port and CPU numbers before using it on another machine.

## Actor startup investigation (2026-10-24)

Saved physical actor attempt `6b248056287743209fce0a5b3a98fe7f` failed before ARM with zero actions after 0.700 s. Replaying its exact artifact and recorded session without hardware under ordinary scheduling succeeded twice; the Python child consumed 1.016 s and 0.922 s CPU during startup. This supports, but does not yet prove, the 500 ms realtime startup ceiling as the cause. The actor-only two-phase ceiling requires an actual realtime replay before deployment acceptance. SSH sessions currently have `RLIMIT_RTPRIO=0`, noninteractive sudo is unavailable, and the system hardware unit is not installed; existing realtime console processes must not be reused or interrupted. Python/ZIP smoke results do not establish actor acceptance.

After staging the updated portal files on Jetson, run this offline validation with administrator authentication. It opens no serial device and does not start the hardware worker. Keep physical console tests idle during the realtime CPU checks.

```bash
bash /home/rbafna/cartpole-portal/source/deploy/portal/check-worker-realtime.sh
```

The wrapper requests administrator authentication only to create a bounded realtime supervisor running as `rbafna` on CPU 4; its isolated children use CPU 5. It stops on a failed check and never installs or starts the physical worker. Because noninteractive sudo is unavailable, the operator must run this command interactively on Jetson.

Require all five isolation/abuse tests and all three actor reset checks to pass before a physical actor acceptance run. The saved actor's provenance is checked by the existing isolated loader. Installation commands above remain separate from validation; starting/enabling the hardware service requires closing the console and ensuring the stopped rig is healthy and homed.

The offline helper uses `LimitRTPRIO=10` plus `chrt --rr 10`, rather than transient `CPUSchedulingPolicy`/`CPUSchedulingPriority` properties: systemd 249 on this Jetson rejects the latter combination before execution. The trusted supervisor still runs as `rbafna` at RR10; child isolation and budgets are unchanged.

After the v7 SDK update, the offline helper uses the current `policies/working.json` deployment copy with the recorded session. The archived actor remains unchanged; its old runtime pins intentionally reject the updated SDK.


## Preparation and execution authority (2026-10-24)

The hosted API uses one `RuntimeStore` owner per queue directory, enforced by an
exclusive process lock. SQLite remains the durable job, approval and result store.
It is not accessed by active-run heartbeat renewal.

1. Claim reserves the job and exclusive rig access for at most 35 seconds of
   **unarmed preparation**. This is a preparation reservation, not permission to
   move. It does not require the short execution heartbeat. The worker downloads
   and hashes the artifact before opening the rig, checks the stopped hardware,
   prepares the upload, launches the isolated child, and obtains its reset ACK.
2. Only after readiness does `start` durably mark the run. Once that commit
   completes, the API publishes a fresh in-memory execution authority. A final
   heartbeat must return promptly and leave enough time for the entire requested
   run before the worker can ARM. Slow setup never subtracts from requested motion
   duration. The unarmed start request has a bounded 30-second network budget.
3. The sandbox has a separate 35-second preparation watchdog. Its execution timer
   starts through the trusted broker's one-shot `begin_run()` immediately before
   ARM. Reset and action IPC deadlines, resource limits, filesystem/network
   isolation, and the firmware action lifetime remain enforced.
4. During execution, heartbeats run every 250 ms. The worker stops after one second
   without confirmed fresh authority; server authority expires after two seconds.
   Monotonic clocks enforce renewal and the fixed run deadline. Heartbeats do not
   wait for SQLite writes, artifact synchronization, or recording uploads.
5. Cancellation becomes sticky in memory before its durable write. API shutdown
   revokes its authorities and drains open database connections before releasing
   ownership. Restart cannot reconstruct execution permission from a database row:
   prior running jobs fail closed and require physical STOP confirmation/recovery.

The legacy direct `Store` remains available for offline queue tests and local
simulation; the deployed `cartpole_sdk.portal.host` selects `RuntimeStore`.
Do not run multiple APIs or directly mutate an active hosted queue through a
second `Store` process. Use the authenticated API.

### Diagnostic evidence and remaining acceptance

On 2026-10-24 an unchanged working actor balanced for approximately 32.74 seconds
within a 35.9-second worker run before runtime authority expired. A subsequent
55-second zero-command test completed 5,497 actions with STOP confirmed and no
firmware fault. Its repeat expired before any action while an API thread spent
several seconds in `wait_on_page_bit_common` and `jbd2_log_wait_commit`. Separate
stack captures located durable SQLite commits and artifact synchronization in
these storage waits. This motivated separating runtime authority from storage;
changing controller gains or policy weights was not indicated by this evidence.

These observations do **not** establish physical acceptance of the new runtime
path. A complete 55-second policy run and its downloadable recording must be
verified after deployment. The 55-second diagnostic under the previous recording
cap omitted 1,410 records; its original manifest preserves that limitation.

Verification before hardware restart: 209 portal tests passed locally (15
platform-dependent skips), followed by 28 focused runtime/reservation tests after
adding the slow-commit reservation guard. On the Jetson, 59 targeted tests passed,
including actual bwrap isolation (two skips). The historical
`evidence/phase5/learned-policy-simulation.py` integration fixture was excluded:
its frozen SDK hashes differ in four files predating this change; it was not
rewritten to conceal that mismatch. In a separate Jetson HTTP diagnostic, all 30
heartbeats succeeded while the SQLite writer lock was held for 3.212 seconds;
maximum heartbeat latency was 14.43 ms. No hardware was opened by that diagnostic.

After staging an update, run the privileged offline checks and start the worker:

```bash
bash ~/cartpole-portal/source/deploy/portal/check-worker-realtime.sh && sudo systemctl restart cartpole-worker-hardware.service
```

The offline script does not open the rig. Physical acceptance remains a separate
portal submission after this command succeeds.

### Public camera playback recovery (2026-10-24)

The viewer falls back to authenticated JPEG previews after seven seconds without decoded video, without waiting for network read/cancellation promises to settle. JPEG transfers have a 15-second timeout. The deployed Jetson presentation settings are `VISION_VIDEO_FPS=15` and `VISION_VIDEO_BITRATE=80` in `~/.config/cartpole-vision/runtime.env`; capture remains configured at 80 Hz. The previous environment is saved as `runtime.env.before-public-video-20261024`. Restart `cartpole-vision.service` with `systemctl --user restart cartpole-vision.service` after changing these settings. No SSH forwarding is needed for the public Funnel page. Vercel needs a new deployment to receive frontend fixes.

Public-path diagnosis: camera and portal loopback each delivered 61 frames in 3.0 seconds at 20 fps. Through Funnel at 600 kbps, frame 40 arrived 13.77 seconds after request start with only 1.956 seconds of encoded video: 7.982 seconds of accumulated delay after the first frame. The player reconnects when that delay exceeds 1.5 seconds. At 80 kbps / 15 fps, a 20-second public test received 270 frames representing 17.906 seconds, with no accumulating delay. Vercel displayed decoded H.264 camera and tracking video. This setting trades visible compression for realtime delivery over the currently constrained public path; it does not reduce camera capture or tracking resolution/rate. Authentication and CORS were successful. The specific cause of the public-path bandwidth constraint is not yet established.
