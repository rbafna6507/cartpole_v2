# Learned balance recovery cycle

User explicitly requests autonomous iteration toward a working trained balance policy as soon as possible. Reuse the current branch and working runtime; preserve unrelated dirty changes and record incremental patches separately.

1. Record a native AUTO/BAL positive control with current saved reference 553 and current working parameters. Preserve faults; recover only after stopped health verifies and home explicitly. No firmware reset/flash with motor supply on.
2. Compare actual Python BAL feedback and a supervised neural approximation of the same BAL law with filtered angle at 100 Hz. This differs from prior arbitrary teachers and prior AUTO-gain distillation; retain all differences in the report. A simulator mismatch does not become a fitted correction or hardware qualification. If export parity is good, the learned equivalent is an explicitly developmental hardware diagnostic.
3. Extend the balance runner only to accept explicitly declared filtered encoder actors, keeping raw encoder start/commissioning checks, sensor freshness, runtime binding and firmware authority. Tests precede the change. Existing raw actor behavior is preserved.
4. Use temporary controller-child-only RR10 and CPUs 4–5; camera stays on CPUs 0–3. The user granted temporary shell 305943 RLIMIT_RTPRIO 10. Keep 20 ms leases, jerk 150, physical switches, and bounded trials. Compare 5 s then 25 s, and repeat promising results at least three times, including native swing-up/settle if feasible. No hands-on pose change during powered motion.
5. Analyze encoder/camera/action/governor traces after each test. Train or adjust only the identified mismatch. Distinguish supervised initialization from PPO and single successes from reliable balance. Save runnable scripts, source hashes, reports, and exact actors. Commit reviewed task work.

Root owns all hardware and runner edits. retention_optimizer owns supervised transfer and simulator comparisons; robust_recipe_plumbing audits model/runtime timing and historical host controls. Neither agent commands hardware.

## Checkpoint after user took manual control

- Autonomous hardware access is paused while the user runs the console. The scoped RR10 SSH shell305943 was closed after its last child exited. Do not reuse the prior clear/upright confirmation for new powered motion.
- Native AUTO and BAL also failed with the preserved current settings. Native AUTO held captured balance0.100s and later faulted4; native BAL exited its angle envelope0.656s after start. Encoder/camera disagreement at startup is evidence for a shared disturbance, not proof of a particular electrical/mechanical cause.
- Exact historical audit found sustained Oct20 native AUTO trials used bw8, reference330. Current trials used bw10, reference553. All feedback gains and other motion/capture settings match; only the home-derived rail differs by0.0375–0.075mm. A later bw8/reference294 trial was operation-complete but did not sustain balance. Restore an exact bw8 comparison before claiming unchanged complete controller configuration.
- Zero-command hanging probe passed5s, fixed counted cart position, no I2C growth, <=0.176degree angle span. Enable-associated disturbance is not universal at every pose. Upright zero test has not occurred.
- The user's manual old/new console snapshots confirm the same gains/bw10 and show another encoder fault4. The newer snapshot includes upright calibrations553->551->1135. Asked whether both later poses were physically the same upright; answer pending. Current live calibration and motor state belong to the user's session and must be re-read after handoff, not assumed553 or disabled.
- Filtered-encoder actor support is deployed with original remote source backed up. Full local production suite2018passed,8skipped,460subtests. New supervised filtered BAL candidate is prepared but not exercised on hardware. Diagnostic200ms startup-settling harness remains local and unconfirmed; do not treat it as a fix.
- Raw snapshots and provenance are in runs/policy-recovery-20261021/hardware-live; parameter/failure comparison is evidence/policy-recovery-20261021/user-manual-audit.json and transfer-audit/parameter-summary.md. No new-cycle commit yet. Preserve unrelated console changes when staging.

## User correction and resumed handoff

User clarified the failed manual runs were an upright calibration issue and reported AUTO/BAL working, then authorized continuing policy work. Their final saved reference is450. The read-only manual trace confirms native BAL remained mode3 for its full10s, ending with the expected duration fault3. Do not carry forward a universal native-failure claim or assume the earlier51degree reference change was spontaneous drift.

User confirmed console closed/rig clear and granted replacement temporary shell306340 rtprio10. Root verified no other console process, read back reference450, cleared only the duration latch, and completed REHOME to countedx0, healthy/disabled, homeepoch36, I2C17 unchanged. Motion/gains remain bw10/jmax150 and the same41parameter snapshot. Pending a fresh user upright pose for filtered learned BAL. Startup settling remains deferred; no delay intervention will be combined with this first test.


## Latest checkpoint: preserved filtered BAL holds and user handback

The corrected saved reference 450 enabled successful native controls and the
filtered supervised BAL candidate. The unchanged
`training/candidates/balance-recovery-20261021/actor.json` completed the requested
5-second trial and two undisturbed requested 25-second trials. Raw-angle RMS was
1.054°, 1.177° and 1.317°, respectively. A third requested 25-second console run also
completed, with raw-angle RMS 2.014° and excursions −8.35…+13.62°; the user explicitly
confirmed **only this third run had pokes**. Count it as a disturbance observation,
not a third undisturbed repeat. All three long traces have fault 0, 2,499 actions,
20 ms leases and clean logger termination with zero dropped records. Exact
observed enabled intervals are approximately 24.99 s because of the normal 10 ms
STOP margin. Hardware acceptance remains false, and this actor has zero PPO
updates: it is supervised transfer of the actual filtered native BAL law.

The thin `scripts/policy-console` / `cartpole_sdk.rig.policy_console` entrypoint
sets GIL 1 ms before unchanged console delegation and restores the prior interval.
Independent review found no Important/Critical issues; full local suite 2030
passed, 8 skipped, 460 subtests passed. The documented user launch keeps the
jetson-control parent SCHED_OTHER and applies RR10 only after `--` to the control
child on CPUs 4–5, with camera CPUs 0–3. The third trial used an imported console
function with the same GIL setting; the new module is the equivalent reproducible
entrypoint, not the literal original command.

The entire completed remote runroot was copied using file-only SSH. Remote and
local archive SHA256 match
`f5c232be121a77b845d0cab9e88c9e4db4a67282d071eb81a6bff6492462707b`;
all 43 files were individually verified, 16 added locally and 27 identical existing
files preserved without differing overwrite. Cameras and REHOMEs are retained.
See `evidence/policy-recovery-20261021/hardware-balance/report.md` and
`docs/console-policy.md` for exact provenance, metrics and the user launch.

The final preserved REHOME finished counted x 0, fault 0, healthy/disabled,
reference 450, home epoch 36, I2C 17. Hardware has since been handed back to the user;
this is a historical handoff state, not permission for renewed autonomous motion.
Root and retention_optimizer own separate combined-policy offline work; this
checkpoint does not modify or qualify those pilots. Preserve this working actor,
all prior failures and the full archive when committing the reviewed checkpoint.
