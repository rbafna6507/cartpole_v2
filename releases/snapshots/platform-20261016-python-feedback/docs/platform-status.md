# Platform status after the live rig build

See the [2026-10-16 checkpoint](checkpoint-20261016.md) for the current
system-ID, Python control, vision/fusion and release-preservation status.

## Console default and jitter comparison, 2026-10-16

The preserved bandwidth-10 profile is now the verified console startup default.
Six further trials compared bandwidth10/9/8 with all other settings fixed.
Bandwidth8 showed less rapid command variation in repeated matched windows and
completed a 60-second AUTO run (56.716 seconds continuous balance after capture),
including return. It is saved separately as
`profiles/candidate-20261016-smoother-bw8.json`; it has not replaced the default.
Capture was slower in two of its three trials. All six trials ended healthy at
home with no new I2C errors or missed control deadlines. The board was restored
to all 40 original default settings, reference330, home epoch9, span16509 steps,
and left disabled. No firmware upload/reset occurred. See
[jitter evidence](../evidence/phase3/jitter-20261016/README.txt) and
[console usage](rig-usage.md).

## Current continuation, 2026-10-16

The native encoder-only tuning batch completed 58 AUTO experiments. Routine
trial duration is now 25 seconds in the diagnostic harness. The console now
loads the preserved bandwidth-10 profile while stopped by default; its default
run duration is unchanged. Use `--keep-board-params` to opt out or
`--startup-profile PATH` for a different profile. Diagnostic CLI commands remain
read-only with respect to tuning. The best saved candidate is
`profiles/candidate-20261016-bw10.json`, available locally and in the active
Jetson release `~/cartpole-v2-live/releases/platform-20261015-v6-tunable`.
All 40 stored settings were verified against stopped-board readback. It excludes
measured rail geometry. Main changes are observer bandwidth `bw=10` and
`pw=3`; jerk stays at 150 m/s³, speed ceilings at 1.5 m/s, and `leff=.124`.

Two trials captured at 2.496/2.526 seconds and held continuously for
57.504/57.472 seconds until their scheduled 60-second endpoint. The latest
completed automatic REHOME and stopped healthy at counted zero. Across eight
candidate attempts, seven were balancing at the planned endpoint, two after a
recapture. The remaining attempt failed its first catch, entered the swing-up
loop, and later stopped on one encoder I²C error. Thus capture/recovery is not
yet robust. A stronger swing-energy gain `ke=5` failed and was reverted to 4.
Rightward displacement improved in the long holds, but residual oscillation and
positive mean cart position remain; neither drift nor true angle bias is solved.

The first 60-second hold subsequently stopped during REHOME because of a
103 ms host receive-to-record processing/scheduling pause. Board ticks continued
normally. A separate guarded return succeeded. The final long confirmation used
a smaller diagnostic record ring and deferred duplicate report conversion,
without relaxing watchdogs; it completed normally. This does not prove the
latency issue fixed or identify GC as its original cause.

The final state is stopped, disabled, homed, fault 0, missed deadlines 0,
cumulative I²C errors 5. After that recovered encoder fault, physical HOME
measured 16,510 steps / 619.125 mm, epoch 8; normal travel boundary is ±294.075 mm.
Reference 330 is an experimental constant trim from today's fresh resting-upright
reference 362, not a validated hanging/nonlinear calibration model. Stable
hanging was recorded before AUTO without overwriting that reference. The tuning
profile does not set the reference. Vision/fusion was not used for control.
No firmware upload/reset occurred in this batch.

See [complete tuning record](../evidence/phase3/retuning-20261016/README.txt),
[comparison data](../evidence/phase3/retuning-20261016/session-comparison.json),
and [filtering comparison](../evidence/phase3/retuning-20261016/filtering-comparison.png).
The following October 15 continuation is historical and its paused/testing
status is superseded by this record.

## Historical continuation, 2026-10-15

The active Jetson release is
`~/cartpole-v2-live/releases/platform-20261015-v6-tunable`. The board runs
`executor-v6-measuredrail`, uploaded with confirmed motor power off and verified
healthy/disabled before power was restored. Both cart switches are enabled.
Fresh homing measured 16514 steps (619.275 mm); the normal envelope is
±294.15 mm, approximately 95% of switch-to-switch travel. The SDK exposes all
41 live motion/tuning settings. Software verification passed 691 tests with
7 skips and 381 subtests; the Teensy build and independent review passed.

The current saved upright reference is **330 counts**. During the latest tuning,
the user's usual upright resting pose read -1.837° with the former reference351.
A stationary capture saved330 and then read0.012° on average. With matched gains,
the first subsequent run's mean balancing cart position was+5.3 mm, compared
with+106.3 mm in the earlier comparison run. This supports a reference-bias
contribution to the rightward displacement; it does not establish repeatability
or prove whether the difference came from sensor movement or pose repeatability.
A nonlinear angle model remains unapproved. Each experiment verifies and records
settled hanging without overwriting the direct upright reference.

Autonomous tuning uses encoder feedback only: native control runs at1 kHz and
SDK telemetry at250 Hz. Vision is observation-only. Sustained low-oscillation
balance is not yet established. Four isolated I²C transaction errors stopped
motion; the second was followed by60 seconds disabled with no additional errors.
After the user's explicit instruction to continue, the fault was cleared and
physical homing repeated. The hardware fault stop remains active. The last observed trial is saved in `profiles/last-observed-20261015.json` and
was restored/read back while disabled. It captured after1.342s and held balance
for6.044s before rail recovery; the run later ended on encoder fault4. The user
reported liking its behavior. This is not sustained-stability acceptance. The
exact archived working profile is saved separately as
`profiles/original-working-20261012.json`. It was loaded and verified, but its
20-second comparison was rejected by automatic approval review after the four
recurring sensor errors, so it has not been AUTO-tested in this comparison.
Testing is paused at the user’s request. The rig was left homed and disabled.
Inspect the moving encoder connection before further powered trials. Profiles
are not loaded implicitly by the console. See
`evidence/phase3/retuning-20261015/tunable-motion/postcapture/result.json`.

Earlier firmware/release and trial details below are historical.

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
has been compiled, tested and flashed with motor power off. Existing measurements
show inconsistent hanging-to-upright offsets and do not qualify for an approved
model. No guessed correction was installed. Subsequent assisted captures yielded
331 and 351 counts; 351 is the current saved working reference. The camera was
repositioned between those captures, invalidating the earlier camera alignment.

Reliable fast swing-up/balance remains unresolved after the fixture/motor changes.
Bounded native tuning resumed using the owner-approved working reference.
Four repeated automatic trials at pw 4.5/6 reached capture but did not sustain
balance; the longest balance episode was 1.332 seconds. A separate balance-only
trial remained near upright for 3.684 seconds before the conservative 120 mm
position guard stopped it. The next trials compare jerk300 with150 after fresh homing on the verified v5
firmware. Older v4 firmware rejects values above150.
The v5 ceiling is now600, while its boot default remains150. Final software
verification passed662tests,7skips and358subtests; one earlier PTY lease-timing
failure and its successful132-test recheck are preserved in higher-jerk evidence.

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

### Measured travel correction deployed 2026-10-15

Homing measured 619.0875 mm, but v5 normal stopping boundaries were only 490 mm
apart (79.15% of travel). The deployed v6 firmware computes a conservative 95%
normal envelope from switch measurements, preserving the existing jerk-aware
braking and independent switches. Current geometry yields 588.075 mm normal
travel. The subsequent deployed measurement is 619.275 mm, with 588.3 mm normal travel.

Native tuning with pc1=-5, pc2=-6, jerk 150 produced two 8 s AUTO trials with
uninterrupted balance from roughly 2.6 s to expiry, but a 20 s repetition lost
balance and triggered rail recovery. Jerk 225 and 300 did not improve these trials.
These are promising short runs, not established reliable tuning. Reference 351
remains the working encoder reference; no camera calibration model or fused
physical control has been commissioned. The rig was left disabled at home.

The user requested runtime motion customization in the same update. V6 now adds
11 stopped-only settings (41 total), including measured rail fraction/margins,
rail recovery and saved-home return. Speed can be set up to the physical pulse
ceiling; acceleration/jerk validation ranges were expanded while keeping actual
boot values unchanged. Verification, staging, upload and physical home validation are complete. The
initial comparison retained Q gains, speed1.5 m/s, acceleration25 m/s² and
jerk150 m/s³. Later experiments compare feedback gains, jerk and estimator
bandwidth; consult the dated evidence rather than treating a trial as a default.


## 2026-10-16 paused hardware / local SDK increment

Hardware remains paused until the user declares readiness. First resumed motion
baseline: archived gains with former >40s holds, jerk150m/s³, freshly captured
working upright, and unchanged health preflight. No deployment or hardware I/O
occurred in this increment. Local native-log identification, Python auto/bal
entry points, and profile-configurable executor simulation are documented in
[paused-development-status.md](paused-development-status.md). Physical Python
control, hanging-only calibration, and fusion feedback remain unvalidated.
