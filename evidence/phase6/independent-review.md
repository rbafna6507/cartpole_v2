# Independent portal / queue / worker review

Review date: 2026-10-13. Repository: `/Users/rbafna/projects/cartpole_v2`.
Scope: portal API and upload storage, durable queue/leases, Linux isolation,
worker/SDK bridge, and raw-executor simulation integration. This reviewer made
no implementation edits, hardware/SSH/UI calls, or commits. Reproductions used
synthetic jobs, trusted fake bridges, temporary files and loopback HTTP only.

## Verdict

No remaining concrete P1/P2 code finding in the reviewed final source. The six
issues below were repaired during review; the final delayed-heartbeat reproduction
now produces no ARM. Ready for the parent's next isolated simulation acceptance
checks. The narrowed SDK mount and combined raw-executor queue worker still need
fresh target Linux validation. This is not hardware/public-service acceptance or
permission to bypass physical switch commissioning.

## Findings and disposition

1. **P1 — stale ownership can reach ARM** — `src/cartpole_sdk/portal/worker.py:200-216` (repaired location).
   Original reproduction delayed the successful `start` response until the old
   running lease expired, queue recovery blocked the rig, an operator explicitly
   confirmed stopped recovery, and another worker claimed it. The old worker still
   called ARM and discovered the invalid lease only at `finish`. A new heartbeat
   after start fixed that instance. Independent follow-up moved the delay into the
   final heartbeat and reproduced the same result on the revised code: with 5s
   jobs and a real 2.05s delay, `ARM(2.929s)` was called while the old job was failed
   and `new-worker` owned the rig. Final ownership replies need a bounded freshness
   check as well as identity/status validation and remaining-duration subtraction.
   No physical device was involved. Both start and final heartbeat responses now
   require monotonic latency <=250ms, with identity/status checks and a run budget
   anchored before start. Re-running the original real 2.05s delay produced
   `Arm durations: []`; the old job remained failed and new-worker held the claim.
   The dedicated regression also passes. **Resolved for the reproduced cases.**

2. **P2 — cross-origin redirects leaked the worker Bearer credential** —
   `src/cartpole_sdk/portal/worker.py:34-86` (repaired location).
   The original urllib transport automatically followed a 302 to another origin
   and forwarded Authorization. Two local HTTP servers with a synthetic token
   reproduced `['Bearer review-placeholder']` at the second origin. The revised
   direct HTTPConnection/HTTPSConnection rejects non-2xx and does not follow
   redirects. The cross-origin regression now passes. **Resolved.**

3. **P2 — inactivity timeouts were not absolute operation budgets** —
   `src/cartpole_sdk/portal/server.py:21-49,70-73` and
   `src/cartpole_sdk/portal/worker.py:34-86` (repaired locations).
   Progress bytes could keep inbound handlers and outbound requests open beyond
   their intended bounds. Server reads now share an absolute header/body deadline.
   The client independently bounds DNS/connect/headers/body, caps pending transport
   threads at two, and aborts an available socket on timeout. Real slow-body and
   slow-response regressions pass. **Resolved for tested slow-drip cases.**

4. **P2 — HardwareBridge shifted the stop deadline after ARM latency** —
   `src/cartpole_sdk/portal/worker.py:152-155` (repaired location).
   A fake Rig with 30ms ARM latency and a 100ms run demonstrated bridge completion
   about 21.3ms after the existing Rig duration guard. This could report otherwise
   valid jobs as faults. The bridge now uses `Rig._deadline_ns` with its existing
   early-stop margin. Re-running the same 30ms fake ARM now completes exactly
   10.0ms before the Rig guard. The MCU/SDK remained independent safety authorities
   even before this fix. **Resolved by independent reproduction and PTY integration.**

5. **P2 — simulation silently used direct acceleration and no lease fault** —
   `src/cartpole_sdk/portal/worker.py:100-130` (repaired location).
   The original SimulationBridge used MujocoBackend directly. Initial None advanced
   to 10ms without terminating instead of exercising the external executor lease.
   It now uses ExecutorSimulation, preserving simulation source/frame provenance,
   applying the binary32 1kHz governor to raw demand, and reporting executor/fault
   diagnostics. Initial None now fails closed in a queue regression. **Resolved.**

6. **P3 — the mounted SDK parent is broader than documented** —
   `src/cartpole_sdk/portal/sandbox.py:159-160` (repaired location).
   The original bind mounted the parent of cartpole_sdk, exposing all site-packages
   read-only in a wheel install, contrary to the documented surface. No actual
   secret exposure or escape was demonstrated. The final bind mounts only the
   cartpole_sdk package into /sdk/cartpole_sdk. A Linux-only synthetic sibling-secret
   exclusion regression was added. **Resolved by source inspection; the new mount
   profile's target test remains pending parent verification.**

## Independent verification

- `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest discover -s tests -p 'test_portal*.py' -v`:
  **41 methods, OK; 36 passed and 5 Linux-only skips**, 7.406s. Includes real
  loopback HTTP, owner/role/origin/path/size checks, transactional claim contention,
  recovery/idempotency/no-follow storage, real bounded pipe IPC, trusted simulation
  worker integration, PTY hardware bridge tests, and the final stale-heartbeat
  regression. The five skips cover four Linux sandbox methods and one actual
  Linux isolated simulation worker method. A skip is not target acceptance.
- `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_host_policy.py`:
  **17 passed**, 0.20s. Includes raw/executed separation, lease/None behavior,
  binary32 governor, hard rail margin, speed ceiling, and emergency braking
  authority independent of a lower raw-demand ceiling.
- Inspected supplied `evidence/phase6/portal-linux-tests.log`: **10 methods run,
  9 passed, 1 expected absent-runtime skip**, 3.416s. This is parent-operated
  Jetson evidence, not a target run performed by this reviewer. It covers actual
  Bubblewrap/libseccomp denial of host-home/serial/network/fork/exec access,
  read-only filesystem behavior, CPU/memory/output abuse and child cleanup.
- Packaging metadata now lists portal/worker entrypoints and HTML/JS/CSS assets.
  A built wheel was not yet independently inspected.

## Reviewed properties and limits

No concrete namespace/seccomp isolation escape was found in the examined profile.
The broker never imports uploaded Python. The child sees selected observations and
returns a bounded numeric intent; the broker supplies session, clock, sequence and
board-anchored TTL. Untrusted code cannot choose operator commands. The default
hardware bridge requires stopped, healthy, homed, switch-enabled streaming state
and never automatically homes, centers, clears faults or disables switches.

Queue transactions bind owners, idempotency payloads, artifact digests and a single
active rig claim. Expired running jobs block that rig until explicit operator
recovery. A failed STOP keeps it blocked. User-visible results omit worker lease
secrets; upload bytes are bounded and verified through SHA256 and no-follow file
operations. Browser output uses textContent and credentials are not in URLs.

The queue token is not a hardware fencing token. Exclusive serial ownership and
operator recovery discipline remain part of physical exclusion. Before releasing
an expired active rig, terminate/quarantine the prior worker as well as verify a
physical stop; merely observing a momentary stop does not certify that a suspended
process cannot later resume. This review does not claim atomic fencing across an
arbitrary process pause between the final software check and an ARM write.

## Declined-to-judge / remaining acceptance

- No live queued policy, motor behavior, stopping distance, switch wiring/homing,
  Z motion, USB timing or 100Hz live inference acceptance was tested here. Physical
  switches are absent; that is an honest commissioning prerequisite, not an
  implementation defect. Simulation is not physical acceptance.
- No public hosting, TLS proxy, account/key lifecycle, deployment permissions,
  disk retention/backups or operational monitoring was accepted. Terminal jobs
  and artifacts need retention/quota policy before public operation.
- No universal kernel/runtime security certification. Bubblewrap, libseccomp,
  architecture, user-namespace policy and the exact readonly runtime/package
  content remain deployment inputs. A mount-profile change needs new target tests.
- No optional NumPy/native-model ABI acceptance or renderer/UI visual inspection.
- Source digest and simulation config support result traceability, but results
  alone do not pin the entire Python/SDK/MuJoCo/kernel runtime for exact replay.
- Supplied target sandbox tests and local trusted-pipe simulation tests do not by
  themselves prove the combined isolated simulation worker on the target.

## Final reviewed source fingerprints

SHA256 of final read-only review inputs (not a commit or deployment claim):

- `src/cartpole_sdk/portal/queue.py`: `c711c090afe59faa2e92395a0f78c8ed6f756e1da60c4353e4d370baacb8b6ba`
- `src/cartpole_sdk/portal/server.py`: `4f529ab6b4494f0d4296fbc1b8d13004fd8ebbec5dd731685ca204b651727595`
- `src/cartpole_sdk/portal/sandbox.py`: `e117484f5a5532f4535e3aeb21e439cc29f10a57bf04b5e221d89d7899e74267`
- `src/cartpole_sdk/portal/security.py`: `582329b7c99f26c5b0f4210eb5d192c8659634d404db3e28557d51a7dfd3d776`
- `src/cartpole_sdk/portal/harness.py`: `5e220d943f84911ef5bc7e9e6c2ad965bdaf6ffa6616f4fcff0f46b993a7bd7b`
- `src/cartpole_sdk/portal/worker.py`: `2dad74153a05169e817689d5647d84dacc25eb81afaa5217e21143ffb838e8d9`
- `src/cartpole_sdk/sim/executor.py`: `6b775473241b32a3b1c0cff669067226ba32f491ef3e51726e7ac9c1570b814f`
- `tests/test_portal_worker.py`: `f9ea17b8c2b3649f87364998533ba464f11de43a75c3e3682268ef2167c0ff70`
- `tests/test_portal_sandbox.py`: `06fcc6414788fb920a15a44631fd7dee939a304f614fb5aeed048a9a2e20ce45`
- `pyproject.toml`: `a9a8efcff45ff64f776254fb73b8088da5082e71e02e433d1091ddad1b71e7a4`


## Focused follow-up: trusted ceilings and learned export (2026-10-13)

**Verdict:** no new concrete P1/P2 defect found in these deltas. The trusted
hardware default remains **0.25 m/s²**, simulation defaults to **25 m/s²**, and an
operator can explicitly configure a finite ceiling in (0,25]. This is approval of
the examined software boundary, not permission to run a higher physical ceiling.
The reported Linux learned-policy end-to-end acceptance below is still failing.

- `portal/worker.py:186-204,237,277-289`: the ceiling derives from trusted worker
  configuration before claim, never a submitted job. CLI backend and source are
  selected together; bridge kind must match the claimed job. Invalid configuration
  fails before claiming. Both PolicyChannel and the trusted broker check the same
  approved ceiling. Results record approved ceiling and observed peak demand.
- `portal/sandbox.py:20-30,129,143-144,177`: exact int/float validation rejects bool,
  nonfinite, zero, negative and >25 ceilings. Strict action envelopes cannot carry
  an overriding max field. HTTP submission also rejects that extra field. The
  ceiling is held in the parent adapter and broker; it is not controlled by
  uploaded Python. The physical regression proves demand 1.0 fails before any
  wire A command and finishes stopped under the default 0.25 ceiling.
- `learning/export.py:38-109`: exporter validates bounded numeric JSON, embeds the
  exact bytes via a Python string literal, selects one fixed explicit channel
  mapping, keeps saved cadence/action semantics/hardware_accepted=False, checks
  fixed runtime-file hashes, and rejects generated source above 64KiB. The output
  requires only stdlib and the readonly SDK, with no separate weight file,
  pickle/eval, model-selected import path or third-party inference package.
  Production upload execution still occurs only after the existing restricted
  child installs its limits. The exporter's compile call parses without executing.
- Provenance limit: the fixed seven runtime hashes are compatibility checks, not
  complete SDK/runtime attestation. `recording.py` (used for strict_json_loads) and
  all transitively imported package initialization/helper files are not pinned by
  that export list. This is not a demonstrated sandbox escape; avoid a claim of
  complete environment attestation or exact replay from those hashes alone.

Independent local commands/results:

- Portal unittest discovery: **48 run, 42 passed, 6 Linux-only skipped**, 7.618s.
  New cases cover trusted numeric ranges, child/HTTP overrides, independent broker
  enforcement against a tampered adapter, physical default rejection before A,
  and simulation demand above 0.25. The added learned Linux case is one of the skips.
- `python -m pytest -q -p no:cacheprovider tests/test_learning_export.py`:
  **4 passed**, 0.32s. Verified deterministic output, exact embedded artifact,
  operation after deleting the original weights, explicit wrong-source refusal,
  stdlib-only isolated-Python import, required hash rejection and embedded tampering.

Read-only inspection of parent-produced
`/tmp/cartpole-next/platform-linux-acceptance.log` at this follow-up:

- Narrowed-mount sandbox: **13 run, 12 passed, 1 expected absent-runtime skip**,
  including exclusion of a synthetic sibling package secret. This clears the
  earlier mount-profile target-test gap for that recorded target.
- Basic actual isolated simulation queue test: **passed**.
- Actual 10s learned simulation queue test: **failed**, worker_guard_failure after
  10.786s wall with 8.73s simulation completed (873 actions), stopped=true, no
  simulation fault, peak raw demand 16.8253 m/s², max inference about 2.75ms.
  Evidence is consistent with the fixed wall budget expiring on a simulation
  slower than real time. It is not a ceiling rejection or isolation escape.
  The failure must remain visible until a fresh target test succeeds; this review
  did not run any target command or alter run/deadline semantics.

Focused final source SHA256 values (supersede earlier hashes for these paths):

- `src/cartpole_sdk/portal/worker.py`: `980d8504bcbb0f096337fff5dbcee5e8e89e56cbcf97ba159302429770f3baf5`
- `src/cartpole_sdk/portal/sandbox.py`: `5a74504fc4231d9446f6ab0f8dd97fcec579ca84879f13baaab95b4e4bc3be97`
- `src/cartpole_sdk/portal/server.py`: `4f529ab6b4494f0d4296fbc1b8d13004fd8ebbec5dd731685ca204b651727595`
- `src/cartpole_sdk/learning/export.py`: `0486e6fc685668f67689dd7390f05d37a23a877b5a3fa744f542138f69f7aa7a`
- `tests/test_portal_worker.py`: `dcbcc83b930ae3e55e3f2ce1785de87d66d3c2b63be8c745467392f332319ef9`
- `tests/test_portal_sandbox.py`: `53f33ded3827f9c6025d7375b654619dfa08e22fffbe1daf6c21c94406f0f2b5`
- `tests/test_portal_http.py`: `5fe33ce02c27f67335b530d09a05373d7ecbdd2cae831a1f783985ac0afa0207`
- `tests/test_learning_export.py`: `246d475b8cf14a8a7fe4de6c0f0913acd07b62c3aa778a36f7b59e2aa399f332`


## Focused follow-up: simulation wall budget (2026-10-13)

**Clear focused verdict:** no concrete issue found in the budget delta. The
longer allowance is source-derived and simulation-only; it does not extend a
physical experiment or allow an uploaded policy to change its approved limits.

- `portal/budget.py:9-14`: exact supported source and finite numeric duration
  0.05..60s produce simulation base wall budget 2x duration (maximum 120s) or
  magnetic-step base budget equal to duration (maximum 60s). Boolean, zero,
  out-of-range, string, NaN, infinity and huge integer inputs were independently
  checked and rejected. Existing startup/finish grace is separate from this
  base wall budget; 120s is not a claim that every process is reaped by that instant.
- `portal/queue.py:171-184`: start derives its one-time deadline from the stored
  immutable source/duration plus the existing 1s finish grace. Heartbeat still
  renews only the existing 2s lease and cannot extend the fixed deadline. Physical
  source deadline arithmetic is unchanged.
- `portal/worker.py:198-206,208-242`: bridge kind must match stored job source before
  deriving the shared budget. Sandbox receives that budget. Physical ARM receives
  original requested duration minus elapsed pre-ARM time, never the doubled wall
  budget. Start/final-heartbeat age guards remain in force. The outer wall guard
  is anchored before start, and existing bounded margin remains. The 10ms action
  deadline, 20ms action TTL, acceleration checks and STOP-finally path are unchanged.
- `portal/sandbox.py:143-177`: only the trusted wall_seconds validation maximum
  grows to 120s. Parent wall watchdog and child resource limits use that supplied
  value; no HTTP/job/child wall-time override was added. Isolation and per-action
  timeout remain unchanged.
- Recovery documentation now explicitly requires terminating or quarantining the
  previous worker before confirming physical stop and unblocking the rig. It
  correctly explains that freshness checks are not hardware fencing.

Independent local portal suite: **50 methods run, 44 passed, 6 Linux-only skipped**,
8.311s. The new queue test checks 10s simulation deadline +21s vs physical +11s,
with heartbeat unable to extend either. The slower-simulation test completes a
0.2s simulation with an explicit 0.4s sandbox/worker base wall budget. Existing
physical ceiling, stale ownership, timeout, authentication and recovery cases pass.

The unchanged 10s learned target test still needs its fresh parent-operated rerun.
At this follow-up, the supplied acceptance log still contains the earlier failed
run; this local review does not replace that target evidence.

Budget follow-up source SHA256 values:

- `src/cartpole_sdk/portal/budget.py`: `10f48a08f3b3314e37c9ba405a8915321e43ae40afa89015f23a954ae13a3cda`
- `src/cartpole_sdk/portal/queue.py`: `e12c4b6c2a5346aeca7f9b02718522d8e53278cec65db4c9c516e649d6b332b8`
- `src/cartpole_sdk/portal/worker.py`: `431addf417efbd9376743d711612c6fad6f038000ba490317837faecc1c9b361`
- `src/cartpole_sdk/portal/sandbox.py`: `900c0918aa3e6c7df6a02ee5e5864ece55f69ae827dc297695ae59b2f659dbce`
- `tests/test_portal_queue.py`: `436042a400b0f052cde59adc72e0b0125f02bdd921f69abbc5d8ffc4aea694cc`
- `tests/test_portal_worker.py`: `412a599bdda4b86272273dbf26df3fcae8dc8f6612dd7467d1af6d9a5e2e2a90`
- `docs/portal.md`: `170ddab413f626225702a30b168024c374a8f768a5a17138bd4b5cc4bf5ff37a`
