# Develop and diagnose an RL controller

A short run cannot prove eventual convergence. It can establish that the task is
controllable, expose implementation or optimization problems, and show which
changes deserve a longer experiment. Software tests establish contracts; they
do not establish that a policy learned control.

The local diagnostics below are offline. They never connect to hardware or Colab.
They reuse the actual observed-state Gym environment, reward and motion governor.
The current production training recipe and active Colab bundles stay unchanged.

## Run a short experiment

From the repository, run one five-second upright-training probe:

```sh
./scripts/rl-diagnostics pilot \
  --profile training/profiles/rl-encoder-20261017 \
  --variant upright --seed 3 \
  --steps 20480 --every 10240 \
  --output runs/local-upright-seed3
```

The initial local runs took about two minutes each, including evaluation (machine
and workload dependent). It freezes the recipe and source before training, evaluates the initial model and
each 10,240-step checkpoint on separate poses, and records optimizer CSV,
training episodes, final evaluation trajectories and model checkpoints. Outputs
must be new directories. The default evaluation runs both hanging and upright
starts for ten seconds and checks the final five seconds continuously balanced.

Repeat with `--variant upright-lowstd` and `--variant upright-scaled`, using unique
output directories. Use optimizer seeds 3, 17 and 29 for each variant. Compare at
equal step budgets. These are three different learning runs per variant, not just
three starting poses evaluated on one policy.

- `upright`: baseline observation units and initial normalized action std 1.
- `upright-lowstd`: change only initial action std to .05. The full acceleration
  bounds remain available, and PPO still learns its standard deviation.
- `upright-scaled`: change only observation units using fixed scales: cart
  position/rail, velocity/vmax, angle sin/cos unchanged, rate/10, acceleration/amax,
  brake unchanged, ages/.02 seconds. No fitted normalization statistics or truth
  observations are introduced.
- `mixed`: optional alternating hanging/upright reset schedule for a subsequent
  task comparison. It is not part of the initial balance-only screen.

All probes default to nominal dynamics, five-second training episodes and the
same optimizer settings. This intentionally simplifies the task relative to
25-second randomized cloud training. A result here cannot be substituted for that
longer combined-task evaluation. Change one factor at a time when extending the
experiments.

Summarize completed comparable runs:

```sh
./scripts/rl-diagnostics summarize \
  runs/local-upright-seed3 runs/local-lowstd-seed3 runs/local-scaled-seed3 \
  --output runs/local-screen-summary.json
```

Use all three optimizer seeds in a real comparison. The summary retains each
seed, plus the median and range; one seed is only a smoke experiment. For plots:

```sh
uv run --script evidence/rl-diagnostics-20261017/tools/plot_screen.py \
  runs/local-upright-seed3 runs/local-lowstd-seed3 runs/local-scaled-seed3 \
  --output runs/local-screen.png
```

Diagnostic checkpoints intentionally lack a deployable `actor.json`. A successful
preprocessing or training change must be integrated into the production training
and numeric SDK export with equivalence checks before hardware use. In particular,
a scaled-observation network cannot consume the unscaled SDK input unchanged.

## What to measure and when to advance

1. **Establish a positive control.** Run a known controller through the same
   sensors and governor. If that fails, inspect the environment before blaming
   PPO. Existing Python control held four nominal upright cases for ten seconds
   each in the initial audit; this is local feasibility evidence only.
2. **Learn balance first.** Measure balanced fraction, longest continuous hold,
   final five-second hold success, drift, rail braking, faults and command changes.
   Compare every optimizer seed. Increasing reward without increasing balance is
   not enough.
3. **Confirm a promising recipe.** Freeze it, then evaluate longer episodes on
   new pose seeds. The initial screen uses development seeds 40000/40001;
   41000–41003 have now been inspected in the teacher diagnostic and are
   development/regression cases. 41004–41007 remain unused, but a substantial
   final qualification needs a larger fresh set.
4. **Add swing-up.** Test hanging starts separately. Preserve balance competence
   while adding capture training. A balance-only learner has not learned swing-up.
5. **Add uncertainty and other sensors.** Reintroduce dynamics/timing variation,
   then compare encoder, vision and fusion. Stress invalid tracking separately:
   it is an explicit stop condition, not a recoverable observation substitution.
6. **Run the long experiment and qualification.** Use multiple training seeds,
   freeze the actor, evaluate on larger fresh sets and inspect trajectories. Then
   run stopped inference and bounded hardware trials through the SDK.

The workflow follows the SB3 recommendation to evaluate separately, run multiple
seeds and examine observation normalization:
[SB3 RL tips](https://stable-baselines3.readthedocs.io/en/master/guide/rl_tips.html).
Small-sample comparisons have substantial uncertainty; see
[Deep RL at the Edge of the Statistical Precipice](https://arxiv.org/abs/2108.13264).

## Results from the first local screen

See [the full evidence and limitations](../evidence/rl-diagnostics-20261017/README.md).
Nine short PPO runs did not establish sustained balance. Supervised initialization
from the working controller was substantially stronger, but also failed the
strict hold gate. No diagnostic recipe or checkpoint was promoted to production.

## Controller initialization and continued learning

The next experiment cycle is implemented in [Local balance-first learning](balance-learning.md).
It adds a better-centered teacher, matched scratch/initialized runs, explicit
zero-action equilibrium projection, frozen-source evaluation, and longer hold
checks. See its evidence before treating any initialized or fine-tuned network
as a swing-up controller.
