# Characterization analysis: both identification fits rejected

The pilot, training and heldout experiments completed within the recorded guards.
They provide useful software timing and commanded-motion characterization, but
**do not yield an accepted physical model**. The existing fitter and all default
acceptance gates were preserved. No model or live setting was promoted.

The frozen plan is `analysis-plan.json`; the reusable read-only implementation is
`analyze_characterization.py`. Final results are in `results/analysis-02.json`.
`analysis-01.json` preserves the initial results; the later version adds tail
resolution and homing geometry details. The primary fit reports are identical.

## Recording checks

All three runs used saved reference 330, home epoch 14, measured span 16,513
steps, `bw=10`, and 100 Hz telemetry. Every recorded action interval was exactly
10 ms in board time. All three had zero clamps, no observed active firmware
faults or deadline-miss increments, no active telemetry-drop increments, no host
policy errors, and zero dropped logger records. Raw hashes match the hardware
reports. Each action agrees with its reference trace and raw state snapshot.

| Quantity | Pilot | Training | Heldout |
|---|---:|---:|---:|
| Actions / observed duration | 2,002 / 20.01 s | 4,002 / 40.01 s | 4,002 / 40.01 s |
| Maximum counted absolute x | 3.4125 mm | 6.825 mm | 5.475 mm |
| Maximum commanded absolute v | 0.03461594 m/s | 0.06921828 m/s | 0.06128084 m/s |
| Maximum applied command absolute a | 0.3282757 m/s² | 0.6598290 m/s² | 0.6718614 m/s² |
| Excitation raw angle span | 0.093573 rad | 0.199417 rad | 0.150331 rad |
| Counted position tracking RMS, excitation only | 0.081851 mm | 0.160035 mm | 0.153613 mm |
| Maximum host policy-call gap | 14.838197 ms | 11.730210 ms | 11.691747 ms |

The pilot fails the unchanged 0.15 rad minimum angular-span gate. Training clears
that excitation gate; heldout only narrowly exceeds the same span. Good counted
tracking is not proof of physical cart tracking: position is motor step count,
and velocity/acceleration are executor command states.

## Frozen training → heldout fit

Only the 0–20 s excitation intervals enter the primary fit. It uses raw decoded
magnetic angle and MCU jerk-limited commanded acceleration. Filtered omega is
omitted. Each run retains its own identity; no interpolation or window crosses
run boundaries. Delay selection and coefficient estimation use training only.

The conditional offset is **−0.1026262615 rad**, derived from the circular mean of
51 quiet stopped training-preflight samples over 0.5 s. That mean is 3.0389663921
rad, with 0.000456162 rad circular spread. The same offset is applied unchanged
to training and heldout. No heldout zero was fitted. This down-pose assumption
is a conditional diagnostic, not an independent encoder calibration.

| Quantity | Raw zero | Conditional training hanging offset |
|---|---:|---:|
| Fit accepted | **No** | **No** |
| Effective length | 1.6190985 m | 0.17799856 m |
| Commanded-input gain | 20.500893 | 1.736196 |
| Angular damping coefficient | 5.283341 /s | 4.339309 /s |
| Selected delay | 0 ms | 0 ms |
| Training integral NRMSE, gate ≤0.15 | **0.687872** | **0.348298** |
| Heldout integral NRMSE, gate ≤0.15 | **0.507743** | **0.409809** |
| Heldout 0.5 s rollout RMSE, gate ≤0.08 rad | 0.036765 rad | 0.022767 rad |
| Heldout absolute-error p95, gate ≤0.15 rad | 0.078873 rad | 0.043747 rad |
| Training nuisance input-offset diagnostic, gate ≤0.02 rad | **−0.842949 rad** | **−0.740322 rad** |

There are 56 training weak-form windows and 39 heldout prediction windows. Both
models fail residual and angle-zero diagnostic gates; raw zero additionally
fails length, gain and damping bounds. Passing the short-horizon rollout gates
does not override these failures. The large nuisance input-offset values signal
model/calibration inconsistency and should not be interpreted as measured
physical encoder errors. Conditional correction reduces error but does not
establish that a constant angular offset explains the data.

Even a software fit that passed these gates would remain unpromoted without
independent angle validity. The command-input gain and delay combine actuator,
sensor and timing effects; they do not identify motor force or true motor delay.

## Zero-command tails

The tails were commanded zero acceleration and had exactly zero recorded applied
acceleration after 20.5 s. Residual commanded velocity remained approximately
+0.01170 mm/s for training and −0.02011 mm/s for heldout. Counted positions drifted
0.225 mm and 0.4125 mm respectively during the tails. These are not independently
verified fixed-cart observations.

After 20.5 s, training angle spans only **0.003068 rad across three distinct raw
values**, with standard deviation 0.0001471 rad. Heldout spans **0.004602 rad
across four values**. The taper left near-static, quantized readings rather than
a useful passive decay. Conditional two-coefficient passive regressions produce
nonpositive gravity and negative damping (about −2.43 /s), so no valid passive
length can be reported. Those regressions are explicitly rejected diagnostics;
small prediction error on near-static data does not make their parameters valid.

## Right-switch fault and full home

The first limit fault in `auto-1792177225658336737` is at board tick 79,384,452:
fault 5, flags 233, counted x=0.2754375 m. The installed right-switch input is
asserted, the driver is disabled, and home is invalidated. Four milliseconds
earlier the governor was already braking, with commanded v=+0.4901766 m/s and
a=−12.09225 m/s² at counted x=0.2743875 m. Deadline and telemetry-drop counters did
not increment across that transition.

The fault's counted x is 33.4875 mm below the prior reported governor rail
reference and 23.487503 mm below its software hard boundary. These are differences
in the old commanded coordinate frame, not independently measured physical
clearances. The log proves an electrical right-limit assertion and response;
it does not distinguish actual switch contact from an electrical transient.

The subsequent `physical-home-1792177518529838521` records both installed switch
contacts, completes its slow two-switch sweep, resets counted center to zero,
and finishes healthy/stopped with epoch 14 and measured span 16,513 steps. The
span changed by 11 steps from 16,502. At the configured step scale the new span
is 619.2375 mm; its geometric half is 309.61875 mm. `INFO.rail_half_m=309.1125 mm`
is the derived governor rail reference from `cart_homing.safeRail`, not exactly
the geometric half-span.

**The user manually moved the cart between the fault and full home.** That breaks
the relationship between old step counts and physical position. Neither the
subsequent coordinate shift nor changed span is direct proof of lost steps.
Successful slow homing also does not establish accurate high-speed tracking or
explain the earlier switch assertion.

## Reproduction and provenance

From the repository root, choose a fresh output filename:

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  evidence/python-control-id-20261016/characterization/analyze_characterization.py \
  --run evidence/python-control-id-20261016/hardware/runs/characterization-pilot-01 \
  --training evidence/python-control-id-20261016/hardware/runs/characterization-train-01 \
  --heldout evidence/python-control-id-20261016/hardware/runs/characterization-heldout-01 \
  --home evidence/python-control-id-20261016/hardware/runs/physical-home-1792177518529838521 \
  --right-fault evidence/python-control-id-20261016/hardware/runs/auto-1792177225658336737 \
  --output evidence/python-control-id-20261016/characterization/results/reproduction.json
```

Six local analysis regression tests passed. The script verifies frozen fitter
and adapter hashes before running and refuses identical training/heldout input.
It preserves compressed/raw input hashes, report hashes, exact local and remote
paths, configurations, admission counts, gate outcomes and source hashes.
`analysis-verification.json` records the final artifact hashes. Original raw
recordings were not modified or duplicated by this analysis. No hardware,
service, parameter, calibration, SDK or other evidence was changed.
