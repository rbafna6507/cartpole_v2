# Run workspace implementation plan

User approved implementation of automatic recording, optional reserved access, integrated video, and a redesigned portal; Python AUTO is a separate evidence-driven repair.

Architecture: retain the durable Python queue and its authenticated roles. A trusted worker records bounded scalar observations/actions outside submitted code, retains a local spool, and uploads a fixed-member ZIP after stop. Owner/operator download access never grants execution authority. Optional reservations gate physical claims; existing approval and execution budgets remain mandatory. Browser Live view consumes only a configured read-only image resource.

- [x] Recording: asynchronous bounded worker recorder, manifests and explicit missing/drop fields, failed-run preservation, immutable artifact upload/download, tests of ownership and failure paths.
- [x] Reservations: transactional non-overlapping windows (up to 30 minutes), optional job binding, owner-scoped listing/cancellation, claim and start enforce window and rig; disabled unless configured. Test conflicts, ownership, boundaries, expiry, simulation independence, disabled behavior.
- [x] Portal: Experiments / Live view / Run data / Reservations; polished responsive design, persistent existing auth and approval, authenticated downloads and truthful service status. Browser verify no console errors, navigation, empty states, video and responsive layout.
- [ ] AUTO: reproduce sampled observer/planner divergence offline; implement only evidence-backed fix with regression tests. No physical test or firmware safety change.
- [ ] Documentation: commands, recording schema/limits, reservation semantics, deployment differences and remaining capabilities; run integration suite and review before source-only commit/push.

Review focus: expired reservations cannot authorize motion; file upload/download cannot cross owner boundaries; interrupted worker recordings disclose incompleteness; camera embedding must not expose operator controls; no simulated result is hardware acceptance.

Verification: full suite 2172 passed/8 skipped; after review fixes, portal and diagnostics 114 passed/6 skipped plus three JavaScript video tests. Actual browser H.264 playback and all four views verified. AUTO remains unresolved: replay tooling added, no speculative deployed behavior change.
