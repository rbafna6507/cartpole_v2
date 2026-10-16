The Teensy 4.1 executor in `firmware/teensy_executor` is a separate copy of the preserved v33 controller. Its portable controller, estimator, governor and recovery headers remain byte-for-byte copies. The new sketch fixes all 30 cart parameters to the saved working settings at boot, including `pw=4.5`, `bal_pw=4`, `rail=.26`, `vmax=1.5`, `amax=25` and `jmax=150`. Wire commands cannot change those safety limits. The EEPROM encoder reference format and bytes 0–7 are unchanged; setup reads a valid saved reference and never restores the historical settings-file calibration. A native test specifically preserves reference 3485 and every EEPROM byte across setup.

Boot establishes shared enable GPIO 8 HIGH before step outputs and starts disabled and unhomed. The `executor-v2-cart2` and `executor-v3-encguard` builds require installed cart switches 1/D26 (left) and 2/D27 (right) LOW. The owner confirmed on 2026-10-14 that only these two switches are installed. Uninstalled inputs 3/D28 and 4/D29 remain visible in raw telemetry but are excluded from homing, clear, arm and pulse-interrupt interlocks through the same compile-time required mask `0x03`. Both Z step outputs are blocked in rate setting and the ISR; they cannot move in this build. The earlier `executor-v1` build required all four LOW and rejected this installation with `HOME: health`. HIGH means pressed or broken/unplugged, and is represented by flags 16/32/64/128. An open or missing required cart switch therefore blocks motion. This profile never detects or enables itself from input levels. `V2 SWITCHES sid 0` is an explicit stopped-only commissioning bypass; `V2 CENTER sid` is allowed only with that bypass, stopped and healthy. It declares the present cart position to be center and does not establish a physical end reference. Reset restores switch checking and discards home. Enabling switch checking invalidates a commissioning home and requires `HOME`. Public commands never move either Z motor.

Commands and replies use `@PAYLOAD*HHHH\n`, CRC16/CCITT-FALSE over exact payload bytes, with at most 255 bytes per line. Bounded input discards an oversized or non-ASCII line through newline. Strict argument counts, decimal uint32 parsing, finite decimal floats and exact session matching reject malformed commands before changing actuation. The sole unframed fallback is the literal `stop`. No historical unframed motion, tuning, Z or calibration command is exposed. The new framed stopped-only calibration command is described below. A stopped-only `V2 INFO sid` request returns the CRC-protected 11-token snapshot `V2 INFO sid executor-v2-cart2 encoder_upright_raw reference_saved mag_status i2c_errors home_epoch measured_span_steps rail_half_m`. It reports the encoder reference loaded from valid EEPROM, current cached AS5600 STATUS, cumulative angle/status I2C errors, and the active home epoch/span/effective rail. It never alters calibration, home, timers or actuation. The wire contract is documented in `docs/specs/live-rig-platform.md` and implemented by the SDK protocol parser.

`HELLO` is stopped-only, changes the session without arming, discards stale transmit work and invalidates actions. `ARM` selects external mode 12, initially demanding zero acceleration; `MODE auto|bal|manual` selects preserved trusted controller modes. `bal` also requires the preserved upright start conditions. Every motion experiment is limited to 1–60000 board ticks. A valid `PING` refreshes only the 200-tick host watchdog. External acceleration and manual velocity require their first action within 20 ticks. Actions require increasing nonzero sequence, an observation at most 20 ticks old, TTL 1–50 ticks, and a strictly future expiry at acceptance; expiry occurs exactly at the boundary, including uint32 wrap. Ping cannot extend an action or experiment. Acceleration is limited to ±25 m/s², then passes once through the original jerk/speed/rail governor. Manual velocity requests are limited to ±0.15 m/s with .5 m/s² and 10 m/s³ limits. Policy modes do not invoke the reference controller's automatic recovery pump.

`STOP` disables immediately and retains the home unless a hard fault already invalidated it. Faults remain latched across stop/session changes. The SDK also latches executor command rejections and requests STOP even if the board fault code is zero. Once the cause is corrected and both required cart inputs are closed, use `stop` then `clear`; neither command starts motion or establishes home. `CENTER` remains deliberately unavailable with switches enabled: use `HOME` to measure the physical cart span. A faulted stopped board reports original mode 4 until an explicit healthy `CLEAR`; clear never enables or homes. Hard encoder, physical limit, timing, rail, controller and homing faults invalidate home. Encoder health requires a successful fresh angle read and a successful AS5600 STATUS read no more than 20 ms old in actual board microseconds, with MD (bit 5) set and ML/MH (bits 4/3) clear. The control tick reads only STATUS every 10 ticks (100 Hz); AGC is not polled in the running control loop. A failed status transaction, magnet loss, weak/strong indication or expired status makes health false and stops an active run. Status transaction failures increment the I2C error count. The extra I2C transaction retains the deadline and ISR stall guards; its physical bus cost still requires target measurement. Expired action, host or duration faults disable; their step coordinate can remain referenced. Fault codes are:

| Code | Meaning |
| --- | --- |
| 0 | None |
| 1 | Action expired |
| 2 | Host watchdog |
| 3 | Experiment duration |
| 4 | Encoder read health |
| 5 | Raw NC limit |
| 6 | Control deadline or ISR stall |
| 7 | Hard software rail |
| 8 | Reference controller fault |
| 9 | Homing fault |

The scheduler performs one actual 1 kHz control tick and does not catch up with repeated stale samples. A missed full period while energized faults. The original step ISR retains an independent >5 ms cutoff even if I2C or the foreground stalls. It samples all four raw NC inputs on every 7 µs invocation before generating a pulse. Unexpected required input HIGH disables all three drivers through shared GPIO 8, clears increments and latches an input fault. An expected homing edge stops cart pulses immediately and remains latched across bounce and concurrent rate setting until foreground qualification. The handoff atomically zeros the cart rate before clearing the latch; qualification debounce happens while stopped. The ISR checks its stall cutoff before returning for an expected homing edge. Native tests exercise this ordering directly.

`HOME` owns cart motion in mode 13 and requires five consecutive board ticks with healthy closed inputs. The confirmed installation maps D26 to the left/negative cart end and D27 to the right/positive end; motor direction still needs physical commissioning. D28/D29 are uninstalled diagnostics only, and Z motion is prohibited. The portable state machine performs negative seek, stopped qualification, finite release/backoff, slower repeat latch, clearance, the equivalent positive sequence, span validation and midpoint centering. Seek/backoff/center speed is .03 m/s, repeat approach .01 m/s, contact/release qualification five ticks, clearance 134 steps (approximately 5 mm), backoff at most 534 steps and 1.5 s, other phases at most 16000 steps and 25 s, and the whole run at most 60 s. It rejects active-at-start, contradictory/opposite cart inputs, excessive chatter, stuck HIGH release, missing trigger, time/travel violations and spans outside 10667–16000 steps (approximately .40–.60 m). Stop, heartbeat loss and duration expiry cancel motion. During centering the ISR suppresses further pulses at the exact integer midpoint rather than relying on 1 kHz polling.

Successful homing disables, declares that midpoint to be zero and sets `homed`. The effective software rail becomes `min(saved .26 m, smaller counted edge half-span − .005 m)`. Existing governor and hard-fault margins apply inside this bound. The saved controller gains are unchanged. The measured width is based on commanded steps, not independent cart position measurement; lost steps cannot be detected by this PCB.

Telemetry is the exact 17-field `V2 S` payload following `V2 S`: session, tick, acquisition microseconds, mode, flags, raw theta, filtered theta, filtered omega, step-derived x, commanded velocity, governed acceleration, raw demand, last action sequence, fault, deadline misses, dropped frames and braking direction. This is 19 whitespace tokens including `V2 S`. Tick and microseconds wrap independently. Rates 0/100/250/500/1000 publish the latest control snapshot. The transmitter has a bounded four-reply queue, one latest snapshot and one current frame; an unsent snapshot is replaced instead of accumulating a historical FIFO. A partial frame finishes to preserve line framing. USB never blocks control waiting for transmit capacity.

Local verification uses actual portable production headers and a native translation unit of the new sketch. The whole-sketch harness substitutes only ARM `primask` assembly with a native interrupt-mask stub; controller/governor, session handlers, telemetry, scheduler and ISR logic are unchanged. Arduino/Wire/EEPROM/LCD/IntervalTimer are peripheral fixtures, so native results do not certify electrical behavior or physical motion. Run:

```sh
.venv/bin/python -m unittest discover -s tests -p 'test_executor*.py'
arduino-cli compile --fqbn teensy:avr:teensy41 --build-path /tmp/cartpole-executor-build firmware/teensy_executor
```

Compilation, host handshake/rates, motion cutoff, reference controller acceptance and physical homing commissioning are separate gates. Local compilation and native tests are recorded in `evidence/phase3/firmware-provenance.json`. Before physical HOME, verify assembled pin routing, NC polarity/disconnect response, cart direction, available travel, Z support under shared disable, contact stop latency and repeatability using `docs/pcb-switches.md`. The direction/span constants have not yet been physically commissioned with the new switches. No worker accessed a device, flashed firmware or ran hardware motion.

## Programming and reset: motor power must be off

Switch off the motor supply before uploading firmware, requesting a bootloader
reboot, or changing USB/board power. Leave the Jetson and Teensy USB connected.
The PCB has no hardware pull-up holding shared active-low ENABLE D8 disabled
while the Teensy is reset or in its bootloader. Firmware safety cannot operate in
that state. During the 2026-10-13 upload attempt the owner reported clicking;
motor power was switched off before recovery. A floating enable/step input is a
plausible cause, not a measured electrical diagnosis.

Teensy Loader CLI 2.2 reached the bootloader but failed on the first write. The
current official 2.3 source increases the first-block timeout from 5 to 45 seconds;
that uploader successfully programmed this rig. Preserve the recovery HEX and
verify the new build hash before upload. The trusted Teensy core's USB CDC
134-baud reset can request its bootloader without direct access to the normal
USB vendor interface; this is still a reset and requires motor power off.

Before motor power is restored, verify a stopped/disabled executor and current
calibration. A hardware default-disable pull-up/interlock, plus stable inactive
step inputs through reset, remains a PCB/assembled-circuit commissioning task.
Do not treat the software switch profile as protection during programming.

## Explicit encoder reference capture

`V2 CALIBRATE sid upright|hanging` requires stopped, healthy, unfaulted state.
Unlike ordinary commands, its `V2 OK sid CALIBRATE` is deferred until capture
and EEPROM verification complete. Capture uses 400 consecutive fresh healthy
samples with a maximum whole-window span of four counts, a five-second elapsed
deadline and the 200-tick host heartbeat watchdog. The core refuses ARM, MODE,
HOME, CENTER and overlapping capture while calibration is active. State flag
256 reports capture/persistence pending. STOP and a new stopped HELLO cancel
unfinished work. This operation neither enables drivers nor changes cart home
or switch configuration; it may run before physical homing.

Persistence executes outside the control tick with drivers disabled. The live
angle reference and estimator are updated only after `teensy_reference_store`
verifies the saved count. The EEPROM layout is unchanged. Failed capture leaves
the old reference; failed persistence preserves the old live reference and
reports whether its existing saved record remains valid. Error replies include
`encoder`, `calibration_timeout`, `calibration_watchdog`, `calibration_state` and
`save`. The SDK cancels on failure/interruption and never interprets an initial
request as completed calibration. Native tests cover deferred success, up/down
poses, reboot persistence, motion guards, STOP cancellation, unstable capture,
unhealthy magnet, lost heartbeat and EEPROM write failure.


## Encoder operating-mode verification (2026-10-14)

`executor-v3-encguard` retains the cart-only switch profile and unchanged saved
controller gains. It reads back AS5600 CONF after configuration, after bus
recovery, and every 10 control ticks (offset five ticks from STATUS polling).
Health requires a successful read no older than 20 ms and
`(CONF & 0x3F0F) == 0x0300`: normal power, watchdog off, hysteresis off,
2x slow filter, fast-filter threshold off. A mismatch or failed read disables
an active run through encoder fault 4 and invalidates home. It never silently
repairs configuration during motion. Boot/recovery uses read-modify-write and
verified readback, retaining reserved and output-stage bits. No OTP burn occurs.

Stopped `INFO` reads CONF immediately and updates cached health before another
command can arm. Its 17-token reply is:

```
V2 INFO sid executor-v3-encguard encoder_upright_raw reference_saved mag_status i2c_errors home_epoch measured_span_steps rail_half_m encoder_boot_conf encoder_conf encoder_conf_valid encoder_raw encoder_raw_age_us encoder_recoveries
```

Configuration values are decimal, with -1 for a failed read. `encoder_boot_conf`
captures the register before setup writes it; `encoder_conf` is current readback.
`encoder_raw_age_us` means time since the raw count last **changed**, not time
since the last successful transaction. A stationary pole can legitimately have
a large age. It is diagnostic, not a blanket stale-angle fault. The SDK accepts
the old 11-token INFO layouts and leaves the new fields unknown for older boards.

The slow-run recordings contain 100–110 ms angle plateaus, compared with angle
changes almost every 10 ms telemetry frame in the earlier fast run on the same
firmware. AS5600 LPM3 has a nominal 100 ms polling period; register readback and
physical validation are required before concluding that mode caused this run.
See the [manufacturer datasheet, register map and power modes](https://cdn.sparkfun.com/assets/f/a/b/b/a/AS5600_Datasheet.pdf).
Recorded analysis and regression results are in
`evidence/phase3/encoder-cadence-20261014/`. Compilation and native tests alone
do not establish live timing, sensor freshness, motor tracking or successful swing-up.
