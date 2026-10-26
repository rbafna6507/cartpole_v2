# Offline developer platform verification — 2026-10-26

No Jetson connection, hardware motion, serial operations, service restart or backend
deployment was performed for this update. Existing working actors, firmware and
gain files are unchanged.

## Verification

- Fresh main regression suite, excluding the two separately checked new training
  modules: **2,384 passed, 17 skipped, 480 subtests passed**. Command:
  `.venv/bin/python -m pytest -q -p no:cacheprovider --ignore=tests/test_controlled_swing.py --ignore=tests/test_controlled_cloud.py`.
- Final portal followup suite: **235 passed, 15 skipped, 16 subtests passed**.
  Includes independently timestamped board snapshot matching/mismatch regression.
  Linux/Bubblewrap skips on macOS are not Linux isolation verification.
- Final starter/profile/dataset/training/cloud targeted check: **31 passed**;
  the additional real loopback HTTP starter submission check: **1 passed**.
  The default execution sandbox blocked binding localhost for that test; it passed
  when rerun with loopback access. No remote portal or physical job was created.
- Frontend: **18 passed**, including legacy-backend recording negotiation.
- Native C++ capture/reference parity, Python feedback and diagnostic tests passed;
  the comparison is documented in `docs/python-auto-offline-audit-20261026.md`.
- Independent review covered source/profile adapters, checkpoint provenance,
  dataset action identity and missing observations, and portal recording races.
  Review fixes were rechecked. Intentional duplicate-ZIP tests emit a warning.

Counts are overlapping suites, not additive. The full suite preceded the final
snapshot-label regression and starter HTTP test; those changes have targeted checks.
Training execution/export pilots, cloud source bundle, dependency preflight and
checkpoint receipts are in `../controlled-swing-20261026/`.

## What still requires hardware access

1. Repair and verify USB/serial reliability before connecting any controller.
2. Coordinate API and worker deployment; verify the Linux sandbox on the actual
   Jetson. New source capabilities do not upgrade a running service automatically.
3. Exercise Python, ZIP and numeric-policy submissions through the deployed worker,
   including preparation/cancellation, a full timed run and download after upload.
4. Confirm actual recording coverage, sample gaps and timestamps against live sources.
5. Compare Python/native AUTO timing and behavior under matched initial conditions
   before tuning gains. No tuning or physical reliability claim is made here.
6. Evaluate any newly trained candidate on held-out seeds before a separate,
   bounded hardware qualification. Simulation success is not hardware acceptance.

## Data interpretation

Scalar observations/actions are mandatory. Detailed recording expands optional
sensing history and retains independently timestamped cached board state. Neither
mode promises losslessness or provides native full-rate encoder counts, raw serial
bytes, complete firmware internals or video. Dataset export preserves quality and
pairing flags; rewards/terminal labels and physically applied actions are unknown
unless separately established. `training_ready` remains false by design.
