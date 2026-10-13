# Vision3: reliable measured motion at 80 FPS

Approved scope: improve tracking on the existing camera and Jetson, at the existing power setting; provide measured accuracy, dropout and latency; investigate Mac streaming alternatives. Build and test offline tonight. Preserve vision and vision2 and do not start a live camera session.

The detector will retain full-frame acquisition, ambiguity rejection and measured endpoints. First optimize equivalent image operations, then benchmark the same saved frames against vision2. No guessed poses or extrapolated velocities will be presented as measurements.

The velocity estimator will use a shorter default window at 80 FPS with bounded extension at slower/jittery delivery. Brief detection losses invalidate the current output but retain recent measured history; long gaps, invalid geometry, reversed time and calibration changes reset history. Effective sample time and estimator delay remain visible.

The dashboard and logs will distinguish camera throughput, processed frames, detected geometry, calibrated angle and valid angular velocity. Rolling and whole-run metrics will include skipped inputs, missing detections, velocity coverage, deadline misses and host-read-to-result latency. Accuracy requires independent reference data: synthetic motion provides exact software truth; manual/encoder references are a separate real-world validation step.

H.264 stays separate from measurement. Expose a video rate cap and disable-video option to quantify CPU competition; avoid JPEG work on the tracking thread. Measure host-read-to-browser-canvas age using clock probes and report clock uncertainty. This excludes exposure/readout/USB time and display scanout.

Evaluate direct private-network transport and WebRTC feasibility without changing network exposure, certificates, SSH configuration, hardware settings or power modes tonight.
