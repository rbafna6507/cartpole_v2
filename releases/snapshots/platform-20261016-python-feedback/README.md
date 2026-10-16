# Cartpole v2

The SDK now connects to a new Teensy safety executor, runs the preserved controller
on hardware, and supports Python policies, MuJoCo simulation, policy training,
recordings, source-specific sensing, and an isolated submission queue. The working
controller and vision3 remain unchanged in `archive/`.

The real SDK/Teensy path completed a ten-second swing-up/balance trial and a slow
return to center. USB telemetry delivered up to 1,000 Hz in stopped tests; a
250 Hz zero-command loop and action expiry were also verified. This does not
establish hard real-time host control or hardware acceptance of learned policies.

## Open the interactive demo

```bash
uv run --locked --extra sim cartpole-v2-view
```

Space pauses, R resets, and Esc exits. The command selects `mjpython` on macOS.
The initial overlay deadlock is fixed and native rendering/pause/reset have been
verified. Episodes intentionally freeze at 30 simulated seconds until R.
See [viewer controls and verification](docs/viewer.md).

## Use the new firmware and SDK

With the executor already installed, inspect the stopped board on the Jetson:

```bash
uv run --locked --extra hardware cartpole-console \
  --port /dev/serial/by-id/usb-Teensyduino_USB_Serial_20242870-if00 --command info
```

The console also provides `auto`, `bal`, external policies, homing, and explicit
switchless commissioning. Read [rig usage](docs/rig-usage.md) before motion and
[executor protocol and programming](docs/executor.md) before uploading firmware.
**Motor power must be off during every flash, bootloader entry, or board reset.**
The existing PCB does not hold the shared enable input disabled without firmware;
clicking was observed during programming and the board was recovered with motor
power off. A hardware default-disable circuit remains necessary.

[PCB switch wiring](docs/pcb-switches.md) specifies normally-closed contacts.
Switch 1 is the left cart limit and switch 2 the right. Physical two-end homing
measured 619.2 mm of travel; `rehome` returns to the established center. Only these
two switches are required for cart motion. Uninstalled D28/D29 remain diagnostic
inputs, Z pulses are disabled, and every boot enables the cart switch interlock.
See [current commands and commissioning evidence](docs/rig-usage.md).

The current operator release is `platform-20261015-v6-tunable`, running
`executor-v6-measuredrail`. The console loads the preserved bandwidth-10 gains
by default (`pw=3`, jerk 150 m/s³). Repeated native AUTO trials captured in about
2.5 seconds; two 60-second trials held continuously for about 57.5 seconds after
capture. A separate bandwidth-8 smoothing candidate also completed a 60-second
trial with return. These are measured bounded results, not unlimited stability.
The working encoder reference is 330 counts, an experimental constant trim;
there is still no accepted hanging-only or nonlinear calibration model.

See the [current task checkpoint](docs/checkpoint-20261016.md),
[tuning and jitter evidence](evidence/phase3/jitter-20261016/README.txt), and
[preserved Jetson releases](releases/README.md). The experimental Python AUTO/BAL implementation now runs through the SDK on the
physical rig. One 25-second Python AUTO trial captured at 3.17 seconds and held
for the remaining 21.8 seconds; other trials exposed host timing and an early
right-switch stop. It is not yet a repeatably commissioned replacement for native
control. See [Python control, gain explanations and identification](docs/python-control-20261016.md).
Release snapshots preserve the established native operator software separately.

## Persistent vision and SDK sensing

The maintained camera runtime is `src/cartpole_vision`; `archive/vision3` stays
unchanged. The Jetson's `cartpole-vision.service` keeps the camera portal running
independently of the console. From a computer on the same Tailscale network:

```sh
python3 scripts/vision-view.py --host 100.126.59.18 --port 13090
```

Open **http://127.0.0.1:13090/**. The portal provides camera, tracked overlay, green
mask, measured rates and plots. The v2 console automatically publishes its
accepted encoder telemetry; closing it marks encoder readings stale while the
camera continues. The camera service never opens serial. An isolated vision
environment prevents normal console installs from removing its dependencies.

[Vision setup and measured performance](docs/vision-usage.md) describes the private
viewer, SSH fallback, service and camera configuration. [SDK sensing](docs/sensing.md)
describes explicit frames and timestamps, the actual shadow fusion monitor, and
hanging model validation. Shadow fusion was verified against stopped live data;
it remains uncommissioned and does not control motion.

## Policies, identification and the portal

- [Host-rate Python control and reproducible RL](docs/policies.md): separate
  100/250 Hz controllers, raw-demand executor simulation, training and held-out
  evaluation. The learned artifact is numeric JSON; hardware transfer is unproven.
- [Sensing and physical identification](docs/identification.md): explicit clocks,
  calibration, validity and held-out rejection. The MuJoCo plant remains provisional.
- [Portal and isolated worker](docs/portal.md): authenticated immutable uploads,
  durable single-rig queue, results and a Linux sandbox. The service defaults to
  loopback. Public hosting and learned-policy hardware acceptance remain deployment gates.
- [Current implementation and acceptance state](docs/platform-status.md).
- [Detailed execution plan](docs/live-rig-plan.md).

## Try the controller in simulation

```bash
mkdir -p runs/demo
uv run --locked --extra sim cartpole-v2 simulate runs/demo/swingup --steps 10000
uv run --locked --extra sim cartpole-v2 simulate runs/demo/upright --start upright --steps 10000
uv run --locked --extra sim python examples/gym_rollout.py --steps 200 --seed 7
```

The first two commands save observations, action/plant traces, model and parameters
in new directories. The model uses provisional physical parameters; successful
simulation does not establish hardware transfer. See [Phase 2 usage](docs/phase2-usage.md)
for custom Python policies, Gymnasium, sensor timing, model configuration and limits.

## Try the Python SDK locally

```bash
mkdir -p runs/sdk-demo
uv run --locked cartpole-v2 import-vision tests/fixtures/vision-real.jsonl runs/sdk-demo/vision.jsonl --session-id demo-vision --frame-id vision:demo-calibration
uv run --locked cartpole-v2 inspect runs/sdk-demo/vision.jsonl
uv run --locked python examples/replay_policy.py runs/sdk-demo/vision.jsonl runs/sdk-demo/my-policy.jsonl --frame-id vision:demo-calibration
```

Edit `MyPolicy` in `examples/replay_policy.py` to experiment. The example receives
real recorded vision observations and writes acceleration requests to a local
trace. Replay uses fixed inputs; it does not simulate the resulting rig motion.
The example is an illustrative mapping, not the tuned balancing controller.
Outputs are never overwritten; choose fresh paths when repeating commands.

See [SDK usage, data semantics and next integrations](docs/phase1-usage.md).
Run maintained tests with
`uv run --locked --extra sim --extra hardware --extra vision --group dev python -m pytest`
(C++17 compiler required for native firmware tests). Archived projects retain
their own separate environments and test commands.

## Run the baseline

The archived console requires the original v33 firmware. The currently installed
executor uses the new console above; the two wire protocols are different. Restore
an archived firmware only with motor power off. With v33 installed, run from the
repository root on the Jetson:

```bash
uv run --project archive/good_balancing_jetson cartpole-console --rate 100
```

The console restores the saved tuning while stopped, verifies 33 parameters and
8 computed gains, and opens the terminal interface. It does not start motion or
restore an old home/upright reference. Close any other Teensy console first.

To use the preserved camera baseline instead of the maintained service, first stop
`cartpole-vision.service`, then run in a separate Jetson terminal with no other
camera owner:

```bash
cd archive/vision3
uv run vision3 --camera /dev/video0 --calibration-file last_calibration.json
```

On the Mac, from the repository root:

```bash
./archive/vision-tunnel.sh
```

After SSH connects, open **http://127.0.0.1:3095/**. Keep the tunnel terminal open.
The tunnel discovers the current direct IPv6 address through a read-only query
using `ssh rbafna@jetson`, then verifies reachability and reuses the trusted host identity.
It needs a working bootstrap SSH key/agent; the final connection can still ask for
your normal password. To preview the selection, use
`./archive/vision-tunnel.sh --print-command`. An explicit destination bypasses
discovery: `./archive/vision-tunnel.sh rbafna@jetson` uses the configured route.
It does not start the camera or control the rig.

- [Jetson setup and testing](docs/jetson-testing.md)
- [Archive contents and recovery](archive/README.md)
- [Console, gains, and firmware](archive/good_balancing_jetson/README.md)
- [Vision, calibration, and system dependencies](archive/vision3/README.md)
- [Control rates, languages, and transport choice](docs/control-timing-and-transport.md)
- [Revised v2 architecture](docs/architecture.md)
- [Phase 2 implementation plan](docs/phase2-plan.md)
- [Phase 2 verification](evidence/phase2/verification.json)
- [Phase 1 implementation plan](docs/phase1-plan.md)
- [Phase 0 plan and decisions](docs/phase0-plan.md)
- [Phase 1 verification](evidence/phase1/verification.json)
- [Phase 0 verification](evidence/phase0/verification.json)

Both projects pin Python 3.11 for `uv` and include a universal `uv.lock`. Their
commands are intended to run from an editable repository checkout; this archive
is not a standalone wheel distribution. Do not copy `.venv` between computers.

No Jetson access, camera capture, firmware upload, or physical motion was performed
during Phase 0. New control and vision work uses directories outside the preserved archived
baselines; later physical work is recorded under `evidence/phase3` and `phase4`.
