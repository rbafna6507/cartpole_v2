# Controlled swing development experiment — 2026-10-26

Offline research only. No rig, Jetson, serial, firmware, or working policy modifications.
`policies/working.json` is copied for actor initialization; critic, optimizer and RNG
start fresh. This is not a continuation of the old combined-policy optimizer.

## Recovered playbook

Read `docs/rl-training.md`, `SYSTEM_README.md` sections 16–17, the October 21 recovery
plan, `combined-next` protocol/package/HTTP watcher, and `recovery-20261021/package_recovery.py`.
The old filtered combined campaign trained **without** domain randomization. Its
reliable recovery uses a genuine foreground training cell and direct HTTP downloads,
not a detached job or kernel-executed status queries. CLI 0.7.4 and all preserved
HTTP watcher source pins match locally. A read-only OAuth session listing succeeded
on October 26 and found no active runtimes (the CLI pruned one stale local record).

## Frozen objective versions

All use the versioned `rig-calibrated-20261021-v1` nominal experiment, filtered
encoder observations, the original 21 actor inputs, 100 Hz decisions and 1 kHz
executor. Original `TrainingEnv` and old policy files are unchanged.

- **v1:** original dense reward, extra quadratic rail-zone cost outside 0.22 m
  (weight 2) and speed cost `0.01*max(abs(omega)-6,0)^2`. Normal horizon truncates
  without terminal dwell bonus; original physical fault penalties remain.
- **v2:** replaces the added speed cost with
  `max(cos(theta)+L_eff*omega^2/(2*9.81)-1.15,0)^2`. This allows the kinetic energy
  required at the bottom to reach upright, unlike a blanket low-speed threshold.
- **v3, launched cloud campaign:** v2 plus termination on an unwrapped angular
  range reaching `2*pi`. Subtract a fixed `3*max_steps` raw penalty (7,500 at 25 s,
  or 75 after optimizer scaling), once, independently of violation time. Report
  `constraint_violation` separately from physical `fault_reason`. Half-turn
  hanging-to-upright motion and crossing the wrapped ±pi boundary are allowed.
  This history-dependent task constraint is partially observed by the unchanged
  feedforward actor. It can fail to learn; it does not guarantee useful swing-up.

Full rotations mean maximum minus minimum **unwrapped physical angle**, divided
by 2pi. Cumulative absolute angular travel is a separate metric (ordinary repeated
pumping can exceed one turn of travel without completing a full excursion).
Reported unwrap assumes less than pi change per 10 ms decision. Rail-zone dwell,
first continuous 1 s catch, final 5 s hold, constraint failures and physical faults
are separate. Controlled success requires final 5 s hold and range < one full turn.

Randomization per episode: effective length ±5%, angular damping/dry friction ±20%
with coherent torque/inertia conversion; encoder noise 0–0.003 rad, telemetry 0–5 ms,
command delay 0–3 ms; encoder bias ±1°, sine shape ±4°, cosine shape ±5° before
quantization and observer. These are engineering coverage bounds, not measured
confidence intervals. Executor rails/limits/leases are fixed. Every episode records
actual sampled settings.

## Measured local pilots

Both 4,096-step pilots used seed 11, 25 s episodes, working-actor initialization,
new training seeds 108000–108127 and one inspected development seed 109400 with
hanging/upright starts under nominal and randomized settings. This is a very small
sample, not a performance estimate. All checkpoints held 2/2 nominal episodes and
1/2 randomized episodes (randomized upright failed final hold); physical faults 0.

| Objective/step | Nominal hanging catch s | Nominal range turns | Nominal rail s | Random hanging catch s | Random range turns | Random rail s |
|---|---:|---:|---:|---:|---:|---:|
| Initial | 4.81 | 1.840 | 2.16 | 6.43 | 1.864 | 3.23 |
| v1/2048 | 4.68 | 1.815 | 1.83 | 7.01 | 1.914 | 2.80 |
| v1/4096 | 4.14 | 1.811 | 1.89 | 9.24 | 5.957 | 5.47 |
| v2/2048 | 4.67 | 1.814 | 1.83 | 10.62 | 5.893 | 6.46 |
| v2/4096 | 5.58 | 2.830 | 2.83 | 8.93 | 3.911 | 4.55 |

**No hanging evaluation met controlled-swing qualification.** v2 selection retained
the initial actor. v1 final export predates the selection improvement; it is an
unselected pilot artifact, not a candidate. Both pilot exports passed numeric SDK
emission parity. Exact experiment source hashes are preserved in `pilot-source`
and `pilot-v2-source` respectively, alongside their checkpoint manifests and reports.
These experiments motivate testing a constraint, not claiming the reward solved it.

## New campaign and checkpoints

`colab-v3-1024000` freezes one projected-PPO seed-11 trial, 1,024,000 training steps,
25,600-step checkpoints, 25 s episodes, learning rate 3e-6, rollout 1024, batch 64,
10 epochs, gamma .999, GAE .98, initial standard deviation .05, reward scale .01.
The narrow inherited exploration and low learning rate may retain the old strategy
or fail to discover a permitted swing. Initial weights remain eligible.
Development seeds are 109400/109401; reserved confirmation 109500–109515 are rejected
by the training/selection CLI. Selection prioritizes controlled successes, hold rates,
faults, rotation excursions, rail dwell and catch time; the last checkpoint has no
special preference. `actor.json` copies the selected actor; all checkpoints remain.

Source ZIP includes new uncommitted modules and the nominal profile JSON. Its recipe,
archives and remote helper are hash-bound. `bundle-rehearsal.json` records the exact
bundle extraction and a local 1,024-step v3 execution/export check. No short smoke
establishes swing-up competence. The cloud source remains frozen even if this checkout
subsequently changes.

The HTTP-only `cartpole_sdk.learning.controlled_watch` verifies the remote recipe,
checkpoint canonical manifest, experiment source pins, archive/actor SHA256 and ZIP
CRC before publishing immutable local checkpoints. It allows up to 15 minutes for
startup, then stops on three consecutive transport failures after first success.
It never allocates, executes kernel status, restarts training or relaunches a VM.
Complete checkpoints are published before slow evaluation. Final report has its own
hash receipt. Keep the watcher/laptop awake and inspect receipts, not stale status.

Resume uses `--resume <complete-checkpoint-directory>` and a **new output directory**,
with the same source/configuration and an additional step budget. It validates all
bindings, loads `EquilibriumPPO`, checks serialized optimizer moments and absolute
counters, then continues with a fresh environment/randomization index. This is full
actor/critic/optimizer continuation, not bitwise environment/RNG restoration.

Example offline training/export:

```sh
.venv/bin/python examples/controller_starter/train.py \
  --output runs/controlled-v3-smoke-001 --steps 1024 --checkpoint-every 1024 \
  --seconds 5 --init-actor policies/working.json --objective controlled-swing-v3
```

Cloud allocation/launch is separate from preparation. Preserve snapshots and final
receipts before stopping a runtime. Never retry an ambiguous allocation blindly.

The final reviewed launch bundle is **`colab-v3-1024000-bound`** (earlier bundle
folders are preserved rehearsals, not launch targets). Its SHA256 is
`30536f1aa86471018ac6c4d7cc38cc9fdbcdc563fe7a21a81a99abab0a814faa`.
The bound checkpoint recipe requires exact profile, model, algorithm, source set,
all runtime source hashes, Python/dependency versions, training/evaluation/reserved
seed sets, initial actor digest, randomization and hyperparameters. Remote preflight
must match dependencies and source before training starts; an unexpected cloud Torch
build tag stops launch for investigation. The watcher reports a failed job even if
it failed before producing any progress file.

Qualification now reports hanging and upright separately. A best development actor
is still exported when no hanging case qualifies, with `selected_step: null`,
`qualified_for_controlled_swing: false` and `deployment_candidate: false`.

Exact continuation example after restoring the source archive and locked environment
from the **same** bundle, with a verified checkpoint copied into that extracted tree:

```sh
# Run inside the restored frozen source tree, using its restored .venv.
.venv/bin/python -m cartpole_sdk.learning.controlled_training \
  --output runs/controlled-v3-continuation-001 \
  --resume recovered/checkpoints/step-000025600 \
  --steps 998400 --checkpoint-every 25600 --seconds 25 --seed 11 \
  --evaluation-seeds 109400 109401 --objective controlled-swing-v3
```

This is an illustrative continuation from step 25,600, not a claim that checkpoint
exists. The remaining 998,400 decisions reach the original 1,024,000 budget. Do not
run continuation against a later edited checkout: strict provenance rejects it.
Keep the Mac awake and online for foreground client and backup downloads. Use the
HTTP watcher's `watch-status.json` and `last-complete.json`; generic kernel status
can queue behind foreground training. Watcher failure never relaunches training.

## Launched and first trained backup verified

The single CPU campaign `cartpole-controlled-v3-20261026` is running from
`colab-v3-1024000-bound`. Setup and exact remote dependency/source preflight passed.
The foreground training cell and HTTP-only watcher run in detached local sessions
under `caffeinate -i`, independently of this agent turn. The Mac must stay online;
process survival, Colab lifetime and completion are not guaranteed. No second VM
was allocated and no working policy was replaced.

`first-trained-checkpoint.json` records an independently rechecked local checkpoint
at **25,600 optimizer steps**: canonical manifest, exact frozen recipe binding,
SHA256, ZIP CRC, restored optimizer state/counter, and exported numeric actor match.
The watcher had verified two checkpoints (initial plus trained) and remained running.
Measured initial optimizer throughput was 151 steps/s; one million training steps
therefore implies roughly 1.9 hours of optimizer time at that rate, plus substantial
checkpoint evaluation and backup time. This is an estimate, not a completion promise.

The initial cloud evaluation had **0/2 controlled hanging successes** under each
nominal and randomized scenario. Upright holds were 2/2 nominal and 1/2 randomized.
The first trained checkpoint's evaluation was still in progress when this receipt
was saved. No controlled swing-up result or deployment candidate is claimed.

Local backups: `runs/controlled-v3-20261026-backups`. Monitor its HTTP-derived
`watch-status.json` and `last-complete.json`; logs and foreground client state are
under `runs/controlled-v3-20261026-cloud`. The watcher stops at its eight-hour bound
or verified completion/failure; it never restarts training. Compact rehearsal outputs
are preserved in `bundle-smoke-results`; duplicate extracted source trees remain
local only.
