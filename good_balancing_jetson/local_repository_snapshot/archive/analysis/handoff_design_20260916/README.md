# Why braking has a higher cap, and how to smooth the handoff

## What the firmware actually does

`amax_b` caps the normal BALANCE acceleration request. It is not a global motor acceleration limit. In `swingup/swingup.ino`, the common motion governor receives `brake_amax=max(amax_s,amax_b)`; automatic rail, spin, and upright-return recovery use the same larger limit. Manual jog recovery uses the separate manual limit.

In `cart_motion.h`, the requested acceleration is first clamped to the driving limit. When predicted stopping distance reaches the available rail distance, the rail override replaces that target with `-direction*brake_amax`. Acceleration still slews by at most `jmax*dt`; velocity and acceleration are not reset at capture. Acceleration inherited from a previous mode can also temporarily exceed a newly smaller driving cap while it slews down.

This is deliberate rail priority with confusing parameter semantics, rather than a missing balance clamp. Using the larger limit consistently avoids predicting a short stop and then applying weaker braking. Simply clamping the braking output to `amax_b` would invalidate that prediction. A true global cap must constrain all driving/recovery requests and the stopping calculation from the outset. Matching `amax_s` and `amax_b` achieves this with the existing settings (for normal automatic motion), without another parameter. Do not change caps in motion and expect an instantaneous, jerk-free reduction of existing acceleration.

## Correction: the log does not show acceleration exceeding the balance cap

| Configured swing / balance / jerk | Peak logged rail-recovery acceleration |
|---|---:|
| 12 / 12 / 60 | 9.748 m/s² |
| 16 / 16 / 70 | 10.500 m/s² |
| 16 / 16 / 100 | 12.500 m/s² |
| 16 / 16 / 50 | 8.900 m/s² |
| 20 / 16 / 40 | 7.960 m/s² |

These are sampled commands, not measured motion. `evidence.py` records windows, source hash, and reproducible maxima. The previous review correctly identified an allowed 20 m/s² braking cap; that was not an observed 20 m/s² braking event.

At these speed/jerk settings the reversal often finishes before reaching either acceleration cap. In the idealized zero-initial-acceleration case, stopping 0.8 m/s at jerk 40 requires 106.7 mm and peaks at only 8 m/s². At jerk 70 it requires 80.6 mm and peaks at 10.58 m/s². Raising the cap from 16 to 20 changes neither example. Lowering jerk alone increases travel during the reversal and can provoke more rail interventions.

## What makes the handoff rough

1. The gate accepts an opposing acceleration demand while forecasting at most 100 ms. The previous reproduction needs 242 ms to reach its initial balance demand, with idealized balance loss after 179 ms.
2. Rail recovery releases control once moving inward inside ±130 mm, even with substantial residual acceleration. At 275.759 s, a SWINGUP sample has inferred x=-127.38 mm, velocity +0.2429 m/s and acceleration +6.600 m/s². BALANCE follows 41 ms later, asking for the opposite acceleration. The cart is already committed to gaining inward speed.
3. The instantaneous acceleration request changes at capture. The governor bounds its slope but can spend the entire short balance attempt at maximum jerk trying to catch up. A smooth acceleration ramp is not enough if the starting state is unrecoverable.

## Proposed control design

- Shape the approach before capture: gradually bring the swing-up acceleration request toward balance demand as the pendulum approaches upright, subject to rail/speed feasibility. Preserve the existing actual acceleration and velocity.
- Accept balance only when the two requests are already close and the governed trajectory has enough time and track. Forecast the changing balance demand, jerk-limited acceleration, speed reserve and stopping room to both ends. A fixed delay/blend after capture would add lag where the arm already needs a prompt response.
- Avoid releasing rail recovery into a catch with a large residual acceleration. Account for the pendulum phase as well as cart speed/acceleration: simply waiting longer can miss the next catch opportunity.
- Keep one consistent brake envelope. Matching caps is the simplest way to make the current normal acceleration and braking ceilings unambiguous. This alone does not fix the handoff.
- Record filtered angle/rate, balance request, applied acceleration, mismatch and capture reason at transition time. Current decimated raw-angle telemetry cannot reconstruct the actual gate state.

## Offline experiment and limitations

`baseline_engine.js` snapshots the existing production simulator; `experiment.js` injects isolated candidate changes without editing firmware or the production simulator. Run `node analysis/handoff_design_20260916/experiment.js` to regenerate `screen.json`.

Nine cases per candidate: three recorded limit sets (12/12/60, 16/16/70, 20/16/40), each starting at -2°, 0°, +2° from hanging for 30 seconds. Calibrated nominal length/damping, perfect motor tracking, existing sensor quantization/differentiator. This is a development screen, not held-out hardware validation.

| Variant | Cases balanced for final ≥5 s |
|---|---:|
| Existing simulator | 0/9 |
| 300 ms governed capture forecast, 5 ms prediction steps | 1/9 |
| Forecast plus approach shaping and acceleration-request matching | 2/9 |
| Forecast plus quieter rail release | 0/9 |
| All three | 1/9 |

The shaping prototype smoothly interpolates by angle between 0.8 and 0.3 rad, on approach with rate below catch_r; capture additionally requires the remaining request difference to be at most 20 ms of available jerk. This reduces the request mismatch at a switch by construction, but does not establish reliable capture. The prototype's shaping eligibility has hard rate/direction boundaries and does not itself run a rail forecast before blending; production design must address those weaknesses. The quieter-return candidate requires |a|≤1.5 m/s² and |v|≤0.20 m/s before release. It reduced repeated rail interventions but often prevented capture. Therefore it should not be adopted as-is.

The unchanged existing `tests/swing_controller_test.cpp` also fails its first hanging-start scenario (L=0.163 m, initial tilt=-0.03 rad, 0 s stable). This failure predates these isolated prototypes; no production code was edited. The experiment cannot justify a production patch or claims of eliminating belt skipping. A better approach planner needs to pass variations in starting phase, inferred cart origin, tracking and lag before deployment.

No firmware, live settings, uploads, direction-pin code, manual-start behavior or 50° abort behavior changed in this investigation.
