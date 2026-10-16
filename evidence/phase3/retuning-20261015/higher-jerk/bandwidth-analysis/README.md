# Native board-time bandwidth comparison

`bw20` did not show a consistent benefit. Returning to estimator bandwidth30Hz
produced the longest continuous balance episode, fewer rail-brake entries, lower
balance-angle RMS, and a lower peak commanded velocity. Three trials cannot
establish a robust optimum, but these logs do not support retaining20Hz as an
improvement. All other recorded parameters are identical: pw4.5, bal_pw4.5,
jmax150m/s³, acceleration limits25m/s², upright raw351.

| Trial | First capture after start | Mode3 duration bounds | Longest contiguous mode3 lower bound | Rail-brake entries / time |
| --- | ---: | ---: | ---: | ---: |
| bw20a | 3.534–3.538s | 0.168–0.184s | 0.092s | 3 / 0.572s |
| bw20b | 1.987–1.991s | 1.496–1.512s | 1.288s | 4 / 0.576s |
| bw30 reversal | 2.595–2.599s | 2.144–2.152s | 2.144s | 1 / 0.144s |

The earlier pw4.5/bw30 trials had1.568–1.584s and1.336–1.352s total mode3;
their longest episodes were1.328s and1.076s. This shows substantial run-to-run
variation, with bw20b comparable to earlier bw30 but bw20a much worse.

All five balance episodes in the new three trials end directly in mode5 rail
braking, not a transition back to swingup caused by exceeding the angle giveup
threshold. Their maximum native angles are19.60°,12.66°,23.82°,21.80°,14.85°.
Capture/centering and stopping margin therefore remain relevant alongside angle
tracking. Native counted x reaches0.2445m,0.24446m,0.24368m respectively. The two
bw20 trials reach the1.5m/s speed ceiling; bw30 reaches1.1813m/s.

## Jerk constraint evidence

During mode3, interval-average |jerk| is at least142.5m/s³ (95% of the150 cap)
for85.7%,73.0%,78.9% of eligible time. These fractions remain85.7%,73.4%,79.9%
when restricting to |x|<0.20m, |v|<1.2m/s and no brake latch. Most of this jerk
points toward the requested acceleration. The native acceleration cap25m/s² is
never reached; peak commanded acceleration across the active windows is
13.70,13.72,11.26m/s².

| Trial | Balance RMS demand−commanded acceleration | p95 absolute residual | Time absolute residual >4m/s² |
| --- | ---: | ---: | ---: |
| bw20a | 3.66m/s² | 6.01m/s² | 34.1% |
| bw20b | 4.67m/s² | 9.99m/s² | 25.0% |
| bw30 reversal | 3.87m/s² | 8.41m/s² | 25.9% |

This is strong evidence that the **software trajectory governor's jerk limit is
frequently active** and contributes to delayed requested acceleration. It is not
an independent measurement of motor acceleration, nor proof that increasing jerk
improves balance. Demand itself changes faster than150m/s³ for38%,61%,72% of
eligible mode3 intervals; higher jerk could also transmit estimator/control
chatter. Rail stopping, speed limits, trajectory demand, and sensing still
interact. The reported `acceleration` is the governed command, not measured
physical acceleration. No firmware or production parameters were changed here.

## Camera and source quality

Dense camera distinct sequence rates are52.41,46.14,47.37Hz, versus about14Hz in
the earlier logs. Valid angle coverage is78.3%,72.9%,78.1%; no source snapshot
is marked stale and none of the active-window sequences are duplicated. Source
host-read to observer receipt p95 is44.7,49.7,47.0ms, with maxima71.8,104.5,
69.1ms. One bw20b envelope exceeds100ms at observer receipt; stale-at-server
false does not erase this extra transport age. Maximum gaps between source
frames are63.4,91.8,50.9ms. Invalid detections remain a meaningful limitation.

The current camera working-upright anchor is-0.009445365634260372rad. No angle
shape model is applied or promoted. For descriptive camera/native mode matching
only, the previously frozen19ms effective delay and a per-session empirical
board/host receipt mapping are used; this is not exposure calibration or a change
to online SDK clock acceptance. Mode3 camera-angle RMS is19.45°,10.36°,7.31°
with9,62,91 valid frames. The short first run has little camera support. Native
mode3 time-weighted RMS is12.70°,11.08°,6.99°. Camera/native differences remain
variable and are not attributed solely to the encoder.

## Reproduction and timing rules

Run `python3 analyze.py`; optional `--root` changes the input parent and `--out`
the result path. `results.json` contains source hashes, every episode's bounds,
all native/camera metrics and previous pw4.5 comparisons. `validation.json`
records checks and hashes of the audited archived v4 motion implementation.

All native metrics use the first8 actual **unwrapped board-clock seconds** after
the report's motion-start STATE. Full Rig logs provide every available STATE;
repeated ticks are deduplicated after confirming identical raw theta. No duration
is estimated by sample count. These trials have complete8s coverage and active
native gaps of approximately4ms, healthy flags and no source fault. Mode
transitions are bracketed by adjacent telemetry states; episode lower duration
is last-minus-first mode3 timestamp and the upper duration uses neighboring
non-mode3 timestamps. Gaps above30ms would split episodes. Aggregate fractions
are duration weighted, with same-mode/no-brake intervals used for jerk evidence.
Finite differences measure average jerk over the observed4ms interval, not each
1ms control tick. Reported mode dwell totals use an explicitly named left-hold
approximation, separately from bounded episode durations.

All final reports show mode0, fault0, counted x0 and reference351.
