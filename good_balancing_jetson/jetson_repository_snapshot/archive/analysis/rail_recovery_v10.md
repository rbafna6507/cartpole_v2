# v10: plot stop commands, 270 mm operation, and requested limits

Source update only; not flashed or tested on the physical mechanism by the assistant.

## Behavior

- Terminal input stays active during plotting: `stop` + Enter sends the stop command, including in automatic/data plots. Plot STOP button, Space/Escape, close, and quit also send stop. A/D/W/S only jog in the manual plot window; typing terminal commands cannot turn `s` into a screw jog.
- Startup/stop remain disabled on shared GPIO27; retains v9 Arduino pin registration fix. Serial writes are serialized; stop cancels a pending manual jog.
- Physical rail remains 300 mm. Operating range expands to ±135 mm (270 mm); release recovery at ±130 mm once moving inward, without center-seeking or dwell. The 5 mm inset avoids boundary chatter. Earlier predictive braking and ±140 mm software fault stay enabled.
- Recovery returns inward at up to 0.15 m/s and 1.5 m/s², respecting lower configured limits and jerk. Manual recovery resumes with a zero velocity target. No position re-zero. Startup response watch remains active.
- User-requested defaults: vmax=0.8 m/s; amax_s=amax_b=18 m/s²; jmax=100 m/s³. At 20T GT2 these are 1200 RPM, 27000 RPM/s, and 150000 RPM/s².
- Pulse timer changes from 8 to 7 µs, with the same period used to calculate DDS increments. Ceiling becomes 71428.57 steps/s (0.892857 m/s), above the requested 64000 steps/s. Control still runs at 1 kHz. Hardware interrupt latency has not been measured at this new rate.
- At 0.8 m/s and zero acceleration, jerk-limited stopping distance is about 67.5 mm; full speed therefore requires braking well before the final 15 mm.

## Verification

- Five console tests: typed stop, parameter edits, immediate stop/quit, pasted input/EOF, and actual Matplotlib stop-button/key/terminal callbacks using a fake serial link.
- Existing console event logging passes. Actual firmware ENABLE/stop/DDS functions pass a compiled GPIO mock, including 64000 steps/s pulse counting at the new timer period.
- Motion governor passes speed/acceleration/jerk/reversal/rail cases at new defaults and historical stress settings. Ten mirrored rail recovery trajectories pass, including maximum-speed approach and inward movement near an end. Edge-started returns release near ±130 mm rather than center.
- Eleven simulator test groups pass, including firmware equation parity, recovery, physical rail/commanded-position distinctions, and startup nonresponse.
- ESP32 compile passes: 336147 program bytes, 22656 global bytes.
- The full closed-loop swing-up regression still fails its sustained-balance requirement: first test reaches only 0.2 s continuous balance. These changes do not establish reliable swing-up/balance.

Recorded-state checks (31 approximate first-BALANCE states, 6 s simulations): archived v7 settles 6/16 training and 2/15 comparison with 5 faults; current equations at recorded limits settle 5/16 and 2/15 with zero faults; new defaults settle 5/16 and 4/15 with zero faults. Assumed 10 ms motor lag yields the same counts at new defaults. These are simulated outcomes, not physical success; original hardware trials did not sustain balance. See `recorded_validation.json`.
