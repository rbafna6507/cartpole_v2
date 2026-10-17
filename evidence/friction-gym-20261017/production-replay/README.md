# Production-backend passive replay

`replay.py` runs the completed batch-7 recording through the actual `cartpole_sdk.sim.MujocoBackend`, with the batch-6 frozen smooth-friction coefficients and no refitting. The first 0.5 s of each annotated release initializes the trajectory using the unchanged frozen `dynamics.initial_state(history_rawq:0.5)` method. Those samples are excluded from scoring; no later measurement changes the predicted trajectory.

The numerical checks pass. This remains development evidence and does not approve the physical cart model or hardware-bound RL.

## Results

The 11 retained releases provide 17,049 scored encoder samples.

| Comparison | RMS | P95 | Maximum |
| --- | ---: | ---: | ---: |
| Production backend versus encoder | 2.662406° | 5.102229° | — |
| Frozen ODE versus encoder | 2.629404° | 5.023758° | — |
| Production backend versus frozen ODE | 0.087711° | 0.205203° | 0.287987° |

The production backend ran 68,196 fixed 1 ms physics ticks. There was no force saturation. The maximum applied cart force was 0.229661 N against the configured 20 N limit. Maximum absolute cart position, speed and acceleration were respectively 1.16e-17 m, 2.71e-18 m/s and 1.12e-16 m/s². This verifies the inverse-force coupling compensation numerically. It does not measure real actuator force or tracking.

[Recorded versus production backend and ODE](batch7/recorded-vs-production.png) plots all releases, zeroed at the recorded hanging encoder baseline. The initialization history is not plotted. Release 11 is the original partial decay and remains included.

## Physics and timestamps

Configuration uses the requested assumed pole mass 0.02275 kg, cart mass 0.35 kg, rail half-length 0.308962494 m, force limit 20 N and cart damping 0.05. The equivalent rod has `L_eff = 9.81/hypot(a,b)` and pivot inertia `I = 0.75*m*L_eff²`. Frozen viscous rate and dry-friction acceleration become `hinge_damping = I*gamma` and `hinge_coulomb_friction_nm = I*c`; the velocity scale is 0.05 rad/s. The local raw-encoder-to-physical phase is `atan2(b,a)`. This phase is not an absolute calibration.

Every physics step calls `backend.step(None)`. In this backend, an absent lease requests zero cart acceleration, and the inverse cart force compensates pendulum coupling. No cart state is pinned, no physics timestep is changed, and this harness never sets the hinge force itself. Production code supplies the dry torque.

Recorded board timestamps are converted to relative integer nanoseconds, with the maximum floating-point conversion roundoff recorded per release. Samples exactly on the 1 ms grid use the corresponding backend state. Off-grid samples interpolate the two adjacent states, without shifting the sample timestamp. There is one such sample in this recording: release 06, sample index 378 after initialization, board-relative time 107.514001 s, one microsecond after a tick. The synthetic test explicitly covers fractional sampling.

The earlier standalone single-hinge harness reported 2.658° encoder RMS and 0.0773° ODE parity RMS. It shortened per-sample integration steps to land at every observed time; this replay keeps the production 1 ms timestep fixed. The slight numerical difference does not change coefficients, initialization, annotations or scored sample coverage.

## Qualifications retained

The original frozen evaluation is source-, annotation- and freeze-bound before its full camera qualification payload is carried into `batch7/report.json.gz`. Camera consistency still fails for release 11; held poses still fail for release 02 (variation) and release 06 (camera/encoder disagreement). Absolute angle calibration and physical cart restraint remain uncertified. No qualification is waived.

The report records raw-source identity, freeze and annotation hashes, frozen method hashes, the replay script hash, production/preprocessing source hashes, package versions, numerical checks and all trajectories. `batch7/summary.json` retains the same metrics and per-release diagnostics without the long trajectory arrays. Original evidence and archived reports are unchanged.

## Reproduce

Run from the repository root and choose a new output directory. The command below uses an isolated environment and cached dependencies; remove `--offline` only if intentionally allowing package downloads on another machine.

```bash
MPLCONFIGDIR=/tmp/cartpole-production-replay-matplotlib \
uv run --offline --no-project --with numpy --with scipy==1.16.3 \
  --with mujoco==3.15.0 --with matplotlib python \
  evidence/friction-gym-20261017/production-replay/replay.py \
  --freeze evidence/system-id-model-review-20261017/candidate-freeze-latest6.json \
  --source runs/passive-batch7-original/passive-training-7/rig-1792268992424581030-2783727930.jsonl \
  --annotations evidence/system-id-model-review-20261017/batch7/training-annotations.json \
  --output runs/production-passive-replay
```

For another recording, supply its matching frozen evaluation with `--qualification-report`. Completed source and sibling collection files are required. Existing outputs are refused.

The focused conversion, timestamp interpolation, timestamp rejection and CLI checks pass:

```bash
uv run --offline --no-project --with numpy --with scipy==1.16.3 \
  --with mujoco==3.15.0 --with matplotlib --with pytest python -m pytest -q \
  evidence/friction-gym-20261017/production-replay/test_replay.py
```
