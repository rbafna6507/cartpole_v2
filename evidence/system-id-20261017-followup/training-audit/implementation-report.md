# Model-bound PPO implementation and synthetic verification

Date: 2026-10-17. Base audited commit: f849312. This report records new offline software verification, not accepted physical model or policy performance.

Delivered:

- `scripts/train-ppo`: executable repository-resolving train/evaluate wrapper; help parses without optional dependencies.
- `examples/train_ppo.py`: explicit model, complete executor snapshot, observation configuration and comparison prior; deterministic CPU PPO training, immutable checkpoint output, resume checks and disjoint evaluation.
- `learning/model_experiment.py`: content/hash/fit-consistency admission; preserves source model scope, assumptions and provenance. Current local scopes remain unqualified for global swing-up and require DEVELOPMENT_ONLY. Rejected fit reports are never admitted as models.
- `learning/ppo.py`: normalized scalar action maps once to raw m/s²; fixed 64×64 tanh PPO, periodic/final checkpoints, source/dependency pinning, fixed training seed pool, held-out reporting. Fixed-horizon terminal reward cannot trigger SB3 time-limit bootstrapping. PPO uses gamma .99; reported score is undiscounted.
- `policies/neural.py`: bounded numeric actor with the shared six-channel/seven-feature SDK encoder, explicit source/frame/cadence/freshness checks and stdlib-only inference. No Torch, MuJoCo or pickle is needed for the actor.
- Separate model-bound CEM module retained as a numeric baseline; old learning defaults and old artifacts unchanged.
- Optional `rl` and `plots` extras plus lockfile; docs/rl-training.md and notebooks/train_ppo_colab.ipynb. No Jetson dependency installation or hardware connection by this agent.

Final targeted command:

`/tmp/cartpole-rl-venv/bin/python -m pytest tests/test_model_training.py tests/test_ppo_training.py tests/test_rig_gym_env.py -q -p no:cacheprovider`

Result: **25 passed in 4.91 s** (`targeted-tests.log`). This includes actual PPO learn/save/reload/resume, train/evaluation seed overlap rejection, source/config mismatch and checkpoint corruption rejection, SDK actor numerical parity, base-only help, numeric actor dependency isolation, finite-horizon no-bootstrap regression, governed/observer behavior and admission gates. Root owns the final whole-repository test run.

Retained CLI demonstration:

- All inputs under `synthetic-ppo-inputs/` are explicitly synthetic DEVELOPMENT_ONLY historical model assumptions; no physical fit is used.
- `synthetic-ppo-final/`: 64 actual PPO steps, n_steps16, batch8, epochs1, training seeds11/12, optimizer seed7, 0.1-second episodes; periodic checkpoints at32/64.
- `ppo-final-heldout.json`: four frozen episodes, seeds1001/1002 × hanging/upright. 0 successes is expected for a horizon shorter than the required full final second; this is an execution check, not a performance result.
- `synthetic-ppo-final-resumed/`: resumes the 64-step checkpoint with32 additional steps, ending at96. Model/experiment/seeds/hyperparameters/source/dependencies remain pinned.
- Logs: ppo-final-train.log, ppo-final-evaluate.log, ppo-final-resume.log.
- Exact model/source/input identity, trained parameters, archive/actor hashes and dependency versions are in each checkpoint manifest. Input source paths point to the original temporary location; identical input relocation does not change experiment identity.

Installed isolated training versions: Python3.11.7, NumPy2.4.6, MuJoCo3.16.0, Gymnasium1.4.0, Stable Baselines3 2.9.0, Torch2.14.1. Installation was confined to `/tmp/cartpole-rl-venv` and `/tmp/cartpole-rl-uv-cache`. These actual versions are saved in provenance; the repository lockfile also preserves platform-specific dependency resolution.

Packaging checks:

- Colab notebook JSON and every Python cell parse; no Colab session was run.
- The documented source archive includes pyproject.toml, README.md, uv.lock, src, examples and scripts. Its wheel built successfully (`source-build.log`) and installed into a fresh dependency-free `/tmp/cartpole-source-test-venv`.
- Installed SDK numeric actor import passed without optional dependencies; command help passed without optional dependencies.
- Executable wrapper help ran from `/tmp`, resolving the repository correctly.
- `git diff --check` passed.

Independent review by the simulation agent reported no remaining blocker for the declared development-only offline scope. Its termination-semantic finding was reproduced before fixing. Concurrent intermediate runs observed source-hash rejections while other agents edited the simulator; the retained smoke and test log were regenerated after source stabilization. No final result relies on those intermediate runs.

Remaining limits: all current scopes are exploratory simulation; no calibrated dynamics randomization or global task-qualification schema is added; actuator tracking, global sensor calibration, real scheduling and physical acceptance remain separate. The standard SB3 checkpoint is a trusted offline serialized training file. The numeric SDK actor is an inference artifact, not a portal/hardware approval. No physical candidate was trained on rejected data.
