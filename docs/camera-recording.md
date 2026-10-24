# Camera recording and disk exhaustion

The continuous viewer keeps rolling `states.jsonl` and `comparison.jsonl`
telemetry: each file rotates at 8 MiB and keeps three backups (`.1` newest,
`.3` oldest). A long-running session therefore retains at most 64 MiB across
these two streams. Startup retains four marked unattended sessions by default,
so their telemetry totals at most 256 MiB plus small metadata files. The
service diagnostics log has an independent 8 MiB limit. Unmarked directories
and explicit `--record` sessions are never automatically deleted.

Telemetry pauses below 256 MiB of filesystem free space, checked once per
second, and retries failed writes every five seconds. Open, rotation, write,
flush, and close errors are contained in recording health; camera tracking,
video, and SDK publication continue. Partial records from a failed write are
truncated before recording resumes. Writes are unbuffered at the Python layer;
this is not a guarantee against power loss or filesystem failure. Records
missed during an outage are counted and are not replayed.

The dashboard Acquisition section and `/api/state` expose recording errors and
coverage. `telemetry_recording` includes `error`, `last_error`,
`written_records`, `dropped_records`, `rotations`, first/last successful write
monotonic times, and storage limits. Comparison recording health is under
`comparison.status.recording`. Counters describe the process lifetime, not the
number of records still retained after rotation. For replay, read backups from
`.3` through `.1`, then the current file; sequence/time gaps remain meaningful.

Explicit raw capture (`--record`) uses a 512 MiB budget and the same 256 MiB
free-space reserve, leaving room for the next frame and container overhead.
It stops recording on budget exhaustion or an encoder/storage error and
preserves its existing capture; it does not silently restart a new raw capture.
`recording.error`, `written_frames`, and `dropped_frames` expose this state.
Raw capture is optional and is not enabled by the continuous service launcher.
Preserved explicit sessions still need operator-managed retention.

If session-directory/metadata creation fails at startup, the viewer continues
and reports `recording_setup_error`. If the directory itself could not be
created, restart the service after restoring space to begin a new recorded
session. Missing final-report storage never prevents camera cleanup. Existing
large, unmarked legacy runs are not deleted by these protections: inspect and
archive/remove those separately when reclaiming a previously exhausted disk.
