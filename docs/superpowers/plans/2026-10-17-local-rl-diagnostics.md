# Local RL diagnostics implementation plan

> Execute inline using executing-plans; use TDD and an independent final review.

**Goal:** Provide reproducible short learning experiments and a useful evidence-based iteration decision.
**Architecture:** Add a diagnostic wrapper and runner beside the existing PPO implementation. Do not change production reward, source contracts, Colab jobs or hardware.
**Tech stack:** Existing MuJoCo, Gymnasium, SB3 PPO, NumPy and Matplotlib.
**Spec:** ../specs/2026-10-17-local-rl-diagnostics-design.md

## Global constraints
- No hardware or cloud mutation. Existing checkout is user-designated and clean at bb032fc.
- Nominal 1 ms physics/100 Hz decisions, actual observed features/governor, 20 ms leases, jerk 150 unchanged.
- Explicit training/evaluation split and immutable output directories. Diagnostic checkpoints are not deployable actors.
- Same budgets and optimizer settings for adjacent comparisons. No convergence guarantee or selection by reward alone.

## Review focus
Seed overlap, observation mutation/truth leakage, evaluation affecting training RNG,
short-window hold false positives, unequal-budget/source mismatches in aggregation.

## Task 1: Diagnostic runner
- [x] Tests first in tests/test_rl_diagnostics.py for reset schedules, fixed scaling, split rejection, immutable outputs, real tiny PPO/evaluation/checkpoint and record completeness.
- [x] Implement learning/diagnostics.py: DiagnosticEnv, evaluate_model, run_pilot, summarize_suite. New examples/rl_diagnostics.py and executable scripts/rl-diagnostics.
- [x] Verify focused tests, help and tiny pilot.

## Task 2: Physical-task feasibility and local trials
- [x] Independent read-only observed-policy/environment audit and positive controls.
- [x] Freeze manifest before each pilot. Run 3 variants by 3 optimizer seeds, 20,480 steps each; inspect intermediate metrics.
- [x] Reproducible plots, retain all outcomes, compare paired seed results; use fresh confirmation only if warranted.

## Task 3: Review and delivery
- [x] Independent source/method review, fix important issues with tests.
- [x] Full suite and artifact verification, docs with exact commands and development cycle.
- [x] Commit source/evidence without pushing.

## Ledger
Initial ruling: user has already authorized autonomous iterative local implementation and experiments. No additional approval gate is needed. Scope is additive diagnostic tooling, so existing production snapshots remain untouched.

Ruling before any learning trial: positive-control feasibility passed 4/4 upright
cases. The governor probe showed initial std1 explores well beyond the immediate
jerk-limited response. Use upright, upright-lowstd (std .05), upright-scaled as
the three equal-budget variants. Mixed remains available but is not part of this
balance screen. Each candidate differs from upright in exactly one factor.
The cloud mixed-task runs remain the longer reference. Evaluation seeds40000/40001
are development; 41000..41007 are reserved for a fresh longer follow-up.

Final ledger: nine PPO probes and four supervised diagnostics completed. No learned
candidate passed strict final hold. Seeds41000–41003 are now inspected development
cases; the adaptive6000-update follow-up is regression. Reviewer findings about
recipe comparability, identity and source hashes were fixed with failing tests
first. Full suite:1409 passed,7 skipped,456 subtests. Existing production/cloud
recipe unchanged. See evidence/rl-diagnostics-20261017 for all outcomes.
