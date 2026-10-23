# Deployed submission worker implementation plan

**Goal:** Accept Python, bounded ZIP projects and numeric actor JSON; execute in an isolated Jetson worker and return recorded bundles through the same API used by either Funnel-hosted or Vercel-hosted UI.

**Architecture:** Retain authenticated API and durable SQLite queue on Jetson, with independent outbound-pull worker services for simulation and hardware. Frontends remain static/swappable. Hardware jobs retain exact-artifact operator approval, exclusive serial ownership, firmware safety and bounded actions. Bubblewrap plus seccomp/resource limits isolates all submitted Python; no upload is imported on the API host.

**Authorization:** User explicitly requests deployment and end-to-end execution; prior autonomous hardware experimentation authorization remains active. Coordinate serial handoff with ongoing AUTO tests. No arbitrary package installation or pickle loading.

## Tasks
- [x] Validate Python (64 KiB), ZIP (8 MiB), numeric actor (1,000,000 bytes), ZIP expansion (32 MiB/256 entries), reject unsafe paths/links/duplicates and unsupported serialization; test adversarial intake.
- [x] Run projects and numeric actors inside existing restricted child; preserve artifact digest and approval binding, quotas, lease, cancellation and recording semantics.
- [x] Extend both frontend copies, upload guidance and operator inspection; run JS tests/build.
- [x] Install durable simulation worker, validate real Linux isolation, then perform public API upload/run/download for each format plus malicious-code failures.
- [ ] Coordinate stopped rig handoff, install hardware worker, perform approved conservative physical test and verify stopped state plus downloadable recording.
- [x] Document installation, credentials, safety boundaries, recovery, supported dependencies/formats and Vercel migration. Commit/push source and deployment configuration without private tokens/logs.

## Review focus
Archive bombs/traversal; invalid models/nonfinite weights; artifact response limits; blocked/expired leases after crash; serial contention; no network/filesystem escape; no successful result before STOP; private diagnostics and bounded bundles.
