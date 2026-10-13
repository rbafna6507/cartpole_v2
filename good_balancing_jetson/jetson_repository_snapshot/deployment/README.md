# Cart-pendulum deployment starter

This directory contains a trusted Teensy executor, a Python SDK, a MuJoCo rig and
a data collection / fitting workflow. It is a commissioning foundation: the code
is tested locally, while physical timing, tracking and the current assembly still
need bench validation. No firmware was flashed or public service deployed.

The baseline is `../teensy_swingup_ethernet/teensy_swingup`. The initial model uses
the historical 125 mm arm, 11.05 g arm mass and two 5.85 g tip weights. The current
assembly is **unconfirmed**. Its saved free-swing fit supplies an initial effective
length and damping; cart mass, COM and drive parameters remain provisional.

## What is included

| Component | Entry point | Behavior |
|---|---|---|
| Teensy 4.1 firmware | `firmware/deployment_executor/` | Cart acceleration, velocity and position targets; encoder/state; local governor, short command leases and latched faults |
| Python SDK | `src/cartpole_deploy/hardware.py` | Explicit home/arm/command/stop over private Ethernet or USB; no automatic enable/retry |
| MuJoCo backend | `src/cartpole_deploy/simulation.py` | Same SDK methods, explicit simulated time, quantized encoder and bounded actuator |
| Gymnasium environment | `src/cartpole_deploy/gym_env.py` | Acceleration actions, seeded episodes and explicit termination; training scaffold |
| Characterization | `cartpole-deploy capture/fit/validate/export` | Timestamped CSV + metadata, passive dynamics fit, independent-release validation and new config export |

This uses MuJoCo's existing physics and Python API; a custom compiled MuJoCo
plugin is unnecessary for the current rig. Python runs the same controller against
`SimRig` or `HardwareRig`. It is API-compatible simulation, not execution of the
Teensy binary inside MuJoCo. The C++ governor is separately compared against its
Python counterpart in tests.

## Start in simulation

From this directory, with Python 3.10 or newer:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[sim,serial,test]'
cartpole-deploy info
python examples/controller.py
cartpole-deploy capture decay --seconds 8 --output runs/sim-fit
cartpole-deploy fit runs/sim-fit/samples.csv --release-s 0 --cart-clamped --output runs/sim-fit.json
cartpole-deploy capture decay --seconds 8 --angle-deg 40 --output runs/sim-validation
cartpole-deploy validate runs/sim-validation/samples.csv --fit runs/sim-fit.json --release-s 0 --cart-clamped --output runs/sim-validation.json
cartpole-deploy export --fit runs/sim-fit.json --validation runs/sim-validation.json --output runs/rig-fitted.json
cartpole-deploy --config runs/rig-fitted.json info
```

Each capture/output is new; existing measurements are never silently overwritten.
These commands collect simulated data. [Characterization instructions](docs/characterization.md)
cover actual hardware capture, release-window selection and what the fit can identify.

Optional GUI: `cartpole-deploy view`. On macOS use
`mjpython -m cartpole_deploy view` because the passive viewer needs MuJoCo's launcher.
The GUI is not part of the headless validation.

## Hardware scope and first connection

Read [firmware and commissioning](docs/firmware.md) before replacing a sketch.
Compile only with `sh firmware/build.sh`; this does not flash a device. Install
the documented Teensy board core and QNEthernet library in Arduino CLI first.
After the owner has installed and checked this firmware, a passive private-link read is:

```sh
cartpole-deploy --backend hardware --host 192.168.50.2 info
cartpole-deploy --backend hardware stream --sensor encoder --seconds 10 --hz 100
```

The legacy firmware uses a different protocol and cannot be driven by this SDK.
No driver is enabled by connecting or reading. Before motion, verify the physical
enable circuit, encoder zero/sign, manual cart center, travel limits and a local
means of removing drive power. Shared enable pin 8 also energizes the Z drivers;
secure that mechanism. This version produces no Z pulses. It has no implemented
IMU or limit-switch input.

Hardware `x/v/a` describe emitted steps and the commanded profile, **not measured
cart motion**. Disabling drive does not guarantee braking or holding. Independent
position feedback and a hardware inhibit are prerequisites for unattended public
experiments. The Teensy safety code only protects the boundaries it can observe.

## Next architecture

Use Vercel for the site/authentication/job API, private object storage for uploads,
and an outbound Jetson worker for execution. Give one trusted local broker the
Teensy connection. The worker and read-only `sensorshare` subscribers use the
broker; user programs never receive direct access to the Teensy socket or devices.
Upload submission is separate from permission to execute.

The [Internet and sensorshare design](docs/internet.md) includes upload handling,
artifact contracts, local timing, sandbox boundaries and a suggested sensor schema.
Those services and ONNX execution are design work in this version, not implemented
public endpoints. Your CLI can start with encoder/state; `imu` should report
unsupported until a real IMU driver and calibration exist.

More detail: [SDK](docs/sdk.md), [simulation](docs/simulation.md),
[characterization](docs/characterization.md), [validation](VALIDATION.md),
[design](docs/design.md).

Run checks with `python -m pytest -q` and `sh tests/native/run.sh`.
