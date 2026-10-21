# Simulation refresh, 2026-10-21

The new profiles are runnable through the production MuJoCo/Gym, SDK observation encoder, local PPO, and headless Colab path. This refresh changes how training represents uncertain sensing; it does not claim a newly identified physical plant or a hardware-ready policy. No hardware was contacted.

## Evidence decisions

| Evidence | Decision |
|---|---|
| Frozen passive model plus later batches8/9 (47 releases, continuous RMS 3.312°) | Keep effective length 0.1603038734m, angular viscous 0.006891975/s, dry friction 1.626894312rad/s² with tanh width 0.05rad/s. |
| Latest stopped executor readback | Rail half-range 0.309074998m, observer 10Hz, jerk 150m/s³, max speed 1.5m/s and acceleration 25m/s². This is historical settings provenance; stopped fault4 and invalid homing are retained. |
| Small driven cart pulses | Preserve the unit-gain acceleration servo as an assumption; commanded velocity and counted position do not identify actual motor tracking or mass. |
| Native AUTO failures and capture mismatch | Do not promote the rejected driven fit or reverse acceleration sign. High-energy validation remains incomplete. |
| Manual mapping and independent upright/freefall | Reject the fitted encoder correction. Two hanging/upright pairs suggest about 9° discrepancy, but do not establish a universal correction. |
| User confirms only camera moved | Treat camera epochs separately. Later image-vertical errors are not evidence of encoder drift. |

Nominal physical torques inherit assumed mass/inertia; controller leff 0.124 remains distinct from the passive plant's effective length. Full provenance and source hashes are in each profile's provenance.json.

## New behavior

The simulated magnetic reading is

`theta + bias + sine*sin(theta) + cosine*(cos(theta)-1)`

before 4096-count quantization and the existing1 kHz observer. Thus angle distortion affects the estimated angular velocity too. The shape terms vanish at upright. Each coefficient is bounded to ±10° to keep the map monotone; nominal coefficients are zero. Training samples per-episode bias ±1°, sine coefficient ±4° and cosine coefficient ±5°. These deliberately chosen ranges cover plausible disagreement; they are not confidence intervals or a fitted forward model. They do not model hysteresis, coupling slip or time-varying zero drift.

Existing plant length±5%, angular damping/friction±20%, Gaussian noise0–0.003rad, telemetry delay0–5ms and command delay0–3ms remain. Limits,20 ms leases and fault behavior do not vary. Camera/fusion use their existing explicit source contract and latency/noise recipes. Magnetic distortion does not alter simulated optical truth; fusion still carries magnetic rate.

The new profile builder produces immutable raw/vision/fused bundles with all source/configuration hashes. Colab previously always selected the generic preset. It now validates, packages and executes the exact randomization.json in the chosen profile, while older profiles retain their previous behavior.

## Verification

- Full suite:1961 passed, 8 skipped, 460 subtests passed. Focused integration:61 passed. Independent review:51 passed, all three profiles reproduced byte-for-byte; no actionable findings.
- Replayed all 11 retained batch7 releases through the production MuJoCo backend without refitting:17,049 samples,2.662406° RMS/5.102229°P95 against encoder;0.087711° RMS versus frozen ODE. Camera/pose qualifications remain failed where originally failed. [Plot](passive-recorded-vs-production.png), [report](passive-summary.json).
- Two independent from-scratch PPO checks,4096 decisions each, 5 s training episodes, snapshots at 2048/4096. Both emitted complete checkpoints and numeric SDK actors. Evaluation used four disjoint pose seeds and both starts (8 episodes per run, 5 s each):0 five-second holds and0 faults for both. These prove execution, not improvement or convergence. No promising candidate was selected.
- The prepared 102400-step Colab bundle pins the custom encoder recipe and 25 s horizon. It was verified locally; no VM was allocated or cloud training started.

`training-checks.tar.gz` preserves both full smoke runs, source snapshots/checkpoints and the prepared Colab bundle. The evaluation JSONs and test logs are kept separately. SHA256SUMS pins the evidence files.

## Run it

Use the already generated `training/profiles/rl-encoder-20261021`, `rl-vision-20261021`, or `rl-fused-20261021` directories. To regenerate from exactly the preserved inputs into a new directory:

```bash
./scripts/prepare-rig-training --angle-source raw --output runs/regenerated-encoder-profile
```

Reproduce both short training checks, using a new output directory:

```bash
./evidence/simulation-refresh-20261021/run-smoke.sh runs/sim-refresh-smoke-repeat
```

For longer training and backup commands, see [the current training guide](../../docs/rl-training.md). The next learning gate remains sustained balance and then swing-up on independent starts and sensor-error corners. Long-run reward alone is insufficient.
