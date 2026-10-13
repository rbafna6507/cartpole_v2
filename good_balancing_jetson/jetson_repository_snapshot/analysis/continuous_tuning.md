# Ongoing swing-up tuning

**Paused for manual cart frequency tests.** See [frequency-test GUI](../frequency_test/README.md).

When enabled, the Codex task reviews new completed logs every five minutes while the app is
running and this Mac is awake. It updates and tests repository files. The ESP32
does not perform online learning. Automation ID:
`review-cart-pole-runs-and-tune-limits`.

## Current repository settings: v4

| Limit | Previous v3 | Candidate v4 |
|---|---:|---:|
| Speed | 1.5 m/s / 750 RPM | 2.34375 m/s / 1,171.875 RPM |
| Swing acceleration | 6 m/s² | 6 m/s² |
| Balance/braking acceleration | 6 m/s² | 6 m/s² |
| Automatic jerk | 150 m/s³ | 120 m/s³ |

The speed ceiling follows from 62,500 pulses/s, 3,200 microsteps/revolution,
and 120 mm/revolution. It is not a measured motor capability. Shared constants
in `swingup/cart_mechanics.h` keep firmware and simulation consistent.

Baseline `run_20260915_190840` reached **117.599° from down**, then declined to
**52.030° maximum over its final ten seconds**. No balance capture occurred.
Peak commanded speed was **1.1199 m/s**, with zero samples at the old speed cap.
Acceleration was near its cap for **50.5%** of active samples. Inferred position
exceeded 100 mm from center for **40.6%** of samples and peaked at 134.06 mm.
These observations do not establish a need for a higher speed or acceleration.

Lowering jerk by 20% is a trial intended to soften reversals. It may also change
pump phase, so physical improvement must be measured. Acceleration remains
6 m/s² pending evidence that the motor follows commands. The repeated startup
zeroing messages in the sidecar are flagged for investigation; they alone do
not establish that resets occurred during motion.

The v4 firmware compiles (334,375 program bytes, 22,640 global bytes). All 13
ideal-actuator closed-loop scenarios, rail-limit tests, and three log-review
tests pass. The user has now run v4; the results below do not show sustained physical balance.

## Physical review — September 15, 20:23 local

| Session | Observed settings (amax_s / jmax / ke) | Result |
|---|---|---|
| 20:11:50 | 6 / 120 / 2 | 57.3° lift, no balance |
| 20:15:12 | 6 / 120 / 2 | Startup nonresponse fault; retry crossed 179.2° from down, BALANCE for only 0.234 s |
| 20:17:52 | 5 / 50 / 2.5 | Startup nonresponse fault; retry reached 105.3°, no balance |

Speed cap was 2.34375 m/s in every session and was never reached. The two
faulting starts showed only 0.086° and 0° encoder span over about two seconds,
while pulses implied 460 mm and 643 mm cumulative cart travel. These are
commanded travel sums, not measured cart displacement. The runs began at
inferred positions −66.9 mm and −132.23 mm; subsequent retries also began away
from the software center. No sustained balance within 10° of upright occurred.

**Decision: hold repository limits and gain unchanged.** Do not escalate limits
until the gross nonresponse is understood and physical motor tracking is
confirmed. The lower-jerk v4 trial has not established an improvement over v3;
the later user experiment changed three parameters together. Preserve those
runtime experiments as evidence rather than overwriting repository defaults
from them. Establish the cart's physical center before resetting its reference,
and compare one change at a time after tracking is confirmed.

Per-session hashes/settings are in `run_reviews/run_20260915_20*.json`;
per-start measurements are in `run_reviews/20260915_2023_episode_review.json`.
The previous candidate is now marked physically trialed, with further tuning
held for motor tracking; it is no longer awaiting its first deployment.

## Apply repository settings

Upload v4 using the repository README. Alternatively, the currently running
v3 firmware supports these same motion settings. At the console, between runs:

```text
stop
set vmax 2.34375
set amax_s 6
set amax_b 6
set jmax 120
params
```

Runtime settings reset on reboot or profile changes. Place the cart at its
physical center before a new startup reference. Run `auto` when ready and
`stop` to finish. The reviewer recognizes the candidate from recorded settings
even if its firmware identity remains v3. It never opens serial, flashes, or
starts a run automatically.

## Review policy

`python3 analysis/review_runs.py --write` records summaries in `run_reviews/`.
It requires logs to be unchanged for two minutes and to end in stopped/fault
telemetry. It defers partial lines, nonfinite/missing data and reset clocks.
Parameter snapshots are taken at the firmware's start acknowledgement, after
the asynchronous parameter replies. Both CSV and event hashes identify inputs.
Older runs lacking snapshots are retained as context, not attributed to a trial.

`tuning_state.json` holds the baseline, reviewed hashes, pending candidate and
history. The recurring reviewer compares only new physical evidence. It waits
for the pending candidate's trial before making another tuning change, and
normally changes one of acceleration or jerk by at most 20%. It checks sustained
near-upright behavior as well as lift, faults, timing and rail proximity; a
brief BALANCE flag alone is not success. Failed candidates are rolled back.

Missing/mixed settings, nonresponse, suspected stalls and timing faults stop
limit escalation. Do not increase acceleration above 6 m/s² until motor tracking
is confirmed. Keep 300 mm travel, the centered startup assumption, manual limits
and rail protection. Preserve user changes. Update shared defaults, fast
profile, config JSON and documentation together, then run:

```bash
clang++ -std=c++11 -O2 -Wall -Wextra -Werror tests/swing_controller_test.cpp -o /tmp/swing_controller_test
/tmp/swing_controller_test
clang++ -std=c++11 -Wall -Wextra -Werror tests/cart_motion_test.cpp -o /tmp/cart_motion_test
/tmp/cart_motion_test
python3 tests/test_run_review.py
arduino-cli compile --fqbn esp32:esp32:esp32 --build-path /tmp/cartpole-build swingup
```

Report meaningful results and tested candidates; stay quiet on unchanged logs.
Motor tracking is still unmeasured: inferred pulse position can be wrong after
missed steps. Simulation cannot ensure physical bring-up.
