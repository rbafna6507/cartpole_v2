# October 20 local balance learning evidence

Development-only evidence. No accepted physical fit, robust-policy claim or hardware qualification. The agent performing these runs used no rig, SSH or network. At packaging, the parent reported unresolved hardware command-lease expiry even with cyclic GC deferred; deferral is a mitigation, not an established fix.

The frozen profile is `training/profiles/rl-encoder-20261020`: executor `bw=10`, `rail=.309000015`; passive physical coefficients remain those of the earlier exploratory model. Source, all eight profile JSON files, checkpoint and recipe hashes were validated before/after training and evaluation. The full profile and source snapshots are inside the archive. `hardware_accepted=false` throughout.

## Outputs and identity

- Full immutable run evidence: `local-balance-20261020.tar.gz`, including all six recipes/reports, all 36 checkpoints, source ZIPs, profile, commands/receipts/logs, heldout evaluations, numeric actor/parity traces, stress traces and teacher diagnostic.
- Compact evidence: JSON files beside this README; `archive-manifest.json` pins every archived file and archive SHA-256.
- Original local runs: `runs/local-balance-20261020/`.
- Selected numeric actor: `runs/local-balance-20261020/selected-sdk-parity/actor.json`. Parent copied the same bytes to `training/candidates/balance-20261020/actor.json`.
- Actor file SHA-256: `b6d1179873eadbfebe0798e7cc39c17f05cc1bf7d9983733550e26e5681e6f08`.
- Selected checkpoint SHA-256: `c5afe39e8db489d8a4d27fd0ddaa5f66e01c6da75d5229fb8db56fb8f73b21b4`.
- Model content SHA-256: `91aff4ebc7c87ba99f942a14c69ed776861e4b2d0d4fd80eacaf8c728b95e174`.
- Upfront protocol SHA-256: `5ba10edd00559f56b2c21bf93aa5269f982e68c7cf1b015722def92034ba6983`.

## Matched experiment

Six trials: teacher/scratch × optimizer seeds 3,17,29; 20,480 online decisions each, checkpoint/evaluation every 4,096; 5-second training episodes, LR 3e-6, policy std .02, equilibrium projection for both arms. Teacher gains are **x=1, v=2, angle=40, rate=2**. Each teacher receives 1,500 supervised initialization updates; online budgets match, total compute/prior knowledge do not. No dynamics randomization was added.

Fresh development poses 61000/61001, 10 seconds each. Selection was declared before training and frozen before heldout: eligible final teacher actors must pass both full sampled balance trajectories; rank smallest worst cart excursion, then tail RMS, then optimizer seed. It selected teacher seed 17. No heldout-based substitution or intermediate-checkpoint selection.

Final development holds: teacher 6/6, scratch 0/6. Initialized teachers also passed 6/6. PPO did not create the initial stabilizing behavior.

Paired heldout: all three teacher initial/final checkpoints, identical fresh poses 62000..62007, 60 seconds each. RMS is mean final-window cart RMS, not whole-trajectory RMS.

| Teacher seed | Initial → final tail RMS (mm) | Initial → final worst excursion (mm) | Final full sampled balance | Paired RMS wins |
| --- | --- | --- | --- | --- |
| 3 | 3.948 → 3.691 | 99.491 → 106.100 | 7/8 | 5/8 |
| 17, selected | 3.930 → 3.711 | 103.523 → 103.590 | 8/8 | 4/8 |
| 29 | 3.524 → 3.647 | 100.866 → 86.686 | 8/8 | 3/8 |

All initial actors passed 24/24 full sampled trajectories. Finals passed 24/24 final-window holds, but only 23/24 entire sampled trajectories: seed3/pose62004 briefly reached 1.011379 rad/s at .10 s. No simulator faults. Across 24 paired poses, RMS improved on 12 and regressed on 12. Selected mean improvement is .220mm with essentially unchanged worst excursion: no reliable general PPO benefit established.

## Numeric SDK parity and stress

The selected checkpoint was exported with existing `candidate_parity.check_candidate`, through the ordinary bounded JSON/source-hash loader. Fresh poses 63000/63001, upright+hanging, 60 seconds: 24,000 action comparisons, max raw difference `5.144450623717489e-6 m/s²`, within `1e-5`; zero rejected inputs. Both upright trajectories passed all 12,000 sampled balance states. Hanging held 0/2; this is a balance-only candidate.

Observed numeric traces pass the balance wrapper's start/runtime state limits. Peak commanded speed .132274m/s, x35.4mm, angle .042952rad, rate .430470rad/s; no rail braking. Peak raw demand1.907m/s² exceeds the wrapper's conservative default .25m/s² refusal ceiling. The default was not raised or clipped. Selected heldout truth peak speed .230616m/s; heldout reports do not retain commanded-speed observations.

Post-selection stress: all 11 unchanged `transfer_checks` scenarios, poses 64000/64001, 10 seconds, both starts, 44 episodes. Upright holds14/18: nominal, length ±5%, friction ±20%, noise .003, delay 8/2 all 2/2. Each sign of 1° angle bias failed 0/2 upright (0/4 combined), reaching approximately 294 mm. Expected delayed-command/invalid-telemetry faults were detected 8/8 in simulation. Hanging task holds 5/18, nominal 0/2; incidental successes do not qualify swing-up. Overall stress gate false; actor bytes preserved.

Stress accounting: **36,016 proposed decisions, 36,012 physically advanced decisions**. Four invalid-input terminal attempts advance no time. The original `stress-summary.json` field `actual_decisions=36012` counts advanced decisions; `final-audit.json` explicitly records both. Neither fault test establishes actual firmware STOP behavior or physical stopping distance.

Counts from actual reports/traces: 122,880 online training decisions; 72,000 development evaluation decisions; 288,000 paired heldout decisions; 24,000 numeric parity decisions. Teacher initialization adds 4,500 supervised updates. Teacher sensitivity below is separate development work.

## Exact commands and replay

Commands were run from `/Users/rbafna/projects/cartpole_v2` with `.venv/bin/python`, Python 3.11.7, gymnasium 1.4.0, MuJoCo 3.15.0, NumPy 2.4.6, SB3 2.9.0, Torch 2.14.1. Full argv, wall times and return codes are in `logs/*.receipt.json`. One CPU thread per process; original pipeline ran at most two workers concurrently.

```sh
export PYTHONPATH=/Users/rbafna/projects/cartpole_v2/src
export PYTHONDONTWRITEBYTECODE=1
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
export VECLIB_MAXIMUM_THREADS=1 NUMEXPR_NUM_THREADS=1
.venv/bin/python /private/tmp/id_balance_pipeline_20261020.py
.venv/bin/python runs/local-balance-20261020/stress_runner.py --prepare
.venv/bin/python runs/local-balance-20261020/stress_runner.py
.venv/bin/python runs/local-balance-20261020/teacher_centering.py
.venv/bin/python /private/tmp/balance_envelope_check_20261020.py
.venv/bin/python /private/tmp/balance_final_audit_20261020.py
```

The `/private/tmp` scripts are preserved byte-for-byte in the run archive (`pipeline.py`, `balance_envelope_check_20261020.py`, `balance_final_audit_20261020.py`). Scripts intentionally refuse existing output paths; use a new output directory for reproduction and record the changed driver hash. An individual training command (substitute each arm/seed; teacher only adds `--gains`) was:

```sh
.venv/bin/python examples/balance_learning.py train \
  --profile training/profiles/rl-encoder-20261020 \
  --output runs/local-balance-20261020/teacher-seed17 \
  --initialization teacher --seed 17 --steps 20480 --every 4096 \
  --seconds 5 --evaluation-seconds 10 --evaluation-seeds 61000 61001 \
  --constraint equilibrium --learning-rate .000003 --policy-std .02 \
  --imitation-updates 1500 --gains evidence/rl-balance-20261018/teacher-gains.json
.venv/bin/python examples/balance_learning.py evaluate \
  runs/local-balance-20261020/teacher-seed17 \
  --output runs/local-balance-20261020/heldout-teacher-seed17-step20480 \
  --seeds 62000 62001 62002 62003 62004 62005 62006 62007 \
  --seconds 60 --checkpoint 20480 --starts upright
```

The pipeline validates exact recipe/source/archive/checkpoint bindings before loading the selected PPO file, then calls `candidate_parity.check_candidate(model, recipe['experiment'], output, checkpoint_sha256=..., seeds=(63000,63001), seconds=60)`. It does not set acceptance fields or rewrite source hashes. Numeric export does not require Torch on the deployment host.

## Bounded hardware interface

`src/cartpole_sdk/learning/balance_hardware.py` and `scripts/run-balance-policy` reuse normal SDK admission. Default shadow, explicit `--execute`, manual centered upright preparation, fixed observed start/run envelopes, capped duration 10 seconds, STOP on loss/refusal, no calibration/fault clearing/gain writes. Start: |x|≤.015m,|commandedv|≤.025m/s, |angle|≤.07rad,|rate|≤.15rad/s. Runtime strict: |x|<.12m,|commandedv|<.25m/s, |angle|<.15rad,|rate|<1rad/s, no brake. Saved upright count is checked against the latest cached INFO before ARM and each action. CLI defers cyclic GC around Rig creation/use/close, recording helper SHA and GC policy; this does not resolve all observed lease stalls.

Example shadow command for an operator who has independently established the exact serial port and saved upright count (the variables are deliberately not inferred or set here):

```sh
scripts/run-balance-policy \
  --actor training/candidates/balance-20261020/actor.json \
  --port "$PORT" --expected-upright-raw "$UPRIGHT_RAW" \
  --development-only --duration 1 --max-acceleration .25 \
  --log-dir runs/balance-shadow-manual
```

`--execute` is the explicit arming switch; do not interpret this document as hardware readiness. This wrapper rejects a hanging start. A generic stopped shadow is a separate path for host numeric-inference timing and does not demonstrate balance. Focused local regression suite: 77 passed across balance wrapper, neural runner, sensor contract and runtime GC helper; independent review reproduced and confirmed the speed and changed-reference fixes.

## Separate teacher-centering diagnostic

After candidate selection and stress, the parent requested a small diagnostic rather than more PPO. Its protocol was saved before running five fixed observed-state linear teachers on new development poses 65000/65001: nominal and ±1° bias, 10 seconds, upright only; 30 episodes, 30,000 proposed/advanced decisions,95.8 seconds. No checkpoint optimization, artifact replacement, export or heldout reuse. Gains below are `(position,velocity,angle,rate)`.

At true vertical and zero velocity/rate, the ideal static relation is `x = -k_angle*bias/k_position`. With the actual original position gain 1, a 1° bias implies magnitude 698 mm; gain 4 gives 174.5 mm, still outside the 120 mm balance envelope; gain 8 gives 87.3 mm, leaving little transient margin. This is an approximate equilibrium argument, not a calibrated nonlinear prediction. The variants have stable continuous eigenvalues for assumed pole damping 0 and 8 s⁻¹, but some lose small-velocity linear stability at the smooth-friction derivative; the full simulation includes friction, delay, jerk and sensor quantization.

| Gains | Nominal full sampled balance | Nominal tail RMS (mm) | ±1° holds | Worst biased excursion (mm) |
| --- | --- | --- | --- | --- |
| 1,2,40,2 | 2/2 | 2.95 | 0/4 | 294.00 |
| 4,4,40,2 | 2/2 | 25.71 | 0/4 | 275.94 |
| 4,6,40,2 | 2/2 | 24.61 | 0/4 | 211.17 |
| 8,4,40,2 | 0/2 | 101.15 | 0/4 | 241.57 |
| 8,6,40,2 | 2/2 | 40.80 | 0/4 | 149.39 |

All 20 biased trials failed. Increasing centering gain alone did not resolve the failure; damping and transient costs matter. These are exploratory points, not a tuned controller or evidence of a universally impossible gain design. The complete frozen protocol, per-episode traces and all failures are in `teacher-centering-diagnostic/` inside the archive. No replacement teacher was selected.
