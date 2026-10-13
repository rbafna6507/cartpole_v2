# Pendulum Lab — current 125 mm arm

Offline browser simulator for the 60T cart, 125 mm pendulum and 300 mm rail. Open `index.html` directly or serve the repository using `python3 -m http.server 8765 --bind 127.0.0.1`, then open `/simulator175/`.

## Current defaults

The startup preset follows v34 firmware: vmax=vmax_s=vmax_b=1.5 m/s, amax_s=amax_b=25 m/s², jmax=150 m/s³, bw=30 Hz, ke=4, kpx=40, kdx=2, pw=6, pz=0.85, pc1=-3, pc2=-4. The 60T GT2 pulley and 1/16 microsteps give 26,666.667 steps/m. The approach targets 0.3 m/s starting at 0.8 rad; capture requires angle <0.25 rad, rate <2 rad/s, speed <0.3 m/s, acceleration mismatch <=2 m/s², and a feasible 180 ms forecast. Normal operating travel remains 270 mm. This is the full-span preset in `analysis/v33_span_tuning/recommended_settings.json`; compact candidates remain experimental. Historical presets retain their recorded settings. JavaScript equations are checked against the compiled firmware headers.

- **Current firmware snapshot:** source configuration at the latest bundle build.
- **Recorded 20T:** parameters from the third automatic trial in `run_20260916_122300`: 0.75/15/15/50, firmware v7. Experiments use the current engine; this is a parameter preset, not exact historical firmware replay.
- **Historical 60T candidate:** preserved old search settings and geometry. Its old validation files describe the earlier engine and are not current validation.

Choose a scenario/input style, edit limits, and run or compare. Charts show angle, cart position, command speed, acceleration, jerk and STEP rate. Initial angular rate, cart speed and acceleration can be set under plant assumptions to reproduce a measured handoff state. Start angle is measured from hanging, except in balance recovery, where it is measured from upright. Export traces and settings before refreshing; experiments are in browser memory.

## Current geometry and evidence

The current arm is 125 mm / 11.05 g with two 5.85 g end weights (22.75 g total).
The user corrected the original 100 mm label on 2026-09-17 and identified the
pre-175 mm captures as this arm. Their refit supplies **0.124454888 m** plant
length, **0.124 m** controller length and **0.913383 s⁻¹** equivalent damping,
from 20 qualifying cycles in three runs. Balance gains and swing-up energy
use the current controller length. Current and upright presets use this model;
recorded and historical candidate presets retain 175 mm dynamics. The calibration
selector labels each capture's physical arm length. The directory name remains
`simulator175` to preserve existing links.

[125 mm provenance and fit](../pendulum_characterization/125mm_11p05g/2026-09-15/README.md).
The measured period identifies effective length, not detailed mass distribution
or motor tracking. Capture overlays reuse fitting data, not held-out validation.

## Archived 175 mm evidence

The three confirmed free-decay captures provide 33 cycles, effective length 0.165775568 m (firmware 0.166 m), and equivalent viscous damping 0.402279 s⁻¹. Physical length is 175 mm. Original calibration logs are unchanged and their hashes are checked on rebuild.

`recorded_20t_trial.json` freezes the exact 44.729-second preferred trial, including SWINGUP and BALANCE samples. It reached 179.908° lift from down, entered BALANCE 16 times, and ended with a software speed-limit fault. Longest BALANCE interval was 0.245 s. Original session snapshot hashes are retained in the file. Its points are measured angle plus pulse-derived position and commanded velocity/acceleration; this is not an independent cart-motion measurement.

`analysis/data_informed_cases.json` contains 31 observed handoff states and duration-weighted clipping statistics. `node analysis/validate_recorded.js` compares seeded recovery with archived v7 and current equations. See [v8 assessment](../analysis/v8_assessment.md) for results and limitations. The ideal model still predicts some recoveries that did not occur on hardware; no reliable physical balance claim is made.

## Model boundaries

The nonlinear acceleration-driven pendulum uses RK4 with 1 ms integration:

```
theta'' = (g sin(theta) - a cos(theta))/L - damping*omega - coulomb*tanh(omega/0.05)
```

It includes encoder quantization/sample holding, the tracking differentiator, jerk/speed/rail limiting, mean pulse counting and optional assumed tracking fraction, lag and delay. Motor torque, resonance, backlash, individual step impulses and actual missed steps are not identified. A smoother hardware run is useful user evidence but does not measure those quantities.

Replay sends the logged acceleration waveform through the selected governor/input style: it is an open-loop what-if, not a reconstruction of the measured trajectory. Calibration overlays reuse calibration data, not held-out measurements. Experiment success requires at least five final continuous seconds in BALANCE with angle <0.1 rad and physical cart position <0.1 m.

The four input styles are acceleration with jerk limiting, acceleration with instantaneous transitions, sampled velocity targets and streamed position targets. The latter two are experimental adapters, not emulations of a named driver library. STEP ceiling and geometry changes in this offline tool do not change firmware.

## Build and check

```
python3 simulator175/build_data.py
node simulator175/test.js
node analysis/validate_recorded.js
```

Optional browser test: `node simulator175/browser_test.js` with a local server running, or set `SIM_URL` to the `file://` URL of `index.html`. Playwright and Chrome are required. `NODE_PATH` and `CHROME_PATH` can locate them.

The older settling search/assessment files are retained as historical 60T experiments. Do not interpret their old pass counts as evidence for current v8 geometry and control logic.

## v22 rail recovery

Normal automatic travel is ±135 mm within the ±150 mm physical rail. At that
threshold, or earlier when predicted stopping distance requires it, automatic
control pauses until speed and acceleration are near zero, then requests an
inward return at up to 0.15 m/s and 1.5 m/s². The stop prediction reserves the
final acceleration ramp-out. Swing-up resumes inward inside ±130 mm with
|v|≤0.155 m/s, |a|≤1.5 m/s² and a cleared braking latch, without seeking center
or waiting at rest. Recovery
keeps the position origin. Timeout is 8 s; the hard fault remains ±140 mm.
The simulator records recovery phases and durations. DDS uses the firmware's
7 µs tick; its pulse ceiling is approximately 71,429 steps/s.
Historical comparisons describe their named engine revisions and limits.

## Angular-rate failsafe (v24)

The current engine trips immediately when filtered |θ̇| > 35 rad/s, brakes and
centers the cart with the existing jerk limit, then resumes swing-up once
centered/stopped and valid |θ̇| < 10 rad/s. There is no full-turn requirement,
angle gate, or dwell. Recovery modes are `spin_brake`, `spin_center`, and
`spin_wait`. Historical validation files retain their named revisions.

## Manual upright trials

Choose **Manual upright · candidate 8** or `?preset=upright`. The balance scenario now represents a manually started upright-only trial: `bal_pw=8`, ±50° fall abort, center, stop, no swing-up restart. Set `bal_pw=7` for the baseline comparison. Simulation initial states bypass the firmware's ±10° start gate so recovery can be stress-tested. See [tuning evidence and instructions](../analysis/upright_tuning.md).

## Compact swing-up comparison

The v22 results record the old engine hash; the engine has since changed to 125 mm.
Running `node analysis/compact_swingup_v22.js` now is a new geometry comparison,
not an exact reproduction of the archived 39 historical 175 mm offline trials of
speed, cart damping/centering, energy gain and phase smoothing.
[Results and limitations](../analysis/rail_recovery_v22.md). They do not change
source defaults or establish physical swing-up performance.

## September 18 hardware update

The recording selector now includes all three completed trials from
`run_20260918_103825`, with acknowledged settings and frozen source files.
The formatted initial paste was rejected: the first two trials actually used
vmax=0.8 and rail=0.15; the last trial used rail=0.1 (only ±85 mm normal operation).
Recorded settings presets preserve their measured initial angle and pulse position.
They are not promises of identical closed-loop trajectories.

The simulator's default encoder sampling is now 1 ms to match the firmware's
1 kHz sampling loop. An optional encoder-offset assumption tests angle-reference
sensitivity without changing the physical plant. The terminal-command export
uses `set NAME VALUE`, omits units, starts with `stop`, ends with `params`, and
does not start motion. It exports the selected experiment, not unsaved form edits.

A recent provisional plant fit and the gain assessment are documented in
[September 18 assessment](../analysis/sep18/assessment.md). The old, separately
calibrated plant remains available. The new fit is based on stopped-command
intervals, not independent cart-motion measurements, and is not applied to
firmware. Angle nonlinearity, actual motor tracking, and mechanical disturbance
remain unmeasured. Do not interpret an isolated simulated capture as sustained
balance; the same final-five-second criterion applies to all tested candidates.

## v28 encoder observer

Current and upright defaults use `bw=30` Hz. The observer equations match the firmware and have C++/JavaScript parity coverage across angle wrap. A quantized 1–5 Hz sine produces about 9 ms of rate phase delay, versus 28–30 ms at `bw=10`. Higher bandwidth increases noise; this does not establish hardware stability. Firmware now rejects bandwidth outside 0.1–100 Hz and resets its observer state when bandwidth changes while stopped. Historical presets keep their recorded bandwidth.
