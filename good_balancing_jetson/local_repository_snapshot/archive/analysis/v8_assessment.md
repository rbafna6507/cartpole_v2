# v8: disabled stops, default limits, and earlier capture

> Superseded: v8 bypassed Arduino GPIO registration for ENABLE, so `auto` could
> report energized without enabling the drivers. v9 fixes this and strengthens
> the mock test. See [v9 assessment](rail_recovery_v9.md).

## Firmware changes

- Startup preloads active-low ENABLE GPIO27 HIGH before enabling its output, serial delays, I2C scan or encoder zeroing. All three drivers remain disabled until a motion command or `on`. Firmware cannot control the earlier reset/bootloader interval.
- `stop`, `off` and fault stops disable all drivers, clear rates and STEP outputs. The pulse ISR and rate setter are gated while disabled, including stale rate writes. Height motors release too; support the height assembly.
- Removed both speed-profile commands and the `fast` prerequisite. Defaults are vmax=0.75, amax_s=15, amax_b=15, jmax=50. Manual jog limits stay separate. GPIO mapping and 175 mm/300 mm configuration are unchanged.
- Predict velocity gained during the jerk ramp back to zero. Begin ramp-down before that velocity would cross vmax. The previous implementation could fault even after requesting maximum opposing acceleration.
- Widen capture from 0.45 to 0.60 rad (25.8° to 34.4°). Keep rate gate at 3 rad/s. Beyond 0.20 rad, require motion toward upright. Reserve 5% speed headroom, retain rail/acceleration checks, and reject a handoff whose short acceleration-ramp forecast is outside the balance dropout window.
- Apply balance acceleration on the actual handoff tick. Widen dropout from 0.70 to 0.80 rad to accommodate the earlier entry. Existing feedback gains and energy gain remain unchanged: candidate gain changes did not establish better performance across separate recorded attempts.

## Clipping in the user-selected trial

Source: `run_20260916_122300`, third automatic episode, 44.729 seconds, recorded parameters 0.75/15/15/50.

| Quantity | Result |
|---|---:|
| Time within 1% of speed cap | 11.51% |
| Longest near-speed-cap interval | 164 ms |
| Time within 1% of acceleration cap | 0% |
| Peak commanded acceleration | 8.65 m/s² |
| Estimated time near jerk cap | 49.11% |
| Upright passes / balance entries | 16 entries, 179.908° maximum lift from down |
| Longest BALANCE-mode interval | 0.245 s |

Speed limiting was intermittent; jerk shaping acted much more frequently. At vmax=0.5, the separate trial spent 52.24% near its speed cap and lifted only 49.06°. The acceleration cap was not reached in either trial. Near-cap time is a duration-weighted telemetry statistic, not a measurement of raw acceleration-demand clipping. Jerk activity uses differences of roughly 10–13 ms telemetry samples and can miss brief within-sample events. Raw demand and limiter reason are not logged in v7.

## Simulation informed by the logs

- Corrected default drive geometry from historical 60T/26,666.7 steps/m to 20T/80,000 steps/m. Current simulator starts with the new firmware limits and capture settings. Historical 60T preset is explicitly labeled historical.
- Replaced the selected recorded waveform with a frozen extraction of the exact 0.75/15/15/50 trial, including SWINGUP and BALANCE samples and its fault result. Provenance includes the original session snapshot hashes and board-time range in the companion case data/review.
- Added initial angular velocity, cart velocity and acceleration, allowing simulation from 31 measured/pulse-derived handoff states rather than only a stationary, centered ideal start. Sixteen cases come from the preferred trial; fifteen comparison cases come from the adjacent jmax=100 and amax=10 trials.
- Shared governor and capture equations have C++/JavaScript parity checks. Pulse-rate ceiling, speed, jerk and rail checks remain enforced.
- Kept effective length and damping from the 33-cycle free-decay calibration. The logs do not directly measure cart acceleration or identify motor torque/lag. Acceleration-response fits were highly sensitive to smoothing/trial, so no fitted motor gain or sign change was adopted. A 10 ms lag scenario is an assumption for sensitivity testing.

Six-second recovery tests start at the first logged BALANCE sample, up to about 13 ms after the true handoff. Raw angle and filtered angular rate are mixed measurements; inferred position and commanded acceleration may differ from physical motion. A case is counted settled when its final continuous interval exceeds two seconds in BALANCE with angle <0.1 rad and position <0.1 m.

| Model | Preferred-trial cases settled | Separate cases settled | Faults / 31 |
|---|---:|---:|---:|
| Archived v7 equations, seeded states | 6 / 16 | 2 / 15 | 5 |
| v8 | 5 / 16 | 2 / 15 | 0 |
| v8, assumed 10 ms motor lag | 5 / 16 | 1 / 15 | 0 |

**This demonstrates fewer modeled faults, not improved balance performance.** None of these recorded physical attempts sustained balance, whereas some seeded ideal simulations recover. The full centered swing-up regression also still fails to capture in its first case. Earlier capture is a hardware trial candidate; reliable physical balance is not established.

Reproduce the case comparison with `node analysis/validate_recorded.js`. Rebuild clipping/capture cases with `python3 analysis/build_recorded_cases.py`; it reads only the fixed episode intervals from the original logs.

## Verification

- ESP32 compile passed: 334,915 bytes program, 22,640 bytes globals.
- Motion regressions passed: speed/acceleration/jerk, reversals, rail margins, and a near-cap low-jerk ramp regression.
- Capture-gate tests passed: earlier inbound capture, rejection when departing, insufficient velocity headroom, rail room and acceleration reversal.
- Compiled real firmware driver functions under mocked GPIO: disabled startup, stop clears/disables all axes, blocked rate writes and ISR pulse/count suppression passed.
- Ten simulator test groups passed, including 100 governor and 100 capture C++/JS parity fixtures, calibration provenance, physical integration, limits and recovery.
- Browser checks passed: current 20T defaults, comparison/sweep, calibration, recorded waveform/replay, inputs, exports and mobile layout.
- Full swing-up capture regression remains failing, as stated above. Hardware enable-pin voltage and balance behavior require physical verification. Not flashed.
