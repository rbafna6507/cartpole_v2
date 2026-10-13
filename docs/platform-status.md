# Platform status after the live rig build

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
| Switches and cart homing | Verified PCB nets, NC wiring map, bounded two-end sequence and native fault tests | Soldering, wiring/direction/stop-distance/homing checks; Z mechanical mapping |

## Hardware left by this task

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

Install and commission the normally-closed switches using the
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
