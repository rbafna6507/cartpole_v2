# Evidence-informed simulation refresh Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans; checkboxes record progress.

**Goal:** Ship reproducible simulation/training profiles that incorporate trustworthy measurements and expose encoder uncertainty through the actual observer.

**Architecture:** Extend existing RigObservationConfig and training randomization with a bounded upstream encoder law, keeping zero defaults and exact legacy migration. Generate pinned profiles and propagate their recipe through Colab. Keep the existing plant and executor architecture.

**Tech Stack:** Python, MuJoCo, Gymnasium, NumPy, Stable Baselines3 PPO, pytest.

**Spec:** docs/superpowers/specs/2026-10-21-simulation-refresh.md

## Global Constraints

- Offline only; preserve archive baselines, previous profiles and unrelated console edits.
- Jerk150 m/s^3, 1 kHz governor, 100 Hz policy,20 ms leases; no relaxed faults.
- Retain passive L_eff=.16030387335574306 and friction; no rejected fit promotion.
- Nominal encoder distortion zero; sampled error is engineering coverage.

## Review Focus

- Legacy complete configs load neutrally; partial new configs must fail.
- Distortion affects angle and estimated rate but never physical truth/reward.
- Camera/fusion does not bypass validity or change its source contract.
- Seeded draws preserve prior recipes and never change executor limits.
- Colab must execute the exact randomization frozen in the selected profile.

### Task1: Causal encoder uncertainty
Files: sim/rig_gym_env.py, learning/model_experiment.py, learning/training_recipe.py; tests/test_encoder_simulation.py.
Interface: three zero-default radians fields encoder_bias_rad, encoder_sin_error_rad, encoder_cos_error_rad; optional encoder randomization group with these exact keys. Each coefficient bounded ±10degrees; triangle derivative bound<1. Exact old complete config gains zero values, partial groups rejected.
- [x] Write tests for cardinal angles, native observer rate, unchanged truth, repeatability, old config migration and invalid coefficients.
- [x] Run failing tests, implement minimal behavior, rerun focused suite.

### Task2: Evidence profile and training packaging
Files: learning/evidence_profile.py, scripts/prepare-rig-training, examples/prepare_rig_training.py, new training/profiles/rl-{encoder,vision,fused}-20261021/, learning/colab_bundle.py, colab_remote.py, tests/test_evidence_profile.py and bundle tests.
Interface: builder uses preserved passive20261017 profile and latest stopped-readback; generates full model/executor/observation/prior JSON plus provenance/randomization manifest. Colab detects optional randomization.json and pins/copies/uses it. Old bundles remain supported.
- [x] Test generated profiles load and preserve physical identification scope, explicit bounds and source hashes.
- [x] Test recipe survives bundle preparation and remote argument generation; implement and run focused checks.

### Task3: Evidence and runnable training
Files: evidence/simulation-refresh-20261021/, docs/rl-training.md, docs/simulation-transfer.md.
- [x] Run same-input observer validation and existing passive/cart replay checks.
- [x] Run short independent-seed training smoke checks and held-out evaluation; preserve all failures.
- [x] Verify full suite, review changes independently, document commands and limits, commit only this task's changes.

## Execution record

User already authorized autonomous implementation and parallel offline work; proceed without another design confirmation. Reuse existing codex/live-rig-platform checkout and explicitly preserve unrelated dirty console files.


## Completion evidence

1961 tests passed, 8 skipped, 460 subtests passed; 61 focused integration tests passed.
Independent review reported no actionable findings, reproduced all three profiles,
and passed 51 focused checks. Two 4096-step PPO execution checks completed; neither
held balance in8 nominal five-second evaluation episodes. Retained unchanged
passive replay:2.662406deg RMS against 17,049 encoder samples. Details and exact
artifacts: evidence/simulation-refresh-20261021/README.md.

Ruling: model update targets sensing uncertainty and recorded geometry/settings;
latest data do not justify a new physical fit. Ruling: no cloud VM allocation or
hardware motion is needed for the requested offline update.
