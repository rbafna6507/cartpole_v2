# Cart-pole on Teensy 4.1 and Jetson

The maintained swing-up controller is
[`teensy_working_jetson_compatible/teensy_swingup`](teensy_working_jetson_compatible/teensy_swingup).
`cartpole.py` is the USB/Ethernet host console. The console files in the bundle
are symlinks to the root files, so the existing bundle command still works.
Older duplicate swing-up controllers have been removed; Git history retains them.
Historical reports and ESP32 tests are under `archive/`. The separate
`teensy_pendulum_characterization` and `deployment` packages are experimental
measurement/executor tools, not the commissioned swing-up controller.

## Current hardware status — October 12, 2026

Live tuning is recorded in `experiments/20261012_balance_tuning/`.
After a fresh physical upright calibration, trials `auto_18` and `auto_19`
each captured once and remained in balance until their timed stops: 17.55 s
and 43.48 s of uninterrupted balance respectively. The user confirmed the first
run physically stayed upright. A 14-count operational reference trim then produced two further 45-second
trials with more than 42 seconds of continuous balance near center. The third
identical repeat (`auto_22`) lost balance and reached rail recovery after about
14.8 seconds. The user reported possible deliberate interference while testing
balance catching, and later confirmed pushing it when it last fell; disturbance times were not recorded. A further unchanged-settings
45-second repeat (`auto_23`) lost balance once, recaptured, and ended in balance
(two balance bouts of 16.68 s and 24.91 s). **Undisturbed repeatability remains
unproven.** The saved working settings are in `presets/teensy_jetson_20261012.json`.
The requested Jetson reference archive is `/home/rbafna/good_balancing_jetson`,
containing local and Jetson source/data snapshots and restoration instructions.

The current firmware is still `swingup-125mm-60t-v33-teensy41`; it has not been
changed or flashed during this investigation. Tests changed runtime settings and
the saved encoder reference. `rail` is a **half-length**, currently 0.26 m,
with normal predictive braking near ±0.245 m. Position comes from motor steps.
The directly captured upright count was 1425; the current saved operational
reference is 1411 after a -14-count centering trim. Raw counts are rig-specific and must not be blindly reused after
moving the encoder or arm attachment. Earlier up/down readings shifted by about
51 degrees; a single offset does not prove encoder repeatability.

A stationary-command decay fit suggests a period of 0.807 s (effective length
0.162 m). This is a provisional identification result, not the selected runtime
`leff`: changing `leff` to 0.162 also changes swing-up and capture behavior and
performed worse in the recorded comparison. The working candidate retains 0.124.

Earlier passive records and the pre-cleanup source/build snapshot are in
`experiments/20261012_swingup/`. Original firmware also remains recoverable from
Git history.

## Run on the Jetson

The Teensy USB serial number is `20242870`. Its stable device name is:

```
/dev/serial/by-id/usb-Teensyduino_USB_Serial_20242870-if00
```

The account must belong to `dialout`; reconnect after adding that group. An
existing `.venv` with pyserial is available in the Jetson repository.

```sh
ssh rbafna@jetson
cd ~/cartpole_inverted_pendulum
.venv/bin/python cartpole.py --text \
  --port /dev/serial/by-id/usb-Teensyduino_USB_Serial_20242870-if00
```

After pulling this cleanup, this root command supports `--text`. The older
bundle command also works:

```sh
cd ~/cartpole_inverted_pendulum/teensy_working_jetson_compatible
../.venv/bin/python cartpole.py --text \
  --port /dev/serial/by-id/usb-Teensyduino_USB_Serial_20242870-if00
```

Use `link`, `stat`, `params`, and `data` to inspect the connection and telemetry.
`stop` disables all drivers; support the height assembly because the shared
ENABLE line also disables the Z motors. `quit` stops and closes the console.
Close other consoles before connecting.

`home` asserts that the cart is physically centered; it does not seek endstops.
`upright` saves the encoder count while the arm is held truly upright. Repeated
upright/down checks must agree before using either `bal` or `auto`. Cart position
is inferred from emitted motor steps, not independently measured.

## Passive measurement scripts

Run `calibrate_encoder_8pos.py` for eight physical angle references and a down
repeatability check, then `characterize_period.py` for three guided free-decay
trials. Both use the current Teensy firmware with motors disabled and preserve
raw data without applying calibration. See [the measurement guide](docs/PASSIVE_MEASUREMENTS.md).

## Build

Requires Teensy core 1.62.0 and QNEthernet 0.37.0 (present on the inspected Jetson).

```sh
./flash_teensy --compile-only teensy_working_jetson_compatible/teensy_swingup
```

To upload, omit `--compile-only` and supply the actual Teensy upload port from
`arduino-cli board list`. Uploading resets the controller; physically re-establish
cart center afterward. Do not upload during a trial.

Native Ethernet details are in
[ETHERNET_README.md](teensy_working_jetson_compatible/ETHERNET_README.md).
The reviewed PCB connector and power mapping is preserved in
[PCB_WIRING.md](docs/PCB_WIRING.md).

## Verification

```sh
MPLCONFIGDIR=/tmp/cartpole-mpl .venv/bin/python -m unittest discover -s tests
.venv/bin/python teensy_working_jetson_compatible/tests/test_port.py
.venv/bin/python teensy_working_jetson_compatible/tests/test_display.py
```

Native C++ tests in `tests/` include the maintained Teensy headers. They exercise
software behavior; they cannot prove motor tracking, encoder mounting, or physical
endstop clearance. Old ESP32-only tests are retained under `archive/esp32_tests`
as historical evidence and are not the active Teensy test suite.

## Return to existing home

At the main `>>>` console prompt, type `rehome` with the cart stopped and the
pendulum hanging still. If the dashboard is open, use `q` + Enter first.
The cart returns toward its existing step-based zero at up to 40 mm/s and stops
within 1 mm. Any key cancels; completion disables all drivers. This command never
changes `home` or `upright`. It cannot detect or correct missed motor steps;
physically recenter and issue `home` if the step-based position is no longer valid.

`rehome` requires only the updated host console; the Teensy firmware is unchanged.
Live verification returned from +6.79 mm to +0.94 mm, then reported IDLE with zero
velocity. The host suite passed all 64 tests. The first test harness checked the
mode before STOP acknowledgment and was safely refused; both recordings are saved.
