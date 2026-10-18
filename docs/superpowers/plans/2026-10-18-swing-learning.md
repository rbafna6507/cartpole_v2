# Swing-up and balance learning implementation plan

> **For agentic workers:** Use executing-plans for the shared harness and independent agents for teacher search and transfer audit. The user authorizes the same autonomous experimental cycle as the balance work.

**Goal:** Establish a reproducible local route toward a single observed-state policy that swings up and balances, with explicit limits on simulation-to-hardware evidence.

**Architecture:** Extend the existing PPO experiment tools with deterministic mixed/curriculum resets and observed-state teacher demonstrations. Preserve unchanged physics, observation and executor contracts. Screen multiple seeds at equal online budgets; retain failures and evaluate frozen candidates on new poses and explicit stress scenarios.

**Tech Stack:** Existing Python 3.11, MuJoCo, PyTorch/SB3 CPU, single numerical thread per worker; bounded parallel experiments on M3 Pro.

**Spec:** User's same-playbook request; docs/balance-learning.md and evidence/rl-balance-20261018.

## Constraints

- No hardware access, flashes, commands, or changes to cloud training jobs.
- 100 Hz policy, 1 ms physics/executor, raw acceleration action, jerk 150 m/s³, unchanged observation freshness and fault rules.
- Actor and teacher act only on observed inputs; truth is for rewards and evaluation.
- Keep every optimizer seed and failed experiment; offline imitation cost and prior information are distinct from online budgets.
- Training poses 20000..20127; teacher development 52000..52005; learner development 53000..53003; reserve 55000+ for frozen qualification.
- No claim of hardware acceptance from simulation. Stress ranges without measured bounds must be labeled engineering hypotheses.

## Tasks

- [x] Test and implement deterministic intermediate-angle resets while preserving existing resets and bookkeeping. Add mixed-start and staged training recipes.
- [x] Screen observed-state swing-up/capture teachers independently, retaining exact sources, recipes and traces. Use an explicit callable and observed-before-action targets for any imitation.
- [x] Add a self-runnable train/evaluate harness with source/checkpoint/data hashes, actor-only supervised initialization, RNG isolation, after-update checkpointing and phase metrics.
- [x] Run short multi-seed comparisons, inspect captures, centering, oscillation and faults, and adapt the next experiment to specific failure evidence.
- [x] Audit hardware/simulator parity and execute finite declared uncertainty scenarios on promising frozen candidates. Distinguish task failures from correctly triggered stops.
- [x] Run longer unseen starts and existing balance regression. Preserve plots, checkpoints and failures, document runnable commands and outstanding blockers, test and independently review before commit.

## Review focus

- Teacher labels must precede action and exclude truth; train/validation demonstrations split by whole trajectory.
- Reset random streams and curriculum stage must be deterministic and recorded; no evaluation-pose contamination.
- Single-network claims must exclude hidden teacher switches/fallbacks; stateful baselines must be identified.
- Metrics must report continuous final holds and capture timing, not reward alone; faulted or short episodes cannot pass.
- Frozen evaluation must check sources, recipe, demonstration and checkpoint bindings; no silent mutation of nominal model for stress tests.

## Completed outcome

18 neural trials, three frozen stress/parity suites, a fresh 60-second neural
evaluation, an independently audited stateful teacher search and a failed
stronger-centering bias screen are retained in evidence/rl-swing-20261018.
All software work and offline checks are complete for this cycle. Nominal
simulation success is not hardware qualification; no candidate cleared the
stress gate. The evidence README records the next controlled learning changes
and outstanding physical-model work.
