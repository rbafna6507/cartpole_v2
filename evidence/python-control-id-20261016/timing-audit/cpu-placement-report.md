# Disabled CPU-placement comparison

The second isolated repeat completed 20 seconds with **5,001 observations and zero board gaps**, while the first isolated run had nine clustered gaps and an active host interval exceeding 20 ms. The clean repeat is useful evidence of improvement, but **does not establish reliable timing or powered-controller performance**. This audit only reads completed files. The primary operator performed and restored the temporary affinities; this analysis does not access or alter live affinities/services/hardware.

All three analyzed runs use disabled observation, zero-policy calculation, 250 Hz telemetry, 1 ms Python switch interval, logger on and mirror on. The rig threads are pinned to CPU 2. The two isolated runs temporarily exclude CPU 2 from 42 vision-process threads. The saved placement reports show all 42 original affinity sets restored identically in both runs, plus two new threads restored in the repeat, with no restoration errors or missing originals. `placement-provenance.json` preserves both reports and original-file hashes. The quiet-pole-aborted attempt `1792180147332969007` is excluded entirely.

| Measurement | Vision unrestricted | Isolated first run | Isolated repeat |
|---|---:|---:|---:|
| Run suffix | `1792180117877407679` | `1792180214148161278` | `1792180287685955032` |
| Active observations | 4,929 | 4,990 | **5,001** |
| Board gaps >6 ms | 67 | 9 | **0** |
| Gap distribution | 63×8, 3×12, 1×16 ms | 7×8, 2×12 ms | 5,000 intervals exactly 4 ms |
| Maximum long gaps in a rolling board second | **16** | **8** | **0** |
| Active wait p99 | 8.5230 ms | 5.3567 ms | 5.1058 ms |
| Active wait maximum | 25.522027 ms | **19.926222 ms** | **7.960111 ms** |
| Caller CPU during worst active wait | 0.169408 ms | 0.222720 ms | 0.181824 ms |

The repeat's largest observe-to-observe host interval is 8.387572 ms, with 0.601792 ms caller CPU, at tick 82443316→82443320. Its first newer receipt arrives 5.874450 ms after wait starts, and wait returns 2.085661 ms later. Thus even the zero-board-gap result has variable host receipt/return latency; it is not a zero-latency loop.

The recorded source catalogs differ only in `cartpole_sdk/rig/client.py`: `a74e3248e0eca53e5cbe9be59cc98377a4aa5d1c88d5884fc9a87e761888aeae` in the first isolated run versus `ec577c1cf47f95572cb5b7d03b6828af136e85e82d88f9393e36db336ffd4b6b` in the repeat. The primary identifies this as the STOP/generic-ERR attribution fix, with the corresponding harness source-pin update. The placement command records the repeat harness as `diagnose_timing_stopfix.py`. These disabled observation traces have no `step` calls or overall failure, so they do not exercise the action/error path addressed by that fix; the timing improvement is not attributed to it. The source change is nevertheless retained explicitly rather than describing the runs as byte-identical.

One clean repeat cannot erase the preceding isolated run's clustered failures, establish a worst-case scheduling bound, or validate the additional command/feedback workload. The contrast between the two isolated runs is evidence of run-to-run variability. No capture/balance claim follows from either disabled zero-policy observation.

The first isolated run's 19.926222 ms wait is **not** an end-of-run timeout. It occurs around 2.3 seconds into the 20-second run, at tick **82369870→82369874**. The board gap is just 4 ms. The entire observe-to-observe host interval is **20.649527 ms**, with 0.704512 ms caller CPU. The first newer frame is received 11.073398 ms after wait starts, followed by another 8.852824 ms before wait returns:

| Event | Host monotonic ns |
|---|---:|
| Previous observation completes, tick 82369870 | 275512339290592 |
| Wait starts | 275512339392769 |
| First newer frame received, tick 82369874 | 275512350466167 |
| Wait returns, tick 82369874 | 275512359318991 |
| Next observation completes | 275512359940119 |

The actual terminal wait is only **0.324324 ms**, has an error flag, and is followed by successful harness completion; this matches the harness's handled end-of-duration timeout. It is excluded from active-interval statistics. The unrestricted run's 25.522027 ms maximum is also active, with an 8 ms board gap and 25.922129 ms observe-to-observe host interval.

The nine long gaps in the isolated run are clustered. Eight fit in the half-open window `(now − 1 second, now]`, from board time 769.433050 to 770.345050 seconds. The third long gap occurs at tick **82369890**; the existing two-long-gaps-per-rolling-second policy budget would reject that third gap. A `max_gap_periods=3` per-gap limit alone does not make the run acceptable under the budget.

These results reinforce two distinctions:

- A reduction in total long gaps does not establish a bound on clustered gaps or worst host wall time.
- A nominal 4 ms board gap can accompany over 20 ms of host delay when receipts are delayed; board gaps alone cannot prove lease-renewal timing.

The trials do not isolate a unique scheduler, GIL, transport, lock, or reader cause. The measured caller CPU is much smaller than the delayed wall time, and the raw reader receipt is itself late. No powered test or controller-gain change is justified by calling this placement configuration reliable. Further disabled diagnosis can retain the single-variable placement comparison and instrument the reader/command path more narrowly.

`analyze_timing_v2.py` adds exact half-open rolling counts, active-interval stage statistics, and separate terminal stages to the original analyzer. The three compressed CPU-placement analysis files preserve the full window members, worst-stage timing and receipt anchors, exact settings/thread affinities, raw-input hashes, and final stage records. Raw recordings remain on the Jetson at the paths in those manifests.
