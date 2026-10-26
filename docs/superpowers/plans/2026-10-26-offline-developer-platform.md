# Offline developer platform implementation plan

**Goal:** Make custom-controller development, reproducible simulation/training, programmatic submissions, and useful recordings accessible without touching the rig.

**Authorization:** User requested implementation with autonomous local experiments and a new Colab training campaign on 2026-10-26. Hardware tests, tuning, service starts and deployment remain deferred until USB is repaired. Preserve existing policies and evidence.

**Architecture:** Reuse SDK channel contracts and calibrated RigCartpoleEnv in an immutable named profile; the same controller artifact runs through explicit simulation/hardware adapters and replay. Reuse authenticated portal routes with an owner-facing client and mandatory recordings. Train a separate controlled-swing candidate with randomized modeled dynamics; retain old model/actors and backup playbook.

**Design choices:** No new database or frontend framework. SQLite and content-addressed bundles remain. No arbitrary dependency installation or approval bypass. Detailed collection must declare unavailable channels, time bases, gaps and requested-versus-applied actions. Sim success is not hardware acceptance. Reward changes are experiment-specific, with rotation/rail-dwell/catch metrics and engineering uncertainty bounds.

## Deliverables and checks
- [x] Versioned calibrated nominal profile and explicit adapters; same starter artifact simulation, replay, ZIP submission; tests reject wrong sources/frames/stale channels.
- [x] Existing PPO training/numeric export example and developer guide reconciled with current portal/recording capabilities.
- [x] Offline native AUTO versus Python AUTO analysis; identify algorithms, sample rates, observer initialization and recovery differences without altering controller tuning.
- [x] Portal client upload/reserve/submit/status/cancel/collect/download; local authenticated API integration checks, authorization isolation and download integrity.
- [x] Mandatory trace plus explicit detailed collection; coverage/manifests and late bundle publication handled correctly; flow regressions tested.
- [x] Separate randomized controlled-swing experiment; compare frozen baseline, run a small local pilot, then launch one bounded Colab campaign with immutable source bundle and hash-verified checkpoint downloads.
- [x] Integration tests, independent code review, command documentation, explicit deferred hardware acceptance checklist; commit and push authorized implementation.

## Review focus
Unknown/ambiguous channel selection; profile identity mismatch; stale/replayed input; termination before bundle publication; owner access leakage and payload bounds; cancellation during preparation; recording backpressure; reward exploiting termination; checkpoints lost or associated with wrong campaign; unsupported physical claims.

## Completion boundary

Offline implementation and verification are complete. One 1,024,000-step Colab campaign was launched; its first trained 25,600-step checkpoint was downloaded and verified. Training completion and candidate qualification are not claimed. Source and frontend are being committed/pushed; no Jetson deployment occurred. See [verification and deferred hardware checks](../../../evidence/offline-developer-20261026/README.md).
