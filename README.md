# Cartpole v2

Start here: [complete system README](SYSTEM_README.md), [command cheat sheet](COMMAND_CHEATSHEET.md), [all CLI arguments](COMMAND_REFERENCE.md), [source/evidence index](SYSTEM_REFERENCE.md), and [preservation audit](PRESERVATION_AUDIT_20261023.md).

October 23 operator release: on the Jetson, `cd ~/cartpole-v2-live/active && uv run cartpole`, or use `cartpole-console` from PATH. In the console, load `policies/working.json` (user-tested 102,400 steps) or `policies/1m.json` (1,024,000-step candidate), then use `policy check swingup` and explicit `policy swingup 25` from a settled, homed hanging start. Deployment itself performs no motion.

For the vertical-enabled runtime, use the deployment copies `policies/working.json` and `policies/1m.json`. Their weights, experiment identities, and observation/action contracts are unchanged; only the reviewed runtime pins and enclosing content digest were migrated. [Migration evidence](policies/vertical-runtime-migration.json) records the original and deployed hashes plus exact numeric inference parity. Original `training/candidates/.../actor.json` files remain immutable and pinned to their archived runtime; the strict loader intentionally refuses them under changed runtime sources. This migration does not confer hardware acceptance.

Locally, `uv run --locked --extra sim cartpole-view-policy` opens the learned Gym viewer; add `--controller reference` for the saved traditional gains on the fitted plant, or `--actor policies/1m.json` for the new candidate. See the cheat sheet for all training, evaluation, console and deployment options.

The sections below retain earlier subsystem introductions. Dated historical measurements: [2026-10-20 checkpoint](docs/checkpoint-20261020.md).

The SDK now connects to a new Teensy safety executor, runs the preserved controller
on hardware, and supports Python policies, MuJoCo simulation, policy training,
recordings, source-specific sensing, and an isolated submission queue. The working
controller and vision3 remain unchanged in `archive/`.

The real SDK/Teensy path completed a ten-second swing-up/balance trial and a slow
return to center. USB telemetry delivered up to 1,000 Hz in stopped tests; a
250 Hz zero-command loop and action expiry were also verified. This does not
establish hard real-time host control or hardware acceptance of learned policies.

## Collect the remaining system identification data

Use `./scripts/system-id-campaign` for repeatable cart-response/timing/AUTO
campaigns and guided motor-disabled angular/cart measurements. Start with
`./scripts/system-id-campaign plan`; an offline `rehearse` command exercises the
artifact/review workflow without hardware. See [collection commands, review,
and portable evidence bundles](docs/system-id-campaign.md). Collection does not
change the existing simulation or trained policy profiles.

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

See the [October 16 checkpoint](docs/checkpoint-20261016.md),
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
- [Model-bound PPO and Colab training](docs/rl-training.md): neural training,
  checkpoint resume, disjoint evaluation and a portable SDK actor using the
  governed/observed simulator. Current model scopes remain development only;
  physical model and learned-policy acceptance are separate gates.
- [Sensing and physical identification](docs/identification.md): explicit clocks,
  calibration, validity and held-out rejection. The MuJoCo plant remains provisional.
- [Runnable system-identification workflow](docs/system-identification-workflow.md):
  labelled release protocols, raw-data and frozen-fit plots, independent validation,
  scoped model export and Gym loading. [PPO and Colab](docs/rl-training.md) adds
  neural training, resumable checkpoints and a portable SDK actor using the
  governed, encoder-observed `RigCartpoleEnv`. Physical-model acceptance remains
  separate from software readiness.
  [October 17 measurements and plots](evidence/system-id-20261017/README.md) record
  the latest physical results; model acceptance for hardware RL remains open.
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

Controller authors: [SDK data and development guide](docs/CONTROLLER_DEVELOPER_GUIDE.md). The portal now requires operator approval for each physical job; the deployed worker, expanded upload formats and Vercel migration are documented in [Portal deployment](docs/PORTAL_DEPLOYMENT.md).

### Vertical screw commissioning

The separate [vertical actuator test](docs/VERTICAL_COMMISSIONING.md) documents
D4/D5 and D6/D7 wiring, independent direction checks, operator-declared bottom
reference, timed bottoming and bounded paired sine motion. It requires a temporary
standalone Teensy firmware and cannot run concurrently with pendulum controllers.
This earlier standalone commissioning path remains available for isolated checks.
The integrated `cartpole-console` implementation is described below.

### Integrated vertical controls

The [integrated vertical guide](docs/VERTICAL_CONTROL.md) covers the
`executor-v7-vertical` firmware and `z` commands in the normal console: independent
or paired physical up/down moves, timed bottoming, explicit bottom reference,
vertical STOP and finite paired disturbances. Left UP is DIR LOW; right UP is
DIR HIGH. Hardware commissioning status and staged-release instructions are in
the guide; the standalone test remains available separately.

### Policy requirements and camera recording

Learned policies own their action decisions; native swing-up/balance gains no
longer need to match their archived training snapshot. Observation filtering and
shared hardware motion/safety requirements still apply. See
[policy executor requirements](docs/policy-executor-requirements.md).

Camera recording is bounded and storage failures are reported without stopping
tracking or video. See [camera recording](docs/camera-recording.md). Portal jobs
use the same Jetson API, SQLite queue, and filesystem artifacts whether the
frontend is served through Funnel or Vercel; see
[portal deployment](docs/PORTAL_DEPLOYMENT.md).
