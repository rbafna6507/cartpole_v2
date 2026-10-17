# Passive operator finish and interrupted batch review

**Goal:** Give passive collection an explicit finish action and analyze the operator's batch 2 recordings without disguising interrupted evidence. Existing autonomous and parallel-work authorization applies.

**Design:** `done` + Enter requests a nonblocking early finish during passive recording. First Ctrl-C during recording requests the same controlled stop; preflight and baseline interrupts remain failures. The camera child ignores terminal SIGINT and is closed by its parent. STOP/camera/telemetry failures still fail collection. Bind requested duration, elapsed duration and finish reason to raw events and reports.

**Interrupted evidence:** Keep original batch files byte-identical. An explicit recovery sidecar may admit only the narrow operator-ended KeyboardInterrupt signature after a valid baseline, with bound source hashes, clean termination, zero logger drops, disabled/healthy telemetry and confirmed STOP, and preserved camera records/clock anchors. Ordinary failure admission stays closed; downstream quality and physics gates stay unchanged.

- [x] TDD and implement early finish in experiments/CLI plus nonblocking terminal helper. Verify baseline cancellation, recording finish, cleanup failures and actual spawned camera SIGINT behavior.
- [x] TDD and implement explicit recovery verification in a dedicated module with workflow/release-review integration. Verify altered hashes, extra errors, malformed clock metadata, unconfirmed STOP, logger loss and early interruption reject.
- [x] Preserve the original training/validation batch and review both raw sources. Freeze honest pose/release/free-motion annotations before model scoring; report any insufficient evidence.
- [x] Fit training, score independent validation, plot observed/predicted motion. Export only if camera/physics gates pass. Do not select favorable validation windows or change gates.
- [x] Run relevant tests and full suite, inspect/review changes, stage updated collector without serial access, save evidence and commit.

No motor commands, firmware/gain/calibration changes or new physical collection in this task. The operator confirms the runs were intentionally ended with Ctrl-C after collection. No claim of accurate dynamics follows merely from recovering the file lifecycle.

## Outcome

Both original interrupted recordings were preserved and recovered with separate reproducible sidecars. All six releases in each were annotated before fitting and retained. The fit was rejected by unchanged camera/pose and dynamics gates, so no model export occurred. Full suite: 1,309 passed, 8 skipped, 390 subtests passed. Independent review issues were fixed and retested. Evidence and reproduction instructions: `evidence/passive-batch2-20261017/`. No serial access or powered motion occurred.
