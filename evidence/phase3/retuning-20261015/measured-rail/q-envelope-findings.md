# Q controller and rail-envelope evidence

The 20 s run does not demonstrate a controller that first balances for 8 s and then deteriorates. It captures on the opposite swing at 4.134 s and first enters rail braking at 5.762 s. Q1/Q2 capture at 2.676/2.624 s and remain continuously in mode 3 through the scheduled 8 s cutoff. Their observed continuous-balance lower bounds are 5.324/5.376 s. The long run has four balance episodes totaling 10.520–10.552 s, with longest continuous balance 3.940–3.948 s.

All timings below use deduplicated board `unwrapped_us`, relative to the reported motion-start packet. Each shown transition is the first packet in the new mode; the actual transition lies between it and the preceding packet, normally 4 ms earlier. All four full logs cover their requested intervals, have no health-invalid samples, and have approximately 4 ms maximum active gaps. No sample-count duration substitution is used.

## Exact long-run transitions

Mode 2 is swing, 3 balance, 5 rail braking, 6 rail return, and 14 the scheduled return-to-home. Native angle and velocity below are the first observed rail-brake states, not an inferred pre-transition state.

| Balance entry s | Last balance s | Rail brake s | Rail return s | Resume swing s | Brake entry x mm | v m/s | theta rad | omega rad/s |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 4.134 | 5.758 | 5.762 | 5.838 | 5.922 | +236.513 | +0.260 | -0.138 | +1.312 |
| 8.822 | 10.814 | 10.818 | 10.874 | 10.958 | +241.425 | +0.168 | -0.143 | +1.059 |
| 11.642 | 15.582 | 15.586 | 15.790 | 15.854 | -95.288 | -1.499 | -0.075 | +0.777 |
| 16.622 | 19.586 | 19.590 | 19.730 | 19.810 | +198.113 | +0.658 | -0.133 | -0.024 |

Initial swing begins at 0.004 s; scheduled return begins at 20.002 s. Every balance exit is rail braking. None is an angle-giveup exit: maximum native absolute angle within the four episodes is 16.61, 20.04, 26.19, and 12.48 degrees, respectively. Full states, including acceleration and demand, are retained in `q-envelope-results.json`.

## What differs and what the envelope constrains

- **Initial capture varies materially.** Q1/Q2 enter with `(theta, omega, x, v)` = `(+0.229, -2.989, +0.0714, -0.0937)` and `(+0.224, -3.086, +0.0620, -0.2345)`; the long run enters with `(-0.181, +2.761, -0.0441, +0.2123)`. These are sampled after the actual capture decision. The long run's resting raw median is 2302 versus 2305 for the shorts, but this small difference alone does not identify the cause.
- **The two short successes are not equally settled.** In the final second, Q1 native angle RMS is 0.55 degrees, demand-minus-commanded-acceleration RMS is 0.22 m/s², and average jerk is near its cap for 7.6% of intervals. Q2 remains oscillatory: 6.37 degrees, 3.97 m/s², and 79.2%. Q1/Q2 make 6/13 cart-velocity reversals over balance, with 0.779/1.350 m of total commanded travel. Their common 8 s survival endpoint hides substantial variation.
- **Long episodes 1 and 2 have positive drift plus oscillation.** Net cart motion is +279.5/+320.6 mm over 1.624/1.992 s, with 2/4 velocity reversals. Episodes 3 and 4 have 7/9 reversals, so the whole trial cannot be summarized as constant drift. Episode 3's final-second native angle RMS reaches 13.62 degrees and cart speed reaches -1.50 m/s. That explains why its rail brake begins well before the cart reaches the boundary.
- **The old envelope is a real active constraint.** Normal travel is ±245 mm (490/619.0875 = 79.15% of measured switch span). The proposed ±294 mm gives 588/619.0875 = 94.98%, approximately 49 mm extra per side. Braking stops the four recorded excursions at +244.575, +244.838, -242.625, and +244.050 mm. The last balance states' outward position plus static jerk-limited stopping distance is approximately 243.8, 244.7, 239.3, and 239.7 mm; the actual governor uses subsequent 1 kHz prospective states, so this is a diagnostic cross-check rather than a bit-exact replay.
- **Extra space does not by itself prove stable balance.** At the four last recorded outward speeds, 49 mm corresponds to only approximately 183, 273, 33, and 75 ms of travel at unchanged speed. Those are scale estimates, not predicted delays or counterfactual outcomes. The wider geometry also enters the capture forecast and speed governor, so even the early trajectory may change.

The camera remains an independent working-reference diagnostic. With the current upright anchor and fixed descriptive 19 ms lag, camera-minus-native episode medians in the long run are +3.46, +3.05, +1.30, and +3.46 degrees. Camera geometry, timing and magnetic history are still confounded; a fixed correction or gravity-truth interpretation is not justified. No camera map is promoted. Commanded cart acceleration is not an independent physical accelerometer measurement.

## Jerk 225 and next controlled measurement

C1 (`jmax=225`) first captures at 5.007 s and has only 1.512–1.520 s continuous balance before rail braking at 6.523 s. C2's summary also reports rail modes and 412 mode-3 samples; its 1.644 s sample-count estimate is not accepted here as audited board-time duration because the full C2 log was not available. Neither result supports adopting 225 over 150.

Once root verifies the wider geometry, repeat **two 20 s trials with Q (`pc1=-5`, `pc2=-6`), `jmax=150`, `pw=4.5`, `bw=30`, `leff=0.124`, and all other capture/energy settings unchanged**. Compare first capture state/direction, longest continuous mode-3 interval, scheduled-cutoff censoring, rail entry position/speed, and final-second oscillation/residuals. This isolates the envelope change before altering gains or jerk. If added space only delays the same oscillation/drift, a subsequent single-factor approach-speed comparison (for example 0.3 versus 0.2 m/s, retaining the current capture gate) is more interpretable than changing geometry, jerk and gains together. No production change or hardware action was performed for this analysis.

Reproduce offline with `OPENBLAS_NUM_THREADS=1 python3 /tmp/cartpole-retune-20261015/jerk-analysis/analyze_q_envelope.py`. The result embeds the analysis-script hash and all full-log/report/camera hashes; it also retains the prior audit's firmware/reference provenance. The four full logs use reference 351 and the same v5 jerk firmware; C1 changes jerk to 225. C2 summary source: `/tmp/cartpole-retune-20261015/cart-poles-q-jerk225-c2-result.jsonl`.
