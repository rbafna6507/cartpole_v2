# Short local RL experiments

User goal: run small reproducible experiments that reveal learnability problems
and useful progress while the long Colab trials continue. No short experiment can
prove eventual convergence. Preserve all cloud jobs, hardware and current recipe.

Builder choices: add an offline-only diagnostic runner using the existing PPO
TrainingEnv and governor. Use five-second nominal training episodes to increase
reset frequency. Compare upright starts, upright starts with smaller initial action standard
deviation, and upright starts with fixed observation scaling. Mixed starts remain
available for later comparisons (see the pre-trial ruling in the plan). The adjacent comparisons change one factor. Use three
optimizer seeds (3,17,29), equal 20,480-step budgets, 128 training state seeds,
separate shared development evaluation seeds, and evaluation at 0/10,240/20,480.
Evaluate both starts over ten seconds, with five-second final holds. No fitted
normalizer, reward change, action-scale change, or physical limit change.

Report each seed, hold success, balanced fraction, longest dwell, first capture,
raw benchmark reward, rail braking, faults, and raw action variation. Preserve
source/config/dependency pins, model checkpoints and all episode/trajectory data.
Call evaluation cases development after inspecting them. Only follow promising
results with a fresh 25-second confirmation; do not claim from one seed or score.

An independent environment audit tests observed-state positive controls to separate
controllability from learning. If no positive control balances, resolve that
before declaring a learner broken. Diagnostic checkpoints are intentionally not
SDK deployment artifacts. A successful change must later receive a production
contract/export/parity change and separate hardware qualification.
