# Vision3 implementation plan

**Goal:** Move substantially closer to reliable 80 FPS moving-arm measurements, with reproducible evidence and a morning runbook.

**Architecture:** Independent copy of vision2. Preserve capture's latest-frame mailbox, full-frame geometric detection, explicit invalid outputs, and bounded H.264 streaming. Add bounded derivative history, equivalent image optimizations and a shared metrics/evaluation layer.

**Tech stack:** Existing Python 3.11, NumPy, OpenCV, Flask, system GStreamer and Chrome WebCodecs. No new runtime dependency.

**Spec:** DESIGN.md. All changes confined to vision3 locally and on the Jetson.

## Review focus

- Slow/jittery frame arrival must not make velocity permanently unavailable.
- Misses must never reuse an old pose as a new measurement; long gaps must reset derivatives.
- Faster segmentation must preserve threshold boundaries and ambiguity rejection.
- Coverage must count skipped camera frames as well as rejected processed frames; uncalibrated data must not look like a velocity failure.
- Latency estimates must expose clock uncertainty and exclude unmeasured sensor/display stages.

## Tasks

- [x] Velocity: tests at 30/40/80 FPS, wrap, acceleration, short dropout recovery, long gaps and geometry rejection. Implement bounded history in state.py, expose support and delay. Run full unittest suite.
- [x] Detector: characterize masks against original expression on random images and fixtures; profile saved frames. Replace whole-frame NumPy segmentation and bounding-box reductions with OpenCV primitives; reduce geometry allocations without changing acceptance thresholds. Compare poses and detection coverage on saved motion.
- [x] Metrics: test skipped frames, warmup/calibration distinction, dropout runs, percentile latency and stale rates. Add metrics.py, engine instrumentation, dashboard diagnostics, offline evaluator with synthetic truth and reference CSV support.
- [x] Streaming: test rate limiting, measurement independence and timing provenance. Move legacy JPEG preview off tracker; add --video-fps and --no-video. Add clock probe and approximate browser age with uncertainty. Investigate installed transport capabilities and document alternatives.
- [x] Validation/deployment: run complete local and Jetson offline suites, same-input vision2/vision3 benchmarks and replay, save results. Copy only vision3 to Jetson. Write single-line morning commands, reference-data protocol and interpretation. Do not start camera tonight.

## Execution notes

User explicitly approved building and selected the vision3 directory. Implement inline in this isolated directory without further approval ceremony or touching existing unrelated Git changes. No commits or broad repository cleanup.

Initial evidence: saved vision2 run had 8,535 valid angle measurements, only 5,395 valid velocities, and median valid-frame processing 24.11 ms. This whole-run sample includes long periods without visible geometry and is not a controlled moving-arm benchmark.

Final verification: 62/62 Jetson Python tests, 61/62 Mac (one Jetson-only skip), 2/2 Node timing tests. Independent review fixes: preserve original camera seq gaps; label unpaced source rates; remove invalid paced velocity truth; tolerate exact 120 ms floating boundary.

Scope update: user explicitly requested stopping vision2 and starting vision3 during execution; vision2 exited, vision3 PID 30032 is live. Later 25 FPS epsilon fix is on disk for next launch; current 80 FPS session was left running to preserve the user’s new calibration. No transport service or network settings changed.
