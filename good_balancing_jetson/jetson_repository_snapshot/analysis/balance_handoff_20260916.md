# Rough movement around balance capture: available evidence

User confirms: the plot freezes while stop still halts the cart. This is consistent with a receive/display problem while outgoing commands still work; it does not distinguish a host reader failure from loss of board telemetry.

## Latest logs are incomplete

- `run_20260916_132201.csv`: 2,753 samples, board time 6,430–34,602 ms; every sample is IDLE. Event log confirms v10 and accepted runtime vmax=0.8, amax_s=amax_b=16, jmax=70 before auto. RX ends in a corrupted text fragment immediately after the parameter/status response. Later stop, auto, and parameter commands are logged as transmitted, with no received acknowledgments. This cannot establish whether they reached the board.
- `run_20260916_131343.csv`: 2,699 samples, all IDLE; receive logging ends around the first auto command, although host commands continue.
- `run_20260916_131606.csv`: 2,269 samples; one short automatic episode shows rail recovery and a no-pendulum-response fault, then telemetry stops. No BALANCE samples. Later host auto/stop commands have no received acknowledgments.
- `run_20260916_131159.csv`: 413 IDLE samples only.

These logs do not capture the user's reported upright/balance behavior. They cannot establish physical cart slipping, a current jerk violation, or a motor-timing cause. No cart encoder measures actual motion.

## Older recorded capture demonstrates target mismatch

In `run_20260916_122300.csv`, trial 3 (v7; vmax=.75, amax_s=amax_b=15, jmax=50):

- First BALANCE sample at board time 489451 ms: raw theta=-0.2592 rad, filtered rate=-2.829 rad/s, inferred x=-0.1142 m, command v=+0.1201 m/s.
- Previous commanded acceleration +3.286 m/s²; first BALANCE sample +3.003 m/s².
- Reconstructing balance demand with the recorded raw angle gives approximately -13.02 m/s². The real controller uses estimated angle, so this is an approximation, not the exact internal target.
- BALANCE lasts only 51 ms. A 16.3 m/s² change needs about 326 ms at that run's jmax=50; at jmax=70 it would still need about 233 ms, if the target stayed constant.
- Finite-difference acceleration slopes in this short segment reach ~55 m/s³ versus nominal 50. Telemetry is decimated and control uses a fixed dt; this does not measure electrical step-pulse timing or mechanical jerk.

Current firmware uses a different capture gate than this v7 run. It preserves acceleration through capture and applies the common jerk governor to every normal balance update. It switches the requested balance target immediately, however. A bounded acceleration slope alone does not ensure successful capture or motor tracking. We have not justified new gains or a weaker jerk limit from the latest incomplete logs.

## Diagnostic correction

`cartpole.py` previously broke out of its serial reader silently on a read exception. A malformed numeric parameter could also terminate the reader. The patch records/reports reader errors, rejects malformed/non-finite numeric data without killing the reader, flushes telemetry periodically, and marks plots red after one second without valid telemetry. This addresses an identified observability defect; it does not establish the cause of the historical receive cutoff.

Eight host tests pass, including corrupt input recovery, visible serial disconnects, stale plot status, terminal stop and STOP-button callbacks. No firmware or live settings changed; restart the Python console to load the patch. Physical capture and slipping remain unverified.
