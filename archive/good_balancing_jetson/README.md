# Known-working balancing console

The four original Python modules, saved settings, and all 13 firmware source files
are preserved byte for byte from commit `1d48532`. Only packaging, launchers,
documentation and test wiring change in Phase 0.

## Start

From this directory on the Jetson:

```bash
uv run cartpole-console --rate 100
```

Equivalent, from any working directory:

```bash
/path/to/cartpole_v2/archive/good_balancing_jetson/run_console.sh --rate 100
```

The default device is
`/dev/serial/by-id/usb-Teensyduino_USB_Serial_20242870-if00`.
Override it with `--port DEVICE`. The launcher uses the terminal interface.
Ethernet is already supported by this baseline console:

```bash
uv run cartpole-console --host 192.168.50.2 --rate 100
```

That command requires the already-configured private Ethernet link. It does not
configure Jetson networking. Do not run USB and Ethernet controllers concurrently.
For optional local graphical plots use
`uv run --extra plot python console/cartpole.py --port DEVICE --rate 100`.

Opening the console sends `stop`, applies the preset, and verifies readback before
the prompt. It is an operator connection, not a passive telemetry subscriber.
No motion, homing, or calibration starts automatically. Importing the modules or
requesting `--help` does not open the Teensy.

## Saved tuning

`settings.json` is authoritative. Its 33 settings and 8 computed gains exactly
match `settings_verified_20261013.json` from the later successful AUTO trial.
Notable values: `pw=4.5`, `bal_pw=4.0`, `pz=0.85`, `pc1=-3`, `pc2=-4`,
`leff=0.124`, `bw=30`, `rail=0.26`, `vmax=1.5`, `jmax=150`.

The console checks firmware identity `swingup-125mm-60t-v33-teensy41`, restores
the parameters while drivers are disabled, verifies derived gains, and writes a
dated preset/readback report under `logs/`. Startup fails if verification fails.
The preset's old encoder-reference numbers are historical metadata only. Current
home/upright calibration is not overwritten. Restart this console after a board
reset to reapply the tuning; firmware defaults alone are not the saved tuning.

At the console, `params` shows readback. `home` establishes the current position as
zero; `rehome` slowly returns to an existing trustworthy step-based home. They are
different operations. Use the existing physical calibration procedure after a
mechanical change. Position is inferred from emitted steps, not independently
measured carriage movement.

## Why these files are present

| File or directory | Needed for |
|---|---|
| `console/cartpole.py` | Device transport, console, terminal/optional graphical controls, logging, rehome and startup sequence |
| `console/console_preset.py` | Loading the saved tuning and checking stopped state, firmware identity, parameter and gain readback |
| `console/vision_telemetry.py` | Nonblocking loopback encoder/health feed to vision3; does not open another serial connection |
| `console/angle_plot.py` | Small plotting transform imported by the console even in text mode; no graphical dependency itself |
| `console/launch.py` | New portable command with terminal mode and stable USB-device default; delegates to the preserved console |
| `settings.json` | The tuned runtime settings; distinct from firmware defaults and physical calibration |
| `teensy_firmware/teensy_swingup/` | The single known-working firmware source tree for reproducible rebuilds; not required merely to launch an already-flashed rig |
| `pyproject.toml`, `uv.lock`, `.python-version` | Dependency declaration, resolved dependencies and Python selection |
| `run_console.sh` | Convenience launcher that works from any directory |
| `tests/` | Offline regression and packaging verification; not runtime dependencies |

The firmware headers are components of **one sketch**, not alternate firmware
versions: `cart_mechanics.h` defines conversion and pulse ceilings;
`cart_motion.h` governs jerk-limited motion; `swing_controller.h` contains the
controller; `rail_recovery.h`, `spin_recovery.h`, and `upright_session.h` implement
mode/recovery behavior; `encoder_reference.h` and `teensy_reference_store.h` handle
angle references and EEPROM; `serial_frame.h` provides framing; `ethernet_config.h`
and `ethernet_transport.h` provide the existing network transport; and
`status_display.h` drives the status display. `teensy_swingup.ino` ties them together.

## Compile and test

Python dependencies are installed by `uv`. Matplotlib is optional for operation
and included in the development group for the retained graphical regression tests.

```bash
uv run --locked --group dev python -m unittest discover -s tests
```

Native test cases require `clang++`. Compilation uses Arduino CLI, Teensy core
1.62.0 and QNEthernet 0.37.0; the display libraries come with that Teensy core.
From this directory, compile only:

```bash
arduino-cli compile --fqbn teensy:avr:teensy41:usb=serial,speed=600,opt=o2std \
  --output-dir /tmp/cartpole-baseline-build teensy_firmware/teensy_swingup
```

This does not flash. The sketch name stays `teensy_swingup` because Arduino expects
the folder and `.ino` filename to match; its parent is now `teensy_firmware`.
There is no Phase 0 requirement to reflash the working board.
