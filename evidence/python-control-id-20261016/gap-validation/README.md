# Bounded observation-gap validation — 2026-10-16

Implemented only the reviewed opt-in policy/runner feature. Default remains strict; console defaults, controller gains, source/skew/age/raw-angle/BAL/rail guards, firmware and 20 ms anchored TTL are unchanged. No hardware, staging or deployment was performed by this validation work.

At 250 Hz, `max_gap_periods=2` accepts board-time deltas 2–8 ms and `=3` accepts 2–12 ms. `None` retains 2–6 ms (100 Hz retains 5–15 ms and rejects non-None options). Sequence replay and reverse/too-short time remain faults. At most two action-producing gaps above 6 ms are accepted in `(now − 1 s, now]`; a third fails before a new action and before advancing policy acceptance state. A gap exactly one second old expires. Counts describe policy-produced actions, not a hardware send acknowledgement. All next-step motion calculations retain nominal 4 ms; only startup travel uses actual elapsed time with endpoint-speed trapezoids and zero initial interval.

`timing` metadata on policy start/end/failure records the configuration, accepted long-gap total/window count and maximum/last observed delta. Only primitive counters and a list of at most two timestamps change per tick; metadata dictionaries are created at run boundaries/failure. Failed sensor selection occurs before cadence bookkeeping. Existing failed/previous-sent observation fields disambiguate which frame failed. The runner exposes the opt-in argument without changing console use.

## Verification

- `pytest tests/test_executor_feedback_policy.py tests/test_capture_forecast.py tests/test_control_observation.py tests/test_rig_console.py -q --tb=short`: **132 passed in 2.98 s**, saved in `scoped-pytest.txt`.
- New tests cover integer/type/rate option restrictions, inclusive cadence boundaries, replay/reverse-time/minimum-gap refusal, budget/expiry/reset, stale/skew/source/frame/missing/brake/rail/spin/raw-BAL guards, nominal-step invariance, travel integration, unchanged kick/recovery wall-time limits, runner STOP/no-new-action and diagnostic failure preservation.
- Four real MuJoCo/executor tests run every 1 ms while host decisions are skipped. They verify held commands/governor jerk, no lease renewal on refusal, and lease expiry exactly 20 ms after the last accepted action.
- One earlier combined policy+console run had **81 passed / 1 failed** in the unrelated existing PTY native AUTO test (`test_noninteractive_auto_records_and_stops_finally`, firmware mode4 versus expected0). That test invokes the native path, not the changed runner; its wall-clock firmware leaves STOP in fault mode after a deadline fault. It passed in isolation, then the full scoped run above passed. No expectation, deadline or safety behavior was relaxed to hide the failure.

## Closed-loop experiments

`run_experiments.py` drives an unmodified binary32 executor governor and MuJoCo plant every 1 ms. New raw requests occur at nominal 4 ms decision times unless deliberately skipped. All requests expire at observation time +20 ms. Gains come from the existing captured bw10 parameter file; measured half rail is 0.309037507 m. Sensor/physics assumptions remain provisional and the simulated sensor does not reproduce the MCU magnetic observer.

Eighteen normal rollouts complete **93 simulated seconds**: six starting conditions, each strict versus occasional 8 ms and 12 ms gaps. Exactly two long-gap opportunities occur per 1.1 s; rail and approach gaps start at 20/80 ms so they occur during transients. All eighteen complete without policy/executor faults. Four additional negative rollouts preserve strict refusal at 8 ms, opt-in refusal at 16 ms, refusal of the third long gap, and expiry at 20 ms with no new decision. No hardware stability claim follows: hanging and moving approach did not capture in any configuration; already feasible initial poses held balance.

| Scenario | Strict / gap2 / gap3 peak absolute x (m) | Completed per run | Outcome |
|---|---:|---:|---|
| hanging | 0.151357 / 0.151362 / 0.151385 | 8 s | No faults; remained swing; no capture |
| balance | 0.014603 / 0.014599 / 0.014591 | 5 s | No faults; held balance |
| capture | 0.155694 / 0.155668 / 0.155617 | 5 s | No faults; held balance |
| approach | 0.104841 / 0.103606 / 0.106567 | 5 s | No faults; remained swing; no capture |
| rail-right | 0.297503 / 0.297503 / 0.297503 | 4 s | No faults; returned inward, resumed swing |
| rail-left | 0.297503 / 0.297503 / 0.297503 | 4 s | No faults; returned inward, resumed swing |

Per-decision traces, transitions, parameters, runtime versions and source SHA256 values are in `*-decisions.json` and `results.json`. `validate_results.py` independently checks saved sequences/window budgets and rail/speed/acceleration/jerk envelopes; its result is in `result-audit.txt`. Small jerk/speed tolerances account only for binary32 rounding.

`benchmark.py` reports five batches of 1000 balanced-feedback `act` calls with prebuilt observations. Median per-call times were 0.049 ms strict, 0.055 ms gap2 and 0.073 ms gap3. Offline simulations were also running, so this is informational host timing, not a comparative real-time guarantee or a timing assertion.

## Runner timing inspection (source only)

No intentional 15 ms delay or lost-notification race was found in the post-action path. `Rig._accept` updates `_state` and notifies under the same condition lock checked by `_wait_state` before waiting; an already accepted newer frame satisfies that predicate immediately. A condition notification does not guarantee immediate thread execution.

The `action_request` timestamp precedes record deque/queue insertion and the final `Rig.step` observation construction. Therefore action-record-to-next-fetch latency includes the step tail, condition wake/reacquisition, and OS/GIL scheduling. The returned observation from `step` is discarded by the runner. The I/O worker processes every line in a read batch, serializes state with `asdict`, and enqueues logs after notification; the logger serializes and flushes each record; an independent mirror worker serializes near 200 Hz. Those compete for scheduling, but no individual cause is established. `put_nowait` avoids waiting for queue capacity, not all mutex acquisition; the logger flushes after releasing the queue lock.

The next discriminating instrumentation is step/wait start and finish wall/thread-CPU times, plus existing fetch/act boundaries. A separate scratch-only harness was produced at `/tmp/cartpole-python-id-20261016/diagnose_timing.py` at the parent request; it verifies frozen source, supports disabled observation and zero-only trials, retains TTL20, and dumps preallocated timing arrays after STOP. No hardware run was performed here.
