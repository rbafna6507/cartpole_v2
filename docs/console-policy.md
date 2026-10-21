# Learned balance through the operator console

The console can retain a selected numeric actor and run it through its existing
Rig connection. This is a development-only, **balance-only** path: prepare a
centered, nearly stationary upright pole before checking or starting it. It does
not swing the pole up. The ordinary `auto` and `bal` commands still select the
board's native controller.

Start an interactive session using the current verified executor parameters:

```sh
./scripts/policy-console \
  --port /dev/ttyACM0 --rate 250 --keep-board-params
```

Then use:

```text
policy load /absolute/path/to/actor.json
policy status
policy check
policy shadow 1
policy run 5
policy unload
```

| Command | Behavior |
| --- | --- |
| `policy load PATH` | Validates the numeric JSON actor, its declared raw or filtered encoder contract and pinned runtime source hashes; binds the currently saved encoder reference. Does not arm, calibrate, home or write parameters. |
| `policy status` | Displays the selected path/hash, saved and current reference counts, action scale, start/run limits and telemetry rate. Status is not a readiness guarantee. |
| `policy check` | Checks the selected actor/reference, current live executor compatibility, homing/switch/magnet health and upright starting state, without arming or changing telemetry. At a different rate, reports that run/shadow will temporarily use 100 Hz. |
| `policy shadow [seconds]` | Evaluates the same balance-only actor on current telemetry while remaining disabled. Defaults to five seconds. |
| `policy run [seconds]` | Explicitly executes the selected actor for up to five seconds by default, through the existing 20 ms action leases. Accepts 0.001–60 seconds. |
| `policy unload` | Clears the console selection. |

A filtered actor receives the MCU filtered angle (`magnetic_filtered`) and
magnetic observer rate. Raw encoder angle remains a separate required guard:
start admission checks the larger absolute raw/filtered angle, and raw plus
selected state channels must remain fresh within 20 ms and mutually aligned
within one 10 ms control period. Selecting filtered input does not relax leases
or substitute a camera measurement.

Only `policy run` grants motion. It uses the actor's complete declared action
scale, at most 25 m/s², and the `rig` guard profile. Initial admission still
requires `|x| <= 0.015 m`, `|commanded velocity| <= 0.025 m/s`,
`|angle| <= 0.07 rad`, `|angular rate| <= 0.15 rad/s` and no rail braking.
After admission, the rig profile enforces the conservative trained/live rail
boundary and native speed bounds; it has no host angle or angular-rate cutoff.
The firmware's braking and hard protections remain active. These are observed
encoder and commanded step-state limits, not independently measured cart truth
or a guarantee of physical stopping distance.

Run and shadow temporarily request 100 Hz while stopped and report the change.
They STOP on completion, failure or Ctrl-C, then restore the original telemetry
rate. If a transport or latched fault prevents restoration, the console reports
that failure and the host's current rate; it does not clear the fault. Ctrl-C
during an interactive run or shadow returns to the same connected prompt.
Cyclic GC is deferred only during the bounded invocation and STOP, then its
previous state is restored. This does not remove operating-system timing jitter.

Selection lasts for this Rig session. A changed actor file or observed change to
the saved encoder reference requires another explicit `policy load`. Loading
binds the stored count; it does not establish that the pole was physically
vertical when that count was saved. Faults, unhomed state and incompatible
parameters must be addressed explicitly by the operator. Policy commands never
clear faults, run HOME, rewrite tuning or select a fallback controller.

For a one-shot invocation:

```sh
./scripts/policy-console \
  --port /dev/ttyACM0 --command policy-run \
  --actor /absolute/path/to/actor.json --development-only --duration 5
```

The one-shot command preserves live executor parameters by default and requires
the explicit development acknowledgement. The `inference` extra supplies the
NumPy backend used by the live balance runner. In interactive sessions, the existing
console startup profile is still applied unless `--keep-board-params` is supplied;
use that option when the actor was exported against the rig's current tuning.
`scripts/policy-console` requests the hardware/inference dependencies through
`uv --project` and runs `cartpole_sdk.rig.policy_console`. That thin module sets
CPython's GIL switch interval to 1 ms before entering the unchanged console, then
restores the saved interval on return or exception. Import and help create no Rig.
It does not grant real-time scheduling.

No actor is marked hardware-accepted by loading, checking, shadowing or running
it. Inspect the existing SDK JSONL trace for action timing, refusals and faults.

## Linux CPU partition for camera and control

The following is the reproducible launch for the preserved filtered BAL actor on
the Jetson release. Run it from a normal `SCHED_OTHER` operator terminal. The
operator grants that terminal's children a maximum real-time priority of 10 once;
only the control child is then placed in `SCHED_RR` priority 10. Keep `chrt` after
the launcher's `--`, so the camera-monitoring parent remains `SCHED_OTHER`.

```sh
cd ~/cartpole-v2-live/releases/id-20261021-policy-console
sudo prlimit --pid $$ --rtprio=10:10
.venv/bin/python scripts/jetson-control \
  --camera-service cartpole-vision.service \
  --camera-cpus 0-3 --control-cpus 4-5 -- \
  chrt --rr 10 .venv/bin/python -m cartpole_sdk.rig.policy_console \
  --port /dev/serial/by-id/usb-Teensyduino_USB_Serial_20242870-if00 \
  --rate 250 --keep-board-params
```

With the rig prepared for the existing balance-only start limits, use:

```text
policy load training/candidates/balance-recovery-20261021/actor.json
policy status
policy check
policy run 25
```

This is the equivalent module launch for the demonstrated console behavior. The
recorded third trial invoked the existing console through an imported function
with GIL 1 ms; the thin module makes that setting reproducible. Its offline tests
cover delegation, exception restoration, help, import, and argument forwarding.
The default log directory is `runs/rig`; `--log-dir` can name a new trace directory.

The CPU sets must be nonempty, available to the launcher, and disjoint. The
launcher reads the current user's systemd MainPID, snapshots all current camera
and descendant thread masks, and temporarily restricts them to the camera CPUs.
It tracks new threads and descendants while the control command runs. Existing
threads recover their individual masks; new ones recover their process's original
mask. PID/TID start times guard against restoring an unrelated replacement.
The launcher does not stop or restart the camera or change its own CPU affinity.
A missing camera service is an error; use `--no-camera --control-cpus 4-5` only
for intentional control-only operation.

On exit or failure the camera masks are restored and verified. A restoration
failure is reported with a nonzero exit code. Ctrl-C forwards SIGINT to the
control process group; the console can STOP its policy and return to its prompt
while the partition remains active. The launcher waits for the command to exit
normally. SIGTERM, SSH hangup (SIGHUP), or a fatal launcher error instead allow
ten seconds for STOP and cleanup before falling back to SIGTERM, then SIGKILL if
needed. The launcher needs only Python's standard library and does not change
controller parameters or Python's GIL switch interval.

## Preserved filtered BAL observations, October 21

`training/candidates/balance-recovery-20261021/actor.json` is a supervised
approximation of the actual filtered native BAL feedback law: **zero PPO updates**.
Its file SHA256 is
`9e498faf5783e278b44cad6d75e720d38a9ef0800b99d0676256c6445373a850`.
The trials used saved upright reference 450, bw 10, jerk 150 and the existing 20 ms
leases. A reference count binds a particular calibration; it does not establish
physical vertical by itself.

| Preserved trial | Requested duration | Raw angle RMS | Counted x RMS | Observation |
| --- | ---: | ---: | ---: | --- |
| `filtered-bal-run5-01` | 5 s | 1.054° | 0.0376 m | Initial bounded hold |
| `filtered-bal-run25-01` | 25 s | 1.177° | 0.0346 m | Undisturbed, per user confirmation |
| `filtered-bal-run25-02` | 25 s | 1.317° | 0.0439 m | Undisturbed, per user confirmation |
| `filtered-console-run25-03` | 25 s | 2.014° | 0.0488 m | User-reported pokes; disturbance observation |

All three long trials stopped cleanly with fault 0 and 2,499 action requests each.
The runner intentionally begins STOP about 10 ms before the executor duration;
measured enabled-to-disabled board intervals were 24.991, 24.990 and 24.991 s.
The poked trial reached raw angles −8.35…+13.62° and counted x −0.1137…+0.1194 m.
Poke strength and timing were not measured, so it is not a third undisturbed
repeat or a calibrated disturbance-rejection result. Counted x remains a step
estimate, not independent physical tracking.

The actor remains **DEVELOPMENT_ONLY, hardware_accepted=false**. These observations
do not establish long-term reliability, hardware qualification, or swing-up.
[The source-bound hardware audit](../evidence/policy-recovery-20261021/hardware-balance/report.md)
contains exact intervals, angle/position ranges, camera coverage, archive hashes,
and the reproducible offline analyzer. Later offline combined-policy work is a
separate candidate and does not change this preserved working actor.
