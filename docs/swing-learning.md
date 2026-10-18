# Local swing-up and balance development

Run these experiments with the rig powered off. The commands use local CPU
simulation and do not connect to hardware or alter Colab jobs. On this M3 Pro,
each worker uses one numerical thread. Three independent seeds can run in
parallel; a GPU is not required for these small networks and serial MuJoCo steps.

The task is one observed-state, feedforward actor for both swing-up and balance.
It emits raw cart acceleration at 100 Hz through the unchanged SDK observation
contract and 1 kHz executor model. The actor never sees simulation truth. Jerk
stays at 150 m/s³ and the recorded motion limits remain unchanged. Physical truth
is used for reward and metrics only.

## Short reproducible comparisons

```sh
./scripts/swing-learning train \
  --profile training/profiles/rl-encoder-20261017 \
  --initialization balance --reset-mode curriculum \
  --seed 3 --steps 20480 --every 10240 --seconds 10 \
  --evaluation-seconds 25 \
  --output runs/my-swing-seed3
```

Repeat with optimizer seeds 17 and 29 and distinct output directories. Match
budgets and settings across comparisons. `scratch` has no supervised
initialization. `balance` fits the observed linear law `x + 2*v + 40*theta +
2*omega` before PPO. `mixed` alternates near-upright and near-hanging resets;
`curriculum` uses 1/4 upright, 1/4 hanging and 1/2 intermediate poses, expanding
intermediate angles by thirds of the online budget. These are reset curricula,
not truth exposed to the actor or changes to physics.

All variants use constrained PPO: the actor's output bias is projected to zero
at the upright equilibrium after initialization and each optimizer rollout.
This is not ordinary PPO and does not preserve its surrogate update bounds.
It still produces an ordinary numeric neural actor, with no teacher fallback.

## Demonstration initialization

Demonstrations contain observed channels immediately before an action, the raw
teacher command and whole-episode IDs. They exclude simulator truth. The format
is an NPZ with `state`, `valid`, `age_s` arrays of shape `(N,7)`, and
`raw_action`, `episode` arrays of shape `(N,)`. Train/validation partitions split
whole pose IDs, keeping both start families together. Failed teacher episodes
are retained and identified in the accompanying metadata.

After restoring the evidence archive, a matched anchored experiment is:

```sh
./scripts/swing-learning train \
  --profile training/profiles/rl-encoder-20261017 \
  --initialization demonstrations --reset-mode curriculum \
  --demonstrations runs/local-swing-teacher-20261018/demonstrations/demonstrations.npz \
  --train-episodes 21000 21001 21002 21003 21004 21005 21006 21007 21008 21009 21010 21011 \
  --validation-episodes 21012 21013 21014 21015 \
  --balance-anchor-weight 10 --imitation-updates 3000 \
  --seed 3 --steps 20480 --every 10240 \
  --output runs/my-anchored-seed3
```

Balance anchoring adds counterfactual near-upright states with independently
varied cart velocity, angle, angular rate, previous acceleration and ages. Its
loss preserves the known feedback law while fitting swing demonstrations. This
addresses a measured failure: plain imitation achieved small action RMSE by
following previous acceleration, almost erasing angle feedback. Zero anchor
weight reproduces the unanchored comparison. An anchor weight is an experimental
loss choice, not a safety guarantee. It changes stochastic minibatch sampling
as well as the objective; selection uses demonstration validation MSE plus
weighted synthetic balance validation MSE. Both errors are recorded separately.

These initializations use extra supervised compute and prior controller
knowledge. Equal online decision budgets do not mean equal total compute.
Teacher search is a stateful controller baseline, separately identified in the
evidence; its success is not a neural-policy success.

## Evaluate before advancing

```sh
./scripts/swing-learning evaluate runs/my-swing-seed3 \
  --seeds 56000 56001 56002 56003 --seconds 60 \
  --output runs/my-swing-long
```

Use fresh seeds declared before inspecting the result. The hold gate requires
all final five seconds of successive 100 Hz truth samples to satisfy
`|theta|<0.15 rad`, `|omega|<1 rad/s`, `|x|<0.12 m`, with a complete horizon and
no fault. Also inspect first capture time, whole-episode balanced fraction,
longest hold, cart excursion, rail braking, final centering and command changes.
A last-window hold alone does not establish uninterrupted balance since capture.

If source files changed since the run, use its verified frozen evaluator:

```sh
./scripts/replay-balance-evaluation runs/my-swing-seed3 \
  --seeds 56000 56001 56002 56003 --seconds 60 \
  --starts hanging upright --output runs/my-frozen-swing-long
```

Despite its older name, the replay command accepts both balance and swing runs.
It extracts only the pinned source archive, retains the original loader checks,
and requires the installed dependency versions to match. Only load trusted
local checkpoints/source archives.

## Stress and SDK inference parity

```sh
./scripts/swing-transfer-check runs/my-swing-seed3 \
  --checkpoint 20480 --seeds 57000 57001 --seconds 25 \
  --output runs/my-swing-transfer
```

This works after source changes too. It verifies the original checkpoint with
its archived loader, then runs separately hashed evaluation tools. The suite
checks nominal behavior, length/friction/noise/delay variations, ±1° observed
angle bias, and expected faults. In `parity/`, the actual exported numeric SDK
actor drives the simulator; its raw commands are compared with SB3 on identical
observations. Action agreement, task success and fault handling are separate
results. Exported actors remain `DEVELOPMENT_ONLY` and unaccepted for hardware.

See [simulation transfer](simulation-transfer.md) for exact scenarios and model
limitations. The ideal cart acceleration servo, incomplete global angle mapping
and unmeasured current timing distribution remain major transfer gaps. A passing
simulation cannot remove them. Physical qualification waits until rig access is
available; these scripts do not initiate it.

## Preserve and compare

Every run retains its source, exact recipe, demonstrations, checkpoints,
optimizer diagnostics and per-checkpoint trajectories. Do not discard poor
seeds or select on a final test set. To compare matched groups:

```sh
uv run --extra rl python evidence/rl-swing-20261018/tools/summarize.py \
  runs/my-swing-seed3 runs/my-swing-seed17 runs/my-swing-seed29 \
  --output runs/my-swing-summary
```

Directory group names must end in `-seedNUMBER`. The script checks completion,
source/data/checkpoint hashes, equal online budgets and matching optimizer seed
sets. Development poses are repeatedly inspected and never called a final test.
The October 18 retained results and decisions are in
[the experiment record](../evidence/rl-swing-20261018/README.md).

## Run the stateful controller baseline

This is a comparison and demonstration generator, not a learned actor or a
hardware command. Use fresh seeds for a new validation set:

```sh
uv run --extra rl python examples/swing_teacher_search.py \
  --profile training/profiles/rl-encoder-20261017 \
  --candidates evidence/rl-swing-20261018/frozen-candidate-expanded.json \
  --purpose frozen_evaluation --seconds 60 \
  --seeds 59000 59001 59002 59003 \
  --output runs/my-controller-baseline
```

The saved `fresh60/source.zip` in the teacher archive contains the exact source
and profile used for the retained result. The plotting script
`evidence/rl-swing-20261018/tools/teacher_trajectories.py` verifies and plots all
eight retained hanging trials; its `--help` lists the input/output arguments.
