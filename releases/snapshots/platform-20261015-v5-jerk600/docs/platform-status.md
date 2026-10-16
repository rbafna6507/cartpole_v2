# Platform status after the live rig build

## Current continuation, 2026-10-15

The current SDK checkout on the Jetson is `~/cartpole_v2`. The board runs
`executor-v4-rehome`, with both cart switches enabled, measured stroke 619.2 mm,
and working upright encoder reference 351 (owner-selected natural upright rest). Stopped integration checks ended at
home with drivers disabled and no fault. Earlier firmware/release details below
are historical.

The maintained `cartpole-vision.service` provides persistent camera, overlay,
mask, plots and metadata over a private Tailscale viewing endpoint. The console
now publishes encoder telemetry automatically from its existing serial owner.
Actual SDK shadow fusion was verified in repeated stopped live runs. The final
25-second stream run accepted 898 camera corrections, with no history truncation
or pending drops and explicit stale status after the monitor stopped. Capture
averaged 75.65 FPS, tracking 39.14 FPS, and preview 39.98 FPS with the SDK and one
visible viewer active. Calibration and timing gates remain unchanged; fusion is
ineligible for motion control.
See [vision usage](vision-usage.md) and [SDK sensing](sensing.md).

Source now supports validated, installation-specific hanging calibration models
and stricter capture stability. The corresponding `executor-v5-calmodel` build
passes compilation/native tests but has not been flashed. Existing measurements
show inconsistent hanging-to-upright offsets and do not qualify for an approved
model. No guessed correction was installed. Subsequent assisted captures yielded
331 and 351 counts; 351 is the current saved working reference. The camera was
repositioned between those captures, invalidating the earlier camera alignment.

Reliable fast swing-up/balance remains unresolved after the fixture/motor changes.
Bounded native tuning resumed using the owner-approved working reference.
Four repeated automatic trials at pw 4.5/6 reached capture but did not sustain
balance; the longest balance episode was 1.332 seconds. A separate balance-only
trial remained near upright for 3.684 seconds before the conservative 120 mm
position guard stopped it. The next trial will compare jerk 300 with 150 after
a verified motor-power-off firmware update; current v4 rejects values above 150.
The v5 source ceiling is now 600, while its boot default remains 150.

Earlier sensing verification: All vision and sensing tests passed in the final regression run. The complete
suite reported 658 passed, seven skipped and one timing-sensitive PTY controller
failure; an earlier run failed a different simulated-worker deadline check.
Those scheduling failures are preserved in evidence, and production safety
deadlines were not relaxed. The browser timing/plot tests also passed (19 tests).
Detailed evidence is in `evidence/phase3/retuning-20261015` and
`evidence/phase4/vision-service-20261015`.

## Historical platform build

The SDK can command real swing-up and balance through the new safety executor.
The saved controller still runs on the Teensy at 1 kHz. The Python path also has
bounded external acceleration, host policies, MuJoCo, policy training, a portal,
and an isolated Linux worker. Hardware acceptance is narrower than the available
software: the learned policy has not controlled the physical rig.

| Capability | Evidence | Remaining acceptance |
| --- | --- | --- |
| Preserved controller through SDK | 10 s powered run, 6.08 s in balance, maximum step-derived displacement 0.19605 m; slow return near center | Longer repeatability and load tests |
| External Python commands | 250 Hz zero command and four 20 s bounded characterization runs; 20 ms action expiry disables | Full host swing-up/balance and learned hardware policy |
| Telemetry | Stopped 100/250/500/1000 Hz checks without new MCU misses or active-reader drops | Sensor-to-action latency and scheduling tails under representative load |
| MuJoCo viewer | Native macOS rendering, Space pause, R reset; overlay lock deadlock fixed | Plant parameters remain provisional |
| Host policies and RL | 100/250 Hz source-explicit controller, CEM training, held-out evaluation, and exported learned policy completing 1,000 actions / 10 simulated seconds inside the Jetson sandbox | Hardware transfer, delay/noise robustness |
| Vision adapter | Separate new provider with explicit clocks, frames, calibration and validity | Independent angle/cart calibration; fused estimator and physical vision control |
| Physical identification | Separate train/held-out recordings and strict rejection reports | No accepted model: training excitation, residual and calibration consistency still fail |
| Upload/queue/worker | Authentication, immutable artifacts, bounded queue ownership, real Linux namespace/seccomp tests | Public TLS/accounts, quotas/retention/monitoring, physical switch commissioning |
| Switches and cart homing | Verified PCB nets, NC wiring map, bounded two-end sequence and native fault tests | Installed cart switches need wiring/direction/stop-distance/homing checks; Z mechanical mapping |

## Cart switch update, 2026-10-14

The owner has installed switch 1 at the left cart end and switch 2 at the right;
3/4 are uninstalled. The `executor-v2-cart2` update requires those two cart
inputs consistently at every start, clear, homing and ISR gate, reports all four
raw inputs, and prohibits Z pulse output. The previous all-four profile explains
`HOME: health` with flags 201. Local regression tests and the Teensy build pass;
upload and physical switch/direction/homing acceptance remain pending. See
`evidence/phase3/cart-switches-20261014/verification.json` for build provenance.
The new console also decodes raw switch inputs in `status` and adds explicit
`upright`/`hanging` stable encoder capture with verified EEPROM persistence.
Today's tiny-step runs had a resting angle near -104 degrees versus yesterday's
174 degrees, with the same saved reference and no new runtime misses or I2C
errors. The preserved controller therefore omitted its near-hanging startup
kick. Why the physical angle/count relationship changed remains unverified;
calibration and both-pose checks are required before further control tests.

## Historical hardware state after the 2026-10-13 build

The motor supply was last confirmed on by the owner. The executor is idle with
all drivers disabled, zero fault, default switch checking enabled and no valid
home. The missing switches therefore block ordinary arming. EEPROM upright
reference 3485 is saved and unchanged; encoder status is 0x67 with zero I2C errors.
The cart was returned near the established center. Step-derived position is not
an independent physical cart measurement.

Do not reset, unplug board power or upload firmware with motor power on. Clicking
occurred while the failed initial upload left the board in its bootloader. Motor
power was switched off before recovery. The PCB lacks a hardware default-disable
bias on the shared enable line; firmware cannot protect motion while absent.
See [programming evidence](../evidence/phase3/programming-incident.json) and
[executor programming instructions](executor.md). No further reset/upload occurred
with motor power on.

## Run the software

On this Mac, from `/Users/rbafna/projects/cartpole_v2`:

```bash
uv run --locked --extra sim cartpole-v2-view
```

The native viewer intentionally freezes at its 30 s episode limit. Press R to
restart. Its reference policy is distinct from the 100 Hz learned policy.

The clean Jetson SDK release is staged separately at
`~/cartpole-v2-live/releases/platform-20261013`; the original checkout and archive
remain untouched. From that release, inspect the stopped executor:

```bash
uv run --locked --extra hardware cartpole-console \
  --port /dev/serial/by-id/usb-Teensyduino_USB_Serial_20242870-if00 --command info
```

Read [rig usage](rig-usage.md) for explicit commissioning and motion commands,
[policies](policies.md) for training/export, and [portal](portal.md) for the
loopback service and trusted worker. The archived console uses the original v33
wire protocol and does not control the newly installed executor.

## Next physical work

Commission the installed normally-closed cart switches using the
[PCB map](pcb-switches.md), and provide a verified hardware default-disable state
through reset. Before changing the simulation, establish an independent angle
reference and calibrated cart displacement, then collect passive-decay and new
held-out forced records. The stronger characterization fit was not accepted by
loosening thresholds or overwriting the working calibration.

Only after containment and sensing are commissioned should full host-policy and
learned-policy trials progress to the rig. Public hardware jobs remain gated on
a healthy physical home and switch profile. Recovery of an expired worker also
requires terminating or quarantining the old process before releasing the rig;
a queue token alone cannot fence a suspended process from later resuming.

## Final software verification

The maintained local suite passed **313 tests and 171 subtests**, with six
Linux-only cases skipped locally. On the Jetson the complete portal suite passed
**48 tests**, with two non-Linux cases skipped. The actual exported learned policy
completed ten simulated seconds under Bubblewrap/seccomp. Simulation has a finite
wall budget of twice its requested horizon; physical duration and action deadlines
remain unchanged. The wheel was installed outside the checkout, its 51 package
files matched source, CLI entrypoints and web assets were checked, and all 70
archived source hashes remained unchanged.

[Machine-readable verification](../evidence/platform-verification.json),
[Linux test log](../evidence/phase6/linux-final-tests.log), and
[independent review](../evidence/phase6/independent-review.md) preserve scope,
failures repaired, hashes and remaining limits.
