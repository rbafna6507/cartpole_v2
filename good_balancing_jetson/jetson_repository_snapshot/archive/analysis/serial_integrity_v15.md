# v15 — serial corruption, stale telemetry and recovery

## Evidence from the reported sessions

- `run_20260916_140605`: 731 accepted telemetry rows, all IDLE, 19 one-second
  telemetry timeouts. Text loses digits, punctuation and spaces. The parameter
  declaring `host_timeout_ms` is corrupted; v14 Python then sends no keepalive.
- `run_20260916_140828`: 334 accepted rows; after STOP at about 41.80 seconds,
  macOS reports `Device not configured` at about 41.93 seconds. Ten subsequent
  writes fail because the port is closed while the reader retries reopening it.
- `run_20260916_140943`: two one-second timeouts; the firmware name, numeric
  parameters and telemetry contain dropped characters. For example a minus sign
  disappears from a parameter and timestamps lose digits. The old parser can
  accept these as plausible numbers even though they are corrupt.

Thus the motion guard is responding to genuinely missing readable telemetry or
USB loss. Merely removing the guard would conceal those failures. These logs do
not establish whether the character loss originates in firmware scheduling,
USB/UART hardware, a cable, host serial handling or another process.

## Changes

- Firmware v15 and both Python tools use 115200 baud. Default telemetry drops
  from 50 to 25 Hz; maximum 100 Hz. Control still runs at 1 kHz; pulse timer,
  0.8/12/12/60 motion limits, gains and measured upright 3416 remain unchanged.
- All firmware replies are `@payload*HHHH\n`, CRC-16/CCITT-FALSE (initial 0xffff,
  polynomial 0x1021). Python verifies before processing/logging numeric data or
  acknowledging STOP. Human boot-ROM output may be rejected during reset.
  Host commands remain plain newline-delimited text; this checksum protects replies.
- Keepalive every 250 ms is independent of receiving `host_timeout_ms`.
- Host drains serial bytes in chunks, retains fragmented frames, bounds oversized
  frames and logs every rejected frame. A checksum mismatch cannot refresh the
  valid-telemetry timestamp or create a numeric calibration reading.
- STOP/rate recovery retries once a second until valid acknowledgment and fresh
  data arrive. Motion needs STOP acknowledgment plus three consecutive valid
  telemetry samples. Automatic commands are never replayed on reconnect.
- `link` reports the exact blocking reason and checked/rejected frame counts.
  Blocked requests are recorded in the events log. Blocked auto/balance no longer
  opens a dashboard; automatic params/stat bursts before those commands are removed.
- Raw encoder snapshots refresh cached magnet diagnostics without printing extra
  magnet messages. Recorder still saves each user-selected raw value directly.
- Old firmware can be explicitly diagnosed with `--legacy-serial` and its baud;
  that mode cannot reliably detect numeric corruption. Default operation requires v15.

## Validation

- ESP32 compile: 339,703 program bytes, 22,736 global bytes (core 3.3.2).
- C++ firmware formatter output matches Python's independent CRC implementation,
  including a known CRC test vector, STOP, negative numbers, encoder readings,
  newline handling and overlong-message rejection.
- Host tests reproduce dropped digits/minus signs and encoder-field corruption:
  corrupt values are rejected, never stored as fresh data. Tests also cover
  fragmented/combined frames, missing STOP acknowledgments, periodic retries,
  parameter-independent keepalive, USB loss/reconnect and no replay of auto.
- Existing encoder-reference, calibration recording, GPIO disable, firmware
  watchdog/parser and plot-command tests pass.
- Simulator regressions pass; these are not a USB soak test or physical balance test.

No upload or motor run was performed. The software changes improve framing,
recovery and diagnostics; they cannot establish that a physical USB fault is
removed. A continuing damaged link remains blocked until valid data returns.
Flash v15 and restart the matching console together before the next run.
