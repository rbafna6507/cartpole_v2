# Independent corrected-upright factorial assessment

The user directly held the pole upright: saved reference370. The earlier inferred270 reference is superseded; the original360 reference was close. Recent hanging positions are recorded as observations and are not calibration targets. This assessment writes only offline notes/results, with no hardware, network, production, or parameter changes.

| Design | First capture, three repeats (s) | Longest balance, three repeats (s) | Median total balance (s) |
|---|---|---|---|
| L.124, bw30 | 2.652, 2.632, 2.668 | 1.024, .944, .184 | 2.436 |
| L.164, bw30 | none, none, none | 0, 0, 0 | 0 |
| L.124, bw10 | 4.616, 4.592, 4.664 | .840, .724, .692 | 1.400 |
| L.164, bw10 | none, none, none | 0, 0, 0 | 0 |

All12 reports indicate healthy completion, zero misses/errors, and successful return. None sustained2seconds of balance. At L.124, bandwidth30 consistently captures about1.96–2.00seconds earlier. The longest-duration advantage is not repeatable: matched four-run-block differences bw30 minusbw10 are +.184,+.220,-.508seconds. Do not claim a robust bandwidth winner for sustained balance from these three repeats.

## Capture failures and rail exits

First-seven raw reports are available. L.164/bw30 reaches a closest filtered angle .379rad at1.352s, outside the .25rad gate, with cart velocity-.409m/s also outside .3m/s. One L.164/bw10 run reaches .209rad at1.352s, but omega4.052rad/s and velocity-.366m/s exceed their gates; the next reaches only.296rad. Both settle into much smaller swing excursions later, with closest-up extrema near1.4–1.5rad after4–5seconds. Thus zero capture is an actual swing/capture-state bottleneck; it does not demonstrate failure of balanced-mode feedback at L.164. The subsequent KE/catch experiment targets this distinct issue.

In available L.124 runs every observed exit from mode3 is into rail braking (mode5), rather than angle giveup. Pole angle at these exits remains within.18rad while cart velocity is outward positive .50–1.05m/s. The run1 near-up cart exit at3.608s has x+.203m,v+.604m/s,angle_hat-.174rad; run7 exits at3.576s with x+.198,v+.630,angle_hat-.096rad. Corrected-reference capture still has substantial cart stopping/control trouble. Its positive drift should not be combined with the opposite-sign drift at oldreference270.

Within-mode balance jerk exceeds135m/s³ on~75–77% of intervals atbw30 versus56–63% atbw10; demand-minus-profile acceleration RMS is3.35–3.98 versus1.62–1.96m/s². These show actuator-command/feedback conflict, but bandwidth also changes approach/capture entry, so they are not isolated sensor-noise experiments. Telemetry at250Hz cannot reconstruct all1kHz gate checks; the 180ms forecast is not independently replayed here.

## Interpretation and limits

Retain the raw-camera/encoder passive-period result~.825seconds and conditional period-equivalent length~.163m. A constant reference correction does not alter full-cycle period. This does not force the practical swing controller to work best at that length: L changes calculated energy, feedback gains, approach demand, and capture prediction together. The current data cannot distinguish all these mechanisms from passive friction/compliance.

The next prescribed hardware batch is evaluated separately: L.164/bw30 with KE4/6 ×catch_a.25/.45, plus L.124/bw30 control, all with directreference370 and fixed remaining design knobs. Larger catch_a also changes the approach-blending ramp, not merely a capture threshold. Rank longest uninterrupted balance, then capture latency; preserve zero-capture runs and variation. Do not overwrite direct upright reference from hanging rest.

Source hashes, all12 repeated metrics, first-seven raw episode entry/exit states, and numerical limitations are in `upright370-independent-summary.json`. No script/production-code edits were made for this followup.
