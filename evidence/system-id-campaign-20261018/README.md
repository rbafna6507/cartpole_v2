# Offline system-ID campaign verification, 2026-10-18

No hardware, Jetson SSH or cloud training was accessed. The rig was disconnected.
The implementation adds collection/evidence tools; no physical parameters,
firmware, frozen models or training profiles were changed.

The new focused suite passed 113 tests. It exercises bounded signed trajectories,
real SDK observations/action leases/STOP and counted returns against a scripted
device, manual disabled measurements, timing wrappers, immutable evidence,
partial/corrupt logs, camera failures, parameter/reference/home pinning,
writer-drain failures and per-trial temporal coverage. Scripted scheduling does
not establish physical motor tracking or live Jetson timing.

The documented `scripts/system-id-campaign --help`, `rehearse`, `review` and
`bundle` commands ran end to end. `synthetic-rehearsal.tar.gz` contains only
explicitly synthetic observations and source hashes. Its companion review rejects
it for fitting; it is a format/review example, not a simulated hardware acceptance
result or a physical data collection. Archive SHA-256:

`8b2a354ca152d1870df11035cf8fd4ef94fc48bcf7bd2a756e2cae4f94d2ecd6`

Independent reviews found and led to regression fixes for:

- Rig.close's short join allowing the logger to outlive evidence sealing.
- Empty/sparse recordings passing a frame-validity-only check.
- Applying file limits after allocating JSON/JSONL contents.
- Missing events in one trial being hidden by valid events in another trial.

Reviewers rechecked the fixes. No motion-boundary or real-Rig API mismatch was
found. This is code/offline review, not hardware validation.

The first full regression run: 1 failed, 1636 passed, 7 skipped, 456 passing
subtests in150.51s. The unchanged spawned-camera integration fixture rejected its
initial clock round trip because uncertainty exceeded10ms; the child retained
that reason in vision-report.json, and the parent reported camera unavailable.
An isolated repeat passed (1 test). The10ms physical clock-uncertainty gate was
not weakened. A subsequent full run without concurrent command checks is recorded
in `pytest-full-repeat.log`: **1637 passed, 7 skipped, 456 subtests passed in142.75s**.

Operator commands and model-update scope are in
[the campaign guide](../../docs/system-id-campaign.md). Actual data analysis,
fitted model changes and simulation/Gym validation remain pending real recordings.

Stored pytest logs have trailing whitespace stripped for clean diffs; test
results and diagnostic text are otherwise retained.
