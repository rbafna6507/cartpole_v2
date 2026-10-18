# Balance learning experiments implementation plan

> **For agentic workers:** Use executing-plans for the shared harness and a separate teacher-search subagent. The user explicitly authorized execution and iterative experiments.

**Goal:** Establish whether controller initialization enables reliable nominal balance before expanding to swing-up.

**Architecture:** Add a local-only experiment harness around the existing observed-state Gym and PPO implementation. Freeze recipes, source and checkpoints. Compare scratch and supervised initialization with identical online interaction budgets and optimizer settings; report initialization costs separately.

**Tech Stack:** Python 3.11, MuJoCo, SB3/PyTorch CPU, two single-thread training workers.

**Spec:** User's four-stage cycle; docs/rl-development-cycle.md.

## Constraints

- No hardware or active Colab changes; 100 Hz actor, original sensor/action contract and governor, jerk 150 m/s³.
- No simulator truth as policy input, no teacher fallback at evaluation.
- Strict final five-second hold and fault criteria unchanged; measure centering/oscillation separately.
- Development seeds 42000..42005 (teacher), 43000..43003 (learner), fresh qualification 45000+ only after selection.
- No deployment claim or export until contract/parity and hardware qualification.

## Tasks

- [x] Add meaningful tests for imitation actor isolation, deterministic seed splits, exact budget/checkpoint accounting, evaluation metrics and source binding.
- [x] Implement learning/balance_experiment.py and self-runnable scripts/balance-learning with train/evaluate commands.
- [x] Find a better centered observed-state teacher in a separate script; freeze selected gains before the matched screen.
- [x] Run scratch/teacher initialization for optimizer seeds 3,17,29 at equal budgets. Keep every result, including failures.
- [x] Inspect trajectories; adapt one factor at a time only if failures justify it. Freeze candidates, run longer fresh initial conditions, and advance to swing-up only if balance is supported.
- [x] Plot learning and cart/angle/action traces. Document commands, results and remaining scope. Run focused/full checks and independent review before committing.

## Review focus

- Evaluation must leave optimizer/exploration RNG unchanged.
- BC must not train critic or standard deviation, and must not call teacher during rollout.
- Repeat outputs and seed overlap must fail before overwriting evidence.
- Every evaluation binds to an after-update checkpoint; no pre-update labeling.
- Source mutation and corrupt checkpoint hashes must fail closed.

## Completed cycle

- 20 local trials, 409,600 online decisions; three-seed ordinary PPO and constrained PPO comparisons, plus documented adaptive ablations.
- Nominal teacher search reduced cart oscillation; actor pretraining created competent balance policies. Ordinary PPO destabilized centering. Equilibrium projection plus a tenfold smaller learning rate retained balance.
- All three final candidates passed all eight fresh 60-second poses (24/24), with no faults and 100% balanced time. This is retention, not evidence PPO improves the teacher.
- Hanging probes passed 1/6: swing-up training remains a subsequent cycle. Wider capture, variation, vision/fusion and hardware qualification are outstanding.
- Full suite: 1,445 passed, 7 skipped, 456 subtests passed. Independent review verified trial and trajectory evidence.
- Evidence, failures, sources and checkpoints: `evidence/rl-balance-20261018/README.md`.
- The encoder Colab backup watcher lost its connection; a fresh status confirmed healthy training, an explicit backup succeeded with SHA-256/CRC checks, and the local watcher was restarted. No training recipe or remote trainer was changed.
