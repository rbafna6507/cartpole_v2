# Remaining implementation and acceptance plan

The specification is [live-rig-platform](specs/live-rig-platform.md). Work proceeds
in the existing `codex/live-rig-platform` checkout with disjoint agent ownership;
the primary agent exclusively operates physical hardware. Archive remains intact.

## Implemented; acceptance tracked separately

- New Teensy executor: framed commands, board-clock action leases, retained 1 kHz
  reference controller, independent ISR cutoff, latest-state telemetry and faults.
- Four NC switch inputs and finite cart two-end homing; measured stroke constrains
  the active software rail. Z homing remains gated on the mechanical mapping.
- Python serial SDK, explicit operator console, trusted policy runner and logs.
- Native interactive MuJoCo viewer with pause/reset and SDK controller semantics.
- Source-explicit vision adapter and conservative pendulum identification tools.

## Execution order

1. Compile firmware, run native fault/whole-sketch tests, review firmware and SDK.
2. Preserve live calibration/parameters and compile recoverable archived firmware.
   Capture a bounded original-controller trial and return to established center.
3. Install the new release outside archive; flash disabled. Verify handshake,
   default switch interlock, stopped telemetry rates and fault recovery first.
4. Explicitly configure switchless commissioning, establish the known center,
   validate bounded external leases and expiry, then run reference swing-up/balance.
   Record exact firmware, parameters, clocks, health, trajectory and stop cause.
5. Collect distinct identification train/validation trials. Fit identifiable
   pendulum quantities only; preserve calibration and reject biased/inadequate fits.
   Integrate validated parameters explicitly into the provisional simulation.
6. Add host-rate control and RL training/evaluation with exact source contracts,
   simulate first, then conduct bounded external-policy hardware acceptance.
7. Build authenticated immutable submissions, durable single-rig queue, independent
   policy isolation, trusted worker and loopback portal. Validate isolation and
   crash/restart behavior before any public deployment.
8. Run integrated tests, archive hashes and independent review; document remaining
   physical/infrastructure prerequisites and commit the completed implementation.

## Current evidence and remaining gates

- Original controller baseline: ten-second run, first balance at 3.851 s, 6.141 s in
  balance, max step-derived travel 0.18371 m; returned to 0.00188 m and disabled.
- New executor compiled, native tests/review completed and flashed successfully
  with Teensy Loader 2.3. Saved encoder upright 3485 remained intact; status 0x67,
  zero I2C errors. Default open NC inputs reject ARM/HOME and leave drivers disabled.
- Motor clicking was reported while in the bootloader after Loader 2.2's first
  flash write failed. Owner switched motor supply off, firmware was recovered,
  disabled checks passed, and owner restored power before the subsequent trial.
  All future resets/uploads require motor power off; see programming-incident.json.
- Stopped telemetry 100/250/500/1000 Hz: zero missed MCU ticks or active-reader drops
  across two-second measurements at each rate. Packet-fill latency removed from
  pyserial receiver. These are short stopped measurements, not load certification.
- Actual 250 Hz zero-command bench accepted 251 commands; withholding renewal produced
  action-expiry fault and disabled at 20 board ticks. Powered zero-policy check passed.
- New SDK preserved-controller trial completed 10 s: 2,500 observations, 6.08 s balance,
  max |x| = 0.19605 m, balance angle RMS = 0.05449 rad. Slow return ended at x = 0.004275 m;
  drivers disabled and default switch interlock restored. No deadlines/I2C errors.
- Two pairs of bounded 20 s physical identification trials completed with about
  5,000 observations per run. Peak step-derived displacement was 1.313/1.088 mm
  in the initial pair and 5.325/4.238 mm in the larger pair. Identification acceptance
  is recorded separately in phase4; command tracking alone does not accept a model.
- Native MuJoCo overlay deadlock repaired: identical Python/MuJoCo/macOS versions
  now render, pause and reset. The 30 s horizon intentionally freezes until R.
- Host 100/250 Hz policy and genuine CEM parameter-search RL are implemented; held-out
  simulation and provenance are recorded in phase5. No learned hardware acceptance.
- Portal/queue/isolation reviewed; real Jetson sandbox attacks and isolated
  simulation queue are checked separately in phase6. No public deployment yet.
- Vision3 stays untouched. Current live angle coverage is poor and cart metric
  calibration absent. Vision/fused physical control and independent cart model
  validation remain uncommissioned.
- Physical switch placement/polarity/homing/stop distance and Z switch mapping
  require assembled hardware. Public hardware jobs are gated on an enabled,
  healthy, physically homed switch profile and operational worker recovery.

Phase 3 hardware evidence is in `evidence/phase3`; compressed original recordings
include hashes and reproducible operator procedures. Current source/build hashes
are separate from the firmware family string returned by INFO.


## 2026-10-15 sensing and calibration continuation

The owner requested autonomous implementation of a persistent high-frame-rate
vision viewer, SDK encoder/vision/fused observations, and a measured model for
inferring upright from a hanging pose. These extend the existing platform; they
must not modify `archive/vision3`. The rig currently runs `executor-v4-rehome`.
Powered tuning is suspended while the observed angle disagreement is investigated.

### Design and ownership

- `src/cartpole_vision/` is a maintained copy of the preserved viewer. It retains
  stream, tracking overlay, mask, metadata and plots. The camera remains owned
  by one process, independent of policy lifetime. Optional `vision` dependencies
  and `cartpole-vision` install through uv. User systemd owns restart/lifetime;
  loopback HTTP and a tailnet-only proxy or SSH tunnel provide viewing. No public
  exposure or serial access is added to the vision process. Log retention is bounded.
- The existing Rig serial owner publishes best-effort accepted encoder telemetry
  through a separate latest-value worker to loopback UDP 3096. Console publication
  defaults on; library callers choose it explicitly. The display must mark absent
  encoder sources stale. It must never open a second serial connection for graphs.
- SDK fusion uses explicit source identity, shared frame, clock mapping, reference
  and calibration fingerprint. A bounded encoder history aligns delayed vision;
  wrapped innovations correct a slowly varying encoder bias. Stale sources,
  reference changes, outliers and clock rollback are visible validity failures.
  Actual SDK fusion is a separate shadow trace, not the old dashboard comparison
  filter and not automatic authorization for powered control.
- A hanging model records paired stable raw hanging/upright windows, approach
  direction, session/fixture identity, uncertainty and held-out validation. Its
  signed correction is `upright = (hanging + 2048 + offset_counts) % 4096`.
  Insufficient or inconsistent evidence cannot produce an approved control model.
  A firmware extension will accept only integer corrections within +/-256 counts,
  while disabled, with the existing stability, cancellation and verified-save
  semantics. Direct upright calibration remains independent. No unvalidated
  correction will be written to the physical board.

### Implementation and acceptance sequence

1. Preserve the current 18 completed repeat-test summaries, synchronized direct
   upright and manual-turn observations, original source hashes, and the rejected
   stronger-gain comparison. Keep direct upright reference 370 unchanged.
2. Implement and test runtime lifecycle, optional packaging, health endpoints,
   viewer regressions, log bounds and service scripts. Only the camera agent may
   temporarily stop the legacy camera process; the primary agent owns all serial,
   motor and firmware operations. Benchmark supported 30/60/80 FPS configurations
   without changing geometry, then retain the fastest reliable measured option.
3. Implement SDK publication/fusion with synthetic wrap, delay, out-of-order,
   calibration change, dropout and stale-source tests. Replay recorded data as
   shadow evidence; fitting to vision is not independent physical validation.
4. Implement model fitting, serialization and validation tests, including raw-count
   wrap, unstable windows, insufficient independent pairs and history/direction
   disagreement. Current data must remain rejected for automatic hanging correction.
5. Add corrected hanging command tests at both firmware core and whole-sketch
   levels before implementation. Add SDK/console tests proving an invalid model
   cannot write calibration and a rejected extension cannot fall back silently.
   Build and review the HEX; any upload still requires confirmed motor power OFF.
6. Install the new camera/SDK release outside archive. Verify sustained camera,
   tracking, encoding and actual received-frame rates independently. Test viewer
   panels and same-tailnet access, service restart, SDK encoder plots, source
   disconnection and the shadow-fusion trace with the motor disabled.
7. Reconcile deployment/docs and save measured limits. Resume bounded powered
   tuning only after source alignment and calibration repeatability support it;
   retain MCU final authority, physical switches and the established home.

### Evidence limiting calibration acceptance

Repeated direct upright capture is approximately 370/371 raw counts. Before the
manual turn, settled down was 2303/2305; afterward it was 2333 at nearly the same
camera orientation. The relative change is about 2.8 degrees. The motor-disabled
slow turn shows angle-dependent camera/encoder disagreement up to about 16 degrees.
Only one full turn direction was captured; directional hysteresis is unresolved.
A stationary zero-command motor hold changed mean encoder angle by only about
0.01 degree. A constant zero or one-direction fitted curve therefore does not yet
justify a transferable full-angle correction. Camera geometry and encoder/magnet/
fixture alignment remain part of the physical acceptance, not assumed truth.
