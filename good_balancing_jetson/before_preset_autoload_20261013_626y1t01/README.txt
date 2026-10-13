GOOD BALANCING JETSON - October 12, 2026 tuning snapshot

Firmware: swingup-125mm-60t-v33-teensy41. No firmware change or flash during tuning.
Current AUTO settings: pw=4.5, pz=.85, pc1=-3, pc2=-4, leff=.124, bw=30.
Rail half-length .26m; runtime speed ceiling 1.5m/s; approach/catch .3m/s.
Full runtime readback, encoder and stopped state: final_state.json.

Results: auto_20 and auto_21 held continuously over42s each. auto_22 lost
balance; user reported possible deliberate interference, without timestamps.
auto_23 repeated identical settings for45s, lost once, recaptured, and finished
balanced (balance bouts16.683s and24.905s). These are working settings, not proof
of uninterrupted repeatability. All failures are preserved in the data.
Cart returned near home after auto_23, x=-.00094m, drivers disabled.
Position is inferred from motor steps, not an independent physical measurement.

CONTENTS
local_repository_snapshot: current Mac source tree, cleanup, analysis, presets,
  passive measurement scripts, experiments and pre-cleanup source/build backups.
jetson_repository_snapshot: original Jetson tree and all its recordings.
executed_tools: exact live trial and recenter scripts used from /tmp.
settings.json / restore_parameters.txt: AUTO settings and console commands.
trial_summary.json: aggregate measured trial metrics.
manifest.json: source commits, uncommitted status, exclusions and transfer hash.
SHA256SUMS: per-file integrity checks for this saved directory.

RUN THE SAVED CONSOLE (does not start motion)
cd ~/good_balancing_jetson/local_repository_snapshot
~/cartpole_inverted_pendulum/.venv/bin/python cartpole.py --text --port /dev/serial/by-id/usb-Teensyduino_USB_Serial_20242870-if00

Then paste restore_parameters.txt commands into that console. These stop drivers,
restore runtime AUTO settings and request a readback; they do not home, calibrate,
or start AUTO. Inspect params before starting a supervised run. Runtime set
parameters are lost on board reset; encoder upright reference is saved in EEPROM.
The current upright reference is1411 (physical capture1425 minus14-count trim).
Do not blindly apply that raw reference after moving the arm, magnet or sensor.
Only issue home with the cart physically centered. STOP disables all drivers.
The upright-only bal mode is separate and was not validated with this preset.

DEPENDENCIES
Python virtualenvs are excluded; command above reuses the existing Jetson venv.
For an independent console environment, create a Python3 venv and install
pyserial. Numpy/scipy are needed for analysis; matplotlib for graphical plotting.
Git internals, dependency environments, caches and build/build_teensy directories
are excluded; specifically named baseline_build/source_baseline are included.
No repository commits, pushes or firmware uploads are performed by this archive.

REHOME UPDATE
Launch the saved console with ~/good_balancing_jetson/run_console.sh
At >>>, type rehome while stopped and hanging still. If in the dashboard,
q + Enter returns to >>>. Any key cancels rehome. It returns at <=40mm/s to
within1mm of existing home and disables drivers; it never resets home/upright.
It cannot recover from missed steps: physically recenter and set home if needed.
The active original Jetson console also has this command. The original files
remain in before_rehome_console and jetson_repository_snapshot.
64 host tests passed. Live rehome returned +6.79mm to +.94mm and reported idle,
zero velocity. rehome_verification.json records this latest stopped state;
final_state.json is the earlier snapshot after auto_23 and recenter_24.
First harness checked before STOP acknowledgment, was refused, and was corrected;
all recordings retained. Balancing settings and Teensy firmware unchanged.
User subsequently confirmed deliberately pushing the pendulum when it last fell;
this is a disturbed trial, with event timing not logged.
