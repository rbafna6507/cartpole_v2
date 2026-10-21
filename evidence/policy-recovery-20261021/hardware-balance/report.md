The preserved filtered BAL actor completed the initial requested 5-second trial, two requested 25-second undisturbed trials, and one requested 25-second console trial with operator-reported pokes. **Only `filtered-console-run25-03` was poked**, as confirmed by the user; it is a disturbance observation, not a third undisturbed repeat. Poke times and forces were not instrumented.

The unchanged actor `training/candidates/balance-recovery-20261021/actor.json` is a supervised approximation of the actual native filtered BAL feedback law, with **zero PPO updates and zero environment training steps**. It remains `DEVELOPMENT_ONLY`, `hardware_accepted=false`; these bounded observations are not qualification or a general reliability claim.

| Trial | Requested s | Enabled-to-disabled board s | Sampled active span s | Raw angle RMS ° | Raw angle range ° | Counted x RMS m | Counted x range m | Faults |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| `filtered-bal-run5-01` | 5 | 4.990984 | 4.989984 | 1.054138 | -2.1094…+1.6699 | 0.037557 | -0.008925…+0.087375 | [0] |
| `filtered-bal-run25-01` | 25 | 24.991000 | 24.990000 | 1.176919 | -3.1641…+2.0215 | 0.034617 | -0.052762…+0.059888 | [0] |
| `filtered-bal-run25-02` | 25 | 24.990000 | 24.980000 | 1.317133 | -3.3398…+2.9883 | 0.043897 | -0.042037…+0.122063 | [0] |
| `filtered-console-run25-03` | 25 | 24.991000 | 24.990000 | 2.013879 | -8.3496…+13.6230 | 0.048846 | -0.113700…+0.119438 | [0] |

Each 25-second trial recorded 2,499 action requests, all with anchored 20 ms leases. All observed states, including cleanup, had fault 0; all three terminated with error=null and zero logger records dropped. No active sample requested rail braking. The last observed state was stopped/disabled. The first two instrumented runs have before/after INFO with unchanged I2C 17; the console trial has I2C 17 before execution, and the later preserved final REHOME also reports I2C 17, counted x 0, fault 0, disabled. No after-run INFO inside the console trial itself is invented.

The policy intentionally exits before its executor duration by `min(0.01, duration_s*0.25)` seconds (`rig/policy.py`, actor-pinned SHA256 `6577e77a54a14ed320ed0dc318a9c180787791ff9dad9324006a16f367ec933a`). Thus a requested 25-second invocation produces approximately 24.99 seconds enabled, and its last enabled telemetry sample can precede STOP by one telemetry interval. `audit.json` also distinguishes host ARM-to-STOP command elapsed time and policy record span; none is rounded into an exact 25-second measured hold.

All trials identify filtered angle input, saved upright reference 450, bw 10, jerk 150, home epoch 36 and measured span 16511. First two long-trial reports show main/control threads on CPUs 4–5, SCHED_RR priority 10, GIL 1 ms, logger/mirror enabled. The third trial has no diagnostic runtime-environment report: its scheduling/GIL launch comes from the root operator record, not an inferred JSON field. It ran the existing console through an imported function; the newly tested `cartpole_sdk.rig.policy_console` module is the equivalent documented entrypoint that scopes GIL 1 ms before delegation. Do not describe that module as the literal original third-trial command.

Raw-angle RMS is calculated over distinct enabled telemetry samples. Counted x, governed acceleration and commanded velocity are internal actuator quantities, not independent measurements of physical cart motion. Filtered-angle RMS, observer rate, timing gaps and finite final-five-second metrics are retained in `audit.json`.

Corresponding camera NDJSON is preserved for each run. The audit counts each camera frame once using its own frame sequence and host-read timestamp, limited to the associated enabled receipt interval; it never substitutes the embedded encoder stream. Valid camera angle coverage is partial (706/1646, 598/1636, and 451/1656 frames for the three long trials). Camera exposure latency and metric angle/position calibration were not revalidated here, so camera-derived hold metrics are not claimed.

Preservation: remote release `/home/rbafna/cartpole-v2-live/releases/id-20261021-policy-console`, runroot `runs/policy-recovery-live-20261021`. Remote and local archive SHA256 both equal `f5c232be121a77b845d0cab9e88c9e4db4a67282d071eb81a6bff6492462707b`. All 43 regular files were checked against the independent remote file-size/SHA256 manifest before extraction. Sixteen new files were added under local `runs/policy-recovery-20261021/hardware-live`; 27 identical existing files were preserved, with no differing overwrite. Source symlinks and unsafe archive paths were rejected. Rehome logs and preceding trials are retained in the same archive.

Actor file SHA256: `9e498faf5783e278b44cad6d75e720d38a9ef0800b99d0676256c6445373a850`; actor content SHA256: `81118e9231b857aa27e99049a6745647e40a587c5643716c754b96e090c1ef34`. Remote deployed launcher, console and actor hashes are in `deployed-source-sha256.txt`; trial logs, camera files, training receipt, and audit script identities are bound in `audit.json`.

Reproduce offline from the repository root using a fresh output path:

```sh
.venv/bin/python evidence/policy-recovery-20261021/hardware-balance/audit.py --output /tmp/filtered-balance-audit.json
```

This audit accessed Jetson files only. It issued no serial, motor, scheduler, service or process-control commands. Hardware has been handed back to the user.
