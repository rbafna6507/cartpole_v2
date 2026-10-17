# Operator collection, simulation contract and PPO handoff — October 17

The operator workflow now supports requested release angles/directions/repetitions, dataset roles and restraint descriptions; raw review; frozen passive-fit predictions; independent fitting gates; and immutable scoped export. Requested poses are nominal metadata, never substituted for measured angles or selected intervals. See [the operator guide](../../docs/system-identification-workflow.md).

The separate Jetson source checkout is `/home/rbafna/cartpole-v2-live/staging/operator-id-20261017`. Collection/plotting dependencies are installed; source hashes, help, and an offline plot of the earlier stopped inspection were verified. Only the stopped inspection was performed before handoff. No new powered batch, firmware upload, gain change or calibration occurred in this work. The old operator release remains available.

`RigCartpoleEnv` uses 100 Hz decisions, the 1 kHz executor governor and encoder observer, commanded cart-state channels, and shared SDK observation encoding. PPO has a self-running entry point, checkpoint/resume/evaluation, numeric SDK actor and Colab notebook. Actual synthetic training completed 64 steps and resumed to 96; these are software checks, not control-performance evidence. See [the training guide](../../docs/rl-training.md) and [training implementation evidence](training-audit/implementation-report.md).

Final whole-project verification: **1104 passed, 8 skipped, 390 subtests passed**. Neural training was additionally tested in its optional dependency environment; final implementation and independent reviewer runs each passed 25 targeted tests. Notebook code parses and source packaging installs; the Colab service itself was not run. [Commands, logs and deployment hashes](verification/report.json) preserve the limits of these checks.

## Physical identification remains open

The existing larger-release failure and equilibrium-dependent driven-fit mismatch remain. Velocity-increment reconstruction leaves training NRMSE essentially unchanged (0.252803 to 0.252802). Run-specific phase nuisance terms improve residuals while substantially changing inferred length/damping, demonstrating confounding rather than a justified calibration. Read [the diagnosis](diagnosis/README.md).

Next informative collection: repeat paired 30°/60° releases with consistent cart restraint and fixed reference/camera; retain fresh validation. For cart coupling, begin with the existing ±5 mm / 0.65 s pilot, then individually review interleaved signed 10 mm pulses at differing durations. New durations have numerical/protocol tests but were not powered on the rig in this handoff. Independent physical cart displacement and full-angle calibration remain needed for those accuracy claims. No rejected fit was promoted or used to train a physical candidate.

## Review artifacts

- [Raw physical recording review](operator-workflow/raw-review/raw-observations.png): observations only, no model selection.
- [Synthetic frozen-fit demonstration](diagnosis/synthetic-fit-review/recorded-vs-frozen-ode.png): explicitly synthetic ODE predictions, not physical measurements or MuJoCo validation.
- [Earlier physical measured-versus-MuJoCo comparison](../system-id-20261017/analysis/manual-repeatability/frozen-model-comparison.png): frozen original conclusions remain unchanged.
- [Simulation contract audit](sim-audit/audit.md), [independent current SDK comparison](diagnosis/simulation-interface-independent-review-v2.json), [PPO review](sim-audit/ppo-independent-review.md), and [collection/fit-review audit](diagnosis/operator-workflow-independent-review.json).

The plant still assumes ideal acceleration tracking until its force ceiling. Physical slip/backlash, a global encoder model, calibrated domain randomization and bounded learned-policy hardware commissioning are separate remaining tasks. Passive-down or driven acceptance is narrower than global swing-up acceptance.
