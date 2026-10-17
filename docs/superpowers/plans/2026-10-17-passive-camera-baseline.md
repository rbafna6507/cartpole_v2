# Passive hanging baseline and camera qualification

> Execute with TDD and the user's existing authorization for parallel agents. Primary owns integration and any remote actions; helper agents work offline on disjoint files. Continue the existing clean `codex/live-rig-platform` checkout.

**Goal:** Prepare reliable operator collection for passive-training-2/passive-validation-2, with independently measured hanging zero and camera evidence for release angles. The user collects afterward; fitting and export wait for those actual recordings.

**Architecture:** Preserve raw encoder and camera readings and the working upright reference. A two-second stationary startup window establishes experiment-relative hanging baselines. Camera data remains mandatory for new passive collection; optional geometry loss is retained as missing evidence, not filled from encoder/fusion. Clock round trips bind camera host-read proxies to collector time. Offline release review checks manually declared free and held-pose windows, measured excursions, coverage and sensor disagreement before new data can support a fit/export.

**Constraints:** No rig motion, ARM, calibration, homing, gain change, firmware upload or camera calibration. New immutable recording and output paths. Historical logs retain their explicitly limited compatibility path. Camera projected angles and receipt timestamps are not absolute physical calibration/exposure timing. Baseline removal is for comparison/plots; raw-angle fit equations retain their training-only phase parameter.

- [x] Baseline helper: test wraparound/nonzero hanging, quiet window, camera geometry/coverage, motion/geometry changes; implement robust independent medians and explicit QC.
- [x] Collection: test mandatory camera, readiness after baseline, no calibration/arm, interruption cleanup, preserved raw readings, source clock anchors and fresh latest camera sample. Add two-second disabled baseline before release timing starts. Record baseline in raw log and completion report; keep camera active throughout.
- [x] Review: test source/hash/clock binding, camera gaps, wrong geometry, missing pose, correct known angle and sensor disagreement. Implement offline review-releases and plot overlays relative to measured baselines; require explicit stationary pose window for verified release angle.
- [x] Fit integration: new baseline-bearing records require bound camera/pose checks; historical data does not acquire new certification. Camera failures block acceptance/export; do not lower frozen numerical fit gates or fuse away disagreement.
- [x] Operator UX/docs: render new raw plots with hanging at zero; explain initial wait, six manual releases and immutable outputs. Support the user's passive-training-2/passive-validation-2 names. User only collects; agent does subsequent review/annotation/fit/export after data exists.
- [x] Verify targeted tests and full suite, review changes, stage updated collector on Jetson without serial access, run help/import and read-only camera checks, commit. No collection or fit claimed until performed.

## Review focus

1. Starting held/oscillating must fail baseline; no silent firmware reference change.
2. Repeated camera heartbeat, missing markers or filtered/fused values cannot count as independent angle samples.
3. Different clocks must be explicitly mapped with uncertainty; stale or reset clocks reject camera qualification.
4. Raw/annotation/camera hashes and baseline identities must remain bound; absent or poor camera evidence cannot silently pass a new-data fit.
5. Initial pose and later damped peak are different measurements; uncertain release boundaries remain unverified rather than being chosen for best fit.

## Execution outcome

Implemented and reviewed on 2026-10-17. Full verification after production changes: `MPLCONFIGDIR=/tmp/cartpole-id-matplotlib .venv/bin/python -m pytest -q` completed with **1,233 passed, 8 skipped, 390 subtests passed**. This includes a real spawned camera recorder against a local HTTP server. Independent review findings concerning passive health flags, stale initial state and camera-clock metadata binding were fixed and regression tested.

Staged 136 source files in `/home/rbafna/cartpole-v2-live/staging/operator-id-20261017-camera-zero`, verified every manifest hash, installed locked hardware/id/plots dependencies, and checked command help. A read-only live camera smoke check recorded 363 frames in about five seconds, all with valid raw geometry, with usable clock anchors and a quiet camera baseline. No serial port was opened and no motion, encoder calibration, gains or firmware were changed. Evidence is under `evidence/passive-camera-baseline-20261017/`.

**Pending operator data:** `passive-training-2` and `passive-validation-2` have not been collected by this task. Annotation, release verification, model fitting, held-out validation and export will use those actual recordings afterward. Passing software and stationary camera checks does not certify moving-camera performance or a dynamics model.
