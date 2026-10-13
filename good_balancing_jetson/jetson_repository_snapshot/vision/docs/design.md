# Single-arm cartpole vision

User-approved direction: replace the proof of concept in a separate cartpole/vision directory. Observe only; no motor commands. Output theta, angular velocity, cart position and velocity, with explicit independent validity and timestamps. Initially support the existing green rigid arm and weighted circular end; multiple arms are out of scope.

Detect saturated green above an absolute brightness floor, then fit rigid geometry. Locate the weighted end using the filled silhouette distance transform and the pivot using local screw contrast near the opposite end. Validate length, straight shaft support, width and pivot appearance. Never rely on the old broad green connected component or a permanent click seed. Use a user-selected cart template as an independent optional measurement when the arm is occluded. Template matching must pass appearance and uniqueness gates and must not silently update itself.

Use causal local linear fits over 80 ms on actual monotonic sample times for velocity. Expose their effective timestamps so smoothing delay is explicit. Unwrap angles across pi. Clear derivative history on invalid measurements, nonmonotonic timestamps or gaps. Measurements are never replaced by extrapolated poses. Output pixel coordinates without calibration; output physical cart units only after two stable measured references and a known separation. Hanging zero requires consecutive stationary observations. Explicit angle convention: zero upright, positive upright toward image-right; hanging is +/-pi.

Capture latest frames in one thread; process once per sequence; preview independently at a lower rate. Log JSONL states and optionally raw MJPEG plus per-frame timestamps. Report negotiated settings and host arrival timing, not invented exposure times or sensor latency. Replay uses video presentation times and identifies screen-recording limitations.

Validate synthetic rotations, clutter, occlusion, reacquisition, timing, calibration, API input/staleness, and this recording. Replay detection coverage is not angle ground truth. Live accuracy and balancing fitness require independent encoder comparison and latency measurement.
