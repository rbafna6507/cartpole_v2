# v13 — serial recovery and four-position encoder calibration

## Evidence

Latest event logs identify the running board as v10; these source changes require flashing.
`run_20260916_133542_events.jsonl` and `run_20260916_133723_events.jsonl`
contain `SerialException: read failed: [Errno 6] Device not configured`.
The user confirms the USB cable remained connected. This is an OS serial-device
access failure; a malformed telemetry number alone does not explain it.
The latter session received STOP before the reader error, about 114 ms earlier.
The 133542 session contains 591 IDLE samples; 133723 contains 4,717 samples,
including 1,068 SWINGUP, 155 RAIL_BRAKE, 32 BALANCE, 28 RAIL_RETURN and 3,434 IDLE.
These logs do not establish the physical cause of USB loss or successful balance.

## Changes

- Requested defaults: vmax 0.8 m/s, swing/balance acceleration 12 m/s²,
  jerk 60 m/s³. At 20T/2 mm this is 1,200 RPM, 18,000 RPM/s, 90,000 RPM/s².
- UART 230400 baud, default telemetry 50 Hz, maximum 200 Hz. Buffers configured
  before Serial.begin. Flash firmware and restart the updated Python console together.
- Control-task messages use a bounded nonblocking queue; UART writes occur in
  loop instead of the 1 kHz control task. Queue drops are counted in stat.
- Host preserves fragmented lines, bounds malformed frames, logs write/read errors,
  and reopens the same serial path after disconnect. It sends STOP first and blocks
  motion until acknowledgment. It never replays an automatic run or jog.
- Host sends STOP on a one-second telemetry gap and blocks motion on stale data.
  It sends periodic ping commands. Firmware disables drivers and faults active
  cart/height motion after 1.5 seconds without host commands. This watchdog does
  not depend on the Python reader successfully sending STOP after disconnection.
- Overlong firmware commands are discarded through their terminator.
- New `enc` snapshots include absolute raw count, absolute startup down-zero,
  magnet diagnostics, validity and driver-enable state. The absolute zero is
  reconstructed from raw count and relative unwrapped ticks.
- `calibrate_encoder.py` captures 0° down, 90° toward +cart, 180° up and 270°
  toward -cart with drivers disabled. It rejects invalid/moving captures, saves
  each completed pose and reports polarity, startup offset and quadrant errors.
  Use a square/level; four manual points cannot characterize all nonlinearity.
- Balance gains and angle correction remain unchanged pending actual measurements.

## Verification and limits

- ESP32 compile passes (core 3.3.2, esp32:esp32:esp32): 339,419 program bytes,
  22,736 global bytes.
- Compiled actual firmware parser/watchdog tests cover fragmented/overlong input,
  active and idle modes, height motion, timeout boundary and timer rollover.
- Actual GPIO/DDS function harness verifies disabled startup/stop and no pulses
  or position increments after disabling.
- Host tests cover disconnect/reconnect, STOP-first behavior, motion gating,
  fragmented telemetry/encoder frames, stale telemetry and keepalive.
- Encoder tests cover wraparound, both directions, known offsets, invalid/moving
  samples and preservation of incomplete measurements.
- Existing console event and plot command tests pass; C++ motion and spin tests
  pass; simulator's 14 test groups pass at the new defaults.
- These are software checks. The existing broader full-swing capture regression
  has not established sustained balance; lower limits are not a proven tuning fix.
- No physical encoder calibration or USB soak test was possible: no ESP32 serial
  device was present during final checks. No firmware was uploaded or motor run.
- Same-path recovery cannot reopen a differently named device; restart with its
  new --port. A reset can invalidate the inferred cart origin: recenter before
  restarting. A cable/hub/power/interference problem remains unconfirmed, not fixed
  by proof of software reconnection. Serial monitors without keepalives will
  trip the firmware timeout during motion; use the updated console.
