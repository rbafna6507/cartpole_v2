# Review of latest cart-pole runs — 2026-09-16

## Finding

The user reports smooth motor/cart motion at vmax=0.75 m/s, amax_s=amax_b=15 m/s² and jmax=50 m/s³. The 20T v7 logs show repeated upright passes and balance entries at these settings. There is no sustained balance. One firmware speed-limit fault occurs in that exact trial; this is a command-limiter problem, not evidence of a detected motor stall.

## Scope and provenance

Reviewed all seven newly available console sessions from run_20260915_202902 through run_20260916_122300: 12 completed automatic episodes. The final console session was still appending idle telemetry when read. Metrics use a snapshot of complete lines; SHA-256 values and capture times are in the companion JSON. Raw source logs were not edited. Starts are paired with firmware acknowledgements in sequence, and parameter snapshots are taken at each acknowledgement.

The three September 16 sessions identify firmware swingup-175mm-20t-v7, 80,000 steps/m, cart STEP18/DIR19, Z1 STEP25/DIR26, Z2 STEP16/DIR17, leff=0.166 m, and rail=0.150 m.

## All reviewed episodes

Lift is measured from hanging down; 180° means upright. Balance duration measures continuous BALANCE mode, not stable balance.

| Session / trial | vmax | amax_s / amax_b | jmax | Duration s | Max lift ° | Balance entries | Longest BALANCE s | Result |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| 20260915_202902 / 1 | 1 | 4 / 5 | 40.000 | 74.17 | 62.66 | 0 | 0.000 | User stopped |
| 20260915_215719 / 1 | 1 | 5 / 5 | 50.000 | 40.28 | 19.51 | 0 | 0.000 | User stopped |
| 20260915_215719 / 2 | 1 | 5 / 5 | 50.000 | 2.01 | 0.70 | 0 | 0.000 | No-response fault |
| 20260915_215822 / 1 | 1 | 5 / 5 | 50.000 | 2.00 | 0.53 | 0 | 0.000 | No-response fault |
| 20260915_215855 / 1 | 1 | 5 / 5 | 50.000 | 7.57 | 5.45 | 0 | 0.000 | User stopped |
| 20260916_122141 / 1 | 0.4 | 13.3333 / 13.3333 | 266.667 | 2.01 | 0.09 | 0 | 0.000 | No-response fault |
| 20260916_122225 / 1 | 0.4 | 13.3333 / 13.3333 | 266.667 | 23.42 | 23.11 | 0 | 0.000 | User stopped |
| 20260916_122300 / 1 | 0.75 | 20 / 20 | 266.000 | 18.01 | 179.38 | 2 | 0.184 | User stopped |
| 20260916_122300 / 2 | 0.75 | 15 / 15 | 100.000 | 44.91 | 180.00 | 4 | 0.358 | User stopped |
| 20260916_122300 / 3 | 0.75 | 15 / 15 | 50.000 | 44.73 | 179.91 | 16 | 0.245 | Speed fault |
| 20260916_122300 / 4 | 0.5 | 15 / 15 | 50.000 | 16.90 | 49.06 | 0 | 0.000 | User stopped |
| 20260916_122300 / 5 | 0.75 | 10 / 10 | 50.000 | 57.44 | 179.99 | 11 | 0.327 | User stopped |

## Preferred trial: 0.75 / 15 / 15 / 50

- Duration 44.729 s; start at inferred x=+65.58 mm, not centered. No home/recenter command is logged in the session.
- Maximum measured lift 179.908° from down; 16 balance entries; longest BALANCE segment 0.245 s. Longest continuous BALANCE segment within ±10° of upright: 0.092 s.
- Peak commanded speed 0.7511 m/s; peak commanded acceleration 8.65 m/s²; peak inferred cart excursion 134.60 mm. Speed is within 1% of the requested cap in 11.46% of active samples; acceleration never reaches 99% of its cap.
- Sampled control computation time: median 652 µs, maximum 735 µs. Largest telemetry gap within this episode: 13 ms. These sampled values do not show a gross update-rate slowdown; they cannot exclude unsampled timing jitter.
- Ends with `! motion speed limit -> FAULT`, not a no-response or rail fault. The last full-session stop was later issued by the user.
- 20T conversions: 0.75 m/s = 1125 RPM; 15 m/s² = 22,500 RPM/s; 50 m/s³ = 75,000 RPM/s². Maximum acceleration ramp takes 300 ms from zero, or 600 ms for a full sign reversal. Actual ramps can be shorter because commands do not reach the acceleration cap.

## Reproduced software speed fault

At board time 521564 ms, the last active telemetry sample gives v=−0.7411 m/s and a=−1.28 m/s². Even immediately ramping acceleration toward zero at the full 50 m/s³ jerk adds approximately a²/(2j)=0.016384 m/s of negative speed, taking the continuous prediction to −0.757484 m/s. The firmware fault threshold is |v| > 0.752 m/s.

A host reproduction using the unchanged production cart_motion::advance function, that logged state, and the strongest opposing acceleration request (+15 m/s²) crosses the threshold after 12 ms: v=−0.752560 m/s. This confirms that ramp-down must begin earlier; the fault is not a motor-stall measurement. The approximately 100 Hz telemetry need not contain the exact 1 kHz control sample that triggered the fault.

## Comparison and next work

- Reducing jmax from 100 to 50 at vmax=0.75 and amax=15 increased observed balance entries from 4 to 16 in similarly long trials, but shortened the longest BALANCE interval from 0.358 to 0.245 s. Different starting positions (+41.71 versus +65.58 mm) and uncontrolled initial states prevent attributing this solely to jerk.
- The later vmax=0.75, amax_s=amax_b=10, jmax=50 trial ran 57.436 s without a firmware fault, reached 179.994°, and entered balance 11 times (longest 0.327 s). It reached the same 8.65 m/s² peak acceleration. Increasing acceleration above 15 is not supported by these observations.
- The vmax=0.5 / amax=15 / jmax=50 trial reached only 49.06°. It also contains Z-axis velocity commands near its end, so it is not a clean cart-only comparison.
- Keep the user-observed smooth 0.75/15/15/50 setting as a documented comparison baseline. First fix speed anticipation under jerk limiting; then evaluate capture feasibility using available velocity, current acceleration, jerk ramp, and rail room. The present handoff checks requested balance acceleration against the cap but not the time needed to achieve it.
- Repeated near-upright passes establish adequate energy on these trials. Capture and stabilization remain the primary observed limitation. Do not infer a need for more speed or acceleration simply from failed capture.

## Measurement limits and changes made

Only the pendulum encoder measures motion. Cart position is inferred from pulses, and speed/acceleration are commands; physical smoothness is the user’s observation. Parameter snapshots report i2c_err=0 before the five comparative trials, not a continuous error counter. One malformed serial line occurred while idle before the preferred trial.

Saved this review, its metrics and a standalone fault reproduction. Recorded the user-observed baseline in tuning history. Firmware defaults, flash state, live console settings and the paused automation were not changed.
