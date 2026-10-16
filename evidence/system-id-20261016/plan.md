# Rig identification and MuJoCo update plan — 2026-10-16

**Goal:** Collect sufficiently excited, independently held-out observations, identify the supported dynamics, and apply only validated quantities to an explicit MuJoCo configuration for subsequent RL work.

**Architecture:** Keep the working firmware, gains, and direct upright reference 330. A trusted bounded 100 Hz SDK experiment controls small cart motions while independent camera recording preserves raw marker geometry and host timestamps. Offline fitting separates commanded inputs, magnetic measurements, camera measurements, timing and calibration assumptions. A new model stays opt-in until it predicts held-out measurements; rejected candidates remain evidence.

**Tech stack:** Existing Python SDK, numpy fitting, MuJoCo, Jetson camera HTTP sensing stream, Teensy v6. No firmware upload or reset.

**Existing specification:** docs/identification.md and the user's authorization to collect all required data and update MuJoCo before RL training. The user explicitly chose autonomous execution; no new design approval is required.

## Constraints and evidence

- Serial has one owner; all powered tests run serially. Installed left/right switches, existing jerk/speed/rail bounds, 20 ms anchored action expiry and health checks remain active.
- Ref330, leff0.124, jerk150 and all working live gains remain unchanged during characterization. This does not constrain the offline fitted model.
- Home epoch14, measured travel619.2375mm currently valid. Counted motion is not independent proof of physical tracking.
- Earlier 20 s multisine plus zero-command tails rejected: near-static tails, nonzero residual/angle-bias diagnostics. Do not quietly lower acceptance thresholds.
- Camera now has correct visible upright orientation and visible pivot/bob at home, but its live calibration is absent. Preserve raw pixels/angle and validity; no implicit fusion or physical-unit claims.
- Absolute masses/force authority cannot be inferred from acceleration and angle alone. Keep explicit assumed quantities and uncertainty.

## Tasks

- [x] Finish one bounded checksum-optimized SDK zero/AUTO check; record limitations and park remaining runtime diagnosis.
- [x] Preserve current source, trial logs, hashes and experimental release; fix reviewed regressions; commit without pushing.
- [x] Add independently bounded raw vision recorder, with read-only HTTP, hard duration, failure metadata and no serial ownership.
- [x] Test smooth cart pulse/return/hold harness offline, including endpoint/continuous bounds and STOP on invalid data or deadline failures.
- [ ] Collect pilot small positive pulse with raw camera. Inspect actual motion/angle excursion, timing, health, cart-hold and residual signal before escalating.
- [ ] Freeze train/held-out experiment IDs, waveform levels/directions and model choices before looking at held-out outcomes. Collect bidirectional repeats and distinct forcing. Preserve faults rather than treating failed records as passes.
- [ ] Fit training-only dynamics (length, viscous/friction terms if justified, commanded-input gain/delay) and explicit sensor nuisance terms only when identifiable. Separate down-region evidence from full-angle evidence.
- [ ] Validate nonlinear rollouts on disjoint held-out trajectories, with signal/conditioning checks and frozen thresholds. Compare raw encoder and camera, marking unsupported sensor assumptions.
- [ ] Add a versioned MuJoCo profile with identified quantities/provenance and remaining assumptions. Verify model equations and replay predictions; preserve default working-controller profile and prior simulation for comparison.
- [ ] Report measured model quality, useful domain randomization ranges, and remaining requirements before physical RL deployment.

## Review focus

Faulted/stale readings must stop motion; recorder failure cannot block control; a pulse must end with bounded cart hold; no model selection may use held-out data; observed small-motion validity must not be reported as validated full-range dynamics.

## Progress ledger

- SDK implementation, release and curated evidence committed as `b94cdf1`; no push. Root verification853 tests/390 subtests,7 skipped; packaged verification194 tests/25 subtests.
- Manual training recording02 captured free swings with driver disabled throughout; operator confirms the cart was held by hand. Recording01 was static and is excluded. Raw camera pixel motion supports stationarity where valid, but does not establish metric or out-of-plane motion.
- A separate passive train/held-out design supplements the forced-input plan. Training candidates and gates are frozen before the next recording. User readiness for that recording is pending.
- No system-ID model or live calibration has been promoted. A candidate MuJoCo comparison may be generated for offline validation, explicitly marked provisional; powered characterization remains pending.

- Training freeze complete: two admissible episodes, viscous candidate length0.160736m/damping0.463156 per second; Coulomb primary rejected. Exact hashes and evidence are preserved. No heldout read.
- Offline MuJoCo candidate overrides and provenance added. Twelve mathematical mapping checks passed; this is not physical validation or a new default. Eleven passive estimator tests passed and the training reports reproduce byte-for-byte.
