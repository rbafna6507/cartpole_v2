# Portal developer workflow and approval implementation plan

**Goal:** Start the agreed invited-user portal by enforcing operator approval before hardware claims and documenting the actual controller/encoder interface.

**Architecture:** Extend the existing authenticated Python queue and worker. Simulation remains independently runnable; each immutable physical job requires an operator approval. Cloud storage/Postgres/Vercel, ZIP/policy intake and replaceable video transport follow this foundation and are not represented as deployed.

**Authorization:** User approved the proposed portal architecture and asked to start building. Continue inline on the existing feature branch; preserve raw evidence and installed rig release. No hardware execution or cloud publication.

**Decisions:** Physical approval records operator, timestamp and the reviewed artifact digest, duration and sensor source. Requests with mismatched review fields fail. Approval does not home, arm, calibrate or bypass worker safety. Existing pending physical jobs become awaiting approval; already claimed/running jobs retain their lease semantics. Source-only upload limits remain 64 KiB until bounded ZIP/object-storage intake is implemented.

## Tasks
- [x] Add failing queue/HTTP tests for physical claim denial, operator-only approval, exact reviewed fields, cancellation and persistence; implement durable approval and migration; retain simulation behavior.
- [x] Expose operator approval in the existing UI and retain role enforcement on the server.
- [x] Document unfiltered radians versus native encoder counts, timing/freshness, lossy display mirror, action contract, simulation/replay and training workflows, and remaining parity gaps.
- [x] Run portal and broader regression tests, review changes, commit and push the first increment.

## Review focus
Migration must not auto-approve legacy jobs. A submitter/worker cannot approve. Cancelling waiting work must release quota. Approval must bind exact immutable input. Existing worker lease/recovery safety remains unchanged.

## Verification and review

- Initial approval tests failed as expected (unapproved jobs were claimable and approval endpoint absent); implementation passed them.
- Independent review found missing operator source inspection and overlapping action buttons. Added a failing HTTP inspection test, then operator-only verified source retrieval and a separate actions wrapper. Added true legacy-schema and repeated-approval receipt coverage.
- Full regression: 2,109 passed, 8 skipped, 460 subtests passed. Final portal suite after review fixes and extra migration tests: 66 passed, 6 skipped, 16 subtests passed.
- Browser check confirmed operator identity, hidden submit form, visible separate review/approval controls and successful source display. The browser automation connection stalled at the native confirmation dialog, so the final browser click was not verified; the approval API transition is covered by real HTTP tests.
- No Jetson deployment, physical run, cloud service publication or firmware change in this increment. Installed operator release remains intact.
- Hosted accounts/storage/queue, ZIP/numeric-policy intake, richer observation/simulation parity, authenticated video/telemetry and downloadable run traces remain subsequent portal work, as documented in the developer guide.
