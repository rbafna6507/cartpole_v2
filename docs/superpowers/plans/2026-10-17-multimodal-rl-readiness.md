# Multimodal RL readiness implementation plan

> **For agentic workers:** Use executing-plans / dispatching-parallel-agents for the scoped tasks below; use test-driven development for behavior changes.

**Goal:** Provide a reproducible Colab CLI training recipe and SDK deployment path for encoder, tracked-vision and fused-angle policies, backed by useful characterization and honest model qualification.

**Architecture:** Keep the trusted Teensy governor at 1 kHz and policy decisions at 100 Hz with 20 ms anchored action leases. Make observation modality an explicit training/inference contract. Share timestamp-aware sensing/fusion between hardware and simulation. Preserve a numeric stdlib SDK actor independently of the SB3 training checkpoint. Refine the passive model only on development/training sources and keep validation-labelled recordings excluded from fitting.

**Tech stack:** Python SDK, MuJoCo, Gymnasium, SB3 PPO, existing vision service, official pinned Google Colab CLI.

**Spec / authorization:** User explicitly requests autonomous data collection and implementation, permits use of training batches for refinement, will launch cloud training personally, and requires vision/fused support. Continue the existing cartpole_v2 checkout. User autonomy supplies implementation authorization; no additional planning approval is required. Vision means tracked angle/rate estimates, not pixels. Fused means fused angle with explicitly aligned magnetic rate unless a separately tested fused rate is introduced.

## Constraints and review focus

- Preserve archived sources, existing firmware/gains and previous evidence; no flashing or resetting the motor board.
- Only the root agent may connect to hardware. Confirm exclusive serial use, camera visibility, stopped/healthy/homed state and quiet pole before bounded pulses; review each run before escalation. Every motion path must STOP on failure.
- No cloud runtime allocation/training on the user's account; prepare and locally test the commands for the user to launch.
- Do not claim policy quality from software smoke tests, or identify physical force/scale from step counts.
- Training8/9 may become development. Validation8/9 remain regression holdouts, already inspected historically; they are not new blind tests.
- Invalid, stale, replayed, wrong-frame, clock-incompatible and missing camera observations must fail explicitly; never substitute perfect state or magnetic data into a vision-only channel.
- Preserve 20 ms cart/magnetic freshness and command leases. Camera freshness has a separately declared bound; changing it must not extend action authority.
- Old complete encoder configurations remain compatible where semantics are identical. New modality/calibration/configuration mismatches reject before arming.
- Reproducible artifact hashes must bind source, model, executor, observation assumptions, modality, randomization and training settings; CPU/GPU/cloud runtime expectations must be stated accurately.

## Task 1: Passive refinement (agent passive_refinement)

Own new evidence/passive-refinement-20261017 and ignored analysis outputs only.
- [x] Freeze training-only method/selection criteria and source roles.
- [x] Fit modest constant smooth-friction candidates on batch6 + training8/9, preserve all annotations and quality flags.
- [x] Freeze candidate before validation8/9 regression evaluation; compare all per-release/pooled scores and both initializations.
- [x] Preserve runnable scripts/plots and either recommend a defensible new profile or retain baseline.

## Task 2: Shared multimodal observation contract (agent vision_policy_contract)

Own sensing/policy_observation.py, policies/rig_observation.py, sim/rig_gym_env.py, policies/neural.py, rig/policy.py, learning/model_experiment.py and focused tests. Coordinate actor export/selector APIs with PPO owner.
- [x] Write failing tests for explicit vision/fused channels, per-source freshness, frame/clock/session mismatch and no fallback.
- [x] Implement causal assembler and sim camera captures with actual tracker derivative/history, delivery latency, quantization/noise/dropout; common AngleFusion.
- [x] Add actor contract/executor bindings and runner validation hooks, preserve stdlib inference and compatible encoder behavior.
- [x] Test causal no-future behavior, warmup, stale/missing frames, wrong modality, fusion fallback semantics, real Gym and inference equivalence.

## Task 3: Training readiness (agent rl_readiness_audit)

Own learning/ppo.py, examples/train_ppo.py, optional learning/training_recipe.py and training tests.
- [x] Test configurable long-horizon discount, wider seed coverage, explicit bounded seeded randomization and resume integrity.
- [x] Implement training recipe with well-defined units, unchanged governor and feasible lease timing; integrate shared multimodal selector and actor export contract.
- [x] Report hanging/upright results separately with sustained balance metrics and preserve old objective semantics when requested.
- [x] Benchmark and learn/save/reload/evaluate all modes; distinguish execution from learned competence.

## Task 4: Cart characterization and observation assumptions (root)

Reuse scripts/system-id and current working staging; new evidence/rl-readiness-20261017.
- [x] Inspect current rig/vision and existing pulse evidence before commanding motion.
- [x] If useful, run signed bounded pulses at different durations and repeats, reviewing each STOP, displacement, camera, clipping and telemetry condition.
- [x] Analyze command/count/optical response and camera timing/quality; retain uncertainty of absolute scale, latency and force.
- [x] Select model and generate new explicit encoder/vision/fused training profiles without overwriting the previous frozen profile.

## Task 5: Colab workflow and hardware actor runner (root)

Create learning/colab_bundle.py, examples/prepare_colab_training.py, scripts/prepare-colab-training, scripts/colab-training; new neural runner module/example/wrapper, tests and docs/rl-training.md updates.
- [x] Write failing tests for flat input ZIP contract, immutable output, source allowlist, valid rollout step multiples, modality selection and generated launch arguments.
- [x] Implement local bundle/launch artifacts using the pinned official Colab CLI and locked environment; no credentials or unrelated runs included. Validate executable syntax and fake CLI sequencing locally.
- [x] Write failing runner tests for live settings mismatch, non-execute shadow behavior, stop-on-error and per-source observation use.
- [x] Implement shadow-default bounded execution through run_policy, exact live executor comparison, explicit development execution and no second governor; record timing/output, preserve actor unapproved status.
- [x] Run local training pilot and stopped hardware shadow checks as meaningful; document exact train/evaluate/download/deploy commands and remaining qualification.

## Task 6: Integration and completion (root)

- [x] Run focused tests and full suite after code stabilization; inspect plots and source/manifest bindings.
- [x] Independent review of final source changes; address important issues with regression tests.
- [x] Commit completed source/evidence/profiles without pushing; deliver runnable Colab commands and honest readiness assessment.

## Execution notes

Baseline3011129 is clean; prior full suite1335 passed /7skipped /456subtests. Retaining the existing user-designated checkout rather than creating another worktree. Current audit identified invalid100000-step example (n_steps1024), only3 repeated seed pairs, gamma.99 at100Hz, absent multimodal training contract, and absent concrete neural shadow/hardware CLI. These are being addressed under the user's autonomous implementation request.


## Final outcomes

- Retained the frozen passive model: the training-only refit improved regression
  RMS by 3.77%, below the declared 5% promotion threshold, and worsened P95.
- Five bounded, camera-recorded cart pulses completed with unchanged settings,
  confirmed STOP and no clipped commands or logger drops. Fixed-model replay
  pooled angle RMS was 1.250 degrees; full-speed transfer remains unqualified.
- Encoder, tracked-vision and fused profiles share causal observation processing
  across simulation and SDK inference. Live camera calibration remains required.
- Actual PPO pilots learned better scores but achieved zero sustained holds.
  The 2,097,152-step recipe is a development experiment, not proven convergence.
- Final suite: 1,403 passed, 7 skipped, 456 subtests passed. Final stopped Jetson
  shadow: 201 inferences, no ARM/actions, disabled throughout, clean termination.
- Exact final Colab bundles, pilot snapshots and physical evidence are preserved.
  Cloud allocation is left to the user; no push is included in this work.
