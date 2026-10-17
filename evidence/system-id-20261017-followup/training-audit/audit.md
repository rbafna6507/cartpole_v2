# RL/training audit — 2026-10-17

Audited repository: `/Users/rbafna/projects/cartpole_v2`, branch `codex/live-rig-platform`, commit `f849312`. This was read-only source work: no hardware access, SSH, package installation, training run, production edit, or acceptance-gate override. Only the existing offline verification tests were run. Official Gymnasium/SB3 documentation was consulted to check the proposed neural-library interface.

## What exists

| Area | Implemented status | Evidence |
| --- | --- | --- |
| Dynamics | MuJoCo two-DOF uniform-rod surrogate, acceleration servo with force cap | `src/cartpole_sdk/sim/model.py`, `sim/backend.py` |
| Gym API | `CartpoleEnv` wraps the direct-acceleration backend; continuous scalar action; sensor state/mask/age dict; standard reset/step | `sim/gym_env.py:20` |
| Executor simulation | Separate wrapper applies the existing binary32 governor once per 1 ms physics tick; raw acceleration request, leases, rail/speed termination | `sim/executor.py:29` |
| Training | Cross-entropy episodic policy search over ten positive gains, initialized from a handwritten energy-shaping/linear controller | `learning/search.py:45` |
| Evaluation | Deterministic seeded starts, fixed reward, disjoint saved training/evaluation seeds, per-episode results, baseline comparison | `learning/rollout.py:87`, `examples/evaluate_policy.py` |
| Policy artifacts | Bounded numeric JSON; fixed policy family; hardware acceptance forced false; no executable weights | `learning/artifact.py:20` |
| SDK inference/export | Explicit source/frame channels; reset/act contract; single-source portal export with inference code hashes | `learning/artifact.py:66`, `learning/export.py:38` |
| Identified model | Fit/report export with scope, assumptions, source/fit hashes, content digest; loader checks digest then returns SimulationConfig | `identification/workflow.py:273`, `:303` |
| Neural RL | No PPO/SAC training, neural inference adapter, checkpoint exporter, or declared RL dependencies | `pyproject.toml`, `learning/` |
| Domain randomization | No dynamics ensemble or per-episode dynamics sampling | `learning/search.py`, `learning/rollout.py`, `sim/config.py` |

MuJoCo and Gymnasium are complementary: MuJoCo computes the dynamics; Gymnasium supplies the environment interface used by an RL algorithm. This repository already uses both. Neither trains a policy by itself. `CartpoleEnv` is a custom physical surrogate, not the standard benchmark `CartPole-v1`.

The recorded phase-five CEM experiment optimized controller gains, not a neural network or the plant dynamics. It used three training seeds times hanging/upright starts, five generations and population ten, for 276 total 10-second training episodes. The saved held-out report records reward 3.449923410 to 3.704015435; both baseline and learned policy succeeded in 12/12 episodes. Some cart excursions increased. These are previously recorded results, not freshly rerun performance claims. Source: `evidence/phase5/report.md` and the associated JSON artifacts.

## Material integration gaps

1. `examples/train_policy.py` always builds provisional `SimulationConfig`; it has no identified-model input. `train(config=...)` can accept a config in Python, but the provenance always says provisional and contains no identified export digest, acceptance scope, source fit, or qualification. `load_model()` discards that metadata after validation.
2. CEM `train()` always builds `HostPolicyParameters()` from the historical preset. Effective length is fixed at 0.124 m and is not searched. Loading a different plant alone would leave the controller prior at that historical value. The baseline must be explicit and its relationship to the model length recorded; changing it silently would make comparisons ambiguous.
3. `ExecutorSimulation` supports explicit `ControllerParameters`, but the learning rollout does not expose or save them. Therefore it uses default governor settings rather than a pinned recorded executor configuration. Rail, acceleration, jerk and velocity settings belong in the experiment manifest independently of learned gains.
4. The existing Gym environment wraps plain `MujocoBackend`. Its action is directly interpreted as executed acceleration; it does not reproduce the CEM raw-demand governor, hard margin, or fault-on-lease-expiry semantics. Feeding this environment to PPO would train a different control problem from SDK deployment.
5. Gym reward differs from the CEM reward and success definition. Shared policy comparisons require one declared objective, horizon, starts and evaluator. A good reward score must be reported separately from balance success, rail approach, force saturation and fault rate.
6. `CartpoleEnv.reset()` defaults to exactly hanging, not the seeded state-family distribution in CEM. Gym seeding currently seeds sensors; general training reset/randomization needs explicit implementation.
7. Sensor sample rate, Gaussian noise, delay and dropout are available, but all retained phase-five performance runs used noiseless, zero-delay channels. Delayed startup creates unknown channels, and existing host-policy training fails closed. A model-bound experiment must declare startup handling; it cannot silently use truth or change missing-sensor behavior.
8. The new host execution path also has `ExecutorFeedbackPolicy`, using explicit x/v/angle/rate/commanded-acceleration/brake-direction channels. That policy is not what the current CEM optimizer learns. `ExecutorSimulation.control_observation()` supplies the extra executor feedback and is the natural input source for a governed neural adapter.
9. A full fit report should remain in an immutable sidecar, with compact digests/scope/assumptions in policy provenance. Embedding a large report into every policy risks the existing 256 KB numeric-artifact and 64 KiB portal-source limits. Export/inference must remain explicit about supported artifact family and runtime; the current exporter cannot export a PPO network.

## Evidence and model adequacy

The physical October-17 passive-repeatability and driven-pulse reports remain rejected. The favorable secondary driven forecast does not remove its training residual and angle/input-bias failures. It estimated input gain about 1.409; current export cannot represent non-unit gain. The old passive candidate is a scoped diagnostic, not an accepted global swing-up model. Do not train a transfer candidate by renaming or manually editing these artifacts.

Current export requires accepted fit evidence and explicit full assumptions. It rejects nonzero Coulomb friction, non-unit driven input gain and nonzero driven delay because the simulator does not represent them. It only maps effective length and viscous damping. Every export retains `recommended_for_hardware_rl=false`.

`passive-down` only supports its local passive claim. Even `driven` is a conditional fit label, not proof of upright/full-swing accuracy, actuator authority or transfer. The current schema has no automatic predicate for "adequate for the whole swing-up task". A new training workflow must not infer that predicate from `accepted_fit=true` alone. Record the intended training task and tested state/input envelope, and keep extrapolation explicit. Accepted simulation training input and hardware policy acceptance are separate decisions.

The fitters report conditional OLS coefficient/length standard errors and a training loss delay profile. They do not provide a calibrated posterior or global uncertainty distribution. The documented exclusions include calibration, serial noise correlation, clock/model bias and errors in variables. No existing trainer propagates those uncertainties. Randomized initial states are not dynamics domain randomization.

For future randomization, preserve two categories: supported uncertainty from repeated independent measurements, and deliberate robustness scenarios with stated bounds. Sample coherent model variants (for example L_eff and gamma together, then recompute hinge damping as gamma * 0.75 * mass * L_eff^2). Keep training, tuning and final evaluation seeds/model variants disjoint. Do not relabel narrow conditional regression error bars as complete plant uncertainty. Do not randomize unsupported gain/delay/friction until the simulator implements and tests those mechanisms.

## Recommended order

1. Finish fresh collection, source admission, held-out validation and a scoped model export using unchanged gates. If a needed fitted term cannot be exported, implement and validate that term before using the model for training; never drop it.
2. Add model-bound experiment admission and manifests. Require a model path; verify the content pin and scope; retain raw-file and canonical hashes, fit-report hash, assumptions, limitations and tested domain. Freeze explicit sensor config, executor parameter snapshot, controller prior, task, objective, seed splits, software versions/source hashes and training budget. Reject malformed/rejected/unsupported models before constructing an optimizer. The physical state of acceptance remains false.
3. Run the existing CEM baseline against that exact experiment as a control, once the requested task has adequate model coverage. Expose prior and executor parameters explicitly. Freeze output, then evaluate once on disjoint final seeds/scenarios; do not select weights or bounds from the final test results.
4. Add a separate governed Gym environment around `ExecutorSimulation`. Use a shared observation encoder with the eventual SDK policy: x, v, sin(theta), cos(theta), omega plus available commanded acceleration/brake direction; retain validity/age information and explicit source/frame checking. Do not give the actor `info['ground_truth']`. Normalize the action to [-1,1] with one documented scaling to raw acceleration; the executor applies its governor exactly once. Use a fixed 100 Hz initial experiment unless measured evidence justifies another cadence.
5. Add one optional neural trainer, initially PPO with a small feedforward network and CPU. PPO supports continuous Box actions and Dict observations; `MultiInputPolicy` fits a dict observation. A shared wrapper/evaluator matters more than choosing PPO versus SAC first. Use a wall-time/step budget and benchmark throughput before a long run. Add SAC later only as a controlled comparison, not as a parallel first implementation. The library's standard saved checkpoint is an offline training artifact; the SDK/portal deployment exporter needs a separate explicit safe numeric representation and parity test.
6. Validate deterministic frozen inference and SDK source/cadence behavior, then do recorded-data shadow evaluation. Physical commissioning, delay/estimator validation, bounded trials and an independent physical acceptance report remain subsequent rig-owner work. Simulation improvement does not enable hardware automatically.

PPO/custom-environment interface checked against official documentation: [PPO](https://stable-baselines3.readthedocs.io/en/master/modules/ppo.html), [custom environments](https://stable-baselines3.readthedocs.io/en/master/guide/custom_env.html), [Gymnasium Env](https://gymnasium.farama.org/api/env/). Resolve and pin a compatible released dependency set when implementation is authorized; the inspected master docs identify themselves as development documentation.

## Smallest independent implementation chunk

I can implement the model-bound CEM experiment path without touching identification fitting, hardware or firmware:

- a metadata-preserving model-input reader/validator;
- a separate required-`--model` training CLI, so the old provisional example cannot silently become an identified run;
- explicit controller-prior, executor and sensor inputs threaded through train/evaluate/rollout;
- a compact immutable experiment manifest and policy provenance binding;
- evaluation that uses the frozen experiment and rejects training/test overlap;
- regression tests for model tamper/rejection/scope, unsupported settings, prior/executor propagation, deterministic tiny simulated training, and artifact/export size/compatibility.

Before implementation, root should choose the task/coverage admission rule. This is necessary because the present accepted-scope vocabulary does not encode global swing-up adequacy. A scaffolding smoke run can use clearly marked synthetic accepted model fixtures; it must not be presented as training on accepted physical evidence. No production training should start from the currently rejected recordings.

The next independently implementable chunk would be governed Gym + shared SDK encoder/decoder tests. Neural dependency installation, PPO training and new neural artifact/export support are separate work.

## Fresh verification

Command: `.venv/bin/python -m pytest tests/test_learning.py tests/test_gym_env.py tests/test_learning_export.py tests/test_system_id_workflow.py -q -p no:cacheprovider`

Result: **45 passed in 7.24 s**. This verifies the existing software subset, not plant accuracy or physical policy acceptance.

Installed local packages observed: NumPy 2.4.6, MuJoCo 3.15.0, Gymnasium 1.4.0; Torch and Stable Baselines3 were not installed. No packages were installed by this audit.
