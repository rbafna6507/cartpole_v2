# v22: controlled rail recovery and compact swing-up comparison

## Change and status

Firmware `swingup-175mm-60t-v22` is compiled and software tested, **not uploaded**.
The cart remains STEP25/DIR26, 60T GT2, 26.666667 steps/mm. Defaults remain
`vmax=0.8`, `amax_s=12`, `amax_b=12`, `jmax=60`, `ke=2`, `kpx=30`, `kdx=0.5`.

The previous recovery could hand control back inside ±130 mm while the cart
was still accelerating strongly inward. One recorded starting state
(x=126.71 mm, v=0.399 m/s, a=−9.014 m/s², amax=18, jerk=200)
released after 55 ms at v=−0.304 m/s and a=−11.214 m/s² under the old headers.
It handed swing-up a substantial cart reversal already in progress.

The new governor reserves distance for the complete jerk-limited stop,
including acceleration ramp-down. Braking remains latched until |v|≤0.005 m/s
and |a|≤0.1 m/s². Return targets at most 0.15 m/s inward and 1.5 m/s².
Release requires inward or near-stopped inward motion inside ±130 mm,
|v|≤0.155 m/s, |a|≤1.5 m/s² and no active braking latch. No acceleration reset
or jerk-limit bypass is used. Late inherited stops outside ±135 mm can depart
inward without repeatedly relatching at negligible outward velocity.

Normal operation is still ±135 mm; hard fault is ±140 mm; physical travel is
±150 mm. Ordinary rail recovery does not seek center. Timeout remains 8 s.
The shared governor also changes predicted braking for manual motion and
the existing spin/upright recovery paths; their dedicated tests pass.
The firmware queues `# rail handoff x=... v=... a=...` for diagnosis.

The same recorded seed now releases after 164 ms at x=129.97 mm,
v=−0.1286 m/s, a=−1.5 m/s², with maximum x=135.55 mm. This inherited
late-braking state starts beyond what the new predictive governor would accept.

## Verification

- Actual C++ headers: 1,148 sampled rail-entry states from three September 17
  logs, plus mirrored copies: **2,296 cases, no failed recovery/jerk/rail checks**.
  Largest |x|=139.884 mm, release |v|≤0.150000 m/s, |a|≤1.500000 m/s²,
  longest recovery=0.425 s.
- These are 25 Hz sampled commanded states, not exact 1 kHz replays. The
  unlogged brake side is inferred from sampled velocity or near-zero position.
  The frozen case file retains snapshot hashes; live logs may continue growing.
- Motion-limit regression, rail handoff/edge-return cases, angular-rate recovery,
  upright-only return, driver-disable/DDS, serial watchdog/parser and capture
  checks pass. The simulator passes **17 groups**, including C++/JS parity.
- ESP32 compile passes: 342447 program bytes, 22720 global bytes.

Reproduce the focused checks:

```sh
python3 -m unittest discover -s tests -p test_recorded_rail_recovery.py
node simulator175/test.js
node analysis/compact_swingup_v22.js
```

Position is inferred from commanded steps. These checks cannot establish motor
tracking, endstop clearance after slipping, or successful physical swing-up.

## Can swing-up use less rail?

Lower speed reduces stopping room. For a complete stop from zero acceleration,
with jerk=120 and acceleration limit=15, 0.8 m/s needs about 65.3 mm, while
0.6 m/s needs 42.4 mm. At default jerk=60, 0.8 m/s needs 92.4 mm. Increasing
the acceleration ceiling alone does not shorten these triangular stops because
they never reach that ceiling. Increasing jerk shortens the stop but changes
motor loading; this comparison does not justify raising the user's limits.

The reproducible sweep in `compact_swingup_v22.js` compares 13 settings across
three starts (center/down and ±10 mm/±5°), 30 seconds each, with ideal tracking
and measured free-decay damping. Base parameters are .8/15/15/120, ke=2,
kpx=30, kdx=.5, matching the limits of the earlier successful physical trial.
These are comparison parameters, not changed firmware defaults.

Representative centered-start results:

| Change | Maximum offset from center | Maximum lift from down | Rail recoveries |
|---|---:|---:|---:|
| Base | 134.9 mm | 149.6° | 24 |
| vmax=0.6 | 128.0 mm | 131.2° | 0 |
| kdx=1 | 134.7 mm | 135.7° | 10 |
| kdx=2 | 125.6 mm | 121.3° | 0 |
| kdx=4 | 93.8 mm | 96.8° | 0 |
| kpx=60 | 134.8 mm | 180.0° | 16 |
| kpx=60, vmax=0.6 | 107.7 mm | 97.2° | 0 |

Increasing `kdx` damps cart velocity but also removes useful energy transfer.
Stronger centering (`kpx=60`) reached upright in all three simulated starts,
with sustained final balance in one; it still used nearly the full rail.
Increasing `ke` to 3–4 created more rail recoveries and no settled balance in
these starts. Phase-smoothing changes did not establish reliable compact capture.

**No tested gain combination established reliable swing-up in less space.**
First compare the recovery fix at unchanged runtime gains and limits. Then a
single-variable increase in `kpx` is a candidate experiment; reducing it was
not supported by the recent hardware run. Avoid stacking speed/damping changes.
A separate swing-up speed cap or a phase-aware trajectory that explicitly
budgets cart travel could be future controller work, but neither is implemented
or validated here.

The model does not reliably reproduce the earlier physical 25.8 s balance hold,
so it supports tradeoff screening, not selection of a proven hardware gain.
Full settings, outcomes and engine hash are in `compact_swingup_v22.json`.
