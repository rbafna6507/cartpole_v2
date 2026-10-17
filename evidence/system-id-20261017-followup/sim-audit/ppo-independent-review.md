# Independent offline PPO interface review

Reviewed 2026-10-17 against the sources pinned below. No hardware, serial, SSH,
network access, model promotion, or physical-policy execution was performed.
This review concerns software behavior under the declared ideal acceleration
servo plant; it does not establish physical model adequacy or useful control.

## Result

No remaining concrete blocker was found for explicitly labelled
`DEVELOPMENT_ONLY` offline training. Existing physical evidence remains subject
to identification admission; this review does not change an evidence status.

The review traced the following boundaries:

- Gym actor features use the shared six-channel SDK encoding (angle expanded
  to sine/cosine), explicit source choice, validity and timestamp semantics.
  Ground truth is confined to reward/diagnostics, never actor observations.
- PPO's normalized scalar maps once to the exact raw acceleration ceiling;
  the executor applies its governor once. An independent `0.3 m/s²` endpoint
  check yielded exactly `0.3`, with no SDK bounds exception.
- A healthy delayed initial snapshot is obtained through actual causal warmup.
  Subsequent missing telemetry terminates the policy episode explicitly,
  rather than causing an unexpected Gym exception or supplying truth.
- Finite-horizon reward is terminal, so SB3 does not bootstrap an additional
  continuing value after the terminal balance-time payoff.
- Model admission preserves development scope, complete configurations and
  accepted-fit requirements. Rejected raw reports are not model inputs.
- Resume validates experiment identity, source/dependency provenance and file
  hashes before loading a trusted SB3 archive. Identical input relocation
  preserves identity. Resume does not claim bitwise uninterrupted episodes.
- Frozen evaluation rejects training-seed overlap and performs deterministic
  inference without optimizer updates.
- The portable actor is bounded numeric data with a fixed architecture and
  explicit SDK channels, freshness/cadence/replay checks and source hashes.
  Its import does not load neural or simulator dependencies.
- CLI and notebook commands agree. The source archive includes README.md,
  scripts and package sources. Inspection extraction uses `result.parameters`.
  All seven notebook Python cells parse; actual Colab execution was not tested.

## Findings corrected during review

1. Returning a time-limit truncation after finite-horizon payoff allowed SB3
   `DummyVecEnv` to bootstrap. The wrapper now returns terminal completion;
   a regression exercises SB3's actual `TimeLimit.truncated` flag.
2. A float32 physical-action Box rounded a 0.3 ceiling outward. The governed
   core Box now preserves float64 SDK bounds, and PPO derives its scale from
   the exact explicit configuration/executor limits.
3. CEM provenance omitted the shared observation codec. Its source is now
   included. Startup text now describes the causal warmup actually performed.

## Verification

Final independent command:

```text
PYTHONDONTWRITEBYTECODE=1 /private/tmp/cartpole-rl-venv/bin/python -m pytest -q -p no:cacheprovider tests/test_rig_gym_env.py tests/test_ppo_training.py tests/test_model_training.py
25 passed in 5.24s
```

The PPO suite performs real bounded learning, save/reload, resume, held-out
evaluation and numeric SDK actor parity. Additional independent checks observed
normalized +1 -> exactly 0.3 m/s², relocated input identity equality and full
post-preflight dropout -> `terminated=True`, `truncated=False`, explicit fault.

This is an execution and interface check, not evidence of successful balancing.
The physical tracking/observer-delay limitations in `audit.md` remain applicable.

## Reviewed source SHA-256

```text
c5ed8c2e9f8bd99d5cc423754e0ededfdf1a59095615e29e2c44fa7574a3b47e  src/cartpole_sdk/sim/rig_gym_env.py
41ce5c64dcd47d9daf5bcb65c053f0ce6efde186a1f649904d0daeb3c3af38e2  src/cartpole_sdk/policies/rig_observation.py
3fcfd81e9539a7b32da3afc9ba235d9c04d7a00880394376e898e9ac0a806c04  src/cartpole_sdk/learning/model_experiment.py
82a818031084794dcf85d98bcb79fd8d3350521ae8ca63585cb4b35bd22ed9fd  src/cartpole_sdk/learning/model_search.py
cdd6c8e35a0936de1bebc4876e9b4014af559cd81e998395836caab61d36e387  src/cartpole_sdk/learning/ppo.py
acc03290e1b09fd7c42689f22fa1cfa8209ba1992284bc2c469bf0c3f89b1190  src/cartpole_sdk/policies/neural.py
30f72a35aace477732306fc638c423970d04036b25c2de729d651b43bb24be2e  examples/train_ppo.py
667951ae2c50f84c26ee9d2f16350be70bdeb930e407e79bf5906fc78e49cded  scripts/train-ppo
af13964f4750ac475da558e27153ea688c659d207eed7f6bdb423a61db917a88  docs/rl-training.md
79804add828020c69190b2f312aef6db6f8943b482eb61b12d2d35ae8f91bbe3  notebooks/train_ppo_colab.ipynb
```
