# Remaining system identification collection

The user authorized local software implementation while the rig is disconnected.
No remote or hardware operation is part of this implementation.

## Design

Extend the SDK with a separate `scripts/system-id-campaign` entry point. Keep
existing frozen model/profile artifacts and existing passive collectors intact.
Use a single serial owner, asynchronous raw Rig logger, separate-process raw
camera recorder, and explicit transport/policy timing instrumentation. Record
source hashes, settings, exact trial order, dataset role, home/reference identity,
STOP outcomes, failures and camera clock anchors. Preserve unsuccessful trials.

The autonomous suite comprises guarded cart trajectories, a quiet 100 Hz timing
hold, and short runs of the existing board controller with unchanged gains.
Trials stop individually; successful trials may return to the saved counted home
and wait for hanging to settle. Any fault aborts the campaign. No fault clearing,
full homing, firmware flashing, calibration, gain changes or watchdog changes.
An explicit `--execute` authorizes powered operation for that invocation.

Manual suites remain disabled throughout: angular holds approached in both
directions, small releases near upright for friction/capture, and ruler-measured
cart positions for image-to-metre calibration. Requested poses are labels;
independent measurements and reference methods must be recorded separately.
Manual cart moves invalidate the counted home physically; require a fresh full
HOME before powered collection. No powered work follows manual prompts.

Offline plan/rehearsal commands never open serial or HTTP. Rehearsal evidence is
explicitly synthetic and cannot qualify a model. Review verifies checksums and
reports completeness, timing and independent camera coverage; packaging retains
all raw and failed evidence. Neither collection completion nor numeric quality
implies model or hardware acceptance. Analysis/export is a separate, explicit
step after real training and held-out validation recordings are examined.

## Implementation steps

1. Tests, then bounded driven trial primitives and disabled manual capture.
2. Tests, then optional timestamped transport/policy adapters and timing summary.
3. Tests, then campaign orchestration, immutable manifest, offline review/bundle,
   CLI and synthetic rehearsal.
4. Document exact operator commands, missing measurements, review criteria and
   downstream simulation/Gym model-update boundaries.
5. Independently review motion boundaries and evidence semantics, run focused
   and full regression tests, run command-line offline rehearsal, and commit.

## Acceptance

No live access needed for verification. Tests exercise STOP on faults/interrupts,
no auto-clear, no powered manual actions, reference/home/settings pinning,
nonfinite/out-of-range input rejection before opening resources, camera failure,
partial logs, tampered manifests, clock/sequence resets and partial writes.
The documented commands produce a portable archive containing raw evidence and
an analysis handoff, without silently overwriting simulation configuration.

## Outcome

Implemented the campaign CLI, driven/manual collectors, timing capture, bounded
evidence review and immutable packaging. Independent safety and evidence reviews
were addressed with regression tests. Final full suite: 1637 passed, 7 skipped,
456 passing subtests. End-to-end offline commands produced a synthetic bundle.
No hardware was accessed; actual fits and model updates await real recordings.
