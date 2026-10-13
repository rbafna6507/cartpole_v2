# v26: independent speed policy and prepared capture

Prepared and uploaded September 18, 2026. **Firmware/defaults/IDLE/disabled output verified over serial; physical motion not tested.**

## Problem and change

The old capture gate allowed cart speed up to 95% of `vmax`. Raising the hard
ceiling therefore admitted higher-momentum handoffs; the energy pump also used
that same ceiling directly. Extra available capability changed the strategy.

The new controller separates the hard ceiling from `vmax_s` and `vmax_b`.
Both operating caps initially remain 0.8 m/s. On the incoming arc, starting
0.8 rad (46°) from upright, it blends pump acceleration into balance feedback
and lowers the planned speed toward `approach_v=0.3` m/s. The blend reaches
full weight at `catch_a=0.6` rad. `catch_v=0.3` m/s is an independent gate.
A handoff requires acceleration demand within `catch_da=4` m/s² of the
current acceleration and a 180 ms forecast without predictive rail braking,
excessive angle, or increased angular error/rate energy. This forecast uses
36 bounded steps of the shared jerk-limited governor. It assumes ideal motion;
its execution time on the actual ESP32 has not been measured.

Neither handoff nor mode-cap changes reset velocity or acceleration. A fixed
bug in the governor now brakes an inherited velocity above a lower mode cap;
previously a zero request could coast indefinitely above that cap.

Defaults use the latest trial gains ke=8, kpx=80, kdx=2, phase_soft=2;
pw=7/pz=0.85 and amax_s=amax_b=12, jmax=60 are retained. The 125 mm arm,
60T pulley, STEP25/DIR26, upright3953 and physical rail remain unchanged.

## Evidence

The latest completed recording is `logs/run_20260918_105100.csv` (861.140 s,
15 automatic attempts). Frozen acknowledged settings and first-BAL telemetry
states are in `recorded_trials.json`; raw file hash and gate counts are in
`recorded_gate_review.json`. Of 122 sampled capture states, 86 exceeded 0.3 m/s;
11 satisfy the new default gate. These are 25 Hz telemetry snapshots with raw
angle, not exact capture-time filtered states. Rejecting failed handoffs does
not itself establish that another attempt would succeed.

A 48-combination approach/capture screen at 40 s selected the current settings;
9/18 sensitivity cases balanced at that duration. `search.json` preserves the
screen. Final matched 60 s tests use the same gains in v25 and v26:

| Result | v25 | v26 |
|---|---:|---:|
| Balanced cases | 11/18 | 13/18 |
| Prior measured plant, centered | Pass | Pass |
| Recent fitted plant, centered | Pass | Pass |

The acceptance criterion is the simulator's final five seconds inside
5.7° upright and 100 mm from center. Two old passes regress: recent plant
with -5° initial offset, and the high-friction sensitivity. Encoder ±2° and
98% motor tracking remain failures. This is a modest model improvement, not
a robust hardware result. `validation.json` lists every case and source hash.
The recent damping fit is provisional; it does not replace physical calibration.

## Checks

- 23 simulator groups, including compiled C++/JavaScript equation parity.
- Complete automatic trajectories and capture decisions identical with hard
  ceiling 0.8 versus 2.0 m/s, for fixed operating caps (including unequal caps).
- C++ capture, cart motion, rail recovery, spin recovery, upright-session and
  quiet-motion tests; lower-cap transition retains bounded jerk and acceleration.
- Firmware serial, driver disable, serial recovery/checksum and encoder-reference tests.
- Browser tests cover new inputs, valid command export, recordings, replay,
  historical presets, desktop and mobile layout; screenshots inspected.
- ESP32 build passed: 343671 bytes program, 22736 bytes global storage.

The legacy `tests/swing_controller_test.cpp` still encodes 175 mm plants and
old gains/acceptance assumptions; it is not the current 125 mm sensitivity
suite. The current suite is `analysis/validate_v26.js` plus firmware equation
parity and the targeted C++ tests above.

Reproduce from repository root:

```sh
node analysis/search_v26.js
node analysis/validate_v26.js
node analysis/check_v26_recording.js
python3 simulator175/build_data.py
node simulator175/test.js
arduino-cli compile --fqbn esp32:esp32:esp32 swingup
```

`v25_engine.js` is the exact pre-change engine snapshot for the matched comparison.
Controller development involved no physical motion. The subsequent user-requested upload passed flash verification and CRC-checked serial verification of v26, defaults, IDLE, STOP and disabled GPIO27. See [upload verification](../v26_upload_verification.json). The serial port was closed afterward; no motion or new gain trial was performed.
