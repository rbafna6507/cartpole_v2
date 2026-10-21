# GC repair and remaining external-control timing blocker

GC deferral removed the observed collection stall in two 25-second quiet repeats and the complete eight-trial gentle campaign. It did **not** establish reliable 100 Hz external control: the later standard training run expired an action after a long delay between state notification and the next policy-loop fetch. The firmware stopped as designed. Retain the existing 20 ms action lease and all freshness, health, position, velocity and STOP requirements. Hardware balance remains blocked on this timing problem.

`report.json` verifies each sealed input manifest and binds raw logs, reports and GC callback files by SHA-256. Raw evidence and dataset roles remain unchanged. The compact output uses `timing_capture.summarize_timing`; only its large per-action acknowledgement array is omitted. The complete source recordings remain available. `timing.png` compares active and stopped receipt intervals and shows the standard-run expiry sequence.

## Comparison

All values are milliseconds. Adjacent original snapshots are classified before filtering, preventing stopped gaps from leaking into active statistics. The active external board intervals in these recordings were exactly 10 ms. Host receipt is a timestamp immediately before state parsing; it is neither acquisition time nor policy-thread wake time.

| Recording | Role | External intervals | Receipt P99 / max | Receipt to write-end P99 / max | Outcome |
| --- | --- | ---: | --- | --- | --- |
| timing-gc-probe-01 | development | 1,972 | 10.578 / 58.037 | 2.490 / 5.888 | Stale host telemetry; subsequent action expiry; last disabled snapshot retained |
| timing-gc-deferred-01 | development | 5,004 | 10.560 / 14.135 | 2.387 / 7.396 | Two 25-second quiet trials completed; STOP confirmed |
| gentle-train-02 | training | 3,874 | 10.577 / 12.901 | 2.486 / 5.683 | All eight trials completed; STOP confirmed |
| standard-train-01 | training | 3,804 | 10.660 / 12.546 | See report | Fifth trial failed with action expiry; last disabled snapshot retained |

The gentle campaign also contains 1,848 active native-control intervals: receipt P99 **10.600390 ms**, maximum **11.856906 ms**. These are reported separately because the native coupled trial does not exercise the external action-renewal loop. No log drops or timing record errors were reported in these four sources. A failed campaign's `stop_confirmed=false` is retained even when its final state is disabled.

### Recorded GC stall and bounded deferral

The reproduction's generation-2 callback interval starts at **637591372078140 ns** and ends at **637591425880201 ns**, an elapsed **53.802061 ms**. The last ordinary state receipt was tick **444447413** at **637591370570191 ns**. Action 1972 used that snapshot and completed its write at **637591371815235 ns**. The host latched `stale host telemetry` at **637591426403802 ns**. A queued healthy tick 423 arrived at **637591428607015 ns**, followed by fault tick 433 at **637591428989354 ns**. Tick 433 is exactly 20 ticks after the final accepted action's anchor. Callback elapsed time is an observed process interval, not a calibrated transport delay or a claim that every thread was stopped for every nanosecond of that interval.

The deferred repeat records no GC callback during the serial session. Its raw termination occurs at **637827716075934 ns**; the subsequent generation-0 collection starts at **637827716739053 ns** and takes **20.022128 ms**. This is consistent with restoring the prior GC state after STOP and disconnect. The sealed report records `cyclic_gc_deferred=true`, `restore_after="serial STOP and disconnection"`, and helper SHA-256 `802328896a1c2e19e56236797afbd729e4d219a531c68a0716f64f25535a8546`. The successful gentle campaign records the same runtime policy. GC deferral addresses this measured cause; it is not a general deadline guarantee.

## Standard-run expiry: delayed dispatch after notification

The standard run completed a 25-second quiet trial and the +10 mm, −10 mm and +20 mm trials. The following trial failed during its initial zero-position hold. GC deferral was enabled in its sealed runtime metadata. The raw log is `runs/id-live-20261020/standard-train-01/rig-1792542790256832287-3830174963.jsonl`, SHA-256 `a37595cc740c2312211c0e09b6dad9c383362c6390b3763b588414a16a55ddc5`.

| Event | Host monotonic ns | Relative to tick-754 receipt |
| --- | ---: | ---: |
| Tick 744 receipt; source of action 156 | 638135733032985 | −9.936763 ms |
| Action 156 write end | 638135734767319 | −8.202429 ms |
| Tick 754 receipt, healthy, `last_seq=156` | 638135742969748 | 0 ms |
| Tick 754 state record | 638135744383168 | 1.413420 ms |
| Next fetch starts | 638135752708644 | 9.738896 ms |
| Next fetch ends | 638135752974930 | 10.005182 ms |
| Timed policy starts | 638135753137243 | 10.167495 ms |
| Timed policy ends | 638135753364743 | 10.394995 ms |
| Action 157 write starts | 638135753791230 | 10.821482 ms |
| Tick 764 fault receipt | 638135754407648 | 11.437900 ms |
| Action 157 write ends | 638135754845623 | 11.875875 ms |

Action 156's tick-744 anchor plus its 20 ms TTL ends at tick **764**, matching the fault. Tick 754 arrived **9.936763 ms** after tick 744, so this event does not show the earlier long receive-gap pattern. The next observation fetch took **0.266286 ms** and the timed policy **0.227500 ms**. The dominant delay occurred before the next fetch started.

`Rig._accept` notifies waiters and releases the condition lock before producing the state record (`src/cartpole_sdk/rig/client.py:275–294`). Thus notification had completed by **+1.413420 ms**, at least **8.325476 ms** before the next fetch began. This is an upper bound on notification time, not an exact wake timestamp. Existing logs cannot distinguish delayed `wait_state` entry, delayed wake/reacquisition, scheduling after wait return, or interruption in the prior loop tail. No specific GIL holder, OS scheduling event or lock owner is established.

## Read-only pipeline review

The firmware sets `action_end=observed_tick+ttl` on acceptance and checks expiry every 1 ms (`firmware/teensy_executor/executor_core.h:59–68,120–125`). With snapshots 10 ms apart and TTL 20 ms, the next action has less than 10 ms of nominal renewal margin after its source snapshot was acquired. Board-to-host delivery, dispatch, policy preparation, policy computation and command delivery all consume that margin. There is no grace period at the old deadline.

The SDK validates a new request against its own observed snapshot and expiry (`rig/client.py:728` onward). This does not prove that the previous accepted action has enough remaining lease for renewal. A snapshot may still be fresh for a new request while the old action has already expired; the MCU remains the final safety boundary. A completed host write likewise does not establish board arrival or acceptance. There is no evidence here of a physical actuator delay or a firmware lease arithmetic error.

`wait_state` checks a latest-state tick predicate while holding a condition lock (`rig/client.py:380` onward). The source review found no lost-notification defect. The runner then performs a separate observation fetch and channel selection (`rig/policy.py:94–102`). In encoder-only capture, that fetch still validates board state and constructs the observation (`identification/driven_capture.py:304–309`). A recording worker and encoder-mirror worker remain in the same Python process; their serialization can compete for interpreter time, but these logs do not attribute this incident to either worker. The mirror's submission itself only replaces a reference. The read path can deliver buffered frames; latest-state pacing must continue to reject genuinely old observation sequences rather than refresh their timestamps.

## Smallest useful next diagnostic

Use a bounded, stopped replay or shadow harness first, preserving the real observation builder, guards and exported numeric actor. Measure the deployed computation on the target rather than substituting the quiet feedback policy's roughly 0.16 ms median. Before another powered external run, add only diagnostic boundaries sufficient to isolate the unexplained interval:

1. Timestamp `wait_state` entry and return with requested and returned ticks, native thread ID, host monotonic time and per-thread CPU time. This separates late entry from delayed wake/return.
2. Timestamp observation-provider entry and exit, plus the existing policy-call and write boundaries. Wrap methods in the experiment harness where possible; exact notify/release timing needs a narrowly scoped diagnostic hook if the coarse bounds remain inconclusive.
3. Store fixed primitive rows in a bounded buffer and flush after confirmed STOP/disconnect. Do not serialize or flush another log at each probe boundary. Record overflow, probe overhead, Python switch interval, CPU affinity and source hashes.
4. If wait-return wall time is long with little thread CPU use, correlate OS scheduling/thread evidence before blaming the GIL. If observation CPU time is long, inspect its measured substage. Replay injected 8–12 ms dispatch stalls to confirm unchanged stale-action/expiry behavior without powered hardware.

Separating display/recording serialization from the control process and reducing cross-thread handoffs are design directions to evaluate if measurement supports them. They are not implemented fixes here. Increasing telemetry frequency changes load and policy cadence and must not be treated as a free repair. Repeating an old policy command under a new observation anchor would conceal a missed decision and is not an acceptable renewal strategy. Changing TTL or weakening freshness would only hide this failure mode.

## Gym implications and limits

Preserve the 1 ms executor, intended decision cadence and 20 ms observation-anchored TTL. Retain previously declared telemetry/command delay sensitivity settings as assumptions, not fitted one-way delays. Add a distinct **dispatch-stall scenario** before action calculation/write; the observed standard failure is not represented by nominal inference cost or independent telemetry dropout. The 54–58 ms GC event remains a regression fault case and must expire the lease. A stale replacement after expiry must terminate rather than restart control. Native coupled evidence does not validate external host dispatch.

These four sources support a repair of one GC failure mechanism and a continuing external-control reliability blocker. They do not qualify the neural actor for hardware, identify physical cart tracking, or supply independent visual measurements. No simulator, model, policy, core runtime or safety-limit change was made during this review.

## Reproduce

```sh
MPLCONFIGDIR=/tmp/cartpole-analysis-mpl .venv/bin/python \
  evidence/system-id-20261020/tools/analyze_timing.py \
  --input runs/id-live-20261020/standard-train-01 \
  --input runs/id-live-20261020/timing-gc-probe-01 \
  --input runs/id-live-20261020/timing-gc-deferred-01 \
  --input runs/id-live-20261020/gentle-train-02 \
  --gc-events evidence/system-id-20261020/live/timing-gc-probe-01-gc.json \
  --gc-events evidence/system-id-20261020/live/timing-gc-deferred-01-gc.json \
  --output /tmp/NEW-cartpole-timing-comparison
```

The earlier v1 comparison is retained. V2 adds the sealed standard failure and separates nearby plot labels. Three focused offline analysis regression tests passed; no full suite, training or hardware operation was run by this analysis task.
