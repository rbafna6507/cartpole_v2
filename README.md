# Cartpole v2

Phase 0 packages the known-working controller and vision3 for repeatable launches.
The Python SDK, new Teensy executor, and MuJoCo backend are the next development
steps; they are not implemented here yet.

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
The tunnel uses the native IPv6 destination and public host key recorded on
October 13; both are configurable. It does not start software on the Jetson.

- [Jetson setup and testing](docs/jetson-testing.md)
- [Archive contents and recovery](archive/README.md)
- [Console, gains, and firmware](archive/good_balancing_jetson/README.md)
- [Vision, calibration, and system dependencies](archive/vision3/README.md)
- [Control rates, languages, and transport choice](docs/control-timing-and-transport.md)
- [Revised v2 architecture](docs/architecture.md)
- [Phase 0 plan and decisions](docs/phase0-plan.md)
- [Local verification](evidence/phase0/verification.json)

Both projects pin Python 3.11 for `uv` and include a universal `uv.lock`. Their
commands are intended to run from an editable repository checkout; this archive
is not a standalone wheel distribution. Do not copy `.venv` between computers.

No Jetson access, camera capture, firmware upload, or physical motion was performed
during Phase 0. Limit switches are not implemented yet. New control or vision
work must use new directories outside the preserved archived baselines.
