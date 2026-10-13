# Larger executor characterization: physical model remains unaccepted

The independent 4x training/held-out pair completed safely according to the
parent-captured report: both final states disabled, fault 0, misses 0; final I2C
errors 0; saved reference 3485 unchanged. Source identity is
`identification-20261013T232736Z`. The larger motion improves the conditional
model considerably, but three unchanged criteria still fail. **No physical model
is recommended, commissioned or applied.**

| Recorded property | train1 | validation1 |
|---|---:|---:|
| Samples | 4998 | 4999 |
| Duration (s) | 19.996 | 19.996 |
| Largest timestamp gap (s) | 0.008 | 0.008 |
| Angular span (rad) | 0.144194 | 0.101243 |
| Command acceleration standard deviation (m/s²) | 0.256677 | 0.254283 |
| Largest command acceleration magnitude (m/s²) | 0.510422 | 0.515402 |
| Step-derived cart peak magnitude (mm) | 5.3250 | 4.2375 |
| Requested commands clipped at 0.75 m/s² | 0 | 0 |

The raw encoder fit rejects calibration/input-zero mismatch, length/gain bounds,
angular excitation and training/held-out integral residuals. Its extreme candidate
length/gain are rejected optimizer outputs, not plant estimates.

## Frozen training-pretrial sensitivity

The last 5 seconds of the **training pretrial only** contain 1250 disabled,
healthy, fault-free settled samples over 4.996 seconds. Their circular mean is
3.032681227 rad, fixing the local hanging-offset sensitivity to
`3.032681227 - pi = -0.108911426 rad`. This value is frozen before fitting and
applied identically to training and validation. No validation sample selects an
offset or parameter. Validation pretrial's own 1249 samples have circular mean
3.028073087 rad: a 0.004608-rad difference recorded only as stability evidence.

Both pretrial angle spans are 0.003068 rad, with angular rate below 0.056 rad/s.
Quantization, correlated samples, bearing friction and actual hanging geometry
limit the physical accuracy of this reference; small statistical scatter is not
a calibrated angle-accuracy bound. A local hanging offset is not independently
verified global upright/angle calibration. Raw measurements and EEPROM remain
unchanged, and the sensitivity cannot itself commission a physical correction.

Under this frozen assumption, the rejected candidate is effective length 0.163020 m,
input gain 1.049747, angular damping 2.245890/s, damping ratio 0.144758, delay 0.020 s.
The fixed candidate performs well on the separate held-out run: 39 prediction
windows, RMSE 0.020244 rad, p95 0.047007 rad and integral NRMSE 0.136953, passing
the corresponding predeclared limits. Overall acceptance still fails:

- Training angular span 0.144194 rad is below the unchanged 0.15-rad criterion.
- Training integral NRMSE 0.174254 exceeds the unchanged 0.15 limit.
- Nuisance gravity/input offset estimates 0.002353/-0.065503 rad disagree; the
  input value exceeds the unchanged 0.02-rad zero consistency limit.

Input remains the sampled MCU commanded/profile acceleration, not independent
cart acceleration. The same row's subsequently sent demand is not aligned to the
preceding angle sample and is not the fitting input. PD 40/8 feedback uses
step-derived cart state. Thus gain/delay remain composite actuator, timing and
measurement/model quantities; cart/pole masses, force gain, slip and independent
physical actuator delay cannot be inferred. Filtered omega is retained in the
source but omitted from fitting because its effective timestamp is unknown.

## Concrete next measurement

A further blind amplitude increase is not the main missing evidence. Obtain an
independently verified angular reference around hanging **and** upright, calibrated
synchronized cart/angle measurement during motion, and repeated passive free-decay
records with the cart physically fixed. These separate angle mapping/zero drift,
true cart acceleration, effective length and damping from feedback/input/model
mismatch. Repeat the stronger forcing/held-out pair only after resolving those
measurements and ensuring real angular coverage meets the unchanged threshold.
The improved candidate is useful for comparing hypotheses, but cannot replace the
existing model or become a safety/controller parameter on this evidence.

## Reproducibility

Original compressed source and exact tested procedure are preserved as
`executor4-identification-report.json.gz` and `bounded_identification4_procedure.py`.
`executor4-characterization-assessment.json` records source/decompressed JSON,
procedure, assessment-generator, canonical row and stationary-reference hashes.
`executor4-train1-rows.jsonl` and `executor4-validation1-rows.jsonl` preserve raw theta
and sampled input with explicit source, clock, reference/frame and globally
qualified run identities. No host/board alignment is inferred.

```sh
PYTHONPATH=src .venv/bin/python evidence/phase4/assess_executor4.py \
  --source evidence/phase4/executor4-identification-report.json.gz \
  --procedure evidence/phase4/bounded_identification4_procedure.py \
  --output-dir evidence/phase4
PYTHONPATH=src .venv/bin/python evidence/phase4/bounded_identification4_procedure.py --verify-only
```

The second command checks only planned waveform endpoints, derivatives and bounds;
it does not construct a Rig or access hardware. No production fit criteria changed.
