# Policy submission portal and isolated pull worker

The portal accepts one immutable Python source file, queues an owner-bound run,
and publishes its bounded result. The trusted worker pulls jobs outbound and
alone owns simulation or a live Rig. Uploaded Python is imported only inside the
Linux Bubblewrap child after filesystem, resource and seccomp restrictions are
installed. There is no unsandboxed execution fallback.

The implementation is loopback-first and is not a deployed public service.
Public hosting still needs reverse-proxy TLS, account/key provisioning, operational
monitoring, disk retention/backups, and target isolation acceptance. Physical
queue runs additionally need commissioned switches and an operator-prepared
homed, healthy, stopped rig. Simulation results never mark a policy physically
accepted. The simulation bridge uses the separate raw-demand ExecutorSimulation
wrapper, with its binary32 1kHz governor, held leases and expiry faults at a 100Hz
policy rate; it does not silently treat raw demand as directly executed acceleration.

## Portal startup

Create a private credential file. Keys should be independently generated random
secrets (at least 32 bytes); each value assigns an immutable principal and role:

```json
{
  "REPLACE_WITH_RANDOM_SUBMISSION_SECRET": ["alice", "submit"],
  "REPLACE_WITH_RANDOM_WORKER_SECRET": ["jetson-worker", "worker"],
  "REPLACE_WITH_RANDOM_OPERATOR_SECRET": ["operator", "operator"]
}
```

Protect that file with mode 0600 and keep it outside the web root. Credentials are
operator configuration; do not use the example placeholder values in operation.

```sh
python examples/portal.py --root runs/portal \
  --credentials /private/config/portal-credentials.json
```

The default address is `http://127.0.0.1:8765`. Open it and enter the submission
token. The browser keeps the bearer token in `sessionStorage` for that tab, never
in URLs, embedded HTML or localStorage. “Forget token” removes it. Uploaded names,
status and results are inserted with `textContent`. No wildcard CORS is enabled.
An explicit `--host` changes binding; `--origin https://your-host.example` permits
that browser origin behind a configured TLS proxy. Remote workers require HTTPS;
plain HTTP is accepted only for localhost. Worker requests reject redirects and
enforce an absolute deadline across connection, headers and body, so a redirect
cannot forward a bearer token to another origin or a slow response prolong a lease.

The interface offers explicit **Simulation sensors** and **Magnetic pole +
estimated cart steps** source selections, a 0.05..60s duration, file upload, a run
ledger, cancellation requests and result inspection. It does not contain operator
home/center/switch/fault-clear controls.

A source is one UTF-8 `.py` file, 1..65536 bytes. Archive, pickle, path traversal,
symlink artifact redirection, NUL, nonfinite JSON and unexpected fields are rejected.
The artifact is SHA256-addressed, created with exclusive/no-follow file operations,
read-only on disk, and verified again before execution. Owner queue capacity is
32 active/pending jobs; refused uploads do not create extra artifact blobs.

## Physical run approval

Each physical submission starts in `awaiting_approval`. An authenticated operator
can use the same UI with an operator token to inspect the immutable job, read its source with **Inspect source**, and click
**Approve physical run**. The request includes its exact `artifact` SHA-256,
`sensor_source` and `duration`. A changed or mismatched review is rejected. The
queue records `approved_by` and `approved_at`, then permits the worker to claim
it. Repeating approval before claim is idempotent and preserves the first receipt.
Submission and worker credentials cannot approve. Pending physical jobs from older
databases are migrated to awaiting approval; existing claimed/running leases are
not rewritten. Waiting jobs count toward the owner quota and can be cancelled.
Approval is a scheduling decision, not physical homing/arming or acceptance.

See the [controller developer guide](CONTROLLER_DEVELOPER_GUIDE.md) for raw versus
filtered data, clock semantics and current training/portal parity limitations.

## Policy contract

```python
from cartpole_sdk.contracts import Acceleration

class Policy:
    def reset(self, session):
        self.session = session

    def act(self, observation):
        # A benign example, not swing-up/balance acceptance.
        return Acceleration(0.0)

def create_policy():
    return Policy()
```

The child receives SDK Session and Observation dataclasses containing only the
selected sources. Simulation retains `simulation` provenance and
`sim:upright+x` frame. Physical selection retains magnetic `encoder-zero` and
step `cart-step-home` frames; step position is estimated and velocity is commanded.
The child receives no Rig, serial device, operator API object, bearer token, host
credentials, model deserializer or Docker socket.

A return value is `Acceleration` or `None`. The broker independently validates
strict numeric finite demand, rejects booleans, and enforces the trusted worker ceiling: 25m/s² by default for simulation and
0.25m/s² by default for hardware. An operator may explicitly set
`--max-acceleration X`, finite and within (0,25], in worker configuration. Submitted
jobs and policy output cannot choose or override this ceiling. The same value is
checked in the sandbox channel and independently in the broker, and recorded in
the result.
It assigns the actual session/clock/sequence and a 20ms expiry anchored to the
observed board snapshot. PING cannot renew an action. None submits no new request;
it does not keep a physical external lease alive. Exceptions, malformed messages,
oversized output, floods, crashes, stale observations and inference deadlines end
the job and request STOP; no replacement zero-action continuation occurs.

The strict 1kHz reference policy is not chosen or retimed by the queue. Physical
board reference modes remain separate operator-console commands.

## Worker startup

On the actual Linux target, install Bubblewrap and libseccomp plus the SDK and
simulation optional dependencies as appropriate. The launcher defaults to an
explicit `/usr` runtime and `/usr/bin/python3`, the readonly SDK package directory,
and the one artifact. A custom minimal runtime can be supplied through the trusted
Sandbox constructor; symlinked project venvs are not automatically mounted into
the child. The broker environment may use a venv, while the child uses the specified
system Python with `-I -S` and an explicit readonly SDK path.

A local isolated simulation worker is:

```sh
python examples/portal_worker.py --local-root runs/portal \
  --worker jetson-worker --rig-id simulation-1 --backend simulation --once
```

An outbound pull worker is:

```sh
python examples/portal_worker.py --portal https://portal.example \
  --token-file /private/config/worker-token --worker jetson-worker \
  --rig-id simulation-1 --backend simulation
```

Remove `--once` to poll repeatedly. A physical worker uses `--backend hardware
--port /dev/serial/by-id/usb-Teensy_example --rig-id cartpole-1`. It requires
positive streaming telemetry and healthy homed enabled-switch-profile idle state
before reset/arm. It never calls CENTER, HOME, SWITCHES-off, fault CLEAR or trusted
board MODE on behalf of submissions. The operator prepares the physical rig using
the separate console and completes actual switch commissioning before enabling
hardware queue operation. No private commissioning override is provided by default.

The worker verifies the downloaded SHA256, launches the restricted child,
requires reset acknowledgment, transactionally marks the job running, then
revalidates the current lease and identity before explicitly arming. Start and
final authority responses must each return within 250ms, including local lock wait
or remote latency; an old response does not authorize motion. The motion
budget starts before the start request so a delayed reply cannot extend it. The worker assigns action sequence and lease fields; the child
cannot extend the fixed duration. A shared source-aware budget derives execution
wall time from the immutable job and validated worker backend: simulation gets
2× the requested simulation horizon (at most 120s), while physical execution keeps
the requested duration (at most 60s). Queue deadline, worker guard and sandbox wall
watcher use this same budget plus their existing bounded startup/finish margins.
There is no submitted wall-budget field. The 10ms action deadline is unchanged. Physical runs stop slightly before the MCU hard
duration deadline. Result fields include backend/source, stopped confirmation,
action/observation counts, approved ceiling, maximum absolute raw demand, maximum
inference time, elapsed wall time, final simulated ground truth and distinct
simulation or board diagnostics. `physical_acceptance` remains false.

## Isolation profile

The target's Bubblewrap 0.6.1 does not support bounded-size tmpfs. This implementation
therefore uses an **entirely readonly filesystem**: `/tmp` is an empty readonly
directory, `/dev/shm` is absent, and uploaded code cannot create temporary files.
Readonly `/usr`, SDK, source and private readonly proc are mounted. Only `/dev/null`
and `/dev/urandom` are bound; serial devices, home, `/etc`, `/run`, `/sys`, host
network and host credentials are absent. Root is remounted readonly after all
mounts. `--unshare-all` plus explicit user/PID/network unsharing, new session,
die-with-parent, dropped capabilities and closed inherited file descriptors are
required. Launch errors are failures, never reasons to run the policy on the host.

The child installs `no_new_privs`, then a libseccomp default-deny filter resolving
syscall **names** on the actual architecture. Only the syscalls needed for readonly
Python inference, memory management, time and pipe IPC are allowed. Fork, clone,
exec, sockets, ptrace, mounts, namespace changes, process_vm and io_uring are denied.
Resource hard+soft limits cover CPU, 512MiB address space, 1MiB per-file size,
32 file descriptors, zero child processes and zero core dumps. A parent wall
watcher independently kills an idle/stalled child; each action defaults to a
10ms response deadline. Startup/reset is bounded to 1.5s.

The child runs single-threaded; OPENBLAS/OMP thread counts are one. An optional
explicit readonly NumPy package/library mount is supported through the trusted
Sandbox constructor, but import and inference must pass the target syscall and
memory tests. No arbitrary site-packages or project home directory is mounted.
The pure Python contract/example needs no NumPy. Code requiring writable caches,
subprocesses, threads, devices or network must be adapted; those capabilities are
not silently restored.

JSONL IPC input is bounded to 64KiB; output lines to 4KiB. Stdout is capped at
1MiB/run, stderr at 16KiB/run, and the output queue holds at most eight lines.
Malformed/duplicate/nonfinite JSON, unsolicited floods, wrong sequence and invalid
reset ACKs fail closed. Pipe writes and reads have deadlines; shutdown kills the
process group, kills the launcher if necessary, reaps it and closes pipes. stderr
is drained with a quota and is not exposed as an uploaded exception traceback.
`PolicyChannel.stderr_tail` retains only the last 4KiB for trusted local debugging;
it is never copied into owner-visible queue results or API responses.

## Queue and recovery semantics

SQLite transactions atomically bind job ownership and idempotency keys, claim one
job per rig identifier, and store the worker's secret lease token. The owner API
never returns that token. Different worker source capabilities claim only eligible
jobs. Pending/claimed/running/succeeded/failed/cancelled transitions are durable.
Heartbeats renew a short claim lease only up to a fixed deadline; a running deadline
is assigned once and cannot be prolonged by a policy.

Cancellation of pending work is immediate. Active cancellation is a stop request
for the trusted worker; the rig lease remains held until STOP is confirmed or
recovery marks it uncertain. Expired claimed work fails without retry. Expired
running work fails and **blocks the rig** because physical motion cannot be assumed
stopped after a worker crash. A new worker does not blindly retry or clear faults.
Before recovering a hardware job, the operator must terminate the prior worker
and its process group, or quarantine it so that it cannot resume or access the
serial rig. Then the operator must verify the physical rig is stopped. A paused
worker (for example SIGSTOP) can resume after any age check; response freshness
is not a fencing mechanism. Only after both worker containment and physical stop
are verified may the operator call the authenticated rig recovery API with
`stopped_confirmed: true`. This assertion attests that the full recovery workflow
has been completed; it is never a request to blindly release an uncertain lease. This queue assertion does not
perform physical recovery itself.

A failed queue/network call does not grant further control. Hardware action expiry
remains enforced by the MCU independently of HTTP timing. Slow network/IPC may
therefore fail a run; successful local simulation or pipe tests do not certify
hardware timing. All physical identification/controller acceptance remains a
separate measured gate.

## API

Every `/api` endpoint requires `Authorization: Bearer <token>`.

| Endpoint | Role | Action |
| --- | --- | --- |
| `GET /api/me` | authenticated | own principal and role |
| `POST /api/jobs/<id>/approve` | operator | exact artifact, sensor_source, duration approval |
| `POST /api/jobs` | submit | source, filename, sensor_source, duration, idempotency_key |
| `GET /api/jobs` | submit/operator | own jobs / all jobs |
| `GET /api/jobs/<id>` | submit/operator | own result / operator inspection |
| `POST /api/jobs/<id>/cancel` | submit | request cancellation of own job |
| `POST /api/claim` | worker | rig and optional sensor_source capability |
| `GET /api/jobs/<id>/artifact` | operator or assigned worker | verified source as bounded base64; operator may inspect before approval |
| `POST /api/jobs/<id>/start` | worker | lease token after child reset ACK |
| `POST /api/jobs/<id>/heartbeat` | worker | lease token, fixed deadline retained |
| `POST /api/jobs/<id>/finish` | worker | lease, terminal status, bounded result |
| `POST /api/rigs/<id>/recover` | operator | explicit stopped_confirmed assertion |

JSON requests use exact fields and at most 100KB bodies. HTTP header lines,
aggregate headers, body reads and the absolute 3s connection budget are bounded; at most sixteen
handlers run concurrently. Same-origin browser mutations are required when an
Origin header is present. The service intentionally has no file-serving traversal,
uploaded source in HTML, broad CORS, anonymous API access, shell invocation, or
raw serial forwarding.

## Evidence

Run `python -m unittest discover -s tests -p 'test_portal*.py'`. Local tests cover
queue races/recovery/ownership/idempotency/path/quota, real authenticated HTTP,
real bounded pipe IPC, simulation broker behavior and a PTY-only hardware bridge.
Linux-only tests in `test_portal_sandbox.py` attempt host-home/serial/network access,
readonly `/tmp` and `/dev/shm` writes, fork/exec, CPU/memory abuse and output floods.
They skip where Bubblewrap is unavailable; a skip is not isolation acceptance.
Parent target validation, actual hardware policy timing, switches, hosting and
operational rollout are separately recorded gates.

Target sandbox validation (2026-10-13): Linux 5.15.148-tegra aarch64,
Bubblewrap 0.6.1, broker CPython 3.11.17, system child Python 3.10,
libseccomp.so.2. Ten sandbox test methods ran: nine passed and one expected missing-runtime
case skipped because the runtime is present. Network/fork/exec cases assert actual
EPERM rather than relying on timeout; isolation tests use a test-only 250ms action
deadline to avoid conflating cold imports with denial. Production stays at 10ms.
The preserved log is [evidence/phase6/portal-linux-tests.log](../evidence/phase6/portal-linux-tests.log).
No physical portal policy run was performed in that historical validation. Switches were subsequently commissioned; this does not by itself qualify physical portal execution.

## Local development preview

```sh
uv run --locked cartpole-portal-dev --root runs/portal-dev --port 8765
```

Open http://127.0.0.1:8765 and select `runs/portal-dev/credentials.json` using
**Load local credentials file**. Choose Submitter or Operator to exercise both
roles. The file persists across restarts, is mode 0600 and contains separate
random credentials; it stays outside Git. This local-only launcher creates no
worker credential and starts no execution worker. Do not host this development
credential workflow on Vercel. The production authenticated API still requires
explicit credentials and does not expose the local-preview metadata endpoint.

`--root` defaults to `runs/portal-dev`; `--port` defaults to 8765. Binding is always
127.0.0.1. Keep the process running; Ctrl-C stops it without deleting the queue.
The existing camera service can be viewed through `scripts/vision-tunnel.sh` at
http://127.0.0.1:3090. This SSH tunnel is independent of the local portal.

Submitted policies now receive all available control-observation samples, while
the worker still validates its required channels. Hardware provides unfiltered
and filtered angle plus governor feedback; simulation retains simulation
provenance and its available governor feedback. This does not yet make the generic
simulator the fitted learned-policy Gym environment, or authorize vision/fused
physical control.

## Experiment workspace, recordings and reservations (October 23 follow-up)

The browser has four views: **Experiments**, **Live view**, **Run data**, and
**Reservations**. The local preview enables reservations and configures the camera
origin at `http://127.0.0.1:3090`. It still starts no worker and cannot execute a
submission by itself. Only `.py` submissions are currently accepted; ZIP packages
and numeric policy upload are not implemented.

### Automatic run bundles

See [the recording schema and recovery guide](RUN_RECORDING.md) for detailed record types and spool handling.

Each claimed run attempts to create a trusted recorder before preparing the
backend. Recorder initialization failure prevents execution. The sandbox never
receives recorder file handles. A bounded queue sends records to a separate disk
writer; overflow or byte-budget exhaustion increments reported drop counts rather
than blocking control. This records control-cadence observations, requested actions,
policy-call timing, session metadata, available initial/final diagnostics, software
source identities and outcome. A requested action is not proof of motor application:
use the available governor/board feedback with its own timestamps.

The worker stops the backend and finishes the job before packaging or uploading.
A persistent local spool survives upload failure. Downloadable ZIPs contain only
`manifest.json` and `telemetry.jsonl`; the server never extracts uploads. Telemetry
is bounded to 12 MiB, ZIPs to 16 MiB, and the manifest describes limits, missing
sources, drops and errors. Owner and operator credentials can download a run;
other submitters and workers cannot download its recording through this API.
Worker upload is bound to the exact retained job/worker/lease and policy hash and
cannot approve, restart, or extend execution. Identical upload retries are allowed;
a different replacement is rejected.

A failed run can still have a useful recording. A process kill may leave only the
local partial spool; automatic crash recovery and remote re-upload scheduling are
not implemented. A queued job cancelled before it is claimed has no sensor run to
record. Video is not saved in these bundles yet. Native raw encoder counts, every
internal 1 kHz firmware sample, and serial bytes are not invented when unavailable.

Optional `--sensing-url` records original developer-stream envelopes on a separate
background connection. It requires the new `/api/streams/ndjson` service version;
the currently running Jetson service must be upgraded before using this option.
It shares the bounded telemetry budget and reports connection errors/drop counts.
Vision data does not feed policy control merely because it is recorded. Live video
preview and optional scalar sensing collection are independent features.

### Optional reservations

The API server enables reservations only with `--enable-reservations`. Local
workers opening the SQLite store directly must also pass `--enable-reservations`;
outbound workers rely on the server's setting. The browser exposes availability,
booking, owner cancellation, and a reservation selector for physical submissions.
The development launcher enables the option to make it testable.

A reservation is an exclusive window of 1–30 minutes, at most seven days ahead.
The browser currently offers 30-minute sessions. Up to eight future/active windows
per owner are permitted. Overlapping bookings on the same rig are rejected in a
SQLite transaction. The server's `--rig-id` is the reservable rig; use the same ID
on its hardware worker. Simulation does not require a reservation.

Physical jobs can optionally bind to an owned reservation. Claims must match its
rig, owner, active window and remaining duration, with setup/stop margin. Start
rechecks eligibility. An unreserved physical job cannot cross into any reserved
window. Existing reservations remain exclusionary if the server is restarted with
the feature disabled; bound jobs do not execute while disabled. A reservation
cannot be cancelled while one of its jobs is claimed/running, and a new booking
cannot displace an active experiment. Cancellation does not silently unbind queued
jobs: cancel those jobs and resubmit explicitly if needed.

A reservation never grants shell/device access, extends the maximum 60-second run,
bypasses physical approval, or keeps the motor enabled between runs.

### Camera presentation

`--camera-url` configures a camera service origin independently of the controller.
The Live view uses the existing H.264 WebCodecs format through the authenticated
`/api/video` relay, with a sampled `/preview.jpg` fallback. It pauses when leaving
the view and never embeds camera calibration or operator controls. The relay
requests only the fixed `/video.h264` resource, never forwards portal credentials,
limits viewers to four, and ends connections after 60 seconds or 64 MiB; the player
reconnects. It does not follow upstream redirects. The page's content policy allows images/media only from that
configured origin and itself. Video viewing does not create a saved recording. The backend must reach the
configured camera origin for H.264; the JPEG fallback additionally requires browser
reachability and HTTPS when the portal is HTTPS. The development server relay is
not a Vercel edge video distribution service; production deployment needs an
authenticated long-lived video service or equivalent. The existing SSH tunnel is
suitable for local development only.

### Additional API routes

All routes below require bearer authentication; mutation Origin checks still apply.

| Route | Authorization and payload |
|---|---|
| `GET /api/video` | Submitter/operator; bounded H.264 stream from the configured camera |
| `GET /api/config` | Authenticated; camera origin, reservation flag, reservable rig ID |
| `GET /api/reservations` | Submitter's own reservations or operator overview |
| `POST /api/reservations` | Submitter; `{rig, starts_at, duration_minutes}` (Unix seconds) |
| `POST /api/reservations/{id}/cancel` | Owning submitter; `{}` |
| `POST /api/jobs` | Existing fields plus optional `reservation_id` for physical jobs |
| `POST /api/jobs/{id}/recording` | Assigned worker; raw ZIP, `X-Worker-Lease`, maximum 16 MiB; bounded 30-second body read |
| `GET /api/jobs/{id}/recording` | Owner/operator; ZIP attachment |

The standalone Python HTTP server remains a development/service backend. Vercel
identity integration, durable hosted storage, authenticated public video delivery,
ZIP/numeric-policy submissions and synchronized recorded video remain separate work.
