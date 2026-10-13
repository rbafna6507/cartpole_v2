# Encoder and pendulum measurements on the Jetson

These scripts use the existing `swingup-125mm-60t-v33-teensy41` firmware and its
USB raw-encoder snapshots. They do not use the experimental `deployment/`
architecture or require a firmware upload. They send only STOP, heartbeat,
parameter, telemetry-rate and encoder-read requests. They do not set `home`,
`zero`, `upright`, gains, or motion limits, and never enable motors.

## Install / copy

Copy these five Python files together into the Jetson repository root:

- `calibrate_encoder_8pos.py`
- `characterize_period.py`
- `passive_capture.py`
- `cartpole.py`
- `angle_plot.py`

The supplied `passive_measurement_tools.tar.gz` contains those files and this
guide. Extract it in `~/cartpole_inverted_pendulum`. It updates the root host
console to the existing Jetson-compatible implementation; it does not change
firmware. The existing repository `.venv` already contains pyserial. No NumPy,
SciPy, GUI, or matplotlib is required for these scripts.

Close other serial consoles. Fix the cart so it cannot move, and support the
height assembly: STOP disables all drivers, including the Z axes.

## 1. Eight-position encoder capture

```sh
cd ~/cartpole_inverted_pendulum
.venv/bin/python calibrate_encoder_8pos.py
```

The default port is the known Teensy:
`/dev/serial/by-id/usb-Teensyduino_USB_Serial_20242870-if00`.
Use `--port DEVICE` if it changes.

Choose one viewing side and describe it when prompted. Starting at down, move
clockwise through 0°, 45°, 90°, 135°, 180° (upright), 225°, 270°, and 315°.
Use an independent physical angle guide; do not position from the encoder.
Press Enter at each pose and hold still until `SAVED` appears, about two seconds.
A ninth reading at 360°/down checks return-to-position repeatability. Take the
full turn only if the arm is mechanically free to do so.

The report contains the raw readings, spread, direction, offset-only residuals,
and closure error. Its 2°/3°/5° review thresholds are diagnostic heuristics, not
proof of control accuracy. Readings are retained even when the pose is unsteady
or spacing is irregular. Invalid/stale sensor replies or unexpected motor enable
stop acquisition and preserve partial logs. No correction is written to firmware.

## 2. Passive period capture

```sh
.venv/bin/python characterize_period.py
```

Default: three trials, approximately 20° displacement **from hanging down**,
30 seconds per release, alternating left/right from your viewpoint.

For each trial:

1. Let the arm hang still; press Enter to capture its resting baseline.
2. Lift it about 20° to the requested side and hold it. Press Enter.
3. Watch the three-second countdown; release without pushing at `RELEASE NOW`.
4. Leave it untouched until capture finishes. Record any contact, push, cart
   movement or timing issue when asked.
5. Let it settle fully and press Enter for the final resting baseline.

Optional longer acquisition:

```sh
.venv/bin/python characterize_period.py --seconds 45 --trials 3 --angle 20
```

The script requests 100 Hz angle telemetry and captures raw encoder snapshots
at approximately 20 Hz. Actual board timestamps, intervals, release markers,
CRC rejection counts and sensor flags are preserved. Period and damping will be
fitted afterward from the recorded motion, considering amplitude and calibration
quality; the script does not invent a fit from a poor release.

## Return the data

Each command prints a new directory under `experiments/`, named
`encoder_8pos_TIMESTAMP` or `pendulum_period_TIMESTAMP`. Send **both entire
directories**, not just `report.json`. They contain:

- `report.json`: firmware parameters, pose/release instructions, exact capture
  windows, operator notes, summaries and completion status;
- per-phase `.jsonl`: timestamped raw encoder readings with AGC/status, validity,
  I²C errors and driver state;
- `serial/`: original checksummed receive-event log and high-rate telemetry CSV.

The serial log also spans prompts and can contain startup backlog. Use the
per-phase board-time windows and release markers when selecting data for a fit.
`zero_raw` in encoder snapshots is the relative tick origin; the saved upright
reference is `parameters.encoder_upright_raw` in the report.

`q` at a position prompt or Ctrl-C stops the script. Completed readings and any
partial current capture remain on disk. Exit requests STOP and telemetry rate
25 Hz. Do not disconnect the board or start another console during capture.
After an interruption, start a new run; the scripts never overwrite or append
to a previous output directory. `--output NEW_DIRECTORY` selects a custom path.
