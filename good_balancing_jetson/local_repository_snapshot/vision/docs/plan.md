# Cartpole Vision Implementation Plan

> Execute inline using executing-plans, TDD and verification-before-completion.

Goal: standalone tested vision measurement system in cartpole/vision.
Architecture: detector -> timestamped estimator -> live/replay interfaces. Optional independent cart template; calibrations are explicit.
Tech stack: Python 3.10+, OpenCV, NumPy, Flask, unittest.
Spec: design.md

Global constraints: observe only; no old files changed; finite JSON; no physical position without calibration; no derivative across losses; no sensor latency claims from host timestamps.
Review focus: ambiguity in green objects; stale camera; camera movement/calibration changes; partial occlusion; variable frame times.

1. Detector (`detector.py`, `tests/test_detector.py`): write known-geometry synthetic scenes and real still regression fixtures. Verify missing implementation fails. Implement chroma mask, geometric candidates, pivot/bob measurements and ambiguity rejection. Run unittest, then inspect replay overlays.
2. Estimation (`state.py`, `tests/test_state.py`): test wrapped rotations, stationary calibration, irregular times, loss/gap clearing and cart scale. Implement timestamped causal estimates and calibration with explicit independent validity.
3. Capture/replay (`capture.py`, `replay.py`, tests): test replay output, input errors and timing. Implement latest-frame live reader, optional raw recorder, replay JSONL/video/report.
4. Dashboard (`app.py`, static HTML, tests): test calibration endpoints, malformed inputs, staleness and cart templates. Implement preview, state API, controls and diagnostics without hardware motion.
5. Validate: full suite, supplied footage replay, live still smoke test, independent code review; document measured results and remaining limitations. Install new directory after sandbox approval and run tests there.

Execution ledger
- User said “ok build it out”; continue implementation without another design handoff.
- Stage outside shared repository in /tmp, then install to requested directory; existing repository has extensive unrelated changes, so do not stage/commit it.

- Detector: synthetic/real regressions pass; real bright-frame test found rim-connected holes, fixed with convex endpoint support and exposed-rim circle fitting.
- Estimation: wrapped/irregular timestamps, loss/gaps, calibration and stale states tested. Ruling: local linear 80ms velocity fit instead of quadratic endpoint derivative; lower noise, with explicit effective timestamps and 20–40ms delay. Control users must account for this delay.
- Capture/replay/dashboard: tested; live requested 80FPS delivered79.75FPS. Synchronous recording slowed tracking; moved recording to bounded background queue with explicit drops.
- Independent reviewer identified fixed-position seed, template conflict reuse, rejected-pose cart leakage. All reproduced with failing regression tests and fixed. Source changes also reset cart derivative/calibration sample history.
- No motor activity; no commits or unrelated files modified. User requested sibling directory; sandbox installation remains the final step.
