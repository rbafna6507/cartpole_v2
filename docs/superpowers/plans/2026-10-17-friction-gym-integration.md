# Friction law, later batches and training Gym implementation plan

> **For agentic workers:** Use superpowers:executing-plans and test-driven-development. Independent recorded-data analysis and physics implementation may run in parallel under dispatching-parallel-agents.

**Goal:** Compare both completed batch-8 and both batch-9 recordings as validation without refitting, implement the verified smooth dry-friction law in the production MuJoCo/Gym path, and supply a runnable development training profile with recorded-data validation.

**Architecture:** Preserve the frozen batch-6 candidate and original acceptance reports. Add explicitly configured hinge torque at each physics tick and include it in cart-force compensation. Both Gym environments inherit the backend behavior. A source-bound development profile carries the fitted passive parameters plus explicit cart, actuator and observation assumptions; it cannot grant hardware approval.

**Spec:** User's approved request on 2026-10-17: compare training/validation batches 8/9, integrate the verified friction law, check cart dynamics and install it in the training Gym. Prior scope and physics are documented in evidence/system-id-model-review-20261017/README.md.

## Global constraints

- Work in the existing cartpole_v2 checkout on codex/live-rig-platform; preserve archived baselines and historical evidence.
- User is collecting data: no hardware command, serial port open, service restart or flash.
- Freeze coefficients before evaluating any batch-8/9 recording; no refit or favorable residual-based interval selection. The user explicitly requested both labels in both batches be evaluated as validation first. If any of them is later used for refinement, relabel it development first and reserve new independent validation.
- 1 ms physics, 100 Hz RigCartpoleEnv decisions, existing governor, telemetry and action contracts retained.
- Smooth torque is -hinge_coulomb_friction_nm*tanh(omega/hinge_friction_velocity_scale_rad_s), scale 0.05 rad/s. Defaults are zero torque and 0.05 rad/s; existing configurations retain zero-friction behavior.
- Old accepted viscous exports remain readable. Existing sign/stiction fitter reports are not silently reinterpreted as the smooth law.
- Latest candidate remains DEVELOPMENT_ONLY while measurement and driven-model qualifications remain unresolved. Training profile is usable through existing explicit development-only training path.

## Review focus

- Torque must be included in the inverse cart force calculation, including signed and zero angular velocity.
- Reset/substep behavior must not retain or double-apply torque; zero torque preserves prior behavior.
- Old explicit SimulationConfig payloads omit new fields; they must load as zero-friction legacy payloads, but partially missing new fields and unrelated omissions fail.
- Passive-fit parameters identify ratios; profile must preserve assumed mass/force/cart dynamics and local calibration limitations.
- Active/incomplete or mislabeled collections must not be treated as successful or independent validation by filename alone.

### Task 1: Frozen later-recording review

Files: new evidence/passive-batches8-9-20261017; reuse frozen analysis tools without changing them.

- [x] Discover completed sources and hash them; wait for successful completion before copying active files.
- [x] Inspect raw encoder/camera curves and freeze release intervals before errors are read.
- [x] Score all suitable releases against candidate-freeze-latest6.json; preserve camera, pose, coverage and failed-collection flags.
- [x] Preserve plots, source identities and exact commands. If data has not arrived, report the missing subset explicitly.

### Task 2: Configurable friction in production physics

Files: src/cartpole_sdk/sim/config.py, backend.py; tests/test_simulation_friction.py.

Interface: SimulationConfig gains hinge_coulomb_friction_nm: float=0.0, hinge_friction_velocity_scale_rad_s: float=0.05. Torque is applied only by backend at each physics tick. No XML-only claim of dry-friction completeness.

- [x] Write failing tests for analytic fixed-cart acceleration, signed torque/energy loss, cart acceleration tracking with nonzero torque, multiple substeps/reset and invalid configs.
- [x] Implement minimal torque and inverse-force compensation; preserve default physics.
- [x] Run focused simulation/executor/Gym tests and report results.

### Task 3: Explicit training profile and compatibility

Files: learning/model_experiment.py; new learning/passive_profile.py, examples/prepare_passive_training.py, scripts/prepare-training-model; tests/test_passive_training_profile.py; training/profiles/passive-20261017; docs/rl-training.md.

Interface: build_passive_training_bundle(freeze_path, output, *, executor_parameters, observation_config, assumptions) writes immutable model.json, executor-parameters.json, observation-config.json, prior-parameters.json and provenance.json. Model uses existing development schema, explicit config and limitations. Physics values derive from frozen coefficients and equivalent-rod inertia. Do not mark rejected report accepted.

- [x] Test invalid/tampered/nonphysical freeze, incomplete assumptions, output overwrite, immutable provenance and exact damping/torque conversion.
- [x] Preserve loading of complete legacy configs by explicitly adding the two neutral friction defaults only when both fields are absent. Keep other config validation strict.
- [x] Generate profile from latest candidate, working controller snapshot and documented assumptions; validate via existing model-bound experiment builder and RigCartpoleEnv.
- [x] Run short real PPO learn/save/reload smoke using this profile; document headless Colab CLI inputs without launching paid training.

### Task 4: Cart dynamics and production-path validation

Files: new evidence/friction-gym-20261017 tools/reports; existing driven evidence read-only.

- [x] Audit existing cart pulse/vision/encoder data, distinguish commanded steps from physical motion and report supported/unsupported dynamics.
- [x] Replay frozen passive traces through actual MujocoBackend and check parity against recorded encoder and standalone ODE.
- [x] Replay recorded cart inputs where supported; do not refit on held-out data or claim physical force identification from commanded quantities.
- [x] Run full test suite, inspect plots and independent review; fix material findings.
- [x] Commit completed work without pushing.

## Execution record

Production integration, installed profile and recorded cart/passive replays are complete. A real 64-step PPO learn/save/reload smoke completed. Full suite: 1335 passed, 7 skipped, 456 subtests passed. Independent reviewer found no actionable defect and separately verified 23 tests / 66 subtests, the bundle hashes, legacy compatibility and actual PPO environment propagation. Historical evaluator tests now use the already preserved historical simulator snapshot; old evidence and hash pins remain unchanged. Both batch-8 recordings were scored without refitting. The user then requested the same frozen-model comparison for both batch-9 recordings, which also completed. All four recordings remain validation-only: all 47 releases pass short-forecast numeric/coverage checks, pooled continuous RMS is 3.31244 degrees, and all camera/pose failures remain included. Retain the current coefficients for development training. No refit has occurred.
