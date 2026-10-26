# Portal reliability and Python AUTO experiments — October 26, 2026

## State and deployment

User confirmed native AUTO and working.json success and authorized autonomous
portal/hardware experiments after USB repair. Parent captured `live-baseline.json`
in a stopped session: fault0, homed, healthy, switches enabled, measured half-rail
0.308175m, saved upright452, all41 controller parameters. No gains, reference,
firmware, homing or Z movement changed in this phase.

The API/user simulation worker source was updated from local96b4827 plus the
regression-tested STOP/outcome and optional-simulation-import fixes. Remote rollback
archive: `~/cartpole-portal/backups/source-before-reliability-20261026.tgz`.
Portal and active console working actor weights matched exactly; their prior
metadata hashes differed. Staged actor bytes now match the active operator copy.

Hardware service was inactive. Noninteractive `systemctl start` returned
`Interactive authentication required`; SSH cannot authenticate sudo. The user was
asked to run the existing realtime check script followed by starting the service.
No physical submitted run has been approved in this phase. Controller reliability
remains unproven and no tuned replacement has been installed.

## Deployed API / isolated simulation acceptance

All use authenticated submitter requests, immutable artifacts, the shared calibrated
profile and normal isolated worker. Results and verified ZIPs are preserved below
`trials-20261026/`. No direct database edits or safety bypasses were used.

| Key | Outcome | Actions | Recording drops |
|---|---|---:|---:|
| sim-zero-001 | succeeded | 200 | 0 |
| sim-zip-001 | succeeded | 200 | 0 |
| sim-actor-001 | succeeded | 200 | 0 |
| sim-cancel-001 | cancelled | 129 | 0 |
| sim-overlimit-001 | isolated policy failure | 0 | 0 |
| sim-stall-001 | isolated policy failure | 0 | 0 |

The stalled action was stopped at approximately10ms response timeout. Cancellation
agrees between queue and manifest. Failure bundles were downloadable too. Detailed
mode captured the available simulation scalar trace; this worker has no optional
sensing URL, so no camera-history coverage is claimed.

Actual Jetson Bubblewrap tests:16 passed,1 skipped,19 subtests. The optional-import
regression separately passed on its hardware-only environment after removing its
assumption that Gymnasium would be installed. Realtime isolation remains an
additional prerequisite, not established by these non-realtime checks.

## Python AUTO test artifact

`python-auto100.py` and `python-auto250.py` use the exact snapshot and existing
ExecutorFeedbackPolicy. A small wrapper raises on policy faults to match console
STOP behavior instead of waiting for action expiry. No gain tuning is hidden here.
Generator/replay CLI: `examples/python_auto_portal.py --help`.

Six short offline probes found substantial sampling/delay sensitivity:100Hz with
3ms telemetry+3ms command delay captured in1.22s and held6.78s in one surrogate;
100/250Hz zero-delay and250Hz with those delays did not capture. Planning-only1ms
counterfactuals did not change zero-delay outcomes. This is insufficient for gain
changes or hardware claims. Await matched physical traces before tuning.

## Verification and camera recovery

Final focused local regression:47 passed (Python AUTO artifact/replay, optional
simulation imports, runtime leases/recording, public simulation exports). Independent
review confirmed generated100Hz policy exactly matches the console's live-snapshot
configuration. The portal's first observation validation occurs after ARM, before
any policy demand; console also performs start validation before ARM. Replay gaps
or unmatched actions must not be represented as complete decision parity.

Camera outage during development was independently diagnosed: the service was in
a no-frame restart loop and direct V4L2 capture returned empty error buffers with
USB protocol errors. Stopped only the camera service, tested capture at30FPS (five
valid960x600 frames), restored80FPS, then restarted service. Sustained capture
returned71–75FPS, over8,000 frames and zero read failures. Authenticated local and
Funnel video endpoints returned200 with Vercel CORS origin; actual Vercel browser
displayed live H.264 video. No permanent camera quality/configuration change. This
restores operation but does not establish a root cause for the USB instability.
