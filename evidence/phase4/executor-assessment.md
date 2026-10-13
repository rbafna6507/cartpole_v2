# Low-amplitude executor characterization assessment

**No physical model is accepted or recommended.** The parent completed both
20-second runs successfully and ended each stopped, disabled and fault-free with
zero misses. Installed encoder reference 3485 remains saved and unchanged.
These records establish bounded command tracking and usable capture, while the
pendulum response is too small for the predeclared identification checks.

| Recorded property | train1 | validation1 |
|---|---:|---:|
| Samples | 4998 | 5000 |
| Duration (s) | 19.995993 | 19.996000 |
| Largest timestamp gap (s) | 0.008 | 0.004 |
| Angular span (rad) | 0.047554 | 0.039884 |
| Command acceleration standard deviation (m/s²) | 0.064076 | 0.063500 |
| Largest command acceleration magnitude (m/s²) | 0.127412 | 0.128814 |
| Step-derived cart peak magnitude (mm) | 1.3125 | 1.0875 |
| Median theta-minus-pi (rad) | -0.108913 | -0.110447 |

The input clears the 0.05 m/s² standard-deviation threshold and training supplies
56 regression windows, but angular span is below the predeclared 0.15 rad.
The unchanged-encoder fit rejects a nonpositive gravity coefficient, the zero
nuisance diagnostic, excitation and integral residuals. Training/held-out integral
NRMSE is 0.295678/0.264506 (limit 0.15). Held-out 0.5-second reinitialized prediction
RMSE is 0.050275 rad and p95 is 0.111307 rad: these two checks pass on their own,
but a quiet trajectory's small prediction error cannot make a nonphysical or
poorly excited fit valid.

A sensitivity check subtracts the fixed **pretrial** parent-reported equilibrium
`3.03 - pi = -0.111593 rad`. It never uses validation to select that offset and
never changes EEPROM. This is an uncommissioned local hanging-angle assumption,
not a proven global encoder correction: hanging and upright calibration errors
may differ. The sensitivity fit also rejects input gain outside its prior bounds,
angle/input zero mismatch, excitation and integral residuals (0.220901/0.252916).
Its rejected gain 4.786, length 0.484 m, damping 3.796/s and delay 0.010 s must not
become a physical model. A numerical full-rank nuisance regression is insufficient
when the actual angular response is this small relative to noise/model discrepancy.

Input is the sampled MCU `state.acceleration`, a commanded/profile acceleration
proxy. The same row's `demand` and `seq` belong to the **new request sent after**
that state was sampled; pairing that request with the preceding observation would
introduce timing error. PD gains 40/8 use step-derived cart state, so even a later
accepted gain/delay would remain composite effective quantities without independent
metric cart acceleration. Filtered omega is retained in the compressed source but
omitted from the canonical fit because its effective timestamp is unknown.

The tested smooth-envelope waveform matches the captured planned bounds:
training target x/v/feedforward-a peaks 1.298 mm / 0.013195 m/s / 0.123222 m/s²;
validation peaks 1.033 mm / 0.011561 m/s / 0.125003 m/s². No requested command was
clipped at the 0.25 m/s² host cap. Verify-only replay executes the waveform checks
without constructing a Rig or opening a device.

## What is needed next

Before treating another fit as physical, independently establish the magnetic
angle mapping around both hanging and upright, obtain a usable synchronized vision
angle/cart calibration or another independent cart/angle measurement, and collect
repeat passive free decays at distinct initial amplitudes. Additional copies of
this same weak response cannot resolve systematic zero/input/model discrepancy.

If future motion is authorized, choose a bounded frequency sweep or narrow-band
excitation using the observed passive period, followed by separate predetermined
held-out forcing, to produce at least 0.15 rad of **real verified pendulum response**.
Maintain the already commissioned travel/velocity/acceleration limits. Scaling the
present waveform blindly by roughly 3.2 would scale its acceleration to about
0.4 m/s² and exceed the current 0.25 m/s² guard; longer duration/frequency selection
and improved measurement should precede any amplitude change. Keep the existing
thresholds and model unchanged until those independent measurements and repeat
held-out checks pass. No further hardware action is requested or executed here.

## Reproduction and provenance

Original compressed source, exact trusted command procedure and run log are
preserved as `executor-identification-report.json.gz`,
`bounded_identification_procedure.py` and `bounded-identification.log` in this
directory. The assessment JSON includes compressed/decompressed, generator,
procedure, log and canonical row SHA256 hashes. Canonical files retain raw theta
and commanded acceleration with explicit session/run/calibration identities.

From repository root:

```sh
PYTHONPATH=src .venv/bin/python evidence/phase4/assess_executor.py \
  --source evidence/phase4/executor-identification-report.json.gz \
  --procedure evidence/phase4/bounded_identification_procedure.py \
  --log evidence/phase4/bounded-identification.log \
  --output-dir evidence/phase4
PYTHONPATH=src .venv/bin/python evidence/phase4/bounded_identification_procedure.py --verify-only
```
