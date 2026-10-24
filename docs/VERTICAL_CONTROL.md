# Integrated vertical rail control

This feature requires **executor-v7-vertical** and the matching SDK. It adds the
vertical axes to the normal cartpole executor and interactive `cartpole-console`;
it is separate from the earlier standalone commissioning sketch.

## Confirmed installation

The owner verified on 2026-10-23 that raw `+` on the left driver moves down, and
raw `+` on the right moves up. The firmware therefore maps physical UP to left
DIR LOW / right DIR HIGH. Operator commands use `up` and `down`, not raw polarity.

| Axis / function | Teensy GPIO |
|---|---|
| Left Z1 STEP / DIR | D4 / D5 |
| Right Z2 STEP / DIR | D6 / D7 |
| Shared active-low driver enable | D8 |
| Cart STEP / DIR, unchanged | D2 / D3 |

The owner confirmed 200 mm usable stroke, supported rail with drivers disabled,
and bottom stops suitable for timed bottoming. Geometry is 200 full steps/rev,
Big Easy Driver default 1/16 microstepping, 5 mm travel/revolution: 640 pulses/mm.
These values match the commissioning defaults; NEMA 17 alone does not establish
the motor step angle. No Z encoder, contact input or stall sensor is commissioned.

## Operator commands

After installing the matching firmware and launching the new release:

```text
z status
z reference both
z move left up 5
z move right up 5
z move both up 20
z move left down 5
z move right down 5
z stop
```

`z reference both` is an **operator assertion** that both ends are physically at
the bottom. Use it only there. It does not move anything or sense the bottom.
You can reference `left` or `right` separately. Moves require the selected axes
referenced and must stay between counted 0 and the configured ceiling (120 mm by default, maximum 200 mm). Independent movement tilts
the rail; software limits cannot establish mechanically permissible tilt.

| Command | Arguments / meaning |
|---|---|
| `z status` | Phase, reference masks, counted positions, completed bottoming mask, firmware ceiling `max_mm` |
| `z limit [MM]` | Read ceiling, or set a shared ceiling for both axes (10..200 mm, default 120); stopped and healthy only |
| `z reference left/right/both` | Declare the selected current positions bottom/zero while stopped |
| `z home left/right/both` | Timed selected-axis DOWN at 40 mm/s for 5 s; stopped-only |
| `z move left/right/both up/down MM [SPEED]` | Relative physical motion, distance >0..20 mm, speed default 2 mm/s, max 40 mm/s; profile duration ≤60 s |
| `z stop` | Cancel both vertical axes; preserve a separate active cart run |
| `z sine [AMPLITUDE HZ CENTER SECONDS]` | Paired sine; defaults ±20 mm, 1 Hz, center 25 mm, duration 10 s |
| `stop` | Existing global STOP; stop and disable the entire rig |

The `left/right/both` notation means choose one word; do not type the slashes.
Commands return to the prompt while movement is running. Wait for completion
shown by `z status` before another vertical movement command. A new movement
never implicitly replaces an active one.

## Bottoming and reference

At a known physical bottom pose you may use `z reference both` directly. Otherwise:

```text
z home both
# Wait at least five seconds and inspect z status and both physical bottom ends.
z status
z reference both
```

The timed operation commands 200 mm of downward motion, including time after
contact. It does not detect or independently stop the first end that contacts,
and it is not an automatic squaring routine. Completion sets a bottoming-complete
mask but does not declare a verified reference. Reference is a separate operator
assertion after inspecting both ends and level rail. Interrupted/cancelled motion
must not be interpreted as successful bottoming.

## Disturbances alongside cart control

Start with small motion while commissioning the integrated build. Once Z is
referenced and both ends are level, an interactive native AUTO run permits a
separate vertical disturbance command:

```text
auto 20
z sine 2 0.25 25 10
z status
z stop
stop
```

The default `z sine` uses ±20 mm (40 mm peak-to-peak), not a 20 mm total excursion.
It moves to the center before the oscillation, ramps amplitude over two seconds
at each end, and finishes at center. Its steady waveform ranges from 5 to 45 mm
above bottom. At 1 Hz the requested peak speed is 125.66 mm/s (~1,508 motor RPM),
so successful pulse generation does not establish loaded motor tracking.

The existing interactive native `auto` command is asynchronous; Python controller
and learned-policy console runs occupy the prompt until they finish. Do not open
a second serial console to work around that. Concurrent external-policy use
requires orchestration through the same SDK connection; there is no implicit
queued disturbance or automatic post-reconnect start in this release.

Homing and reference changes are stopped-only. Cart HOME/REHOME and recovery paths
are not places to introduce new vertical motion. A running disturbance remains
subordinate to the existing cart run's authority and global safety conditions.

## Safety and position meaning

The cart retains its original 7 µs pulse timing and controller math. Z uses a
separate 4 µs pulse timer and bounded profiles, with physically opposite DIR
polarities. All drivers still share D8. Global STOP, controller/encoder/limit
faults, heartbeat loss and foreground timing failure stop all axes; vertical
motion does not bypass those guards. A Z-only run has a separate executor mode
(15) and never requests cart steps.

The owner confirmed mechanical support when shared enable is released. Unlike
the standalone test's hold-on-stop behavior, the normal executor's **global STOP
disables all drivers**. `z stop` leaves an independent active cart run enabled;
if Z was the only motion, the executor can disable the shared drivers.

Position is based on commanded microsteps. It does not detect lost steps,
backdrive, slips, stalls or physical skew. Reference/cancellation/fault lifecycle
must be checked in `z status`; never use the bottoming-complete flag as contact
sensor evidence. Power-up/new connection must not silently restore a physical
reference. No permanent direction or Z calibration is written to encoder EEPROM.

The existing state packet remains unchanged. Separate `V2 Z` metadata reports Z
phase, reference mask, left/right counted millimeters and bottoming-complete mask;
the SDK polls these at 20 Hz during vertical motion and records the replies in
its run log. They are counted-position snapshots, not physical encoder readings.

The SDK recognizes v7 for normal cart control, parameters, and learned policies.
Specialized research capture helpers that explicitly require v6 retain those
checks until separately commissioned on v7.

## Deployment and validation

The integrated source, compiled firmware and matching SDK must be deployed as a
pair. Do not run the standalone test client against normal executor firmware.
Use the generated release manifest and firmware checksums. Restore the previous
operator release/firmware as a pair if rolling back; leave old files intact.

The integration is staged separately before flashing. Native state-machine and
whole-sketch tests, SDK/console tests and the Teensy build are required before
handoff. The 91 native firmware checks and Teensy build pass, including changing
encoder telemetry during Z-only motion and absence of cart pulses. Hardware pulse timing, interference with cart deadlines, loaded motion
and disturbance rejection still need physical acceptance on the assembled rig.

### Staged integrated release

Release directory: `/home/rbafna/cartpole-v2-live/releases/operator-20261023-vertical`.
Preparation stages this release without changing the `active` pointer, flashing,
or moving hardware. First exit the standalone `vertical>` client with `quit` and
close other serial clients. Then, on the Jetson:

```bash
cd /home/rbafna/cartpole-v2-live/releases/operator-20261023-vertical
sha256sum -c artifacts/SHA256SUMS
~/cartpole-v2-live/tools/loader-2.3/teensy_loader_cli --mcu=TEENSY41 -w -v artifacts/teensy_executor.ino.hex
# Press the Teensy's PROGRAM button if the loader waits.
uv run cartpole
```

This explicit release directory selects the matching console without modifying
the previous active deployment. Check `info` reports `executor-v7-vertical`, then
`z status`. At the physically verified bottom, run `z reference both` and try
`z move both up 5`; wait until idle before the next command. Use `z home both`
only for the approved timed bottoming routine, then inspect and reference.

## Configurable height ceiling — operator-20261024-zlimits

Both screws default to a **120 mm maximum height above the explicitly referenced
bottom**. `z limit` reads the firmware ceiling; `z limit 100` sets both screws to
100 mm. Relative move endpoints cannot exceed it. Sine extrema retain 2 mm
clearance from bottom and ceiling, so a 120 mm ceiling permits a maximum sine
height of 118 mm. The firmware also checks each generated non-homing target before
handing it to the pulse timer. The physical stroke ceiling remains 200 mm.

Changes require the entire rig stopped, healthy, no calibration, and no Z motion.
A new limit below either referenced current position is rejected: move down first.
The setting survives a console reconnect but is RAM-only and resets to 120 mm on
firmware reboot. It is independent of controller gains and learned-policy settings;
`save`/`load` controller profiles do not change it. Timed downward homing remains
40 mm/s for 5 seconds; it is explicitly exempt from counted travel limits because
it seeks the bottom without a valid position reference.

The firmware identity remains `executor-v7-vertical`; the appended `max_mm` field
in `V2 Z` reports this capability. Use this release's matching SDK/console for Z
commands after flashing. With older firmware the new console reports `max_mm: null`,
uses a 120 mm host ceiling, and refuses custom changes until you flash. A host-only
ceiling cannot constrain other software issuing raw serial commands.

The staged release is `/home/rbafna/cartpole-v2-live/releases/operator-20261024-zlimits`.
The `cartpole-console` launcher selects it through the `active` symlink. Firmware
is **staged, not flashed**, and this deployment does not move or re-reference axes.
Close the console and stop the hardware worker before flashing to avoid serial
contention:

```bash
sudo systemctl stop cartpole-worker-hardware.service
cd ~/cartpole-v2-live/releases/operator-20261024-zlimits
sha256sum -c artifacts/SHA256SUMS
~/cartpole-v2-live/tools/loader-2.3/teensy_loader_cli --mcu=TEENSY41 -w -v artifacts/teensy_executor.ino.hex
# Press PROGRAM on the Teensy if requested.
cartpole-console
```

Then inspect `z status` / `z limit` for `max_mm: 120`. Establish the physical bottom
reference explicitly before motion; flashing invalidates counted references.
Example commands at the console:

```text
z limit
z limit 100
z status
z limit 120
```

Previous launcher target: `releases/operator-20261024`. Existing releases, policies,
controller gains, and encoder calibration files are retained. Physical acceptance
of the newly flashed build is still required; automated tests use simulated I/O.
