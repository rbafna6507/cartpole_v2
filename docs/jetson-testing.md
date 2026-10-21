# Jetson test handoff

Phase 0 was checked locally. The owner performs the following Jetson checks;
no remote processes, firmware uploads or live captures were run by this change.
This is packaging of the current controller, not installation of new safety firmware.

## Copy and prepare

Copy `archive/good_balancing_jetson` and `archive/vision3` from this checkout to
the corresponding locations under your chosen Jetson `cartpole_v2` directory.
Include `pyproject.toml`, `uv.lock`, and `.python-version`, but exclude `.venv`,
`__pycache__`, `*.egg-info`, `logs`, and `runs`. The relative vision `console`
symlink must stay intact for the combined integration tests. Git clones do not
include ignored recordings; those are unnecessary for launch.

`uv` must be installed. It creates each local environment and can obtain Python
3.11 if needed. The video helper still needs the existing Jetson system GStreamer
runtime; use the prerequisite check in the vision README.

## First launch

1. Stop and close the existing balancing console using its normal procedure.
   Close the existing vision app so it releases the camera and port 3090.
2. From the Jetson repository root, run:

   ```bash
   uv run --project archive/good_balancing_jetson cartpole-console --rate 100
   ```

   Expected: `Preset verified` with 33 settings, the saved firmware identity,
   and disabled drivers. No motion should start. `params` should show `pw=4.5`,
   `bal_pw=4`, `rail=0.26`, and `bw=30`. Keep this console open for encoder telemetry.

3. In a separate Jetson terminal:

   ```bash
   cd archive/vision3
   uv run vision3 --camera /dev/video0 --calibration-file last_calibration.json
   ```

   Expected: loopback server on port 3090 and a new session under `runs/`.
   The saved camera geometry must still match; otherwise set a fresh hanging
   reference. A valid angle calibration does not establish cart meters.

4. On the Mac, from this repository root:

   ```bash
   ./archive/vision-tunnel.sh
   ```

   Open http://127.0.0.1:3095/ after SSH connects. With no destination, the helper
   discovers the current direct IPv6 through authenticated `ssh jetson` using
   only `ip -j -6 addr show scope global`, then probes candidate SSH addresses.
   It retains your configured user, keys and bootstrap host-key identity, with
   strict verification enabled. Bootstrap discovery needs an available SSH
   key/agent; the final tunnel can prompt for your normal password.

   To check the selected command without opening the tunnel, run
   `./archive/vision-tunnel.sh --print-command`. If discovery is unavailable,
   `./archive/vision-tunnel.sh rbafna@jetson` explicitly uses your configured route
   (which can have poor video performance), or pass a current destination using
   `JETSON_SSH_TARGET`. See `archive/README.md` for overrides. Do not disable host
   verification to work around a mismatch.

5. Confirm the separate camera, valid-angle, valid-velocity and encoder counters;
   inspect raw and fused traces while the rig remains stopped. Smooth video alone
   is not successful tracking. Check that stale/missing inputs remain visible.

6. Once you have checked physical home/reference and the stopped setup, use the
   same supervised operating procedure as the known-working console. No reflash
   is required by Phase 0. The saved tuning does not overwrite fresh upright or
   home calibration. Limit switches remain future work.

## Useful overrides

```bash
uv run --project archive/good_balancing_jetson cartpole-console --port /dev/ttyACM0 --rate 100
uv run --project archive/good_balancing_jetson cartpole-console --host 192.168.50.2 --rate 100
uv run --project archive/vision3 vision3 --help
```

The Ethernet example requires the existing private-link network configuration.
Only one console should own the rig. Help commands do not open devices.

Save the console's preset JSON report, vision `session.json`, `final_report.json`,
and any observed launch errors for comparison. A clean Ctrl-C shutdown writes the
vision final report. Tunnel Ctrl-C only closes the viewer connection; it does not
stop either Jetson application or command the rig.
