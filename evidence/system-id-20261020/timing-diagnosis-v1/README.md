# Encoder-only host timing diagnosis

The collected timing shows two different failure patterns: ordinary host receipt/write jitter can exhaust a short remaining action lease, and a long Python GC pause can stop the entire control process. Neither is evidence of physical motor delay. Keep the existing **20 ms action TTL**, state freshness guards and fail-closed STOP behavior.

`report.json` binds every sealed recording and the separate GC callback file by SHA-256. It uses the existing `timing_capture.summarize_timing`; large per-action acknowledgement arrays are omitted from the summary, while the complete raw logs remain untouched. No dataset roles, failures or STOP qualifications are changed.

## Observed distributions

All values below are milliseconds. Active intervals join adjacent original healthy, enabled external-control snapshots only. Stopped and transition intervals are reported separately. Each listed active board-snapshot interval was exactly 10 ms, including the snapshots eventually delivered after a long host pause.

| Recording | Active intervals | Receipt gap P50 / P99 / max | Receipt to action-write end P50 / P99 / max | Outcome |
| --- | ---: | --- | --- | --- |
| timing-probe-01 | 502 | 10.008 / 12.506 / 14.387 | 2.189 / 5.926 / 10.460 | Completed; STOP confirmed |
| gentle-train-01 | 1,005 | 10.002 / 12.391 / 14.108 | 2.203 / 6.048 / 8.551 | Third actuator trial failed; final successful STOP report absent; last disabled snapshot retained |
| timing-cpu-separated-01 | 1,989 | 10.000 / 10.558 / 61.075 | 1.516 / 2.458 / 5.791 | Stale host telemetry; action-expiry fault subsequently received; last disabled snapshot retained |

The successful probe's **22.631 ms** maximum stopped receipt interval is not an active-control maximum. The CPU-separated recording has tighter ordinary timing, but still has a 61.075 ms gap. A short successful run or an improved P99 does not bound rare stalls. The recording names describe the collection conditions supplied by the operator; these runs alone do not isolate CPU-affinity causation.

The quiet feedback policy took approximately **0.2 ms median** in the first two recordings and **0.159 ms median** in the CPU-separated recording. Its maximum was 5.076 ms in the failed gentle run. This includes scheduling during the instrumented call and is **not the neural actor's inference cost**. Receipt-to-write-end time includes host work after `State.received_ns`; preceding board-to-host age is absent from that measurement. Do not add unrelated quantiles or interpret acknowledgement receipt bounds as a one-way delay.

## Action 241 expiry

The final third-trial sequence in `gentle-train-01` is preserved in `runs[1].fault`:

1. Action 241 used tick **444153771**, with a 20 ms lease ending at tick **444153791**.
2. Tick **444153781** reported `last_seq=241`, no fault and enabled external control. It arrived **13.219535 ms** after tick 771, although those board snapshots are 10 ms apart.
3. The host started writing action 242 **3.780878 ms** after receiving tick 781 and completed the write **5.668404 ms** after receipt. Policy execution itself took **0.216286 ms**; the write took **1.887526 ms**.
4. Tick **444153791** then reported fault **1 (`ACTION_EXPIRED`)**, disabled output and `last_seq=0`. This is exactly 20 ticks after action 241's anchor.

The host completed the action-242 write before receiving the fault frame. That does not prove the board accepted the replacement before expiry: writes and received board snapshots have different timing meanings. No physical actuator latency or calibrated board/host clock offset is inferred.

## GC probe

The separate `timing-gc-probe-01-gc.json` contains 69 generation-0 collections (maximum **0.422824 ms**), seven generation-1 collections (maximum **3.866898 ms**) and one generation-2 collection lasting **53.802061 ms**:

- Start: host monotonic **637591372078140 ns**.
- End: host monotonic **637591425880201 ns**.
- Objects collected: **0**; the traversal still consumed the elapsed time.

These callback intervals are source-bound in this report. The parent investigation matched this interval to its contemporaneous stale-host failure; this report does not substitute the earlier CPU-separated recording for that later probe's raw telemetry. The callback file and earlier CPU-separated run are distinct evidence.

The new `rig.runtime.defer_cyclic_gc()` helper defers automatic cyclic collection only for an explicitly bounded session. The outer context must contain the full `Rig` context so STOP/disconnect happen before restoring the prior GC state. The helper does not call `gc.collect()`, change thresholds or alter leases. Four focused tests cover initially enabled/disabled state, nesting, exception restoration and overlapping thread scopes. Post-change live measurements are required before claiming the failure is resolved.

## Gym stress representation

Keep measured timing evidence separate from chosen simulation assumptions:

- Preserve the existing 1 ms executor physics, 100 Hz nominal decisions and 20 ms lease. Anchor each action expiry to the observation it actually used. A delayed/batched frame must not receive a fresh timestamp or lease.
- Use a small **declared sensitivity grid**, such as telemetry-delay steps `{0, 2, 5, 8}` and command-delay steps `{0, 2, 5}`, with each step equal to 1 ms. These are stress settings, not fitted one-way delays. Add a 10+10 ms case specifically to check stale-at-arrival/expiry termination.
- Test missing actions using `step(None)` and correlated bursts. A roughly 54–61 ms host stall must cause the unchanged lease to expire; it is a fault-case test, not a demand for a policy to balance through an unavailable controller. The current fixed-delay/independent-dropout settings do not represent a correlated process stall or queued frame delivery faithfully.
- For timing-sensitive policy validation, measure the actual exported numeric actor on the target host, including the observation builder, guard checks, logging and transport path. Use bounded stopped shadow execution first; quiet timing-policy costs cannot certify a neural actor's deadline margin.
- After GC deferral, compare fresh labeled repeats under the intended runtime conditions. Retain the pre-fix failed evidence as regression cases, without fitting a high dropout probability to one observed stall or weakening any rejection threshold.

No simulator, trained actor or observation profile was changed by this analysis. No hardware or network operations were performed.

## Reproduce

```sh
MPLCONFIGDIR=/tmp/cartpole-analysis-mpl .venv/bin/python \
  evidence/system-id-20261020/tools/analyze_timing.py \
  --input runs/id-live-20261020/timing-probe-01/timing-probe-01 \
  --input runs/id-live-20261020/gentle-train-01/gentle-train-01 \
  --input runs/id-live-20261020/timing-cpu-separated-01 \
  --gc-events evidence/system-id-20261020/live/timing-gc-probe-01-gc.json \
  --output /tmp/NEW-cartpole-timing-diagnosis
```

`timing-baseline-v1` and `timing-baseline-v2` retain the earlier two-recording reports. The v2 baseline figure removes overlapping fault labels; its numerical findings are unchanged.
