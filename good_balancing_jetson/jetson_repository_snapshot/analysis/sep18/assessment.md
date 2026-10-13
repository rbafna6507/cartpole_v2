# September 18 — data-informed simulator update and gain screening

## Recommendation

Use this as the **next controlled trial**, not established hardware tuning:

| Parameter | Recorded full-rail trial 2 | Next candidate |
|---|---:|---:|
| vmax (m/s) | 0.8 | 0.8 |
| amax_s / amax_b (m/s²) | 12 / 12 | 12 / 12 |
| jmax (m/s³) | 60 | 60 |
| ke | 8 | 8 |
| kpx | 150 | **80** |
| kdx | 4.4 | **2** |
| phase_soft (rad/s) | 0.2 | **2** |
| pw (automatic balance) | 7 | 7 |
| rail (half travel, m) | 0.15 | **0.15** |

The candidate settled in **11/18** 60-second sensitivity cases; the recorded
high-centering-gain settings settled in **0/18** under the same limits and cases.
The 18 cases are deterministic sensitivity checks, not a probability of success.
Failures remain with encoder offsets ±2°, added delay, altered tracking, and
some displaced starting positions. Do not promote these settings to proven defaults.

`phase_soft=2` makes small phase errors request less abrupt pumping;
`kpx=80` reduces how strongly cart centering competes with energy pumping.
`kdx=2` was selected with those values as a combination; this search does not
establish that reducing each gain separately improves hardware.

[Copy-ready commands](next_trial_commands.txt) stop and set parameters but do not
start motion. Manually center the cart, then issue `home` before starting a new
auto attempt. `home` only sets the cart origin. The software rail remains ±135 mm
inside the 300 mm physical travel. No firmware defaults were changed or flashed.

## What actually ran

The initial pasted lines included labels/units without `set` and were rejected.
The recorded runtime settings, captured from acknowledged replies, take precedence:

| Trial | Accel caps | Jerk | Half rail | Captures | Longest balance | Rail time |
|---|---|---|---|---|---|---|
| 1 | 14 / 14 | 70 | 0.15 m | 13 | 0.514 s | 5.2% |
| 2 | 12 / 12 | 60 | 0.15 m | 9 | 0.462 s | 14.9% |
| 3 | 12 / 12 | 60 | 0.10 m | 8 | 0.513 s | 67.9% |

All trials used vmax=.8, ke=8, kpx=150, kdx=4.4, phase_soft=.2, pw=7.
Trial 2 began near pulse x=-109 mm, so it was not a repeat of a centered start.
Trial 3 reduced normal operating travel to ±85 mm, rather than changing just a
simulation plotting boundary. No trial achieved sustained balance. User confirmed
that the simulation from which the settings were taken also did not sustain balance.

The final frozen session has 343.088 seconds of telemetry and three completed
trials. One parse error occurred on serial attachment; no continuing parse errors
were recorded. Telemetry is sampled around 25 Hz, while control samples the encoder
at 1 kHz. Cart position remains inferred from emitted pulses; slip is not measured.

## Model changes and evidence

- Simulator encoder sampling corrected from 2 ms to **1 ms**, matching the firmware.
- Added encoder-offset sensitivity without changing the true physical angle.
- Added the three measured trials, acknowledged-parameter presets, and source hashes.
- Added a recent provisional plant preset while retaining the prior calibration.
- Added valid terminal-command export to avoid rejected formatted pastes.

The recent fit uses the stopped-command interval at 105–111 s with nonlinear
pendulum dynamics and viscous/Coulomb friction. It gives effective length
**0.11872 m**, damping **0.4221/s**, Coulomb term **0.0124 rad/s²**. Effective length
is not physical arm length: the physical arm remains 125 mm.

The dynamics were kept fixed on a separate stopped-command interval at 294–301 s;
only its initial angle/rate and constant angle offset were fitted for each model.
On that interval, angle RMSE improved from **17.76°** for the prior plant to
**7.09°** for the provisional plant. Training-window RMSE was 9.46° versus 3.91°
when initial states were fitted fairly for both. This is conditional waveform
validation, not a fully independent trajectory prediction. No actual cart-position
sensor establishes whether the disabled cart remained perfectly still.

Residuals remain substantial, some later peak amplitudes increase, and the earlier
four-pose encoder calibration had a large left-horizontal discrepancy. Therefore
these estimates are provisional: do not overwrite firmware length or the previous
physical calibration, or infer motor lag/torque from this fit. Different fit windows
produce materially different friction values. Both plants and friction alternatives
are represented in the gain sensitivity checks.

## Search and limitations

`search_sep18.js` screened 360 reproducible random combinations with the original
plant. `refine_sep18.js` screened 162 combinations near promising regions. The six
best refinement candidates and recorded settings were each checked in 18 cases
for 60 seconds by `final_sep18.js` (126 final simulations). Selection uses this
sensitivity suite; the suite is not independent hardware validation.

Success requires the final five seconds continuously in BALANCE with |angle|<0.1 rad
and |physical cart x|<0.1 m. A momentary capture is not success. Actuator tracking,
encoder offset, and added lag/delay cases are assumptions, not fitted measurements.
The existing jerk, speed, rail and overspeed safeguards remain enabled. No controller
logic or physical motion limits were changed. Full results and engine hash are in
[final_validation.json](final_validation.json).

The simulator still does not reproduce the measured capture counts exactly. It
supports choosing a better next experiment; it cannot establish reliable hardware
balance while encoder geometry and actual motor tracking remain uncertain.

## Reproduce

From the repository root, `python3 analysis/analyze_sep18.py` rebuilds recorded
trials from frozen CSV/events. SciPy and NumPy are needed by `fit_sep18.py` and
`check_sep18_fit.py`; the fit scripts write diagnostic JSON. Run the three Node
search/validation scripts in the order above, then `python3 simulator175/build_data.py`
and `node simulator175/test.js`. Browser tests also exercise recording selection
and console-command export.
