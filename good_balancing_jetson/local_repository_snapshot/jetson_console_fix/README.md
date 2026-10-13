# Jetson console dashboard fix

Replace cartpole.py and angle_plot.py in your teensy_swingup_ethernet directory
with these files. No firmware flash is required.

Run in an interactive terminal (use ssh -t if needed):

    uv run --with pyserial --with matplotlib cartpole.py --host 192.168.50.2 --text

Wait for fresh telemetry/startup STOP acknowledgment, then enter auto.
Text mode retains telemetry logging and accepts stop + Enter, Space/Esc to stop,
and q + Enter to exit. Terminal EOF/disconnection still stops motion.

The old dashboard always called plt.show(), then sent stop on exit. With a
non-interactive Matplotlib backend, show returns immediately, causing an
unrequested stop after auto. This matches headless Jetson use but is not proven
to be the only cause of the reported symptom without the session event log.
The updated console chooses text mode when Linux has no display, when --text
is specified, or when the figure canvas has no desktop interactive framework.
Desktop plotting explicitly blocks until the plot closes.

Watchdogs, reconnect/startup STOP handshake, and stop-on-dashboard-exit remain.
A STOP during initial connection is expected. If auto still stops, retain the
printed events log path and provide its entries around auto and stop; it records
outgoing commands, telemetry timeout, reconnect and incoming firmware messages.

Validation: four regression tests passed for explicit text selection, headless
Linux, Agg despite DISPLAY being set, and preserved STOP on terminal EOF.
Hardware operation has not been tested here.

    python3 -m unittest discover -s tests
