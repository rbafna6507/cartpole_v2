# System identification checkpoint — 2026-10-16

The hand-restrained free-decay recording produced two usable training episodes. The magnetic viscous candidate has effective length 0.160736 m and angular damping 0.463156 /s; the separate raw-camera diagnostic estimates 0.158815 m. Measured periods range from 0.805 to 0.855 s. The declared viscous+Coulomb model rejects because it estimates negative viscous damping.

**Independent physical validation is pending.** These training estimates have not changed live firmware, gains, reference 330, package defaults or sensor calibration. The fitted phase offset is a local gravity-phase nuisance parameter; it is not an established global encoder correction. Camera pivot positions are quiet where observed, but the second episode fails the preset coverage/gap check.

## Evidence and reproduction

- `analysis/manual-ringdown-train-02-report.md`: full findings and assumptions.
- `analysis/manual-ringdown-train-02-freeze.json`: exact candidate, selection, source and artifact hashes frozen before heldout collection.
- `data/manual-ringdown-train-02-columns.json.gz`: complete lossless selected-column export. Full original logs remain on the Jetson with hashes preserved in the summary.
- `analysis/manual-ringdown-train-02-selected.json.gz`: exact fitting episodes.
- `heldout-protocol.json`: independent validation acquisition procedure; motor stays disabled while the operator holds the cart.
- `ringdown_probe.py`: separately bounded cart excitation harness, verified offline only. Its first physical test remains pending.
- `verification/`: 11 passive fitter tests and 46 bounded-harness tests passed. The frozen fit and selected episodes reproduce byte-for-byte.

From the repository root:

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  evidence/system-id-20261016/analysis/analyze_manual_train_02.py \
  --input evidence/system-id-20261016/data/manual-ringdown-train-02-columns.json.gz \
  --output-dir /tmp/cartpole-passive-reproduction
```

## Opt-in MuJoCo comparison

`mujoco-passive-candidate/model-config.json` contains only effective length and mapped hinge damping for offline comparison. It loads through the existing `SimulationConfig` JSON path. Its provenance explicitly preserves assumed masses, cart damping and force authority. The surrogate's displayed rod length is not a measured physical dimension. It has no Coulomb/stiction or encoder correction component.

The mapping was checked against the existing MuJoCo backend in 12 zero-cart-acceleration cases. Instantaneous equations match to numerical precision, no force saturation occurs, and the maximum 0.5 s trajectory difference from an independent 0.25 ms RK4 calculation is 0.004342 rad. This verifies implementation equivalence only; it does not establish agreement with unseen rig measurements.

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python \
  evidence/system-id-20261016/analysis/prepare_passive_mujoco.py \
  --training-summary evidence/system-id-20261016/analysis/manual-ringdown-train-02-summary.json \
  --output /tmp/cartpole-passive-mujoco-comparison
```

The next step is the independent manual recording, evaluated without refitting these coefficients. Driven-cart input gain, delay and physical motion validation remain separate requirements before treating this as an RL plant model.
