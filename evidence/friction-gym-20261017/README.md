# Frozen passive friction in the training Gym

The batch-6 smooth-friction candidate is now implemented in the production MuJoCo backend used by both Gym environments. The installed profile is `training/profiles/passive-20261017`. This is an explicitly **DEVELOPMENT_ONLY** model; the original fit acceptance and measurement limitations remain intact. No controller tuning, firmware, serial port, or powered hardware operation was performed for this integration.

## What is implemented

The backend applies `-I*c*tanh(omega/0.05)` at every 1 ms physics tick, alongside viscous damping, and includes the applied hinge torque in the cart-force calculation. Here `I=0.75*m*L_eff^2`, `L_eff=0.16030387335574306 m`, `gamma=0.006891975341585199 /s`, and `c=1.6268943123178277 rad/s^2`. Defaults retain the old zero-dry-friction behavior. Complete legacy model configurations remain readable; incomplete new configurations are rejected. Loading MJCF alone does not include the backend-applied torque.

`./scripts/prepare-training-model` builds a source-bound profile from the frozen coefficients, complete executor readback, observation configuration and explicit assumptions. It refuses output overwrite. It does not refit data or turn the old sign/static-friction report into an accepted smooth-friction export. The profile contains the exact freeze bytes and file hashes, plus the recorded controller prior independently of the fitted plant length.

See [training instructions](../../docs/rl-training.md) for the ready-to-run local command and headless Colab CLI workflow. The prior and executor use the inspected working settings, including jerk 150 m/s^3, observer bandwidth 6, and rail half-span 0.308962494 m. Masses, force authority, cart damping, delay and noise remain declared assumptions.

## Recorded-data checks

[Production passive replay](production-replay/README.md) uses all 11 batch-7 releases with fixed coefficients. It initializes once from the first 0.5 s of each release and scores the rest without measurement correction:

| Comparison | RMS angle error | P95 absolute error |
| --- | ---: | ---: |
| Production MuJoCo versus encoder | 2.662406 degrees | 5.102229 degrees |
| Frozen ODE versus encoder | 2.629404 degrees | 5.023758 degrees |
| Production MuJoCo versus frozen ODE | 0.087711 degrees | 0.205203 degrees |

Original pose and camera failures are retained. [Batch-8 validation](../passive-batches8-9-20261017/README.md) separately evaluates both newly collected files as validation against the unchanged batch-6 model. Batch 9 remains reserved until the batch-8 decision is made.

[Cart dynamics audit](cart-dynamics/README.md) replays six completed signed 10/20/30 mm pulses. The fixed model gives 0.880 degrees short-forecast RMS on the original four small pulses and 1.132 degrees on the previously inspected 30 mm pair. Reconstructing input from recorded governor-velocity endpoints gives 0.018-0.125 mm RMS against step-derived position, with 0.187-0.316 pixel optical RMS. This resolves the drift caused by integrating sparse acceleration snapshots. It does not independently identify physical distance scale, motor latency, force limits, slip or the assumed masses. The original weak-form training gate still fails: NRMSE 0.26796 versus the 0.15 limit. Predicted low-amplitude ringing decays faster than observed.

## Software verification

- `uv run --locked --extra rl --extra sim --extra id --extra plots pytest -q`: **1335 passed, 7 skipped, 456 subtests passed**, preserved in [full-suite-final.txt](verification/full-suite-final.txt).
- Independent integration review: no actionable findings; 23 focused tests and 66 subtests passed independently, and the installed-profile PPO environment reset and stepped successfully.
- A real 64-step PPO smoke learned, saved checkpoints at steps 32/64, and reloaded for evaluation. [The preserved checkpoint and manifest](verification/ppo-smoke/preservation.json) bind the exact inputs. Four evaluated episodes had zero successes; this tiny run checks software only and is not a trained policy.
- Historical replay tests load the already preserved historical simulator snapshot whose hashes their evaluator pins. Those historical sources and evidence are unchanged; new tests and production replay exercise the updated backend.

The earlier full-suite log is retained with its two historical-source-pin failures, followed by the corrected historical-fixture run. Both logs are evidence rather than claims about the physical model.

## Next qualification work

The current profile can start exploratory simulation training. Before treating it as a reliable hardware-transfer model, resolve camera/pose measurement disagreements, characterize driven response beyond small hanging pulses, independently measure the cart's optical scale/timing, and test robustness to uncertain force, mass, delay and observation parameters. No accepted global swing-up/balance or hardware qualification is claimed.
