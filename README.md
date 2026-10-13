# Cartpole v2

The Python SDK now supports explicit sensor channels, validated acceleration
intents, recordings and deterministic local replay. The known-working controller
and vision3 remain preserved under `archive/`. Live SDK control, the new Teensy
executor and MuJoCo are subsequent milestones.

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
Run tests with `uv run --locked python -m unittest discover -s tests`.

## Run the baseline

On the Jetson, from this repository's root, with `uv` installed:

```bash
uv run --project archive/good_balancing_jetson cartpole-console --rate 100
```

The console restores the saved tuning while stopped, verifies 33 parameters and
8 computed gains, and opens the terminal interface. It does not start motion or
restore an old home/upright reference. Close any other Teensy console first.

In a separate Jetson terminal, with no other camera owner:

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
using `ssh jetson`, then verifies reachability and reuses the trusted host identity.
It needs a working bootstrap SSH key/agent; the final connection can still ask for
your normal password. To preview the selection, use
`./archive/vision-tunnel.sh --print-command`. An explicit destination bypasses
discovery: `./archive/vision-tunnel.sh jetson` uses the configured route.
It does not start the camera or control the rig.

- [Jetson setup and testing](docs/jetson-testing.md)
- [Archive contents and recovery](archive/README.md)
- [Console, gains, and firmware](archive/good_balancing_jetson/README.md)
- [Vision, calibration, and system dependencies](archive/vision3/README.md)
- [Control rates, languages, and transport choice](docs/control-timing-and-transport.md)
- [Revised v2 architecture](docs/architecture.md)
- [Phase 1 implementation plan](docs/phase1-plan.md)
- [Phase 0 plan and decisions](docs/phase0-plan.md)
- [Phase 1 verification](evidence/phase1/verification.json)
- [Phase 0 verification](evidence/phase0/verification.json)

Both projects pin Python 3.11 for `uv` and include a universal `uv.lock`. Their
commands are intended to run from an editable repository checkout; this archive
is not a standalone wheel distribution. Do not copy `.venv` between computers.

No Jetson access, camera capture, firmware upload, or physical motion was performed
during Phase 0. Limit switches are not implemented yet. New control or vision
work must use new directories outside the preserved archived baselines.
