# Independent live-rig pre-hardware review

Review date: 2026-10-13. Repository: `/Users/rbafna/projects/cartpole_v2`.
Base/HEAD: `ffb42b10644c311cd47d38e569175f0012e8c5ca`; reviewed uncommitted live implementation.
Read-only reviewer: no source edits, commits, SSH, serial access, flashes, or physical motion.
Local native reproduction artifacts are under `/tmp/cartpole-next/review-tests`.

## Verdict

**Firmware is suitable to proceed to stopped flash/handshake validation**, subject to the firmware owner's successful real Teensy build and the parent operator's recoverable baseline/calibration preservation gate. This is not motion or physical switch commissioning approval. Current no-switch commissioning is explicit and was not treated as a defect. Production remains default switch-enabled with D26/D27 cart negative/positive and D28/D29 required healthy; no Z motion is exposed.

All five findings below have been repaired and independently retested. No open concrete blocker remains for stopped flash/handshake validation in the source identities recorded below. Physical acceptance remains separate.

## Findings and disposition

1. **P1, fixed — latch a raw homing edge until stopped debounce owns it.** `firmware/teensy_executor/teensy_executor.ino:185`, `:594` (original edge path was `:185`, foreground path `:590-606`). The original ISR only zeroed `ax_inc`. A HIGH contact followed by LOW before the next 1 ms tick left the state machine in SEEK_NEG and restored toward-limit pulses. Native reproduction printed phase SEEK_NEG, nonzero rate 24051815, energized=1. Fix adds a persistent ISR edge latch, suppresses pulses even after raw LOW, consumes the edge into VERIFY, and atomically zeros the cart increment before clearing the pending latch. The atomic zero also closes an interrupt window after a foreground rate write raced with the first edge. Regression coverage includes bounced HIGH/LOW, rate restoration, exact IRQ injection during consume, and eventual safe fault on unstable contact. Independent final native suite passed.

2. **P2, fixed — preserve the remainder of a partially transmitted line through HELLO.** `firmware/teensy_executor/teensy_executor.ino:821` and `:882` (original `:812`, `:868`). Original resetTx discarded an in-flight frame after its prefix had reached USB, concatenating it with new HELLO. A 20-byte-room native reproduction yielded `@V2 S 7 0 0 0 5 0.21@V2 HELLO 8 1 1000*A62D\n`; SDK rejected it. Fix drops unsent backlog while finishing the already visible line; native `hello_partial` passes.

3. **P2, fixed — rate-zero commands lacked state confirmation and stale stopped-state refresh.** `src/cartpole_sdk/rig/client.py:359`, `:367` (pre-repair lines). `_command_state` originally waited for a newer snapshot without requesting STATUS. Actual firmware RATE 0 has no periodic snapshots, so STOP/CENTER/SWITCHES/CLEAR time out despite valid ACKs. `_stopped_healthy` additionally refuses a snapshot older than 100 ms with no refresh API path. The PTY fake initially emitted unsolicited state after every command, masking this mismatch. Fix at current `client.py:364` and `:389` adds bounded explicit STATUS after ACK, bounded refresh of stale stopped snapshots, and rejection of motion/HOME with rate zero. PTY test suppresses unsolicited command snapshots to match the real firmware. Independently passed.

4. **P2, fixed — one-shot CLI HOME aborted immediately.** `src/cartpole_sdk/rig/console.py:119` and `src/cartpole_sdk/rig/client.py:402` (pre-repair lines). Parent identified and reviewer confirmed: `Rig.home` returns when mode 13 is observed; main then exits its context and calls STOP. The script therefore starts a seek and promptly aborts it. Fix at current `console.py:83` and `:134` adds a bounded completion wait with fault/interrupt/finally-stop handling. Follow-up review also corrected the default timeout: 10 s cannot complete the minimum 0.4 m span at 0.03 m/s; omitted HOME duration now defaults to 60 s (`console.py:106`, `:113`), while motion stays 10 s and an explicit shorter HOME timeout is honored. PTY completion regression and all eight console tests independently passed. Measured span and safe rail are internal firmware values; current V2 S has no fields for them, so no CLI output should claim to have measured them independently.

5. **P2, fixed — tolerate bounded pre-HELLO stream resynchronization.** `src/cartpole_sdk/rig/client.py:230`, `:299`; `src/cartpole_sdk/rig/transport.py:17` (pre-repair lines). Opening serial resets buffered input while a firmware line may already be in flight. Receiving only its tail before a valid new HELLO currently latches ProtocolError. Independent PTY reproduction: connect returns with `ProtocolError('invalid framing')`, then the first center operation fails. Old-session ERR replies before HELLO also hit the strict wrong-session guard. Fix at current `client.py:232`, `:281` adds bounded pre-handshake discard/resynchronization, retains the command timeout, and switches back to strict parsing after matching HELLO. PTY regression passed; repeating the independent old-tail reproduction now returns error=None and permits center.

No additional concrete firmware or SDK safety/protocol blocker was found in the final reviewed snapshot.

## Verification performed

- Initial independent suite: 34 `test_rig*.py` tests passed; 21 `test_executor_native.py` tests passed.
- Independent native review reproductions: transient raw homing edge resumed seek; partial TX HELLO produced a malformed combined frame. Evidence: `review-tests/edge.txt`, `review-tests/hello.txt`, snapshot/probe sources alongside them.
- Independent PTY connection reproduction of initial old-frame tail preceding valid HELLO confirmed latched connection error.
- Repaired firmware independent suite: **24 tests passed**, including `bounced_isr_edge`, `edge_consume_race`, `hello_partial`, ISR stall/limit/center guards, mode watchdogs, action age/TTL/sequence/wrap, source wire compatibility, and EEPROM3485 preservation.
- Repaired SDK independent suite: **37 tests passed**, including rate-zero stopped command confirmation, stale stopped snapshot refresh, pre-HELLO partial tail/old-session ERR handling, asynchronous HOME completion, and strict corruption/lease/failure checks. After the HOME default correction, all eight console tests passed again; independent partial-tail reproduction also passed.
- Commands: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest discover -s tests -p test_executor_native.py -v` and the equivalent `-p 'test_rig*.py'`.
- The production controller/mechanics/motion/encoder-reference/storage helper files match the preserved archive; meaningful live changes are in the new executor core, homing machine, and sketch integration.
- Source review confirms nonzero exclusive session IDs; no HELLO while enabled; strict finite decimal actions; anchored <=50-tick expiry and <=20-tick observed age; sequence monotonicity within a lease; PING cannot renew actions; 200-tick host watchdog; <=60 s experiment lifetime; homed healthy gates; foreground missed-period fault and independent >5 ms pulse ISR cutoff; no recovery pump for external mode.
- Switch/homing review confirms enabled profile defaults, all four raw channels sampled by pulse ISR, unexpected limit fail-stop, no initial-active homing, bounded seek/backoff/repeat/center stages, min/max span checks, measured rail clamped to the preserved saved rail with margin, exact pulse-side center stop, and no Z step commands in the exposed protocol.

## Declined to judge / remaining separate acceptance gates

- Physical contact polarity/direction/wiring, switch placement, mechanical stop distance, inertia/coast after disabling, motor tracking/lost steps, and shared-enable effects on the Z assembly. No switches are installed; missing hardware was not counted as an implementation failure.
- Actual flash/reboot behavior, exact live EEPROM contents after flash, and recovery of the known-working binary. Native EEPROM3485 preservation is a software check, not a physical readback.
- Measured 100/250/500/1000 Hz delivery, actual foreground/ISR jitter under USB/SPI/I2C load, and MCU disconnected/stalled transport behavior. These require the planned stopped hardware tests.
- Sensor physical health: current `enc_ok` means successful raw-angle I2C reads. Ongoing magnet MD/ML/MH quality is not part of this flag; native tests do not certify magnetic attachment or measurement validity.
- Physical switch homing completion/rail span and Z switch role mapping. There is no Z motion authorization from this review.
- Reference swing-up/balance performance, external host policy timing/acceptance, identification results, and untrusted-process/container/queue isolation. These are downstream phases.
- Absolute guarantee of absence of interrupt races: the review covered concrete ISR/foreground shared paths and added adversarial injection for the found edge race; the host stub is not a cycle-accurate Teensy model.

## Reviewed firmware identities

SHA-256 at final firmware re-review:

- `teensy_executor.ino`: `0cae0120c3d21b3fe72fc23d2e6ef6b240db4b6cdcdf48b039ef1549a7d15b4f`
- `executor_core.h`: `b503969c8bfe6ee47f0712b91b559b7df53349c0035d5ad44f02d052d83b1450`
- `cart_homing.h`: `d2e5356bfdd5eac391802434c04b7631f4fd6962b7c163f1c770d9b22584c54f`
- `teensy_reference_store.h`: `3f271a9d5441f6337668c68b1d5e2467aa602c8977dc98b1badc54f603dd6e4d`

Final SDK SHA-256:

- `src/cartpole_sdk/rig/client.py`: `d161746671eb4ff78a03d78ccbb946d0f887fea9c401c3c608cb6d4748c35eff`
- `src/cartpole_sdk/rig/console.py`: `3d739d4c4216696fd5ba579c9c28ce29af9dcba79f3b0f644bd235e2d39a1dff`
- `src/cartpole_sdk/rig/protocol.py`: `3ea81063ea99fb8e0c8f92c577d07cd0a6c4741732179aaa1efe466d6aa937fc`

## Focused follow-up: INFO, magnet health, viewer lock (2026-10-13)

**Verdict unchanged: suitable for stopped flash/handshake validation after target build and baseline preservation. No new actuation blocker found.** Read-only review; no SSH, serial, hardware, GUI operation, or project edits.

- `executor_core.h:59` and `teensy_executor.ino:901`: INFO is an exact-argument, matching-session, disabled-only query; it does not refresh leases, enable drivers, change EEPROM, or modify reference coordinates. The 11-field payload fits its fixed buffer. `protocol.py:130`, `client.py:257`, `client.py:554` strictly parse identity, integers, reference/saved/status/span ranges, and finite positive <=0.26 m rail, retain receipt time, and return the actual reply while stopped (including fault diagnosis). `executor-v1` identifies a firmware family, not a unique binary: retain source/build hashes separately.
- `teensy_executor.ino:357`, `:363`, `:552`: 100 Hz STATUS-only checks require MD with neither ML nor MH, a successful status read no older than 20 ms using wrap-safe microseconds, and successful current 1 kHz angle reads. Invalid health reaches Core.sample before control and disables/invalidate-home on an active lease. Independent pulse-side stall protection remains. This supersedes the earlier report's I2C-only magnet-health limitation. Native tests cover healthy, weak, strong, absent, status-read failure, and angle-read failure; actual 100 Hz status transaction load remains a stopped-hardware timing measurement.
- **P3 nonblocking diagnostic inconsistency:** `teensy_executor.ino:1064` still passes I2C-only `enc_ok && enc_consec_err==0` to the LCD snapshot. The LCD can therefore show ENCODER: OK during a magnet fault although mode, telemetry, and physical cutoff are correct. Parent and firmware owner notified to use `encoderHealthy()`; not a flash blocker.
- INFO now makes loaded EEPROM calibration/reference_saved, home epoch, measured span, and effective rail externally inspectable. This supersedes the earlier report's statement that span/rail are unavailable on the wire. Live EEPROM3485/readback and actual switch geometry still require parent hardware evidence.
- Viewer: `src/cartpole_sdk/sim/viewer.py:164` and `:190` submit overlays outside `viewer.lock()`; camera/scene/data mutations remain inside. The regression in `tests/test_viewer.py:132` meaningfully rejects both initial and repeated overlay submission under the mutex. No issue found in this focused two-call change. Native GUI behavior was reported by the parent, not independently operated by this reviewer.

Independent verification: **34 firmware native tests, 41 rig SDK tests, 14 viewer tests passed.** Additionally compiled the production sketch through the existing native harness and decoded real `info_snapshot` and `info_homed` frames with production `decode/parse_info`: snapshot reported reference3485/saved=true/rail0.26; homed case reported span10668 and rail0.195025.

Follow-up SHA-256 identities:

- `teensy_executor.ino`: `e7c24ef427ca63ec222a9a516bbcbf855545df75a6497738200b0c725962fabe`
- `executor_core.h`: `1252ecc4a5faa169bf9f605d88e24efeb3f31282deb2296b2a1ba85d6fbd717d`
- `rig/client.py`: `da88ee569232c17d92b46b9050b302aeb173a75c0468365e3334723bb48f8168`
- `rig/protocol.py`: `86c890b6bfe7d1d7cc4425e1af1e0e838502d062c15e90ba3b7e8c57dd25196b`
- `rig/console.py`: `2e9ec3afb83a0452b904f4f43d8f9681d1239a5d1768d515bf73cb50633e7be5`
- `sim/viewer.py`: `795d23539f77bbdbc801e8db8adeeb3d741bee2005c3ffc44d524bfa8eca1ee4`
