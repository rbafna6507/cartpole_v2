# Cartpole v2 — source and evidence reference

Companion to [SYSTEM_README.md](SYSTEM_README.md). This index describes the source snapshot audited on October 23, 2026. Function names below identify navigation points, not additional console commands. Historical experiment records retain their original status and dates.

## src/cartpole_sdk

### [src/cartpole_sdk/__init__.py](src/cartpole_sdk/__init__.py)

Local cartpole policy SDK. Imports never connect to hardware.

### [src/cartpole_sdk/adapters.py](src/cartpole_sdk/adapters.py)

Offline legacy adapters; no device access, clock alignment, or sensor fallback.

Callers must namespace frame_id by source (e.g. firmware:raw versus
vision:calibration-1). A vision input must represent one calibration epoch; the
states file cannot prove this because calibration events are stored separately.
Supplying frame_id asserts the caller has checked that requirement. A detectable
calibrated-to-uncalibrated transition is rejected; recalibration while the flag
stays true is undetectable here and still requires caller verification. Host-read
proxy effective times are not camera acquisition times or measured delay fixes.
cart_extrapolated means spatial projection beyond calibrated rail endpoints; it
is preserved as an estimated method, never as future temporal prediction.

Public definitions: `import_console`, `import_vision`.

### [src/cartpole_sdk/cli.py](src/cartpole_sdk/cli.py)

Local recording, replay and simulation commands; no command connects to the rig.

Public definitions: `inspect_recording`, `main`.

### [src/cartpole_sdk/contracts.py](src/cartpole_sdk/contracts.py)

Source-explicit SI contracts shared by replay and future rig/simulation backends.

Timestamps belong to Session.clock_id. Validation is a software integration guard,
not a physical safety authority. Importing this module has no device side effects.

Public definitions: `ValidationError`, `SelectionError`, `Topology`, `Session`, `Channel`, `Sample`, `Observation`, `validate_observation`, `select_channels`, `Acceleration`, `ActionRequest`, `ActionLimits`, `validate_action`, `Policy`.

### [src/cartpole_sdk/control/__init__.py](src/cartpole_sdk/control/__init__.py)

Dependency-free offline reference control at the archived 1 ms step.

### [src/cartpole_sdk/control/forecast.py](src/cartpole_sdk/control/forecast.py)

Fast, stateless capture feasibility screen for the SDK control loop.

This follows ``swing_control::canCapture`` and ``cart_motion::advance`` over
36 fixed 5 ms steps, using ordinary Python float64 arithmetic. The live motion
governor remains the binary32 implementation in :mod:`.motion`; this forecast
must never supply actuator state. It has no compilation or third-party runtime
dependencies.

This is not native bit parity or a guarantee of physical capture. Float32
rounding and libm differences can change the tick on which a discontinuous
settled-velocity guard switches. Small guard margins below reject numerically
ambiguous decisions, but do not constitute a formal error bound for all gains
and parameters. Conservative rejections are more common with tight speed caps.
Validate the intended controller envelope against native and
physical behavior before relying on this as a capture policy.

Public definitions: `can_capture_fast`.

### [src/cartpole_sdk/control/motion.py](src/cartpole_sdk/control/motion.py)

Port of archived cart_motion.h, using SI units and binary32 arithmetic.

The settled-velocity guard switches abruptly to zero demand. Pure float64
trajectory drift crosses that guard on a different tick from native float32;
scalar operations therefore round explicitly. sqrt uses Python libm then rounds
to binary32. Native parity still uses tolerances rather than bitwise claims.

Public definitions: `sqrt`, `clamp`, `slew`, `velocity_accel`, `settled_velocity_accel`, `stopping_distance`, `State`, `advance`.

### [src/cartpole_sdk/control/parameters.py](src/cartpole_sdk/control/parameters.py)

Saved candidate controller settings, independent of rig calibration.

Public definitions: `ControllerParameters`, `validate_coupled`, `Gains`, `load_tuned_parameters`, `gains`.

### [src/cartpole_sdk/control/policy.py](src/cartpole_sdk/control/policy.py)

Strict SDK adapter for the archived single-pole, 1 kHz reference controller.

Only angle and cart position feed the reference: it retains the firmware's own
angle observer and commanded cart velocity. Do not pass its governed output
through a second governor when implementing a future hardware executor.

Public definitions: `ReferencePolicy`.

### [src/cartpole_sdk/control/reference.py](src/cartpole_sdk/control/reference.py)

Offline reference of the archived 1 kHz controlTick.

Rate estimation, gains and feedback use Python float64. Decoded/wrapped angles
round binary32 transcendental operands/results to preserve upright start guards.
Motion scalar operations round to binary32 because settled-velocity guards
amplify float64 drift. Floating elapsed-time counters retain binary32
accumulation so dwell guards occur on the same tick.
Micros/millis arithmetic wraps at uint32, while the public clock is unwrapped.
wrap uses atan2(sin,cos); +/-pi representations are equivalent, not bit exact.
Hard-rail guards round parameter/input operands to binary32 as in the firmware.
No pulse generation, calibration, Z-axis, I2C, or foreground scheduling is modeled.
Measured homing geometry and saved-center REHOME are live-executor features;
rail_fraction and rehome_* do not synthesize either feature in this reference.

Public definitions: `wrap`, `estimate`, `balance`, `energy`, `speed_limit`, `approach`, `PumpState`, `swing`, `can_capture`, `ResponseWatch`, `RailRecovery`, `SpinRecovery`, `ControllerOutput`, `ReferenceController`.

### [src/cartpole_sdk/identification/__init__.py](src/cartpole_sdk/identification/__init__.py)

Offline identification. Optional numerical dependencies load only when used.

### [src/cartpole_sdk/identification/adapters.py](src/cartpole_sdk/identification/adapters.py)

Explicit adapters; no inference of columns, units, angle sign or acceleration.

Public definitions: `read_rows`, `sdk_run_rows`.

### [src/cartpole_sdk/identification/campaign.py](src/cartpole_sdk/identification/campaign.py)

Repeatable collection campaigns; immutable evidence, never automatic model activation.

Public definitions: `plan_suite`, `seal`, `verify`, `collect_campaign`, `analysis_request`, `review_campaign`, `bundle_campaign`, `rehearse`.

### [src/cartpole_sdk/identification/campaign_analysis.py](src/cartpole_sdk/identification/campaign_analysis.py)

Offline pixel/count shape prediction for sealed campaign recordings.

These regressions do not identify physical actuator gain or latency. Camera
host-read clocks use HTTP anchors; board snapshot clocks use a receipt proxy.
Only training records choose the shared gain and lag. Validation uses those
frozen values and each trial's preceding quiet baseline, with no refitting.

Public definitions: `map_camera_clock`, `bounded_interpolate`, `analyze_campaigns`, `main`.

### [src/cartpole_sdk/identification/campaign_cli.py](src/cartpole_sdk/identification/campaign_cli.py)

Run the remaining system-ID measurements and package raw evidence for analysis.

Public definitions: `parser`, `main`.

### [src/cartpole_sdk/identification/cli.py](src/cartpole_sdk/identification/cli.py)

Operator procedures for immutable collection, fitting and scoped simulation.

Public definitions: `parser`, `main`.

### [src/cartpole_sdk/identification/driven_capture.py](src/cartpole_sdk/identification/driven_capture.py)

Bounded, opt-in driven ID using existing motion governors and live parameters.

References and step estimates are not independent proof of physical cart motion.
No imports connect hardware; no procedure changes gains, seeks switches or clears
faults. Camera geometry loss remains missing evidence, while stale frames abort.

Public definitions: `actuator_plan`, `trajectory`, `DrivenPolicy`, `run_actuator`, `run_timing_hold`, `run_coupled`, `return_saved_home`.

### [src/cartpole_sdk/identification/driven_validation.py](src/cartpole_sdk/identification/driven_validation.py)

Offline, encoder-only prediction conditioned on commanded acceleration.

No fitting or hardware access. The fixed pole law does not turn MCU command
states into physical acceleration measurements. Phase baselines are explicit
sensitivities, and every half-second prediction reinitializes from past data.

Public definitions: `FrozenDrivenModel`, `causal_encoder_rate`, `advance`, `score_trajectory`, `analyze_driven_campaigns`, `main`.

### [src/cartpole_sdk/identification/experiments.py](src/cartpole_sdk/identification/experiments.py)

Reusable bounded collection procedures. Import never opens hardware.

The reference is A*sin^4(pi*t/T), defaultT=.65s, followed by active cart feedback.
The hold is feedback-forced, not proof that the physical cart is fixed. Import
and --check-waveform are offline. No home, clear, calibration or SET is issued.

Public definitions: `amplitude`, `hold_duration`, `pulse_duration`, `validate_excitation`, `wrap`, `waveform`, `waveform_bounds`, `validate_board`, `validate_preflight`, `stationary_preflight`, `RingdownPolicy`, `plain`, `run_pulse`, `validate_camera_finish`, `run_passive`, `inspect_rig`, `sample_camera_clock`, `record_camera`, `CameraRecorder`, `collect`.

### [src/cartpole_sdk/identification/finish.py](src/cartpole_sdk/identification/finish.py)

Nonblocking operator finish requests, scoped to passive recording only.

Public definitions: `TerminalFinish`, `PassiveFinish`.

### [src/cartpole_sdk/identification/fit.py](src/cartpole_sdk/identification/fit.py)

Weak-form fit for theta'' = alpha sin(theta)-gamma theta'-beta a cos(theta).

Compact test functions vanish together with their first derivative at window
ends. Twice integrating by parts avoids differentiating observed angle. Delay
selection and uncertainty use training only; held-out data assess prediction.

Public definitions: `FitConfig`, `FitReport`, `identify_pendulum`.

### [src/cartpole_sdk/identification/fit_review.py](src/cartpole_sdk/identification/fit_review.py)

Review an existing passive fit against its exact annotated validation source.

No parameter fit, model export, new acceptance decision, device access or
interval selection occurs here. Predictions use the pinned passive ODE method,
not MuJoCo. Driven reports need their own input-aware review and are rejected.

Public definitions: `forecast_segment`, `review_fit`.

### [src/cartpole_sdk/identification/interruption_recovery.py](src/cartpole_sdk/identification/interruption_recovery.py)

Explicit offline recovery of an operator-interrupted, disabled passive run.

The failed collection and camera reports remain immutable. A recovery is a
separate, reproducible evidence statement; it never means the requested run
completed, that release poses passed review, or that a model was accepted.

Public definitions: `recover_passive`, `validate_recovery`.

### [src/cartpole_sdk/identification/manual_capture.py](src/cartpole_sdk/identification/manual_capture.py)

Guided, motor-disabled measurements; importing this module opens no devices.

Targets describe what the operator should try. Only independently measured
operator entries are physical labels. Raw telemetry and camera streams remain
owned by the outer collection session; these records annotate their windows.

Public definitions: `run_manual`.

### [src/cartpole_sdk/identification/passive.py](src/cartpole_sdk/identification/passive.py)

Offline passive weak-form identification, with frozen independent validation.

No hardware, network, calibration or simulator mutation. Callers must establish
free-release boundaries and fixed-cart/angle validity independently.

Public definitions: `digest`, `segments`, `integral`, `matrix`, `solve`, `nrmse`, `advance`, `predict`, `camera_stationarity`, `fit_passive`.

### [src/cartpole_sdk/identification/passive_baseline.py](src/cartpole_sdk/identification/passive_baseline.py)

Pure quality gates for experiment-relative hanging references.

These bounds describe collection quality, not calibrated angular accuracy. Raw
encoder and camera readings remain in their original frames; no firmware or
saved upright reference is changed here. The camera service calibration is
never reset or changed.

Public definitions: `camera_geometry`, `build_baseline`.

### [src/cartpole_sdk/identification/protocol.py](src/cartpole_sdk/identification/protocol.py)

Nominal operator conditions; never substitute requested angles for readings.

Public definitions: `make_protocol`, `validate_protocol`, `instructions`.

### [src/cartpole_sdk/identification/release_review.py](src/cartpole_sdk/identification/release_review.py)

Offline, hash-bound review of independently observed passive release poses.

Camera angles are apparent image-plane angles relative to the measured initial
hanging pose. No sign, scale, offset, latency, model or interval is fitted here.

Public definitions: `analyze_releases`, `review_releases`.

### [src/cartpole_sdk/identification/review.py](src/cartpole_sdk/identification/review.py)

Plot admitted raw recordings before choosing intervals or fitting any model.

Public definitions: `review_recording`.

### [src/cartpole_sdk/identification/rig_logs.py](src/cartpole_sdk/identification/rig_logs.py)

Offline adapter for Rig's JSONL, with explicit board-clock/input semantics.

Public definitions: `rig_log_rows`.

### [src/cartpole_sdk/identification/timing_capture.py](src/cartpole_sdk/identification/timing_capture.py)

Opt-in host timing evidence; no device access, synchronization, or actuation.

Pass ``rig._record`` to either wrapper. It already queues log writes off the
control path. Records contain counts and protocol identities, never byte payloads
or exception messages. Capture itself has overhead; these are instrumented runs.

Public definitions: `TimingTransport`, `TimedPolicy`, `summarize_timing`.

### [src/cartpole_sdk/identification/workflow.py](src/cartpole_sdk/identification/workflow.py)

Immutable offline identification artifacts and explicitly scoped model export.

Public definitions: `digest`, `write_json`, `read_json`, `provenance`, `load_records`, `annotation_template`, `passive_episodes`, `fit_passive_logs`, `fit_driven_logs`, `export_model`, `load_model`, `gym_smoke`.

### [src/cartpole_sdk/learning/__init__.py](src/cartpole_sdk/learning/__init__.py)

Numeric policy deployment is dependency-free; training needs the sim extra.

Public definitions: `train`, `evaluate`.

### [src/cartpole_sdk/learning/artifact.py](src/cartpole_sdk/learning/artifact.py)

Bounded JSON data only. No pickle, dynamic import, eval or executable weights.

Public definitions: `validate_artifact`, `read_artifact`, `save_artifact`, `LearnedPolicy`, `load_policy`.

### [src/cartpole_sdk/learning/balance_experiment.py](src/cartpole_sdk/learning/balance_experiment.py)

Local balance-first PPO comparisons. No hardware access or deployment export.

Public definitions: `source_identity`, `teacher_gains`, `fit_teacher`, `evaluate_balance`, `run_trial`, `evaluate_saved`.

### [src/cartpole_sdk/learning/balance_hardware.py](src/cartpole_sdk/learning/balance_hardware.py)

Bounded, development-only learned control through the normal SDK runner.

The default requires an already homed, stopped rig and a prepared upright start.
Explicit hanging admission permits a swing-up/balance actor with the rig profile.
It never recenters, clears faults, writes parameters or changes calibration.
Limits apply to observed state, not independently measured truth;
STOP/lease expiry is not a model of physical stopping distance.

Public definitions: `BalanceOnlyPolicy`, `run_balance_policy`, `main`.

### [src/cartpole_sdk/learning/candidate_parity.py](src/cartpole_sdk/learning/candidate_parity.py)

Candidate-specific offline export/inference parity, separate from task success.

The actual numeric SDK actor drives the unchanged governed simulator. SB3 is
evaluated on identical encoded observations as a comparison only. This does not
exercise live transport, host STOP, firmware execution or Jetson deadlines.

Public definitions: `source_identity`, `model_weights_sha256`, `check_candidate`.

### [src/cartpole_sdk/learning/colab_bundle.py](src/cartpole_sdk/learning/colab_bundle.py)

Immutable selected-source bundles for the official Colab CLI (no network).

Public definitions: `prepare_bundle`, `verify_bundle`.

### [src/cartpole_sdk/learning/colab_remote.py](src/cartpole_sdk/learning/colab_remote.py)

Generated bundle's remote helper. Only stdlib; runs on an explicitly allocated VM.

Public definitions: `write_state`, `safe_extract`, `setup`, `verify_installed_binding`, `job`, `start`, `status`, `package`.

### [src/cartpole_sdk/learning/colab_watch.py](src/cartpole_sdk/learning/colab_watch.py)

Local checkpoint downloads; never allocate, restart, or keep a runtime alive.

Public definitions: `watch_job`.

### [src/cartpole_sdk/learning/continuing_swing.py](src/cartpole_sdk/learning/continuing_swing.py)

Training-objective ablation: dense reward with a continuing normal horizon.

This jointly removes the finite terminal-dwell bonus at a normal horizon and
allows SB3's time-limit value bootstrap there. It therefore compares a dense
continuing-horizon objective with the existing finite terminal-dwell objective;
it does not isolate either change by itself.

All physical transitions, observations, actions, leases, randomization, and
fault endings/penalties remain those of RobustSwingEnv. In particular the
existing remaining-time fault penalty is unchanged and can still be partially
observed: this ablation does not establish a fully observed continuing MDP.
Episode score uses the modified reward, while balance/hold metrics are unchanged.

Public definitions: `ContinuingSwingEnv`.

### [src/cartpole_sdk/learning/diagnostics.py](src/cartpole_sdk/learning/diagnostics.py)

Offline learning probes; checkpoints deliberately are not SDK deployment actors.

Public definitions: `DiagnosticEnv`, `preserved_rng`, `evaluate_model`, `diagnostic_provenance`, `run_pilot`, `summarize_suite`.

### [src/cartpole_sdk/learning/error_training.py](src/cartpole_sdk/learning/error_training.py)

Offline balance learning with explicit actor-input angle errors.

This perturbation is not a calibrated encoder law. Physics, telemetry, truth
reward, validity, ages and angular rate retain their existing definitions.
No hardware API, SDK actor export, or acceptance transition is provided.

Public definitions: `bias_observation`, `AngleErrorEnv`, `source_identity`, `load_profile`, `evaluate_errors`, `run_trial`, `evaluate_saved`, `main`.

### [src/cartpole_sdk/learning/evidence_profile.py](src/cartpole_sdk/learning/evidence_profile.py)

Reproducible offline training profiles from preserved rig evidence.

The passive plant remains a development assumption. Only the recorded rail and
executor settings are refreshed; encoder variation is engineering coverage, not
an accepted calibration. No hardware discovery, connection or fitting occurs.

Public definitions: `build_evidence_training_bundle`.

### [src/cartpole_sdk/learning/export.py](src/cartpole_sdk/learning/export.py)

Export a frozen numeric artifact as one bounded portal create_policy module.

The generated file embeds exact artifact bytes and explicit source selection.
It imports only stdlib and the readonly SDK; no external weight file is needed.
It deliberately retains the saved policy cadence and hardware_accepted=False.

Public definitions: `export_policy`.

### [src/cartpole_sdk/learning/model_experiment.py](src/cartpole_sdk/learning/model_experiment.py)

Explicit model admission for offline development experiments.

An identified-model-v1 export certifies only its recorded fit scope. Neither
that scope nor a development fixture establishes global swing-up qualification.
This module never modifies an identification report or grants hardware approval.

Public definitions: `digest`, `read_json`, `complete_config`, `load_training_model`, `build_experiment`, `validate_experiment`.

### [src/cartpole_sdk/learning/model_search.py](src/cartpole_sdk/learning/model_search.py)

Model-bound CEM on the governed, observed simulator; development only.

This is numeric controller parameter search, not neural RL. Its distinct
artifact schema prevents legacy direct/provisional evaluation or export.

Public definitions: `provenance`, `rollout`, `train`, `validate_artifact`, `save_artifact`, `read_artifact`, `evaluate`.

### [src/cartpole_sdk/learning/passive_profile.py](src/cartpole_sdk/learning/passive_profile.py)

Prepare explicit development training inputs from a frozen passive candidate.

This converts effective damping/friction accelerations to joint torques. It does
not refit observations, relax identification gates or certify a physical model.

Public definitions: `build_passive_training_bundle`.

### [src/cartpole_sdk/learning/ppo.py](src/cartpole_sdk/learning/ppo.py)

Offline PPO training on an explicit governed/observed model experiment.

Checkpoints are trusted SB3 training files. actor.json is a bounded numeric SDK
inference artifact; neither file approves physical deployment.

Public definitions: `provenance`, `experiment_identity`, `TrainingEnv`, `export_actor`, `load_checkpoint`, `train_ppo`, `evaluate_ppo`.

### [src/cartpole_sdk/learning/projected_ppo.py](src/cartpole_sdk/learning/projected_ppo.py)

PPO with a zero-action equilibrium projection after each optimizer rollout.

The result is an ordinary feedforward actor. No controller fallback or special
inference wrapper is required. This is an explicit constrained PPO experiment,
not vanilla PPO; projecting between rollouts does not preserve PPO's surrogate
trust-region guarantees.

Public definitions: `equilibrium_observation`, `EquilibriumPPO`.

### [src/cartpole_sdk/learning/retained_ppo.py](src/cartpole_sdk/learning/retained_ppo.py)

Experimental PPO with a fixed-anchor actor retention step.

After EquilibriumPPO's update, a separate Adam optimizer fits the Gaussian actor
mean to pinned, caller-supplied initial-actor outputs, then projects equilibrium
again. This is an explicit proximal supervised intervention, not the original
PPO objective or a trust-region guarantee. Neither improved return nor improved
anchor error after equilibrium projection is guaranteed.

Callers supply observed training/demonstration states and frozen actor means in
normalized action coordinates, without clipping. Targets may exceed [-1, 1].
The module never collects data or changes environment/randomization settings.
Multiply reported normalized RMSE by the experiment's action scale (e.g. 25)
to obtain raw acceleration disagreement.

Use RetainedPPO.load for configured checkpoints: anchors, private sampling RNG,
and separate Adam state are preserved. Plain PPO.load cannot restore the extra
optimizer. SB3's usual environment/global-RNG resume limitations still apply.

Public definitions: `RetainedPPO`.

### [src/cartpole_sdk/learning/robust_swing.py](src/cartpole_sdk/learning/robust_swing.py)

Offline full-task actor transfer and matched engineering randomization.

Transfers numeric actor weights only. Critic, optimizer and exploration are fresh;
old-profile performance does not certify the new experiment. No hardware API or
actor export is provided. All physics and reward assumptions remain explicit.

Public definitions: `source_identity`, `validate_task`, `RobustSwingEnv`, `actor_weights_hash`, `copy_actor_weights`, `load_warm_start`, `migration_parity`, `evaluation_scenarios`, `evaluate_fulltask`, `run_trial`, `main`.

### [src/cartpole_sdk/learning/rollout.py](src/cartpole_sdk/learning/rollout.py)

Seeded SDK-policy episodes against the provisional governed MuJoCo plant.

Public definitions: `initial_state`, `simulation_channels`, `rollout`, `evaluate`.

### [src/cartpole_sdk/learning/search.py](src/cartpole_sdk/learning/search.py)

Cross-entropy episodic policy search over a disclosed handwritten prior.

No expert action targets are used. Candidate gains receive only mean episodic
reward on the fixed training split. This is model-free parameter-search RL in a
provisional simulator, not a learned dynamics model or hardware-trained policy.

Public definitions: `provenance`, `train`.

### [src/cartpole_sdk/learning/swing_experiment.py](src/cartpole_sdk/learning/swing_experiment.py)

Offline swing-up/capture learning. No hardware access or acceptance claim.

Public definitions: `SwingEnv`, `load_demonstrations`, `fit_demonstrations`, `source_identity`, `run_trial`, `load_trial`, `evaluate_saved`.

### [src/cartpole_sdk/learning/training_recipe.py](src/cartpole_sdk/learning/training_recipe.py)

Reproducible engineering stress ranges, never fitted model uncertainty.

Nominal evaluation and the admitted model stay immutable. Only supported plant
and transport mechanisms vary; executor limits and action leases never vary.

Public definitions: `default_randomization`, `validate_randomization`, `sample_configs`.

### [src/cartpole_sdk/learning/transfer_checks.py](src/cartpole_sdk/learning/transfer_checks.py)

Finite offline engineering stresses for an already loaded, frozen policy.

The caller validates checkpoint loading. This module pins that caller's binding,
the evaluation runtime and actual in-memory weights; no hardware is accessed.
Passing these scenarios is not an identified uncertainty or hardware guarantee.

Public definitions: `source_identity`, `scenarios`, `run_suite`.

### [src/cartpole_sdk/policies/__init__.py](src/cartpole_sdk/policies/__init__.py)

Source-explicit policies; importing policies never opens or arms a device.

### [src/cartpole_sdk/policies/damping.py](src/cartpole_sdk/policies/damping.py)

Small offline teaching policies, not commissioned rig controllers.

Public definitions: `AngularDampingPolicy`.

### [src/cartpole_sdk/policies/executor_feedback.py](src/cartpole_sdk/policies/executor_feedback.py)

Host AUTO/BAL with explicit MCU observer and motion-state feedback.

This is a sampled 100/250 Hz controller, not native 1 kHz bit parity. Only the
executor governs actuators. A float64 forecast screens capture; current motion
feedback is always supplied by the observation, never predicted internally.
Spin faults and BAL loss stop rather than implementing native return routines.

Public definitions: `ExecutorFeedbackPolicy`.

### [src/cartpole_sdk/policies/host.py](src/cartpole_sdk/policies/host.py)

A separate sensed-state controller at 100 or 250 Hz, returning RAW demand.

This is a handwritten energy-shaping/linear-feedback prior, not the archived
ReferencePolicy, not a 1 kHz observer, and not a commissioned hardware policy.
The executor, not this policy, applies jerk/speed/rail limits. Angle is upright=0,
positive toward positive cart x; source/frame selection never converts frames.

Public definitions: `HostPolicyParameters`, `HostRatePolicy`.

### [src/cartpole_sdk/policies/neural.py](src/cartpole_sdk/policies/neural.py)

Bounded numeric PPO actor inference through the ordinary SDK Policy API.

Only a fixed two-layer tanh MLP is supported. No Torch, pickle, executable graph,
simulator, device object or automatic hardware source selection is loaded.

Public definitions: `validate_actor`, `NeuralPolicy`, `load_neural_policy`.

### [src/cartpole_sdk/policies/numeric_backend.py](src/cartpole_sdk/policies/numeric_backend.py)

Opt-in, prepacked float64 inference for the fixed numeric actor.

This module does not load artifacts or admit hardware. The caller must retain
the ordinary actor loader's provenance checks and all policy/runner guards.
NumPy is imported only when this backend is explicitly constructed.

Public definitions: `NumpyActorBackend`.

### [src/cartpole_sdk/policies/rig_observation.py](src/cartpole_sdk/policies/rig_observation.py)

Shared, dependency-free encoder for rig SDK and governed Gym policy inputs.

Only explicit channels are read. This module imports no simulator or device
client; it can run on the policy host. The encoder preserves validity and age,
using finite zeros for missing values. The trusted runner/policy must still
enforce freshness and reject unusable channels before sending hardware actions.

Public definitions: `observation_contract`, `validate_observation_contract`, `contract_from_config`, `rig_channels`, `simulation_channels`, `channel_age_limits`, `select_rig_observation`, `encode_rig_observation`.

### [src/cartpole_sdk/portal/__init__.py](src/cartpole_sdk/portal/__init__.py)

Authenticated policy submissions and fail-closed isolated execution.

### [src/cartpole_sdk/portal/budget.py](src/cartpole_sdk/portal/budget.py)

Trusted source-derived execution budgets shared by queue and worker.

Submitted duration is a simulation horizon or physical experiment duration.
Simulation gets twice that duration in wall time; physical duration is unchanged.
There is no submitted wall budget field.

Public definitions: `execution_wall_seconds`.

### [src/cartpole_sdk/portal/harness.py](src/cartpole_sdk/portal/harness.py)

Bwrap child entrypoint. Only this restricted child imports submitted code.

Public definitions: `read_message`, `emit`, `main`.

### [src/cartpole_sdk/portal/queue.py](src/cartpole_sdk/portal/queue.py)

Durable owner-bound jobs and one transactional lease per physical rig.

Public definitions: `QueueError`, `name`, `Store`.

### [src/cartpole_sdk/portal/sandbox.py](src/cartpole_sdk/portal/sandbox.py)

Fail-closed bwrap launcher and independently bounded newline JSON IPC.

Public definitions: `SandboxError`, `validate_acceleration_ceiling`, `PolicyChannel`, `Sandbox`.

### [src/cartpole_sdk/portal/security.py](src/cartpole_sdk/portal/security.py)

Child-only Linux restrictions, installed before any uploaded source import.

Public definitions: `install_limits`.

### [src/cartpole_sdk/portal/server.py](src/cartpole_sdk/portal/server.py)

Bounded loopback-first HTTP API; browser credentials never appear in URLs.

Public definitions: `PortalServer`, `Handler`, `make_server`, `main`.

### [src/cartpole_sdk/portal/worker.py](src/cartpole_sdk/portal/worker.py)

Trusted outbound pull worker. Uploaded modules are never imported here.

Public definitions: `WorkerError`, `RemoteQueue`, `SimulationBridge`, `HardwareBridge`, `run_once`, `main`.

### [src/cartpole_sdk/recording.py](src/cartpole_sdk/recording.py)

Strict, deterministic JSONL v1 recordings.

Wire format: {type: session, version: 1, session: <Session fields>}, then
{type: observation, observation: <Observation fields>}, and exactly one
{type: footer, count: <number of observations>}. All objects have exact keys.
The footer detects truncated streams; it is not a cryptographic integrity check.

Public definitions: `strict_json_loads`, `canonical_json`, `write_recording`, `read_recording`.

### [src/cartpole_sdk/replay.py](src/cartpole_sdk/replay.py)

Deterministic open-loop replay; actions never alter subsequent observations.

Public definitions: `ReplayStep`, `replay`, `write_trace`.

### [src/cartpole_sdk/rig/__init__.py](src/cartpole_sdk/rig/__init__.py)

Optional live rig API. Importing this module does not open or arm hardware.

### [src/cartpole_sdk/rig/client.py](src/cartpole_sdk/rig/client.py)

Exclusive stopped-on-connect live executor client with bounded board leases.

Only trusted operator code owns Rig. Policies receive observations and submit
ActionRequest objects through a broker, never this serial transport.

Public definitions: `RigError`, `Rig`.

### [src/cartpole_sdk/rig/console.py](src/cartpole_sdk/rig/console.py)

Operator console for board reference modes and explicit external policies.

Public definitions: `execute_command`, `main`.

### [src/cartpole_sdk/rig/console_policy.py](src/cartpole_sdk/rig/console_policy.py)

A selected development actor on the console's existing Rig.

Public definitions: `ConsolePolicy`, `execute_policy_command`.

### [src/cartpole_sdk/rig/cpu_affinity.py](src/cartpole_sdk/rig/cpu_affinity.py)

Reversible Linux camera/control CPU partitioning; standard library only.

Public definitions: `AffinityError`, `parse_cpus`, `validate_partition`, `ProcessIdentity`, `ThreadIdentity`, `ProcFS`, `CameraAffinity`, `service_main_pid`, `run_control`, `main`.

### [src/cartpole_sdk/rig/neural_runner.py](src/cartpole_sdk/rig/neural_runner.py)

Explicit development-only neural inference against a stopped live SDK rig.

Shadow is the default. Camera networking runs in a bounded background reader;
the telemetry-paced policy path never waits on HTTP. Calibration and clock
bindings are operator-supplied evidence, not inferred from a frame label.

Public definitions: `validate_sensing_config`, `VisionStreamSubscriber`, `CameraObservationProvider`, `validate_live_executor`, `run_neural_policy`.

### [src/cartpole_sdk/rig/parameters.py](src/cartpole_sdk/rig/parameters.py)

Live tuning names, numeric limits and explicit host profile files.

This module never loads profiles implicitly or opens a rig transport. The
operator console selects its startup profile separately in rig.startup.

Public definitions: `parameter_name`, `float32`, `parameter_value`, `parameter_map`, `validate_parameters`, `validate_spin`, `read_profile`, `write_profile`.

### [src/cartpole_sdk/rig/policy.py](src/cartpole_sdk/rig/policy.py)

Trusted host policy runner. Untrusted submissions belong in a separate broker.

Factories are explicit Python callables supplied by trusted operator code; no
module/path imports or user code loading occur here. The preserved 1kHz reference
policy is not selected automatically at a slower telemetry rate.

Public definitions: `ZeroAccelerationPolicy`, `run_policy`, `run_host_controller`.

### [src/cartpole_sdk/rig/policy_console.py](src/cartpole_sdk/rig/policy_console.py)

Run the operator console with a scoped 1 ms Python GIL switch interval.

Public definitions: `main`.

### [src/cartpole_sdk/rig/protocol.py](src/cartpole_sdk/rig/protocol.py)

Pinned V2 ASCII framing. Parsing has no transport or actuation side effects.

Public definitions: `ProtocolError`, `crc16`, `encode`, `decode`, `uint32`, `unwrap32`, `State`, `parse_state`, `ExecutorInfo`, `parse_info`, `parse_parameter`, `LineBuffer`.

### [src/cartpole_sdk/rig/runtime.py](src/cartpole_sdk/rig/runtime.py)

Explicit runtime scopes for bounded live rig sessions.

Public definitions: `defer_cyclic_gc`.

### [src/cartpole_sdk/rig/startup.py](src/cartpole_sdk/rig/startup.py)

Console-only startup profiles. Importing the SDK never changes board tuning.

Public definitions: `StartupParameters`.

### [src/cartpole_sdk/rig/transport.py](src/cartpole_sdk/rig/transport.py)

Optional pyserial adapter; importing the SDK never opens a device.

Public definitions: `Transport`, `SerialTransport`.

### [src/cartpole_sdk/sensing/__init__.py](src/cartpole_sdk/sensing/__init__.py)

Pure source adapters; providers require explicit clocks and calibration.

### [src/cartpole_sdk/sensing/calibration.py](src/cartpole_sdk/sensing/calibration.py)

Offline hanging-to-upright calibration with reproducible validation evidence.

The correction is added after the ideal half-turn. This is a reference conversion,
not an encoder linearization or a camera calibration. Validation bounds are
empirical observed error envelopes, not statistical confidence guarantees.

Public definitions: `signed_count_delta`, `CalibrationPolicy`, `fit_calibration`, `CalibrationProfile`, `load_json`, `main`.

### [src/cartpole_sdk/sensing/frames.py](src/cartpole_sdk/sensing/frames.py)

Explicit angular coordinate transforms; no inference from a frame label.

An anchor records the original source calibration and a measured zero in that
source's coordinates. A direct upright camera anchor must be supplied by the
operator; a magnetic half-turn assumption is not a camera calibration.

Public definitions: `wrap`, `AngularAlignment`.

### [src/cartpole_sdk/sensing/fusion.py](src/cartpole_sdk/sensing/fusion.py)

Causal, shadow-only complementary angle correction.

Encoder observations supply fast relative motion. Camera updates compare against
wrapped interpolation of encoder history at the camera effective timestamp, never
against the newest encoder angle. A slow rate-limited correction is carried to the
current encoder angle. This is not a model of nonlinear/hysteretic magnetic error,
not an exposure-time estimator, and not a commissioned control observer. Rates
remain source-specific; silently averaging differently delayed rates is avoided.

Public definitions: `SourceIdentity`, `FusionConfig`, `AngleFusion`.

### [src/cartpole_sdk/sensing/policy_observation.py](src/cartpole_sdk/sensing/policy_observation.py)

Explicit, causal camera/encoder composition for development policy inference.

The caller supplies measured angular anchors and a camera-to-board clock map.
Composition retains the board sequence and availability used by action leases.
Camera receipts newer than that snapshot wait for a later board observation.
This module opens no device, changes no calibration and grants no deployment
acceptance. Fused angle is the existing SDK complementary observer; angular
velocity remains the independently named, aligned magnetic rate estimate.

Public definitions: `PolicyObservationAssembler`.

### [src/cartpole_sdk/sensing/shadow.py](src/cartpole_sdk/sensing/shadow.py)

Configured read-only bridge from SDK mirror/camera snapshots to shadow fusion.

A receipt-anchor clock map is an explicitly chosen approximation. Its transport
latency, uncertainty, residual budget and lifetime are required configuration,
not measurements of exposure time. Changing board session or calibration latches
an error and needs a new observer. This module never opens serial or commands Rig.

Public definitions: `ShadowObserver`.

### [src/cartpole_sdk/sensing/stream.py](src/cartpole_sdk/sensing/stream.py)

Bounded read-only NDJSON transport for the maintained sensing service.

Every blocking response read, including HTTP headers/chunk framing, uses the
same absolute deadline. The transport does not map clocks, reset calibration,
filter samples, or retry: those decisions remain with the caller.

Public definitions: `StreamDeadline`, `StreamDisconnected`, `SensingStreamClient`.

### [src/cartpole_sdk/sensing/telemetry.py](src/cartpole_sdk/sensing/telemetry.py)

Best-effort loopback mirror of the SDK's single serial owner's accepted state.

Submission replaces one immutable snapshot reference. Serialization/network work
runs on a separate worker, cannot queue unbounded history and cannot send rig
commands. State receipt time is retained, so a disconnected owner never appears
fresh because a viewer re-polled or a worker was delayed.

Public definitions: `encoder_packet`, `EncoderPublisher`.

### [src/cartpole_sdk/sensing/vision.py](src/cartpole_sdk/sensing/vision.py)

Read-only vision3 snapshots converted into source-explicit SDK observations.

vision3 t is host read completion, an acquisition proxy rather than a sensor
exposure timestamp. Display/comparison fusion is deliberately never consumed.

Public definitions: `calibration_fingerprint`, `ClockMapping`, `VisionProvider`, `VisionHTTPClient`.

### [src/cartpole_sdk/sim/__init__.py](src/cartpole_sdk/sim/__init__.py)

Optional MuJoCo backend. Install the SDK's sim extra before importing.

### [src/cartpole_sdk/sim/backend.py](src/cartpole_sdk/sim/backend.py)

MuJoCo plant with cart acceleration intent, bounded force, and sensor transport.

This backend is an unvalidated model, not a hardware safety authority. Expired
leases use zero acceleration demand (which can require a nonzero cart force).

Public definitions: `GroundTruth`, `SimulationDiagnostics`, `MujocoBackend`.

### [src/cartpole_sdk/sim/config.py](src/cartpole_sdk/sim/config.py)

Explicit provisional plant and simulated sensor assumptions (SI units).

Public definitions: `finite`, `number`, `integer`, `SimulationConfig`, `SensorConfig`.

### [src/cartpole_sdk/sim/executor.py](src/cartpole_sdk/sim/executor.py)

RAW-demand execution model with the original binary32 1 kHz governor.

MujocoBackend retains its direct/executed-acceleration semantics. This wrapper
models the *external* executor path separately. Faults terminate the rollout at
the fault tick: no physical disabled-motor stopping distance is claimed. Sensor
noise/delay belong to the plant and are never bypassed for policy feedback.

Public definitions: `ExecutorDiagnostics`, `ExecutorSimulation`.

### [src/cartpole_sdk/sim/gym_env.py](src/cartpole_sdk/sim/gym_env.py)

Headless Gymnasium interface to the provisional acceleration-driven plant.

Action: one cart acceleration in m/s². Sensor observation: x, v, sin(theta),
cos(theta), omega, with a five-element validity mask and effective age in seconds.
Unavailable values use finite zero placeholders with mask=0; unknown age is -1.
Reward uses true plant cos(theta) - (x/rail_half_m)**2 - .001*action**2, an
illustrative upright/centering/control-cost objective, not a validated target.
Default control interval is 10 ms; backend/reference integration defaults to 1 ms.

Public definitions: `CartpoleEnv`.

### [src/cartpole_sdk/sim/model.py](src/cartpole_sdk/sim/model.py)

Generate a two-DOF, contact-free MJCF surrogate from explicit configuration.

Public definitions: `model_xml`.

### [src/cartpole_sdk/sim/policy_viewer.py](src/cartpole_sdk/sim/policy_viewer.py)

Local native viewer for numeric actors and the saved reference controller.

Learned mode uses the actual 100 Hz RigCartpoleEnv and numeric SDK actor. Reference
mode uses the same fitted plant with the 1 kHz ReferencePolicy, saved gains and
ideal sensors; its output is already governed, so no second governor is applied.
Imports create no window and no hardware connection. GUI state is display-only.

Public definitions: `NumericViewerPolicy`, `LearnedViewerSession`, `ReferenceViewerSession`, `create_session`, `summary`, `run_viewer`, `main`, `launch`.

### [src/cartpole_sdk/sim/rig_gym_env.py](src/cartpole_sdk/sim/rig_gym_env.py)

100 Hz Gym adapter for governed actions and causal encoder/camera sensing.

This opt-in environment leaves the frozen direct-acceleration model unchanged.
Raw angle plus estimated angular rate matches Rig.observation/HostRatePolicy;
filtered angle is an explicit alternative for ExecutorFeedbackPolicy. All SDK
channels retain source='simulation': names do not certify physical sensors.
Vision uses the maintained tracker's causal derivative, VisionProvider and
explicit anchors. Fused angle uses AngleFusion plus aligned magnetic rate.

The plant is still an ideal acceleration servo with an assumed force ceiling.
Step position is an ideal commanded pulse count, without ISR phase/direction
setup timing, missed steps or backlash. The reused governor checks physical
plant x, which differs from this command-count estimate by quantization while
the servo tracks. Force saturation terminates as unsupported tracking, rather
than allowing that discrepancy to train a policy. Timing settings are declared
integer delays, not measured transport distributions. Faults end the episode;
disabled-motor travel is not modeled.

Public definitions: `RigObservationConfig`, `RigCartpoleEnv`.

### [src/cartpole_sdk/sim/viewer.py](src/cartpole_sdk/sim/viewer.py)

Native passive viewer for the real SDK reference policy and MuJoCo plant.

Importing this module creates no window. The GUI receives a display-only mirror:
its native reset, keyframes, perturbations and option edits cannot change the
backend's authoritative controller, sensor clock or plant configuration.

Public definitions: `ViewerSession`, `copy_display_state`, `run_viewer`, `main`, `launch`.

### [src/cartpole_sdk/simulation.py](src/cartpole_sdk/simulation.py)

Closed-loop local runner and reproducible output bundle (requires sim extra).

Public definitions: `SimulationStep`, `SimulationRun`, `ZeroPolicy`, `run_simulation`, `write_simulation`.

## src/cartpole_vision

### [src/cartpole_vision/__init__.py](src/cartpole_vision/__init__.py)

Observe-only cartpole vision. No motor or controller interfaces.

### [src/cartpole_vision/app.py](src/cartpole_vision/app.py)

Thread-safe measurement engine and local calibration dashboard API.

Public definitions: `Engine`, `create_app`.

### [src/cartpole_vision/capture.py](src/cartpole_vision/capture.py)

Latest-frame camera capture and honest host-delivery diagnostics.

Public definitions: `ArrivalStats`, `Camera`, `RawRecorder`, `BufferedRecorder`.

### [src/cartpole_vision/cart.py](src/cartpole_vision/cart.py)

Independent, fixed-template cart measurement. No self-updating drift.

Public definitions: `CartTemplate`.

### [src/cartpole_vision/comparison_process.py](src/cartpole_vision/comparison_process.py)

Keep encoder/fusion work in its own process; camera submissions never wait.

Public definitions: `ComparisonProcess`.

### [src/cartpole_vision/detector.py](src/cartpole_vision/detector.py)

Geometric detector for a green shaft with a wider circular weighted end.

All processing is bounded to 960px width. No pose is extrapolated. A missed
frame does not disable subsequent detection. Confidence is a heuristic quality
score, not a probability or a calibrated angular error bound.

Public definitions: `Pose`, `Detection`, `ArmDetector`.

### [src/cartpole_vision/encoder_feed.py](src/cartpole_vision/encoder_feed.py)

Independent encoder history and display fusion; input is local console telemetry.

Public definitions: `Comparison`, `EncoderReceiver`.

### [src/cartpole_vision/evaluate.py](src/cartpole_vision/evaluate.py)

Offline, reproducible motion evaluation. Never opens a camera.

Public definitions: `error_stats`, `accuracy`, `render_arm`, `load_package`, `benchmark`, `main`.

### [src/cartpole_vision/fusion.py](src/cartpole_vision/fusion.py)

Angle fusion for display only. Timestamps are estimated host measurement times.

Public definitions: `wrap`, `ClockMapper`, `AngleFusion`.

### [src/cartpole_vision/gst_encoder.py](src/cartpole_vision/gst_encoder.py)

System-Python GStreamer helper. Stdin: timestamped BGR. Stdout: H.264 packets.

Separate process uses the Jetson's existing GI runtime, without adding packages
or requiring GI in the vision virtual environment. Diagnostics go to stderr.

Public definitions: `exact`, `main`.

### [src/cartpole_vision/history.py](src/cartpole_vision/history.py)

Bounded measured samples for charts; never fills in missing measurements.

Public definitions: `MeasurementHistory`.

### [src/cartpole_vision/http.py](src/cartpole_vision/http.py)

Private streaming HTTP settings; no system-wide networking changes.

Public definitions: `StreamingRequestHandler`, `ViewServer`.

### [src/cartpole_vision/live.py](src/cartpole_vision/live.py)

Run the observe-only cartpole vision dashboard.

Public definitions: `arguments`, `main`.

### [src/cartpole_vision/metrics.py](src/cartpole_vision/metrics.py)

Measurement coverage and timing, independent of UI/stream throughput.

Public definitions: `percentiles`, `counts`, `coverage`, `summarize`, `MeasurementMetrics`.

### [src/cartpole_vision/pipeline_benchmark.py](src/cartpole_vision/pipeline_benchmark.py)

Paced 80 FPS synthetic source through the real engine/optional H.264 worker.

No camera, network listener, power change or hardware control. Reports local
service/encode latency only; rendering the input cache is outside the trial.

Public definitions: `run`, `main`.

### [src/cartpole_vision/preview.py](src/cartpole_vision/preview.py)

Low-rate JPEG fallback, independent of measurement processing.

Public definitions: `PreviewWorker`.

### [src/cartpole_vision/probe.py](src/cartpole_vision/probe.py)

Measure camera delivery and tracking throughput without running a web server.

Public definitions: `main`.

### [src/cartpole_vision/replay.py](src/cartpole_vision/replay.py)

Deterministic offline analysis; input PTS or raw timestamp sidecar is authoritative.

Public definitions: `annotate`, `replay`, `main`.

### [src/cartpole_vision/runtime.py](src/cartpole_vision/runtime.py)

Bounded on-disk diagnostics and camera liveness for unattended viewing.

Public definitions: `JsonlLog`, `prune_sessions`, `camera_failure`.

### [src/cartpole_vision/sdk_feed.py](src/cartpole_vision/sdk_feed.py)

Read-only receiver for genuine SDK shadow observations. Never controls hardware.

Public definitions: `empty_snapshot`, `SDKFeed`.

### [src/cartpole_vision/sensing_stream.py](src/cartpole_vision/sensing_stream.py)

Bounded pull-driven sensing stream. Camera and encoder timestamps stay intact.

Public definitions: `encode_envelope`, `envelopes`.

### [src/cartpole_vision/state.py](src/cartpole_vision/state.py)

Timestamped measurements, calibration and causal velocity estimates.

Public definitions: `wrap`, `Derivative`, `StateEstimator`.

### [src/cartpole_vision/stream.py](src/cartpole_vision/stream.py)

Bounded, timestamped H.264 transport; camera capture never waits for viewers.

Public definitions: `read_exact`, `read_packet`, `Broadcast`, `RateGate`, `select_frame`, `VideoStream`.

## Command wrappers and examples

Wrappers select dependencies, module entry points, and/or host scheduling. Inspect the linked wrapper before reusing a historical command; commands that connect to the rig can move hardware.

- [scripts/balance-error-learning](scripts/balance-error-learning): exec uv run --project "$repo_dir" --extra rl python -m cartpole_sdk.learning.error_training "$@"
- [scripts/balance-learning](scripts/balance-learning): exec uv run --project "$repo_dir" --extra rl python "$repo_dir/examples/balance_learning.py" "$@"
- [scripts/benchmark-numeric-inference.py](scripts/benchmark-numeric-inference.py): Reproduce actor parity and warmed host latency without a device or Torch.
- [scripts/check-encoder-repeatability](scripts/check-encoder-repeatability): exec uv run --locked --project "$repo_dir" --extra hardware python \
- [scripts/colab-training](scripts/colab-training): exec uv run --project "$repo_dir" python "$repo_dir/examples/colab_training.py" "$@"
- [scripts/install-vision-service.sh](scripts/install-vision-service.sh)
- [scripts/jetson-control](scripts/jetson-control)
- [scripts/policy-console](scripts/policy-console): exec uv run --project "$repo_dir" python -m cartpole_sdk.rig.policy_console "$@" exec uv run --project "$repo_dir" --extra hardware --extra inference python -m cartpole_sdk.rig.policy_console "$@"
- [scripts/prepare-colab-training](scripts/prepare-colab-training): exec uv run --project "$repo_dir" --extra rl python "$repo_dir/examples/prepare_colab_training.py" "$@"
- [scripts/prepare-rig-training](scripts/prepare-rig-training): exec uv run --locked --project "$repo_dir" python "$repo_dir/examples/prepare_rig_training.py" "$@" exec uv run --locked --project "$repo_dir" --extra sim python "$repo_dir/examples/prepare_rig_training.py" "$@"
- [scripts/prepare-training-model](scripts/prepare-training-model): exec uv run --locked --project "$repo_dir" python "$repo_dir/examples/prepare_passive_training.py" "$@" exec uv run --locked --project "$repo_dir" --extra sim python "$repo_dir/examples/prepare_passive_training.py" "$@"
- [scripts/replay-balance-evaluation](scripts/replay-balance-evaluation): exec "$repo_dir/.venv/bin/python" "$repo_dir/examples/replay_balance_evaluation.py" "$@"
- [scripts/rl-diagnostics](scripts/rl-diagnostics): exec uv run --project "$repo_dir" --extra rl python "$repo_dir/examples/rl_diagnostics.py" "$@"
- [scripts/robust-swing-learning](scripts/robust-swing-learning): exec uv run --project "$repo_dir" --extra rl python -m cartpole_sdk.learning.robust_swing "$@"
- [scripts/run-balance-policy](scripts/run-balance-policy): exec uv run --project "$repo_dir" python -m cartpole_sdk.learning.balance_hardware "$@" exec uv run --project "$repo_dir" --extra hardware --extra inference python -m cartpole_sdk.learning.balance_hardware "$@"
- [scripts/run-neural-policy](scripts/run-neural-policy): exec uv run --project "$repo_dir" python "$repo_dir/examples/run_neural_policy.py" "$@" exec uv run --project "$repo_dir" --extra hardware python "$repo_dir/examples/run_neural_policy.py" "$@"
- [scripts/run-vision-service.sh](scripts/run-vision-service.sh): exec .venv-vision/bin/cartpole-vision "$@" \
- [scripts/swing-learning](scripts/swing-learning): exec uv run --project "$repo_dir" --extra rl python "$repo_dir/examples/swing_learning.py" "$@"
- [scripts/swing-transfer-check](scripts/swing-transfer-check): exec "$repo_dir/.venv/bin/python" "$repo_dir/examples/swing_transfer_check.py" "$@"
- [scripts/system-id](scripts/system-id): exec uv run --project "$repo_dir" python -m cartpole_sdk.identification.cli "$@" exec uv run --project "$repo_dir" --extra id --extra plots python -m cartpole_sdk.identification.cli "$@" ;; exec uv run --project "$repo_dir" --extra sim python -m cartpole_sdk.identification.cli "$@" ;; exec uv run --project "$repo_dir" --extra hardware --extra id python -m cartpole_sdk.identification.cli "$@" ;; exec uv run --project "$repo_dir" --extra id python
- [scripts/system-id-campaign](scripts/system-id-campaign): exec uv run --project "$repo_dir" python -m cartpole_sdk.identification.campaign_cli "$@"
- [scripts/train-ppo](scripts/train-ppo): exec uv run --project "$repo_dir" python "$repo_dir/examples/train_ppo.py" "$@" exec uv run --project "$repo_dir" --extra rl python "$repo_dir/examples/train_ppo.py" "$@"
- [scripts/view-policy](scripts/view-policy): exec uv run --locked --project "$repo_dir" --extra sim python "$repo_dir/examples/view_policy.py" "$@"
- [scripts/vision-tunnel.sh](scripts/vision-tunnel.sh): exec ssh -N -T -o ExitOnForwardFailure=yes -o ServerAliveInterval=15 -o ServerAliveCountMax=3 \
- [scripts/vision-view.py](scripts/vision-view.py): Localhost viewing proxy over the private Tailscale network.
- [examples/balance_learning.py](examples/balance_learning.py): Matched local balance learning and longer evaluation. Never connects to hardware.
- [examples/balance_teacher_search.py](examples/balance_teacher_search.py): Serial observed-state balance teacher search; local nominal simulation only.
- [examples/calibrate_angle.py](examples/calibrate_angle.py): Offline calibration tools; never opens a rig, port, camera, or network connection.
- [examples/cartpole.py](examples/cartpole.py): SDK-backed live operator console; install cartpole-sdk[hardware] first.
- [examples/centering_bias_screen.py](examples/centering_bias_screen.py): Bounded exploratory observed-state balance-law screen; no hardware approval.
- [examples/colab_training.py](examples/colab_training.py): Operate an explicit Colab CLI session. start allocates a real CPU VM and launches training.
- [examples/evaluate_policy.py](examples/evaluate_policy.py): Compare immutable learned weights with the pretraining handwritten policy.
- [examples/export_policy.py](examples/export_policy.py): Export frozen learned weights to one source file for the isolated portal.
- [examples/gym_rollout.py](examples/gym_rollout.py): Exercise the RL interface; this random-policy smoke run does not train an agent.
- [examples/host_cartpole.py](examples/host_cartpole.py): Local MuJoCo auto/bal using the same ExecutorFeedbackPolicy as python-auto/python-bal.
- [examples/identify.py](examples/identify.py): Offline fit: independent input files, explicit adapters, reviewable JSON.
- [examples/identify_rig.py](examples/identify_rig.py): Offline rig-log fit. Inputs can be logs, .jsonl.gz, or ARCHIVE.tar.gz::MEMBER.
- [examples/load_identified_model.py](examples/load_identified_model.py): Run a content-hashed identification export in headless100Hz Gym; no hardware.
- [examples/portal.py](examples/portal.py)
- [examples/portal_worker.py](examples/portal_worker.py)
- [examples/prepare_colab_training.py](examples/prepare_colab_training.py): Validate and package a selected training profile; never connects to Colab or the rig.
- [examples/prepare_passive_training.py](examples/prepare_passive_training.py): Prepare immutable Gym/PPO inputs from a frozen passive candidate; no rig access.
- [examples/prepare_rig_training.py](examples/prepare_rig_training.py): Prepare a new evidence-bound development training profile; offline only.
- [examples/replay_balance_evaluation.py](examples/replay_balance_evaluation.py): Replay a trusted local balance or swing run with its verified archived evaluator.
- [examples/replay_policy.py](examples/replay_policy.py): Edit MyPolicy to experiment locally. This example never connects to hardware.
- [examples/rl_diagnostics.py](examples/rl_diagnostics.py): Short offline PPO experiments and summaries; never connect to a rig or Colab.
- [examples/run_neural_policy.py](examples/run_neural_policy.py): Run a numeric SDK actor in shadow, or explicitly execute development actions.
- [examples/sensing_shadow.py](examples/sensing_shadow.py): Read-only SDK shadow observer; persistent sensing stream or deterministic JSONL replay.
- [examples/shadow_policy.py](examples/shadow_policy.py): Offline timing/source shadow of HostRatePolicy over a recorded reference run.
- [examples/simulate_policy.py](examples/simulate_policy.py): Edit MyPolicy, then: uv run --extra sim python examples/simulate_policy.py runs/my-sim
- [examples/swing_learning.py](examples/swing_learning.py): Local observed-state swing-up and balance training; no hardware commands.
- [examples/swing_teacher_search.py](examples/swing_teacher_search.py): Exploratory observed-state swing-up teacher screen; simulation only.
- [examples/swing_transfer_check.py](examples/swing_transfer_check.py): Run current offline transfer checks over a trusted, verified frozen swing run.
- [examples/train_policy.py](examples/train_policy.py): Train numeric parameters from episodic reward in the provisional simulator.
- [examples/train_ppo.py](examples/train_ppo.py): Train/resume/evaluate a model-bound PPO actor offline; no rig access.
- [examples/view_policy.py](examples/view_policy.py): Local actor/reference GUI; automatically uses mjpython on macOS.
- [examples/view_simulation.py](examples/view_simulation.py): Native SDK simulation. On macOS: .venv/bin/mjpython examples/view_simulation.py

## Maintained and historical documentation

- [Revised v2 architecture](docs/architecture.md) — `docs/architecture.md`
- [Balance runner guard profiles](docs/balance-guard-profiles.md) — `docs/balance-guard-profiles.md`
- [Local balance-first learning](docs/balance-learning.md) — `docs/balance-learning.md`
- [Cartpole v2 checkpoint — 2026-10-16](docs/checkpoint-20261016.md) — `docs/checkpoint-20261016.md`
- [Policy guards, new characterization and robust-learning follow-up](docs/checkpoint-20261020-followup.md) — `docs/checkpoint-20261020-followup.md`
- [Encoder-only characterization and balance-policy checkpoint — 2026-10-20](docs/checkpoint-20261020.md) — `docs/checkpoint-20261020.md`
- [Learned swing-up and balance through the operator console](docs/console-policy.md) — `docs/console-policy.md`
- [Control timing, language, and Jetson–Teensy transport](docs/control-timing-and-transport.md) — `docs/control-timing-and-transport.md`
- [Programming and reset: motor power must be off](docs/executor.md) — `docs/executor.md`
- [Offline sensing and identification](docs/identification.md) — `docs/identification.md`
- [Jetson test handoff](docs/jetson-testing.md) — `docs/jetson-testing.md`
- [Remaining implementation and acceptance plan](docs/live-rig-plan.md) — `docs/live-rig-plan.md`
- [Paused hardware work — 2026-10-16](docs/paused-development-status.md) — `docs/paused-development-status.md`
- [PCB switch wiring and bounded homing](docs/pcb-switches.md) — `docs/pcb-switches.md`
- [Phase 0: portable known-working baseline](docs/phase0-plan.md) — `docs/phase0-plan.md`
- [Phase 1 Foundation Implementation Plan](docs/phase1-plan.md) — `docs/phase1-plan.md`
- [Python SDK: recordings and policy replay](docs/phase1-usage.md) — `docs/phase1-usage.md`
- [Phase 2 Controller and Simulation Implementation Plan](docs/phase2-plan.md) — `docs/phase2-plan.md`
- [Phase 2: reference controller and simulation](docs/phase2-usage.md) — `docs/phase2-usage.md`
- [Remaining system identification collection](docs/plans/2026-10-18-system-id-campaign.md) — `docs/plans/2026-10-18-system-id-campaign.md`
- [Angle-error training and explicit balance refusal diagnostics](docs/plans/2026-10-20-angle-error-training.md) — `docs/plans/2026-10-20-angle-error-training.md`
- [Live system identification and balance deployment, 2026-10-20](docs/plans/2026-10-20-system-id-model-training.md) — `docs/plans/2026-10-20-system-id-model-training.md`
- [Platform status after the live rig build](docs/platform-status.md) — `docs/platform-status.md`
- [Host policies and reproducible policy search](docs/policies.md) — `docs/policies.md`
- [Policy submission portal and isolated pull worker](docs/portal.md) — `docs/portal.md`
- [Python control and identification — 2026-10-16](docs/python-control-20261016.md) — `docs/python-control-20261016.md`
- [Live rig SDK and operator console](docs/rig-usage.md) — `docs/rig-usage.md`
- [Develop and diagnose an RL controller](docs/rl-development-cycle.md) — `docs/rl-development-cycle.md`
- [Train an SDK policy with MuJoCo, Gymnasium and PPO](docs/rl-training.md) — `docs/rl-training.md`
- [Read-only encoder telemetry and SDK shadow fusion](docs/sensing.md) — `docs/sensing.md`
- [What offline success can establish](docs/simulation-transfer.md) — `docs/simulation-transfer.md`
- [Live rig platform: remaining phases](docs/specs/live-rig-platform.md) — `docs/specs/live-rig-platform.md`
- [Phase 1: local policy contracts and deterministic replay](docs/specs/phase1-foundation.md) — `docs/specs/phase1-foundation.md`
- [Phase 2: Python reference controller and MuJoCo backend](docs/specs/phase2-controller-simulation.md) — `docs/specs/phase2-controller-simulation.md`
- [Friction law, later batches and training Gym implementation plan](docs/superpowers/plans/2026-10-17-friction-gym-integration.md) — `docs/superpowers/plans/2026-10-17-friction-gym-integration.md`
- [Local RL diagnostics implementation plan](docs/superpowers/plans/2026-10-17-local-rl-diagnostics.md) — `docs/superpowers/plans/2026-10-17-local-rl-diagnostics.md`
- [Multimodal RL readiness implementation plan](docs/superpowers/plans/2026-10-17-multimodal-rl-readiness.md) — `docs/superpowers/plans/2026-10-17-multimodal-rl-readiness.md`
- [Passive hanging baseline and camera qualification](docs/superpowers/plans/2026-10-17-passive-camera-baseline.md) — `docs/superpowers/plans/2026-10-17-passive-camera-baseline.md`
- [Passive operator finish and interrupted batch review](docs/superpowers/plans/2026-10-17-passive-operator-finish.md) — `docs/superpowers/plans/2026-10-17-passive-operator-finish.md`
- [System identification and training fidelity plan](docs/superpowers/plans/2026-10-17-system-id-fidelity.md) — `docs/superpowers/plans/2026-10-17-system-id-fidelity.md`
- [Reproducible system identification implementation plan](docs/superpowers/plans/2026-10-17-system-id-workflow.md) — `docs/superpowers/plans/2026-10-17-system-id-workflow.md`
- [Balance learning experiments implementation plan](docs/superpowers/plans/2026-10-18-balance-learning.md) — `docs/superpowers/plans/2026-10-18-balance-learning.md`
- [Swing-up and balance learning implementation plan](docs/superpowers/plans/2026-10-18-swing-learning.md) — `docs/superpowers/plans/2026-10-18-swing-learning.md`
- [Colab checkpoint recovery implementation plan](docs/superpowers/plans/2026-10-21-colab-recovery.md) — `docs/superpowers/plans/2026-10-21-colab-recovery.md`
- [Console policy operation and reliable inference implementation plan](docs/superpowers/plans/2026-10-21-console-policy.md) — `docs/superpowers/plans/2026-10-21-console-policy.md`
- [Local policy confidence cycle Implementation Plan](docs/superpowers/plans/2026-10-21-policy-confidence.md) — `docs/superpowers/plans/2026-10-21-policy-confidence.md`
- [Learned balance recovery cycle](docs/superpowers/plans/2026-10-21-policy-recovery.md) — `docs/superpowers/plans/2026-10-21-policy-recovery.md`
- [Evidence-informed simulation refresh Implementation Plan](docs/superpowers/plans/2026-10-21-simulation-refresh.md) — `docs/superpowers/plans/2026-10-21-simulation-refresh.md`
- [Short local RL experiments](docs/superpowers/specs/2026-10-17-local-rl-diagnostics-design.md) — `docs/superpowers/specs/2026-10-17-local-rl-diagnostics-design.md`
- [Local policy development cycle, 2026-10-21](docs/superpowers/specs/2026-10-21-policy-confidence.md) — `docs/superpowers/specs/2026-10-21-policy-confidence.md`
- [Evidence-informed simulation refresh, 2026-10-21](docs/superpowers/specs/2026-10-21-simulation-refresh.md) — `docs/superpowers/specs/2026-10-21-simulation-refresh.md`
- [Local swing-up and balance development](docs/swing-learning.md) — `docs/swing-learning.md`
- [Collecting the remaining system identification data](docs/system-id-campaign.md) — `docs/system-id-campaign.md`
- [Run system identification yourself](docs/system-identification-workflow.md) — `docs/system-identification-workflow.md`
- [Interactive MuJoCo simulation](docs/viewer.md) — `docs/viewer.md`
- [Persistent camera viewer](docs/vision-usage.md) — `docs/vision-usage.md`

## Experiment evidence

- [Hardware characterization and policy follow-up — 2026-10-20](evidence/balance-error-20261020/README.md) — `evidence/balance-error-20261020/README.md`
- [Bounded angle-error training pilot — 2026-10-20](evidence/balance-error-20261020/angle-error-learning/README.md) — `evidence/balance-error-20261020/angle-error-learning/README.md`
- [Saved-forecast horizon audit](evidence/balance-error-20261020/horizon-audit/README.md) — `evidence/balance-error-20261020/horizon-audit/README.md`
- [Camera, balance-launcher and identification checks — October 21](evidence/camera-id-20261021/README.md) — `evidence/camera-id-20261021/README.md`
- [Oct21 balance operator trace audit](evidence/camera-id-20261021/operator-policy/report.md) — `evidence/camera-id-20261021/operator-policy/report.md`
- [Colab runtime loss and checkpoint recovery — October 18, 2026](evidence/colab-recovery-20261018/README.md) — `evidence/colab-recovery-20261018/README.md`
- [Repeat encoder mapping and independent validation — 2026-10-21](evidence/encoder-map-repeat-20261021/README.md) — `evidence/encoder-map-repeat-20261021/README.md`
- [Post-tightening encoder and controller check — 2026-10-21](evidence/encoder-tightening-20261021/README.md) — `evidence/encoder-tightening-20261021/README.md`
- [Frozen passive friction in the training Gym](evidence/friction-gym-20261017/README.md) — `evidence/friction-gym-20261017/README.md`
- [Existing cart evidence and frozen driven replay](evidence/friction-gym-20261017/cart-dynamics/README.md) — `evidence/friction-gym-20261017/cart-dynamics/README.md`
- [Production-backend passive replay](evidence/friction-gym-20261017/production-replay/README.md) — `evidence/friction-gym-20261017/production-replay/README.md`
- [Operator batch 1: raw-data review, 2026-10-17](evidence/operator-batch1-20261017/README.md) — `evidence/operator-batch1-20261017/README.md`
- [Batch 2 passive identification and early finish](evidence/passive-batch2-20261017/README.md) — `evidence/passive-batch2-20261017/README.md`
- [Passive batch 3: completed training, interrupted validation](evidence/passive-batch3-20261017/README.md) — `evidence/passive-batch3-20261017/README.md`
- [Passive batch 5: cleaner capture, persistent model/measurement errors](evidence/passive-batch5-20261017/README.md) — `evidence/passive-batch5-20261017/README.md`
- [Batches 8 and 9 — unchanged batch-6 candidate validation](evidence/passive-batches8-9-20261017/README.md) — `evidence/passive-batches8-9-20261017/README.md`
- [Passive camera and hanging-zero collector verification](evidence/passive-camera-baseline-20261017/README.md) — `evidence/passive-camera-baseline-20261017/README.md`
- [Passive refinement implementation plan and pre-fit method](evidence/passive-refinement-20261017/METHOD.md) — `evidence/passive-refinement-20261017/METHOD.md`
- [Passive refinement — training-only selection and frozen regression](evidence/passive-refinement-20261017/README.md) — `evidence/passive-refinement-20261017/README.md`
- [Independent Phase 1 whole-change review](evidence/phase1/review.md) — `evidence/phase1/review.md`
- [Independent Phase 2 final review](evidence/phase2/review.md) — `evidence/phase2/review.md`
- [Independent live-rig pre-hardware review](evidence/phase3/independent-review.md) — `evidence/phase3/independent-review.md`
- [Hanging reference conversion: measured model contract](evidence/phase3/retuning-20261015/calibration/README.md) — `evidence/phase3/retuning-20261015/calibration/README.md`
- [Slow manual angle-map assessment, 2026-10-15](evidence/phase3/retuning-20261015/calibration/manual-angle-map-assessment.md) — `evidence/phase3/retuning-20261015/calibration/manual-angle-map-assessment.md`
- [Four stopped/resting micro-motion screens, 2026-10-15](evidence/phase3/retuning-20261015/calibration/micro-motion-screens/README.md) — `evidence/phase3/retuning-20261015/calibration/micro-motion-screens/README.md`
- [Natural-upright 351: camera-relative map feasibility](evidence/phase3/retuning-20261015/calibration/natural351-camera-map/README.md) — `evidence/phase3/retuning-20261015/calibration/natural351-camera-map/README.md`
- [Native-count acquisition without reflashing or changing reference 370](evidence/phase3/retuning-20261015/calibration/state-acquisition-proposal.md) — `evidence/phase3/retuning-20261015/calibration/state-acquisition-proposal.md`
- [Native board-time bandwidth comparison](evidence/phase3/retuning-20261015/higher-jerk/bandwidth-analysis/README.md) — `evidence/phase3/retuning-20261015/higher-jerk/bandwidth-analysis/README.md`
- [Offline jerk comparison](evidence/phase3/retuning-20261015/higher-jerk/jerk-analysis/README.md) — `evidence/phase3/retuning-20261015/higher-jerk/jerk-analysis/README.md`
- [Q controller and rail-envelope evidence](evidence/phase3/retuning-20261015/measured-rail/q-envelope-findings.md) — `evidence/phase3/retuning-20261015/measured-rail/q-envelope-findings.md`
- [Recorded upright shadow demonstration](evidence/phase3/retuning-20261015/sensing/README.md) — `evidence/phase3/retuning-20261015/sensing/README.md`
- [Sensing investigation, 15 October 2026](evidence/phase3/retuning-20261015/sensor-disagreement/README.md) — `evidence/phase3/retuning-20261015/sensor-disagreement/README.md`
- [Slow manual angle-map assessment, 2026-10-15](evidence/phase3/retuning-20261015/sensor-disagreement/manual-angle-map-assessment.md) — `evidence/phase3/retuning-20261015/sensor-disagreement/manual-angle-map-assessment.md`
- [Raw camera / encoder geometry comparison at direct reference370](evidence/phase3/retuning-20261015/sensor-disagreement/upright370-camera-comparison.md) — `evidence/phase3/retuning-20261015/sensor-disagreement/upright370-camera-comparison.md`
- [Independent corrected-upright factorial assessment](evidence/phase3/retuning-20261015/sensor-disagreement/upright370-independent-summary.md) — `evidence/phase3/retuning-20261015/sensor-disagreement/upright370-independent-summary.md`
- [Low-amplitude executor characterization assessment](evidence/phase4/executor-assessment.md) — `evidence/phase4/executor-assessment.md`
- [Larger executor characterization: physical model remains unaccepted](evidence/phase4/executor4-assessment.md) — `evidence/phase4/executor4-assessment.md`
- [Next identification trials](evidence/phase4/next-excitation-protocol.md) — `evidence/phase4/next-excitation-protocol.md`
- [Local development checks, 2026-10-16](evidence/phase4/paused-20261016/README.md) — `evidence/phase4/paused-20261016/README.md`
- [Phase 5 policy evidence](evidence/phase5/README.md) — `evidence/phase5/README.md`
- [Phase 5 host controller and RL report](evidence/phase5/report.md) — `evidence/phase5/report.md`
- [Independent portal / queue / worker review](evidence/phase6/independent-review.md) — `evidence/phase6/independent-review.md`
- [Policy confidence experiments — 21 October 2026](evidence/policy-confidence-20261021/EXPERIMENTS.md) — `evidence/policy-confidence-20261021/EXPERIMENTS.md`
- [Final verification and review](evidence/policy-confidence-20261021/FINAL-REVIEW.md) — `evidence/policy-confidence-20261021/FINAL-REVIEW.md`
- [Short balance hardware iterations](evidence/policy-confidence-20261021/hardware/README.md) — `evidence/policy-confidence-20261021/hardware/README.md`
- [Policy HOME repeatability fix](evidence/policy-rail-repeatability-20261021/README.md) — `evidence/policy-rail-repeatability-20261021/README.md`
- [Filtered BAL foundation → combined swing-up and balance](evidence/policy-recovery-20261021/combined-next/README.md) — `evidence/policy-recovery-20261021/combined-next/README.md`
- [evidence/policy-recovery-20261021/console-launcher/README.md](evidence/policy-recovery-20261021/console-launcher/README.md) — `evidence/policy-recovery-20261021/console-launcher/README.md`
- [evidence/policy-recovery-20261021/hardware-balance/report.md](evidence/policy-recovery-20261021/hardware-balance/report.md) — `evidence/policy-recovery-20261021/hardware-balance/report.md`
- [Colab recovery and operator policy comparison](evidence/policy-recovery-20261021/recovery-20261021/README.md) — `evidence/policy-recovery-20261021/recovery-20261021/README.md`
- [Disappeared Colab training session — 21 October 2026](evidence/policy-recovery-20261021/recovery-20261021/diagnosis/diagnosis.md) — `evidence/policy-recovery-20261021/recovery-20261021/diagnosis/diagnosis.md`
- [Recovered combined PPO actors](evidence/policy-recovery-20261021/recovery-20261021/policy/README.md) — `evidence/policy-recovery-20261021/recovery-20261021/policy/README.md`
- [evidence/policy-recovery-20261021/transfer-audit/parameter-summary.md](evidence/policy-recovery-20261021/transfer-audit/parameter-summary.md) — `evidence/policy-recovery-20261021/transfer-audit/parameter-summary.md`
- [evidence/policy-recovery-20261021/transfer-audit/reference450-native/report.md](evidence/policy-recovery-20261021/transfer-audit/reference450-native/report.md) — `evidence/policy-recovery-20261021/transfer-audit/reference450-native/report.md`
- [evidence/policy-recovery-20261021/transfer-audit/report.md](evidence/policy-recovery-20261021/transfer-audit/report.md) — `evidence/policy-recovery-20261021/transfer-audit/report.md`
- [Explicit learned swing-up through the console](evidence/policy-swingup-console-20261021/README.md) — `evidence/policy-swingup-console-20261021/README.md`
- [Python feedback commissioning and identification — 2026-10-16](evidence/python-control-id-20261016/README.md) — `evidence/python-control-id-20261016/README.md`
- [Characterization analysis: both identification fits rejected](evidence/python-control-id-20261016/characterization/analysis-report.md) — `evidence/python-control-id-20261016/characterization/analysis-report.md`
- [Bounded characterization harness — prepared, not run on hardware](evidence/python-control-id-20261016/characterization/report.md) — `evidence/python-control-id-20261016/characterization/report.md`
- [Bounded observation-gap validation — 2026-10-16](evidence/python-control-id-20261016/gap-validation/README.md) — `evidence/python-control-id-20261016/gap-validation/README.md`
- [Native-run identification: rejected](evidence/python-control-id-20261016/native-identification/report.md) — `evidence/python-control-id-20261016/native-identification/report.md`
- [Python AUTO capture loss and cadence audit — 2026-10-16](evidence/python-control-id-20261016/reliability-audit/report.md) — `evidence/python-control-id-20261016/reliability-audit/report.md`
- [Saved timing analysis](evidence/python-control-id-20261016/timing-audit/README.md) — `evidence/python-control-id-20261016/timing-audit/README.md`
- [Isolated-CPU AUTO action expiry — 2026-10-16](evidence/python-control-id-20261016/timing-audit/auto-1792181042331498776-report.md) — `evidence/python-control-id-20261016/timing-audit/auto-1792181042331498776-report.md`
- [Disabled CPU-placement comparison](evidence/python-control-id-20261016/timing-audit/cpu-placement-report.md) — `evidence/python-control-id-20261016/timing-audit/cpu-placement-report.md`
- [Logger/mirror and zero-demand timing diagnosis — 2026-10-16](evidence/python-control-id-20261016/timing-audit/report.md) — `evidence/python-control-id-20261016/timing-audit/report.md`
- [evidence/python-control-id-20261016/verification/final-code-review.md](evidence/python-control-id-20261016/verification/final-code-review.md) — `evidence/python-control-id-20261016/verification/final-code-review.md`
- [evidence/python-control-id-20261016/verification/legacy-budget-fixture-review.md](evidence/python-control-id-20261016/verification/legacy-budget-fixture-review.md) — `evidence/python-control-id-20261016/verification/legacy-budget-fixture-review.md`
- [evidence/python-control-id-20261016/verification/rollover-fixture-review.md](evidence/python-control-id-20261016/verification/rollover-fixture-review.md) — `evidence/python-control-id-20261016/verification/rollover-fixture-review.md`
- [Vision audit — 2026-10-16](evidence/python-control-id-20261016/vision-audit/README.md) — `evidence/python-control-id-20261016/vision-audit/README.md`
- [Local balance learning — October 18, 2026](evidence/rl-balance-20261018/README.md) — `evidence/rl-balance-20261018/README.md`
- [Local RL development screen — 2026-10-17](evidence/rl-diagnostics-20261017/README.md) — `evidence/rl-diagnostics-20261017/README.md`
- [Cartpole v2](evidence/rl-diagnostics-20261017/runtime-supplements/README.md) — `evidence/rl-diagnostics-20261017/runtime-supplements/README.md`
- [System identification and multimodal RL readiness, 2026-10-17](evidence/rl-readiness-20261017/README.md) — `evidence/rl-readiness-20261017/README.md`
- [Swing-up learning and offline transfer checks — 2026-10-18](evidence/rl-swing-20261018/README.md) — `evidence/rl-swing-20261018/README.md`
- [Full-task robust swing pilot — 2026-10-20](evidence/robust-swing-20261020/README.md) — `evidence/robust-swing-20261020/README.md`
- [Simulation refresh, 2026-10-21](evidence/simulation-refresh-20261021/README.md) — `evidence/simulation-refresh-20261021/README.md`
- [Native swing-up recovery and encoder checks — 2026-10-21](evidence/swingup-resonance-20261021/README.md) — `evidence/swingup-resonance-20261021/README.md`
- [System identification checkpoint — 2026-10-16](evidence/system-id-20261016/README.md) — `evidence/system-id-20261016/README.md`
- [Offline identification preparation](evidence/system-id-20261016/analysis/README.md) — `evidence/system-id-20261016/analysis/README.md`
- [Independent passive heldout review — 2026-10-16](evidence/system-id-20261016/analysis/heldout/independent-review.md) — `evidence/system-id-20261016/analysis/heldout/independent-review.md`
- [Independent passive heldout result, 2026-10-16](evidence/system-id-20261016/analysis/heldout/manual-ringdown-heldout-01-report.md) — `evidence/system-id-20261016/analysis/heldout/manual-ringdown-heldout-01-report.md`
- [Manual free-decay training freeze, 2026-10-16](evidence/system-id-20261016/analysis/manual-ringdown-train-02-report.md) — `evidence/system-id-20261016/analysis/manual-ringdown-train-02-report.md`
- [evidence/system-id-20261016/camera-id-measurement-notes.md](evidence/system-id-20261016/camera-id-measurement-notes.md) — `evidence/system-id-20261016/camera-id-measurement-notes.md`
- [Rig identification and MuJoCo update plan — 2026-10-16](evidence/system-id-20261016/plan.md) — `evidence/system-id-20261016/plan.md`
- [evidence/system-id-20261016/verification/passive-id-independent-review.md](evidence/system-id-20261016/verification/passive-id-independent-review.md) — `evidence/system-id-20261016/verification/passive-id-independent-review.md`
- [System identification — October 17, 2026](evidence/system-id-20261017/README.md) — `evidence/system-id-20261017/README.md`
- [Camera pixels versus counted cart motion](evidence/system-id-20261017/analysis/camera-step-training/README.md) — `evidence/system-id-20261017/analysis/camera-step-training/README.md`
- [New manual releases: frozen Oct16 model assessment](evidence/system-id-20261017/analysis/manual-repeatability/README.md) — `evidence/system-id-20261017/analysis/manual-repeatability/README.md`
- [Analyze independently collected short pulses](evidence/system-id-20261017/tools/README.md) — `evidence/system-id-20261017/tools/README.md`
- [Acceleration wire underflow fix — 2026-10-17](evidence/system-id-20261017/verification/action-encoding-review.md) — `evidence/system-id-20261017/verification/action-encoding-review.md`
- [Read-only camera measurement review — 2026-10-17](evidence/system-id-20261017/verification/camera-measurement-review-20261017.md) — `evidence/system-id-20261017/verification/camera-measurement-review-20261017.md`
- [Pulse batch independent review — 2026-10-17](evidence/system-id-20261017/verification/pulse-batch-independent-review-20261017.md) — `evidence/system-id-20261017/verification/pulse-batch-independent-review-20261017.md`
- [Independent system-ID CLI review — 2026-10-17](evidence/system-id-20261017/verification/system-id-cli-independent-review-20261017.md) — `evidence/system-id-20261017/verification/system-id-cli-independent-review-20261017.md`
- [Operator collection, simulation contract and PPO handoff — October 17](evidence/system-id-20261017-followup/README.md) — `evidence/system-id-20261017-followup/README.md`
- [Offline input and equilibrium diagnosis — October 17, 2026](evidence/system-id-20261017-followup/diagnosis/README.md) — `evidence/system-id-20261017-followup/diagnosis/README.md`
- [Simulator, actuator and SDK observation audit](evidence/system-id-20261017-followup/sim-audit/audit.md) — `evidence/system-id-20261017-followup/sim-audit/audit.md`
- [Independent offline PPO interface review](evidence/system-id-20261017-followup/sim-audit/ppo-independent-review.md) — `evidence/system-id-20261017-followup/sim-audit/ppo-independent-review.md`
- [Verification record](evidence/system-id-20261017-followup/sim-audit/verification.md) — `evidence/system-id-20261017-followup/sim-audit/verification.md`
- [RL/training audit — 2026-10-17](evidence/system-id-20261017-followup/training-audit/audit.md) — `evidence/system-id-20261017-followup/training-audit/audit.md`
- [Model-bound PPO implementation and synthetic verification](evidence/system-id-20261017-followup/training-audit/implementation-report.md) — `evidence/system-id-20261017-followup/training-audit/implementation-report.md`
- [October 20 live characterization and simulation evidence](evidence/system-id-20261020/README.md) — `evidence/system-id-20261020/README.md`
- [Encoder-only driven assessment, 2026-10-20](evidence/system-id-20261020/driven-combined-v1/report.md) — `evidence/system-id-20261020/driven-combined-v1/report.md`
- [Gentle driven training: conditional prediction, 2026-10-20](evidence/system-id-20261020/driven-gentle-v1/report.md) — `evidence/system-id-20261020/driven-gentle-v1/report.md`
- [October 20 local balance learning evidence](evidence/system-id-20261020/learning/README.md) — `evidence/system-id-20261020/learning/README.md`
- [Encoder-only host timing diagnosis](evidence/system-id-20261020/timing-diagnosis-v1/README.md) — `evidence/system-id-20261020/timing-diagnosis-v1/README.md`
- [GC repair and remaining external-control timing blocker](evidence/system-id-20261020/timing-gc-comparison-v2/README.md) — `evidence/system-id-20261020/timing-gc-comparison-v2/README.md`
- [GC repair and remaining external-control timing blocker](evidence/system-id-20261020/timing-gc-comparison-v3/README.md) — `evidence/system-id-20261020/timing-gc-comparison-v3/README.md`
- [Offline system-ID campaign verification, 2026-10-18](evidence/system-id-campaign-20261018/README.md) — `evidence/system-id-campaign-20261018/README.md`
- [Passive system identification — later recordings prioritized](evidence/system-id-model-review-20261017/README.md) — `evidence/system-id-model-review-20261017/README.md`

## Firmware

Portable safety/control headers and the board sketch are the authoritative implementation. Native tests exercise these headers; they cannot verify electrical reset behavior.

- [firmware/teensy_executor/cart_homing.h](firmware/teensy_executor/cart_homing.h)
- [firmware/teensy_executor/cart_mechanics.h](firmware/teensy_executor/cart_mechanics.h)
- [firmware/teensy_executor/cart_motion.h](firmware/teensy_executor/cart_motion.h)
- [firmware/teensy_executor/controller_parameters.h](firmware/teensy_executor/controller_parameters.h)
- [firmware/teensy_executor/encoder_reference.h](firmware/teensy_executor/encoder_reference.h)
- [firmware/teensy_executor/ethernet_config.h](firmware/teensy_executor/ethernet_config.h)
- [firmware/teensy_executor/ethernet_transport.h](firmware/teensy_executor/ethernet_transport.h)
- [firmware/teensy_executor/executor_core.h](firmware/teensy_executor/executor_core.h)
- [firmware/teensy_executor/model_encoder_reference.h](firmware/teensy_executor/model_encoder_reference.h)
- [firmware/teensy_executor/rail_recovery.h](firmware/teensy_executor/rail_recovery.h)
- [firmware/teensy_executor/saved_center_return.h](firmware/teensy_executor/saved_center_return.h)
- [firmware/teensy_executor/serial_frame.h](firmware/teensy_executor/serial_frame.h)
- [firmware/teensy_executor/spin_recovery.h](firmware/teensy_executor/spin_recovery.h)
- [firmware/teensy_executor/status_display.h](firmware/teensy_executor/status_display.h)
- [firmware/teensy_executor/swing_controller.h](firmware/teensy_executor/swing_controller.h)
- [firmware/teensy_executor/teensy_executor.ino](firmware/teensy_executor/teensy_executor.ino)
- [firmware/teensy_executor/teensy_reference_store.h](firmware/teensy_executor/teensy_reference_store.h)
- [firmware/teensy_executor/upright_session.h](firmware/teensy_executor/upright_session.h)

## Preserved numeric actor identities

SHA-256 below hashes the complete file bytes. An actor’s embedded canonical content hash is a different value. These are artifacts, not blanket hardware acceptance claims.

| Candidate | File SHA-256 |
|---|---|
| [balance-recovery-20261021](training/candidates/balance-recovery-20261021/actor.json) | `9e498faf5783e278b44cad6d75e720d38a9ef0800b99d0676256c6445373a850` |
| [balance-recovery-20261021-rail1mm](training/candidates/balance-recovery-20261021-rail1mm/actor.json) | `a8910fd30d1cbd3cffc887410415cd26a138b115880c5d50b940a5eb50c1b97b` |
| [combined-recovery-20261021-step000102400](training/candidates/combined-recovery-20261021-step000102400/actor.json) | `37c84e14081ad590ce2d2be9d88b41ffc7f6f676be50098d0030fac2dd504f21` |
| [combined-recovery-20261021-step000102400-rail1mm](training/candidates/combined-recovery-20261021-step000102400-rail1mm/actor.json) | `0d17c63c7b779286ab9954da8bc7cc74850f7da235fc393f35867115819dbe16` |
| [combined-recovery-20261021-step000460800](training/candidates/combined-recovery-20261021-step000460800/actor.json) | `dff5494b5057677696ffc3218c7c956c5a93ec3b5feb06cd846bd9404a6e8ca2` |
| [combined-recovery-20261021-step000460800-rail1mm](training/candidates/combined-recovery-20261021-step000460800-rail1mm/actor.json) | `f1673cd25546368fa1e18853ac6c671bcd8cc610fdb3335446214fa99b470b4b` |

## October 23 operator release additions

- [Operator launcher](src/cartpole_sdk/rig/operator.py): `cartpole` / `cartpole-console`, tested scheduling defaults, explicit overrides, no-device help/dry-run.
- [Release tools](src/cartpole_sdk/release.py) and [wrapper](scripts/cartpole-release): committed-source packaging, member hash verification, additive offline installation, activation and managed PATH wrappers.
- [Command cheat sheet](COMMAND_CHEATSHEET.md) and [complete argument reference](COMMAND_REFERENCE.md): current usage and 105 help outputs.
- [New training protocol](training/protocols/combined-operator-20261023.json): preserves the experiment and foundation weights with explicit current runtime/source bindings.
- [Working policy alias](policies/working.json) and [million-step alias](policies/1m.json): exact copies, not separate training results.
- [Million-step recovery manifest](training/candidates/combined-recovery-20261023-step001024000-rail1mm/recovery-manifest.json), [release evidence](evidence/operator-release-20261023/README.md), [training smoke summary](evidence/operator-release-20261023/training-smoke-summary.json).
