# Logger/mirror and zero-demand timing diagnosis — 2026-10-16

The recordings show substantial time outside the policy caller's CPU accounting, including late reader receipts and delayed returns from waits. Expensive feedback arithmetic is not necessary for the failures: disabled observation with a zero-policy calculation has long gaps, and the zero-demand armed run expires an action lease after a 22.31 ms host interval.

This audit reads saved files only. It does not operate serial, command motion, change affinity, stop services, or edit SDK/firmware. All five trace dumps covered here have zero instrumentation drops, and their recomputed raw observation counts/max gaps match the harness reports. Seven local synthetic analyzer tests pass. The original report, timing-array and available JSONL paths and hashes are preserved in each result. The CPU-placement trials and clean repeat are assessed separately in `cpu-placement-report.md`.

## Disabled comparisons

These are sequential 20-second, 250 Hz, all-CPU, 1 ms Python switch-interval observations. They use the zero-policy calculation, not the feedback forecast. Background load and run order are not controlled.

| Run suffix | Logger | Mirror | Observations | Gaps >6 ms | Gap distribution | Wait p99 wall / thread CPU |
|---|---|---|---:|---:|---|---:|
| `1792179772031636973` | on | on | 4,845 | 141 | 127×8 ms, 13×12 ms, 1×16 ms | 9.556 / 0.221 ms |
| `1792179922924907108` | off | on | 4,914 | 83 | 80×8 ms, 2×12 ms, 1×16 ms | 8.344 / 0.211 ms |
| `1792179973779047271` | off | off | 4,928 | 70 | 68×8 ms, 2×12 ms | 8.269 / 0.211 ms |
| `1792180009230430865` | on | off | 4,917 | 79 | 75×8 ms, 3×12 ms, 1×16 ms | 8.550 / 0.226 ms |

The dominant measured stage in those long-gap intervals is `wait` in 139, 81, 69, and 77 cases respectively. Time outside caller CPU accounts for over half the interval in 140/141, 83/83, 69/70, and 78/79 cases. Each disabled-worker configuration has fewer gaps than the initial baseline in this sequence, but no configuration eliminates them. These are not randomized repetitions, so the differences are not isolated causal estimates of logger or mirror overhead.

The added logger-on/mirror-off run has a maximum of nine long gaps in one rolling board second. Its largest host observation interval is 14.354421 ms across a nominal 4 ms board gap, dominated by an `observe` call taking 12.870491 ms wall versus 0.550400 ms caller CPU. Removing the mirror therefore does not eliminate delayed work outside the wait stage either.

For the baseline's 16 ms board gap, tick **81938445→81938461**, the host interval is 17.866097 ms with only 0.624288 ms caller CPU. The wait consumes 17.424650 ms wall versus 0.191616 ms CPU. The first newer frame, tick 81938449, is received **13.693930 ms after wait starts**; wait then takes another **3.730720 ms** to return. The record therefore includes both late receipt and delayed return after a newer frame was received. The instrumented work does not identify whether reader scheduling, GIL contention, a lock, transport/USB buffering, or another source dominates.

Conversely, the no-log run's 16 ms board gap occurs across only a 4.168807 ms host interval. Board gaps alone do not measure how long the caller stalled: buffered board frames can catch up. Without JSONL, that run cannot establish the intermediate reader-receipt order.

## Armed zero-demand expiry

Run `timing-zero-1792179806748582658` attempts 515 policy calls before an executor `ACTION_EXPIRED` fault. The active observation span is 2.188 seconds. The analyzer excludes the separate pre-arm observation. There are 30 active observation gaps above 6 ms: 27×8 ms and 3×12 ms. All 30 are dominated by time outside caller CPU. Eighteen are dominated by wait, nine by step before/through the command record, two by a post-action-record step tail, and one by time between instrumented stages.

The decisive sequence is:

| Event | Exact host monotonic ns | Board anchor |
|---|---:|---:|
| Last timely frame receipt | 275104882758675 | 81962415 |
| A513 `step` starts | 275104883715235 | input 81962415 |
| A513 command log | 275104896549982 | observed tick 81962415, TTL 20 ms |
| A513 action-request log | 275104896758402 | expiry tick 81962435 |
| A513 `step` returns | 275104897228586 | still returns observation 81962415 |
| Wait starts | 275104897329036 | after 81962415 |
| First newer frame receipt | 275104903615159 | 81962419, still last_seq 512 |
| Next frame receipt | 275104904698122 | 81962423, still last_seq 512 |
| Wait returns | 275104905356661 | returns 81962423 |
| A513 acknowledged in telemetry | 275104906801933 | 81962427, last_seq 513 |
| A513 still last accepted | 275104907254869 | 81962431, last_seq 513 |
| A514 command log | 275104907960961 | observed tick 81962423 |
| First fault receipt | 275104909220215 | **81962435, fault 1, disabled** |
| A515 command log | 275104909918595 | observed tick 81962431 |

The step on observation 81962415 consumes **13.513351 ms wall / 1.207552 ms CPU**. Its command log appears 12.834747 ms after entry; only 0.678604 ms remains after that command record, including a 0.470184 ms post-action-record tail. The decisive delay therefore occurs **before or through sending/logging the command**, not primarily in the tail after it. The existing boundaries do not separate lock acquisition, serial write, and command-record work.

The following wait consumes **8.027625 ms wall / 0.201632 ms CPU**. Frame receipt 81962415→81962419 takes **20.856484 ms** of host time despite a 4 ms board interval. The wait returns 1.741502 ms after that first newer receipt. Across successive observed snapshots 81962415→81962423, the entire host interval is **22.314396 ms wall / 1.996928 ms caller CPU**; the board snapshots themselves are only 8 ms apart because receipt was delayed.

A513 is the last acknowledged action, and fault 1 is observed exactly at its anchored expiry tick **81962435**. A514 and A515 are logged but never acknowledged. Host command-log order versus fault receipt cannot prove which board tick physically received either request. The later generic `ERR mode` replies precede `OK STOP` replies and are consistent with late acceleration requests; they must not automatically be attributed to STOP. The raw fault state already has the driver disabled, x=0, v=0 and a=0. This log retains fault 1; subsequent recovery/readback belongs to the primary operator.

## What to investigate next

The evidence supports an unprivileged, reversible, **disabled-only** scheduling/CPU-placement comparison with identical logger/mirror options and recorded affinities/background load. It does not justify increasing action TTL or declaring the bounded observation-gap option sufficient. A caller can see a modest board gap while both reader receipt and command execution have fallen behind in host time.

If the step stall recurs, the next useful instrumentation boundary is inside the command path: separate command-lock wait, transport write, and recording, while retaining caller CPU and wall clocks. The current trace cannot uniquely assign its 12.835 ms pre-command span to any one of them. This audit proposes no production change and executes no experiment.

## Files and reproduction

- `comparison.json` contains the compact configuration/quantile comparison.
- Each `timing-*-analysis.json.gz` contains exact sequence anchors, worst-stage breakdowns, input hashes, settings/affinities, and available raw failure events.
- `analyze_timing.py` is a standalone, standard-library-only read-only analyzer; `README.md` documents its units and invocation.
- `test_analyze_timing.py` verifies schema validation, preflight exclusion, CPU/wall accounting, step-tail boundaries, wait receipt timing, and summary units.
- `verification.json` records test output and artifact hashes. Raw timing arrays and JSONL remain at their exact remote paths; they are not duplicated here.
