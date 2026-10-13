# Phase 5 policy evidence

All files here are **local simulation evidence**. The plant is provisional and
has not been physically identified or accepted. No file here certifies hardware
swing-up, timing, safety, stopping distance or trained-policy acceptance.

The controller and learning implementation is documented in
[`docs/policies.md`](../../docs/policies.md).

- `host-rate-validation.json`: handwritten `HostRatePolicy` at 100 and 250 Hz,
  seeds 501/502/503, one hanging and one upright start per seed, 10 s horizons.
  Both rates achieved 6/6 final-second balance successes. The 100 Hz hanging
  episodes used the governor's .245 m braking margin; 250 Hz peak excursions
  were smaller (.199–.238 m). The hard trip is .250 m with the default rail.
- `reference-simulation-baseline.json`: unchanged 1 kHz `ReferencePolicy`,
  saved controller parameters, two seeds and two initial-state families. Its
  already-governed outputs go directly to unchanged `MujocoBackend`. Three of
  four trials met the final-second balance definition. Seed 501 hanging was
  still swinging at 10 s (theta 1.90663 rad, omega −10.55269 rad/s), without a
  fault. This is a separate rate/observer/control baseline, not the RL prior.
- `learned-policy.json`: CEM result and reproducible provenance, including all
  numeric weights, pretraining parameters, optimization seed, training seeds,
  candidate scores, source/model hashes and simulator/sensor assumptions.
- `training.log`: generation progress from the recorded command.
- `heldout-100hz.json`: frozen-weight comparison against the pretraining
  handwritten controller on disjoint seeds. Per-episode state and outcome
  fields are authoritative; the final report summarizes them.

The optimization split is seeds **11, 12, 13**. Handwritten characterization
seeds 501–503 are never used in CEM fitness. Frozen-weight held-out seeds are
1001–1006. Both initial-state families use randomized cart position/velocity,
pole angle and angular velocity. Training uses zero sensor transport delay and
10 ms acquisition; it does not model measured USB performance or MCU magnetic
filter dynamics. See the report for limitations and acceptance status.

The initial development training run was interrupted before producing an
artifact when review found the firmware .250 m hard trip. The retained final
training run starts from the original pretraining weights, uses the same seed,
and captures source hashes at startup under the corrected wrapper. No partial
result from the interrupted run was selected as the initializer.

## Final experiment outcome

Training reward improved from 3.597891644 to 3.706169242. Exact replay reproduced
the selected score and all saved source hashes matched. On the frozen held-out
set, reward improved 3.449923410 → 3.704015435; both the original and learned
policies succeeded in 12/12 episodes. Mean final continuous balance from hanging
improved 7.2733 → 8.4967 seconds. Some cart excursions increased, and one learned
trial still reached the governor braking margin. These are noiseless provisional
simulation results only.

See [report.md](report.md) for actual commands, per-seed comparison, verification,
and remaining acceptance. `reproducibility-check.json` records exact replay and
source-hash verification; `evaluation.log` is the CLI summary; `tests.log` records
301 passing maintained tests, five skips and 160 passing subtests.

The single-file portal submission is `learned-policy-simulation.py` (19,866 bytes),
with its own export manifest. `host250-reference-shadow.json` records the limited
real-data source/cadence check; no shadow action was transmitted. See the report
addendum and docs/policies.md for exact isolated Linux integration commands.
