# Colab checkpoint recovery implementation plan

> **For agentic workers:** Use executing-plans for the recovery adapter and parallel independent policy/diagnosis checks.

**Goal:** Continue the interrupted filtered combined-policy campaign from its verified checkpoint and provide an evaluated numeric actor for operator-run hardware balance tests.

**Architecture:** Preserve the frozen protocol and original run. Add an evidence-local continuation adapter that restores full PPO state into a fresh environment, records the non-bit-exact resume boundary, and writes source-bound reports/checkpoints. Prepare a new immutable bundle/session and restart checkpoint backups. Export candidates without changing firmware or console admission.

**Spec:** User request in this chat: recover training, investigate Colab termination, and give commands to run the partial policy.

**Constraints:** No hardware motion or serial access; keep original balance actor, frozen sources and evidence unchanged. Original 1,024,000-step/trial budget, six trials, filtered100Hz encoder inputs, jerk150. Resume model/critic/optimizer/counters; explicitly disclose fresh environment and global RNG. No claim of hardware acceptance.

**Review focus:** Wrong checkpoint/report/protocol bindings; counter or optimizer reset; duplicate launch/overwrite; resumed watcher following wrong session; admitting hanging starts through balance-only console.

- [x] Test continuation loading: reject mismatched binding/counter, retain optimizer moments and weights, perform real optimizer update with absolute counters.
- [x] Implement continuation adapter and immutable recovery bundle, preserving original evidence and logging resume lineage.
- [x] Verify extraction/source bindings, smoke continuation and focused regression tests; review before cloud launch.
- [x] Allocate one new session and verify actual resumed progress; launch bounded checksum-verifying HTTP backups.
- [x] Evaluate latest and earlier checkpoint, export/stage chosen actor additively, verify runtime compatibility and provide exact upright-start console commands.
- [x] Record provider diagnosis with evidence and uncertainty, commit completed changes.
