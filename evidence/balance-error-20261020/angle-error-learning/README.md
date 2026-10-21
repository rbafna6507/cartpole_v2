# Bounded angle-error training pilot — 2026-10-20

Development-only, upright-only plumbing experiment. No hardware actor was exported. Original source-pinned modules, profile and prior actor bytes stayed unchanged. This is not the subsequent full swing-up task.

New module: `src/cartpole_sdk/learning/error_training.py`; CLI: `scripts/balance-error-learning`; tests: `tests/test_error_training.py`. The completed module is frozen so saved-checkpoint replay source checks remain valid. Related focused regression suite: **30 passed**, including 17 new tests and actual tiny PPO/checkpoint replay.

The wrapper draws a private, seeded, constant angle offset per training episode and rotates only valid actor sine/cosine after the existing quantization. True dynamics, true-state reward, angular rate, validity and ages remain unchanged. This is an actor-input perturbation, not a calibrated encoder model. Cart and true-angle RMS are reported independently; the existing balance/dwell reward was not replaced by an RMS objective.

`--observer-bw 8` rebuilds the admitted experiment with a copied executor dictionary. It never rewrites the bw10 source profile or bypasses live SDK executor comparison. Overrides 6,8,10 were implemented; bias amplitude is bounded 0..3 degrees. This pilot used raw encoder angle only. Only raw input is supported by this experiment claim: the frozen CLI does not explicitly reject non-raw profile inputs, and such use has not been validated.

## Frozen comparison

Optimizer seeds3,17, each baseline0 degrees versus uniform±1 degree. Four runs ×4096 decisions = **16,384 training decisions**; all initial/final evaluations total **80,000 decisions**. Two single-thread workers; wall time about166seconds. Teacher gains(1,2,40,2),1500 supervised updates/run,LR3e-6,std.02,equilibrium projection,5second training episodes. Both arms start with exactly matching weight hashes and matching initial evaluation metrics within each seed.

Train poses13000..13127; independent fresh development poses66000/66001. Fixed evaluation matrix0,−.5,+.5,−1,+1degrees,10seconds each,initial/final. These are inspected development results, not heldout selection. All failures are retained; no candidate selected.

| Seed | Initial nominal tail cart RMS | Final baseline | Final bias-trained |
| --- | --- | --- | --- |
| 3 | 6.237mm | 7.525mm | 8.805mm |
| 17 | 7.524mm | 7.525mm | 9.077mm |

Both final arms held nominal4/4 full sampled episodes. Both achieved **0/16 holds** on all nonzero evaluation biases. Whole-trajectory nominal cart/true-angle RMS: baseline22.056mm/0.16725degrees; bias-trained22.681mm/0.16911degrees. This short budget demonstrates the experiment path, not robustness improvement or convergence. A memoryless actor may not distinguish angle bias from true tilt; no guarantee follows from adding randomization.

## Exact commands

Run from the repository root with the existing RL environment. All actual argv, return codes and logs are retained in the archive; `driver.py` reproduces the two-worker orchestration and writes the protocol before running. It refuses to overwrite the original output folder.

```sh
export PYTHONDONTWRITEBYTECODE=1
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
export VECLIB_MAXIMUM_THREADS=1 NUMEXPR_NUM_THREADS=1
scripts/balance-error-learning train \
  --profile training/profiles/rl-encoder-20261020 \
  --output runs/NEW-bias1-seed3 --observer-bw 8 --seed 3 \
  --bias-degrees 1 --steps 4096 --every 4096 \
  --seconds 5 --evaluation-seconds 10 --evaluation-seeds 66000 66001 \
  --learning-rate .000003 --policy-std .02 --imitation-updates 1500
```

Repeat with seed17 and with bias0 using distinct output paths. For replay on new poses (not run as part of this pilot):

```sh
scripts/balance-error-learning evaluate runs/NEW-bias1-seed3 \
  --output runs/NEW-evaluation --seeds 67000 67001 --seconds 10
```

Replay refuses overlapping pose seeds, changed source/archive/checkpoint hashes, and existing output directories. To replay after later source changes, restore the archived source in a separate checkout with the pinned dependency versions. Neither CLI exports a deployment actor or changes acceptance fields.

The compressed archive preserves all four recipes, eight checkpoints, source snapshots, initial/final full traces, actual training-episode offsets, logs/receipts, frozen protocol and driver. `archive-manifest.json` hashes every payload and the archive; each compressed payload was read back and verified.
