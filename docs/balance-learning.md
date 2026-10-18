# Local balance-first learning

These experiments run entirely on this computer. They do not command the rig or
change Colab training. Keep the production training profiles unchanged while
comparing hypotheses locally.

The environment uses the rig SDK's observed inputs, 100 Hz policy decisions,
1 ms physics/executor steps, delayed/quantized encoder observations, one action
governor, ±25 m/s² raw actions and jerk 150 m/s³. The actor receives no simulator
truth. Truth is used for rewards and evaluation metrics.

## Train a short comparison

The initial three-seed comparison used 20,480 online decisions per seed. A teacher
initialization additionally uses 1,500 supervised optimizer updates on synthetic
observed states. Equal online interaction budgets do not mean equal total compute
or equal prior information.

```sh
./scripts/balance-learning train \
  --profile training/profiles/rl-encoder-20261017 \
  --initialization teacher \
  --gains evidence/rl-balance-20261018/teacher-gains.json \
  --constraint equilibrium --learning-rate 0.000003 \
  --seed 3 --steps 20480 --every 4096 \
  --output runs/my-balance-teacher-seed3
```

Use unique output directories and optimizer seeds 3, 17 and 29. For a matched
scratch control, change only `--initialization scratch`, remove `--gains`, and
retain the constraint, learning rate, budgets and seed list. For an ablation of
the equilibrium constraint, use `--constraint none`. The standard comparison
used learning rate 0.00003; the reduced-update experiment used 0.000003.

`equilibrium` is an explicitly constrained PPO experiment: after initialization
and each rollout's PPO update, the actor's final output bias is adjusted so the
mean command is zero for a centered, stationary, upright observation with fresh,
valid channels. The policy remains an ordinary neural network; there is no
controller fallback at evaluation. This constraint does not protect all feedback
gains or guarantee PPO's usual surrogate-update bounds. Logs include the applied
correction and KL measured after projection.

Each run freezes its recipe and source archive, saves after-update checkpoints,
records training episodes and optimizer diagnostics, and evaluates every checkpoint
on the same development poses. Reports include continuous hold, centering RMS,
cart displacement, angle error, command changes, rail braking and faults. A high
reward is not an acceptance criterion. Development seeds are not a final test set.

## Evaluate a frozen candidate

After selecting a recipe, declare fresh pose seeds and a longer duration before
looking at their results. Example for a newly trained run (choose unused seeds):

```sh
./scripts/balance-learning evaluate runs/my-balance-teacher-seed3 \
  --seeds 48000 48001 48002 48003 --seconds 60 \
  --output runs/my-balance-long
```

The hold flag means **the final five seconds** meet all three bounds continuously:
`|angle| < 0.15 rad`, `|angular rate| < 1 rad/s`, and `|cart position| < 0.12 m`,
with a full episode and no fault. To claim a full-duration hold, also inspect
balanced fraction and longest continuous dwell. The final-window RMS alone can
look good after a previous failure; inspect trajectories and total balanced time.

Hanging starts are a separate task. Probe them explicitly:

```sh
./scripts/balance-learning evaluate runs/my-balance-teacher-seed3 \
  --seeds 49000 49001 --seconds 25 --starts hanging \
  --output runs/my-balance-hanging-probe
```

A balance-only network has not been trained to swing up. This test measures that
gap; it does not add swing-up training.

If the source has changed since training, strict source guards reject evaluation.
Replay the original evaluator instead, keeping the same installed dependencies:

```sh
./scripts/replay-balance-evaluation runs/my-balance-teacher-seed3 \
  --seeds 48000 48001 --seconds 60 --output runs/my-original-source-evaluation
```

This verifies hashes, extracts the frozen source into a temporary directory, runs
its unchanged evaluator, and records replay provenance. Use only trusted local
checkpoints. It does not install packages or bypass the original guards.

## Compare and preserve results

```sh
uv run --extra rl python evidence/rl-balance-20261018/tools/summarize.py \
  runs/my-balance-scratch-seed3 runs/my-balance-scratch-seed17 runs/my-balance-scratch-seed29 \
  runs/my-balance-teacher-seed3 runs/my-balance-teacher-seed17 runs/my-balance-teacher-seed29 \
  --output runs/my-balance-comparison
```

The summary checks completion, source/checkpoint bindings, equal budgets and
optimizer-seed sets before plotting. Run comparisons with matching recipes;
keep learning-rate or constraint ablations as separate suites. Every seed counts.

Archived evidence for the October 18 cycle lives in
`evidence/rl-balance-20261018`. It includes failed attempts, selected gains, all
checkpoints, exact sources and trajectories. Restore its archives into a new
folder rather than overwriting active runs.

## Advancement criteria

1. Preserve nominal balance across multiple optimizer seeds, with substantial
   centering margin and no faults. Compare against the initialized actor too:
   retaining a teacher's skill is not evidence that PPO improved it.
2. Freeze candidates and test long, unseen poses; then expand the capture region
   and initial angular rates. The current default upright resets are only about
   ±4° from vertical, with small cart/velocity disturbances.
3. Add a swing-up/capture curriculum and evaluate hanging starts separately while
   retaining the established balance regression suite.
4. Add measured dynamics/timing variation, observation failures, vision/fusion,
   and wider independent evaluation before any bounded hardware qualification.

The diagnostic checkpoints intentionally have no deployment `actor.json`.
Hardware acceptance remains false. These nominal simulation results cannot
establish transfer to the real rig.
