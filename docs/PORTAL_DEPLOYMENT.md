# Deployed portal and interchangeable frontends

The API owns authentication, uploads, SQLite job/reservation state, immutable artifacts and run bundles. Independent Jetson workers pull jobs over authenticated HTTP on loopback. The browser never talks to serial or launches containers. Uploaded code runs only in the Bubblewrap child after namespace, seccomp and resource restrictions are installed.

## Hosting topology

Today `https://jetson.tail6f8113.ts.net` forwards through Tailscale Funnel to the loopback API on port 8780. That API also serves static UI assets. The independent frontend repository is https://github.com/rbafna6507/cartpole-portal.

For Vercel, import that repository with root `.`, build `node build.mjs`, no install command and no output-directory override. Set `CARTPOLE_API_ORIGIN=https://jetson.tail6f8113.ts.net`. Add the exact Vercel/custom HTTPS origin to `~/.config/cartpole-portal/service.json` on Jetson and restart `cartpole-portal.service`. Never put a bearer token in Vercel environment variables or compiled assets. Browser camera/API requests go directly to the authenticated API; video does not run through a Vercel function.

**No new database is needed when moving only the frontend.** SQLite remains durable on Jetson, and workers retain their loopback API address. Funnel is the API transport as well as the current UI host. To remove Funnel entirely, provide another HTTPS reverse proxy for this API or move the API/queue/artifact storage to a persistent hosted backend. Vercel static hosting alone cannot replace those services.

## Current validation status

All three upload formats pass public HTTPS simulation execution and ZIP download checks. Network access and infinite-loop submissions fail closed and return diagnostic recordings. The portal regression suite passes 196 tests locally (10 platform-dependent skips), with actual Linux sandbox checks performed separately.

Physical execution is still under commissioning: short runs can succeed, but intermittent IPC/control timing spikes trigger the firmware action-expiry guard even for zero-output scripts. The hardware worker is stopped pending diagnosis; do not treat this as unattended hardware service readiness. Its system unit is staged, not installed/enabled. No firmware deadline was relaxed.

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
.venv/bin/python deploy/portal/install-worker-service.py --python "$PWD/.venv/bin/python" --backend hardware --port /dev/serial/by-id/usb-Teensyduino_USB_Serial_20242870-if00
# Prepare the stopped/homed rig with commissioned switches before starting hardware:
systemctl --user start cartpole-worker-hardware.service
systemctl --user status cartpole-portal.service cartpole-worker-simulation.service cartpole-worker-hardware.service
sudo tailscale funnel --bg 8780
tailscale funnel status
```

The worker installer accepts `--python`, `--backend simulation|hardware`, hardware `--port`, `--start`, `--enable`, trusted `--max-acceleration`, `--numpy-root` and `--sandbox-cpu`. Start and boot enablement are separate. Worker `Restart=no` deliberately avoids an automatic retry after uncertain lease/rig state. The installer defaults to a conservative 0.25 m/s² demand ceiling; this is suitable for acceptance/data collection, not swing-up. The deployed worker is explicitly configured with `--max-acceleration 25` to support the existing learned actors, matching the existing firmware demand limit. Operators can set a validated ceiling up to 25 m/s² in trusted service configuration; submissions cannot override it. Firmware safety remains enforced.

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

Every attempted worker run creates a bounded recording, including failed runs when recording initialization succeeds. Download bundle contains `manifest.json` and `telemetry.jsonl`: original observation channels/timestamps, requested actions, inference durations (including failed policy attempts), backend diagnostics, outcome, software hashes and explicit coverage/drop information. Telemetry is capped at 12 MiB and ZIP at 16 MiB. Camera-derived measurements require a configured compatible developer-stream service; full video, serial bytes and firmware-internal samples are not included. A local spool survives upload/network failures; a missing remote bundle is not silently presented as complete.

## Reserved development and recovery

Reservations gate eligible physical jobs to their owner's time window; they do not grant SSH or bypass isolation/operator approval. For direct console experiments, stop the hardware worker first, and close the console before starting it again:

```bash
systemctl --user stop cartpole-worker-hardware.service
uv run cartpole
# Exit console, leave rig healthy/homed/stopped, then:
systemctl --user start cartpole-worker-hardware.service
```

An expired lease or unconfirmed STOP blocks the rig queue. Inspect the physical rig before operator recovery; restarting the service alone does not clear a blocked queue. Preserve private recording spools for diagnostics. Back up SQLite with its transactional backup mechanism plus artifacts/bundles; do not copy only a live database while ignoring WAL state. Configure retention before broad public enrollment: the current deployment uses invite tokens, bounded jobs/artifacts and local storage, not self-service accounts or unlimited archival storage.

## Realtime hardware worker

The hardware worker needs predictable scheduling to keep observation-anchored 20 ms actions fresh. The target unit in `deploy/portal/cartpole-worker-hardware.service` runs the trusted worker as `rbafna` with SCHED_RR priority 10 on CPU 4. Submitted processes are explicitly demoted to SCHED_OTHER before isolation and the harness verifies that state before importing code; seccomp does not allow changing scheduling. The isolated child is assigned CPU 5 with `--sandbox-cpu 5`, separating it from the realtime broker. The camera and API are assigned CPUs 0–3. Simulation does not require realtime scheduling.

The child uses system Python; its NumPy wheel must match that interpreter, independently of the API virtualenv. On this Jetson:

```bash
uv pip install --python /usr/bin/python3 --target /home/rbafna/cartpole-portal/sandbox-packages numpy==1.26.4
```

`--numpy-root /home/rbafna/cartpole-portal/sandbox-packages` mounts only NumPy and its bundled libraries read-only. Numeric actors retain the ordinary loader's provenance checks and use the existing prepacked float64 NumPy backend. No Torch or pickle is loaded.

For persistent realtime scheduling, install the staged system unit with administrator permission, after stopping any user/test hardware worker. Never run two hardware workers against the same device. The system unit is a target-specific template; review account, paths, port and CPU numbers before using it on another machine.
