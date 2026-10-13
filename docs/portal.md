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
| `POST /api/jobs` | submit | source, filename, sensor_source, duration, idempotency_key |
| `GET /api/jobs` | submit/operator | own jobs / all jobs |
| `GET /api/jobs/<id>` | submit/operator | own result / operator inspection |
| `POST /api/jobs/<id>/cancel` | submit | request cancellation of own job |
| `POST /api/claim` | worker | rig and optional sensor_source capability |
| `GET /api/jobs/<id>/artifact` | assigned worker | verified source as bounded base64 |
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
No physical portal policy run has been performed; no switches are installed, and
the default hardware bridge correctly requires that prerequisite.
