# Local development checks, 2026-10-16

No hardware activity. These artifacts are experimental, not commissioned models
or acceptance of physical host control.

## Identification

Training is complete eligible native control data from reference330-g1. The same
fit is assessed separately against later h1 (jerk300) and k1 (speed1). No model
coefficient, calibration offset, threshold or delay was adjusted using held-out
results. The adapter excludes disabled/noncontrol/fault intervals without joining
across them; hashes and admission counts are embedded in each report.

| Quantity | Training estimate |
|---|---:|
| Effective length | 0.15204 m |
| Composite commanded-input gain | 0.8751 |
| Viscous angular damping coefficient | 0.2781 /s |
| Effective input delay grid minimum | 0 ms |

Both reports are **rejected**. The fit's gravity-zero diagnostic is −0.48°, but
its input-zero diagnostic is −8.83°. Training integral normalized RMS is 0.189
(limit 0.15). Half-second prediction RMS is 0.895 rad on h1 and 0.879 rad on k1;
the limit is 0.08 rad. The 0 ms optimum is not evidence of zero physical latency.
The apparent asymmetry in angle-zero diagnostics can reflect sensor/actuator
model errors or closed-loop confounding; it is not a measured calibration offset.

Prediction starts with a causal angle-derived rate estimate because native
filtered omega lacks calibrated effective timestamps. Thus the forecast error
contains state-initialization error as well as dynamics error. Do not attribute
all of it to physical plant mismatch. Likewise, conditional regression standard
errors exclude correlated sensor error, calibration uncertainty and model bias.
No candidate parameters were copied into MuJoCo defaults. Cart/pole masses,
force gain, true cart acceleration and missed-step behavior remain unidentifiable
from these commanded/step-count channels alone.

Reproduce from repository root, choosing a new output path (existing evidence is
not overwritten):

```sh
uv run --extra sim python examples/identify_rig.py \
  --training 'evidence/phase3/retuning-20261015/tunable-motion/postcapture/reference330-first.tar.gz::reference330-g1-1792099465601576729/rig-1792099465632851039-3956487517.jsonl' \
  --validation 'evidence/phase3/retuning-20261015/tunable-motion/postcapture/reference330-first.tar.gz::reference330-j300-h1-1792099527041280586/rig-1792099527072622842-4181688593.jsonl' \
  --output /tmp/cartpole-id-h1.json
```

Exit code 2 means a report was written but rejected (inspect the report);
argument/input errors also report code 2 with a CLI error and no fit report.
For k1, use `late-comparisons.tar.gz::reference330-speed1-k1-1792099820902940709/rig-1792099820926986316-1213678713.jsonl`
in the same archive directory. Training remains g1.

## Python policy simulation

Complete saved profile `profiles/last-observed-20261015-full-snapshot.json`;
jerk150, effective speed1m/s, saved rail half-range0.30915001m, leff0.124.
Seed1; ten seconds per trial; ideal source=`simulation`; 1ms physics/governor.
Balance criterion: |theta|<0.15rad, |omega|<1rad/s, |x|<0.12m.

| Host mode | Rate | Longest continuous balance | Terminal fault |
|---|---:|---:|---|
| auto | 100 Hz | 7.87 s | none |
| auto | 250 Hz | 8.10 s | none |
| bal | 100 Hz | 10.00 s | none |
| bal | 250 Hz | 10.00 s | none |

The summary contains the exact first-balance times, input seed and uncompressed
trajectory SHA256 values. Each `.json.gz` preserves raw demands, governed
accelerations, state, mode, rail braking, configuration and input profile hash.
These checks verify integration with the software governor. They do not establish
robustness across initial conditions or sensor errors, Jetson timing, or physical
acceptance. The host feedback equations are not the complete native state machine.

```sh
uv run --extra sim python examples/host_cartpole.py \
  --mode auto --rate 250 --seconds 10 \
  --profile profiles/last-observed-20261015-full-snapshot.json \
  --output /tmp/cartpole-python-auto.json
```
