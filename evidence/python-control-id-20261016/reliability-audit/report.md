# Python AUTO capture loss and cadence audit — 2026-10-16

The completed 25-second Python trial did **not** sustain balance: it captured at 3.280 seconds, returned to swing at 4.256 seconds, and spent exactly **0.976 seconds** in balance. The next repeat stopped on a separate 16 ms observation gap before capture. Neither run establishes a reliable Python AUTO controller.

This is a read-only audit of saved recordings. No hardware, calibration, parameter, SDK, firmware, service, or controller change was made by this analysis. All prior identification rejection gates remain unchanged; no physical model is accepted here.

## What the recordings establish

| Measurement | Python completed trial | Native comparison |
|---|---:|---:|
| Run | `auto-1792178712717473923` | `native-1792178943322637321` |
| Requested duration | 25 s | 25 s |
| First observed capture | 3.280 s | 2.476 s |
| Balance samples/actions | 244 actions | 5,631 telemetry samples |
| Continuous balance duration | 0.976 s, closed by release | 22.520 s observed sample span, still balanced at trial end |
| Raw-angle RMS **during balance** | 19.18865° | 4.03763° |
| Balance maximum absolute counted x | 253.6875 mm | 185.7375 mm |
| Balance maximum absolute commanded v | 1.494016 m/s | 0.7998413 m/s |
| Balance maximum absolute applied command a | 19.42408 m/s² | 8.983128 m/s² |

Both use reference 330, home epoch 14, span 16,513 steps, bandwidth 10, and identical 41 live parameters. The native controller executes at 1 kHz; Python executes at 250 Hz with MCU observer and motion-state feedback. Telemetry is 250 Hz in both recordings. Native mode 2 is SWINGUP and mode 3 is BALANCE. Python's firmware remains in EXTERNAL mode 12; the explicit policy transitions identify its balance interval.

Native success shows that the current rig and gains could balance in that trial. It does not prove every capture state is recoverable or isolate why the Python trial lost balance. The trials start from different pendulum states and follow different swing trajectories. Counted x and commanded v/a are not independent measurements of actual motor/cart tracking.

## Capture and loss

The frozen Python policy replays all 6,248 requests with maximum absolute error `3.553e-15 m/s²`, and its phase transitions match the log exactly. Fast float64 capture, the Python reference with binary32 motion arithmetic, and the compiled actual C++ capture header agree on **every one of the 6,248 states**. They also agree on all 163 actions in the failed repeat. No arithmetic disagreement or wrong AUTO/BAL gain selection explains these captures.

AUTO uses `pw=3`, including its balance phase, in both implementations. The resulting gains are approximately `(-22.025593, -2.391380, -3.412844, -3.185321)`, with acceleration request `-(k1*theta + k2*omega + k3*x + k4*v)`. `bal_pw=4.5` is for a BAL-only start.

At Python capture the recorded state is:

| Quantity | Value |
|---|---:|
| Filtered angle / raw angle | −0.1338945 / −0.1549321 rad |
| Estimated angular rate | +0.7407548 rad/s |
| Counted x / commanded v | −0.0355125 m / +0.2529373 m/s |
| Applied command a | −4.285492 m/s² |
| Balance request | −0.493191755 m/s² |
| Request-to-current-a difference | 3.792300245 m/s², below the 4 m/s² gate |

The native comparison's first balance telemetry sample has theta `+0.1862744`, omega `−1.500902`, x `+0.0103875`, v `−0.2259751`, and a `+2.74272`. The exact native transition can occur between telemetry samples, so this is not necessarily its exact gate input.

In Python, an oscillation grows after capture: v reaches +1.346 m/s by about +240 ms, x reaches +253.7 mm around +408 ms, then the cart reverses and approaches −1.494 m/s. At +976 ms, filtered theta `−0.8034759` crosses `giveup=0.800000012` and the policy returns to swing. Raw theta is `−0.7853982`, omega `−3.746401`, x `+0.1081875`, v `−0.2435953`, and a `−19.27587`. This is the ordinary AUTO give-up rule, not a rail, sensor, spin, cadence, or firmware fault. No brake direction is asserted during this balance interval.

The settled-velocity bounds alter 22 of 244 balance requests. The first is at 3.808 s, **528 ms after capture**, after the oscillation has already grown. Replaying four 1 ms governor steps from each recorded state while holding either the clipped or unclipped balance request produces identical results in 21 of those 22 intervals. The remaining interval differs by 0.138935 m/s² and 0.00004424 m/s after four steps. This fixed-state diagnostic cannot reconstruct the counterfactual closed-loop trajectory, but provides little support for blaming the added speed bound for the initial divergence.

The approach planner's 4 ms versus native 1 ms horizon does change the pre-capture requests: at 3.260–3.272 s the 4 ms requests are approximately 0.42 m/s² less negative. That can change the approach trajectory and capture timing. The recorded state cannot tell us what trajectory a 1 ms-horizon host would have produced.

Capture's 180 ms forecast predicts filtered theta `−0.05284`, omega `+0.09560`, v `+0.19034`, a `−0.31330`; the recorded Python values at +180 ms are `+0.01519`, `−3.30056`, `+1.05205`, `+9.47553`. The native forecast also differs materially from its observed +180 ms response despite eventual sustained balance. Thus forecast acceptance is not a validated physical stability guarantee. Earlier system-ID fits remain rejected. No mass, motor slip, angle-zero error, or effective-length conclusion follows from this comparison.

The observer transient also matters: over the 16 ms before Python capture, raw angle moves at an average −0.959 rad/s while the reported observer rate at capture is +0.741. In native, the analogous raw slope is +3.068 while observer rate is −1.501. Both therefore have an apparent inbound observer state while recent raw angle moves outward. This feature is shared; an added raw-rate capture gate cannot be justified from the failed Python trial alone.

## Timing during the capture loss

All 6,247 action-to-action board intervals in the completed Python trial are exactly 4 ms. All 244 balance action sequences appear in the next 4 ms telemetry sample. There is no skipped action observation or long strict-cadence gap during the loss.

Within balance, host `received_ns` to command-record latency has median 1.661 ms, p95 2.137 ms, and maximum 4.561 ms. At capture it is 2.642 ms. These are host logging proxies, **not** synchronized measurements of board actuation latency; the sequence acknowledgement only brackets acceptance at telemetry resolution. Their nonzero, variable timing and the 4 ms sample-and-hold distinguish the host loop from native 1 kHz feedback, but one unmatched trajectory does not prove a specific delay caused the loss.

An offline shadow on the first 1.1 seconds of native balance quantifies sensitivity to older observations. The same-snapshot balance equation differs from recorded native demand by RMS 0.01140 m/s² (rounding and post-tick motion state contribute). Replacing only its input snapshot with one 4 ms older raises RMS difference to 0.76532 m/s² and maximum difference to 2.53004 m/s². At 8 ms these become 1.48406 and 5.01318 m/s². This holds the recorded trajectory fixed; it is not a simulated stability result or an estimate of actual host delay. `timing-shadow.json` retains the exact sample counts and statistics.

## Exact failure timeline for the later repeat

Run `auto-1792178798176817624` sent 163 actions, then the strict policy rejected observation tick 80954888 after last sent tick 80954872. This is a **16 ms** board-clock gap. Every intermediate 4 ms telemetry frame is present:

| Tick | Host `received_ns` | Since previous receipt |
|---:|---:|---:|
| 80954872 | 274097333587960 | — |
| 80954876 | 274097339835718 | 6.247758 ms |
| 80954880 | 274097345087106 | 5.251388 ms |
| 80954884 | 274097345622988 | 0.535882 ms |
| 80954888 | 274097349747380 | 4.124392 ms |

The last action request was recorded at `274097334991505`; the next fetch started at `274097350544450`, **15.552945 ms** later. Frames 876, 880, and 884 had already arrived 10.709, 5.457, and 4.921 ms before that fetch. There is both uneven reader/transport arrival timing and a runner interval during which available intermediate frames were not consumed. This is not a missing-board-frame or duplicate-observation explanation.

The failed fetch itself took 0.170339 ms, and the rejected policy call took 0.093313 ms. No recorded GC event overlaps the last-action-to-failure interval. The preceding GC lasted only 0.185379 ms and ended 14.819 ms before the last action request. These records do not identify OS scheduling, GIL scheduling, sleep behavior, or network latency as the unique root cause.

STOP was recorded immediately after the policy failure and is observed at board tick **80954891**, before the last command's tick-80954892 lease deadline. Firmware fault remains zero, and miss/drop counters do not increase. The strict guard worked; the recording does not show an expired command lease.

## Next bounded test

Resolve and instrument the observation-gap handling first. The next hardware comparison should change **only the reviewed cadence-handling option**, keeping 250 Hz, CPU affinity, Python switch interval, bandwidth 10, gains, reference, home epoch and capture gates fixed. Report accepted long-gap counts, failed observations, board/host timing, faults, actual mode intervals, and RMS restricted to balance. A completed 25-second trial with a brief capture is not a balance success. Repeated trials are needed before calling the controller reliable.

If cadence reliability holds but these short capture losses recur, compare timing and approach-planner hypotheses separately using offline shadows before another single-variable motion test. This evidence does not justify simultaneously retuning gains, bandwidth, speed limits, and capture gates, or relaxing the physical identification gates. No additional test was executed by this audit.

For the next **control** comparison after stationary timing is acceptable, a short native BAL-only versus Python BAL-only trial from the existing strict quiet-upright start envelope would remove AUTO approach and capture as variables. Both must explicitly use their common BAL-only gains (`bal_pw=4.5`) and unchanged safety envelopes; root must review and execute any motion. Only controller execution location/cadence changes. This can test sampled feedback and transport timing, but it does not directly validate AUTO's `pw=3` balance phase. Avoid changing bandwidth or either gain set in the same comparison.

## Provenance and reproduction

`analysis.json.gz` contains every selected state from −100 to +1,200 ms around capture, calculated requests/bounds, mode intervals, all oracle disagreements (none), raw input hashes, exact parameters, the failure timeline and source-equation hashes. `native-1792178943322637321-compact.json` contains the read-only remote extraction, including its original report/JSONL paths and SHA-256 hashes. Raw Python logs remain under `../hardware/runs/`; no giant raw log was duplicated here.

The offline policy and numerical modules are the already-frozen `../capture-audit/source/`, and the actual C++ oracle uses `../capture-audit/headers/`. Current SDK development was deliberately not imported. These frozen controller equations match the recorded requests and current native motion/control header hashes. The collector only reads JSON files; its source is `collect_native_reliability.py`.

From the repository root, write a fresh output path:

```sh
.venv/bin/python evidence/python-control-id-20261016/reliability-audit/audit_reliability.py \
  --run evidence/python-control-id-20261016/hardware/runs/auto-1792178712717473923 \
  --run evidence/python-control-id-20261016/hardware/runs/auto-1792178798176817624 \
  --native evidence/python-control-id-20261016/reliability-audit/native-1792178943322637321-compact.json \
  --output /tmp/cartpole-reliability-reproduction.json.gz
.venv/bin/python -m unittest discover -s evidence/python-control-id-20261016/reliability-audit -p 'test_*.py' -v
```

The script refuses to overwrite an existing result. It compiles a temporary C++ numerical oracle, and performs no hardware I/O.
