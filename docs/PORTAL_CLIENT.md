# Agent and script API workflow

`cartpole_sdk.portal.client.PortalClient` uses the same bearer-authenticated API as
the browser. A submitter can reserve, upload/request a run, inspect status, cancel,
and collect verified data. It cannot approve physical runs or issue worker leases.
There is no separate upload-to-run race: `submit` uploads an immutable artifact and
creates the job in one transaction. Reuse the same idempotency key and identical
arguments to recover an uncertain submission response. Changed arguments require a
new key. Reservation creation is not idempotent: inspect `reservations()` after an
uncertain response before booking again.

```python
import os
from pathlib import Path
from cartpole_sdk.portal.client import PortalClient

# HTTPS for remote servers; HTTP is accepted only for localhost.
client = PortalClient(os.environ['CARTPOLE_PORTAL_URL'],
                      os.environ['CARTPOLE_SUBMIT_TOKEN'])
assert client.me()['role'] == 'submit'
job = client.submit(
    Path('policy.py'),  # also supports bounded ZIP projects and numeric actor JSON
    sensor_source='simulation', duration=1.0,
    idempotency_key='experiment-001', recording='detailed',
)
print(job['id'], job['status'])
# A configured simulation worker is needed. Local portal preview starts none.
manifest = client.collect(job['id'], Path('experiment-001.zip'), timeout=180)
print(manifest['status'], manifest['coverage'], manifest['recording'])
```

This is an example to run against an intentionally configured server; installing
the SDK or importing the client does not connect to a rig or submit anything.
Tokens belong in environment variables or a secret manager, never repository files.
The client does not follow redirects. Requests and downloads have bounded sizes
and deadlines; failures do not trigger automatic duplicate mutations.

For a physical session, reserve preparation and iteration time independently of
the short run duration:

```python
import time
config = client.config()
reservation = client.reserve(config['rig_id'], time.time() + 300,
                             duration_minutes=30)
job = client.submit('policy.py', sensor_source='magnetic-step', duration=1.0,
                    idempotency_key='physical-experiment-001',
                    reservation_id=reservation['id'], recording='detailed')
assert job['status'] == 'awaiting_approval'
# An operator must inspect/approve; the reservation window must be active, and
# the rig must already be prepared and healthy before its worker may run.
print(client.get(job['id']))
# client.cancel(job['id']) requests cancellation; it does not itself stop hardware.
# client.cancel_reservation(reservation['id']) requires no active claimed/run job.
```

`wait(id, timeout=...)` returns when execution reaches a terminal status. Packaging
and upload occur after the backend stops, so a terminal result can still say
`local_pending_upload`. `collect(id, destination, timeout=...)` waits for the bundle
to become available too. An upload failure can leave a local spool indefinitely;
collection then times out rather than claiming that data was downloaded. A job
cancelled before claim has no recording and collection reports that explicitly.
Use `download(id, destination)` for an already available recording.

Downloads verify both the server's whole-ZIP SHA-256 and byte count, the exact fixed
ZIP members, manifest job/artifact identity, and telemetry SHA-256. The client does
not extract archives and refuses to overwrite an existing destination. Hashes
prove transport/content consistency against the authenticated server, not physical
execution or independent authenticity. Inspect drop counts and coverage even for
successful runs. File persistence errors propagate to the caller.

`recording='standard'` is the default mandatory bounded scalar trace.
With a trusted worker `--sensing-url`, standard recording also retains the existing
30 Hz latest-envelope capture (one sample per stream, 3 MiB cap).
`recording='detailed'` expands that isolated collector to up to 128 history samples
per stream per envelope at 30 Hz, with an 8 MiB cap, and records cached decoded
board state at the observed control cadence on hardware. It issues no extra serial
queries. More history helps retain samples produced between collections; cursors
and source gap metadata remain intact, and completeness is not guaranteed. The mode is
immutable and bound into idempotency. A missing source is reported in coverage;
it does not cause fabricated data or change policy input. Neither mode records
video, full-rate firmware internals, or raw serial bytes. See
[recording coverage and limits](RUN_RECORDING.md).

Deployment status: these changes are source-only. The existing server and worker
need a coordinated update after hardware/USB readiness is restored. Nothing here
deploys or restarts either process. `/api/config` advertises `recording_modes`; the
frontend omits new fields for older APIs, and the client rejects unsupported
detailed requests before creating a job. Standard requests remain compatible.
An updated API alone does not upgrade a worker; actual manifest coverage is the
authoritative record of what that worker captured.
