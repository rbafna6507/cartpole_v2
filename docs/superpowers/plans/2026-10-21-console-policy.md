# Console policy operation and reliable inference implementation plan

> For agentic workers: implement scoped tasks with failing regressions first; parent owns hardware, integration, review and commits.

**Goal:** Run the learned balance actor through the console, fix the two observed operational failures, and measure performance in short repeated physical trials before claiming balance.

**Architecture:** Console retains one Rig connection and a selected numeric actor. Homing-derived rail compatibility is explicit and bounded; current measured rail governs motion. Speed up validated numeric inference without changing weights. Preserve old release/artifact, re-export an identifiable runtime-compatible candidate when pinned sources change. Use existing recorded data and simulation before any retraining.

**Tech stack:** Existing Python SDK, numeric JSON actor, optional NumPy inference, USB serial and unchanged Teensy executor.

**Spec:** User request in current chat: policy should run through console; autonomously collect, refine and train until working. Original working native gains and archived sources remain available.

## Constraints and review focus

- No board flash/reset while motor powered; no firmware change planned.
- Only parent connects/commands the rig. No automatic fault clearing or hidden native-controller fallback presented as learned control.
- STOP on faults, cancellation and normal exit. Never fake parameter readbacks or disable model provenance checks.
- Test reference changes after load, HOME roundoff, materially changed rail, console rate mismatch, failed arm/lease, cancellation and numerical parity.
- Work in existing clean branch; explicit user autonomy authorizes implementation without another design approval.

## Tasks

- [ ] Trace latest logs: MODE error is preceded by lease fault1 after103 actor calls; rail changed0.309000015 to0.309037507 after HOME. Preserve raw traces and replay.
- [ ] Console selection/run/check/shadow commands. Own console integration module and console/startup tests. Commands reuse the existing Rig, preserve native auto/bal, use declared full actor acceleration only on explicit policy run, STOP on Ctrl-C without discarding interactive session. Display current reference and limits; no silent parameter changes.
- [ ] Optimize fixed numeric inference with explicit backend and parity/benchmark evidence. Keep original weights and scalar backend; record backend provenance. Parent evaluates latency on Jetson before powered use.
- [ ] Rail compatibility: admit measured-homing rounding changes within an explicit narrow bound, verify current measured-home cap, retain exact checks for other settings, use intersection of trained/live rail bounds. Test smaller/larger/materially incompatible spans. Re-export a separate candidate if pinned source changes.
- [ ] Validate combined offline behavior and candidate compatibility; preserve old artifact/release and stage a new release without flashing.
- [ ] Parent: stopped preflight and readiness, then short timing hold and learned balance trials; acquire upright reference only with user coordination if needed. Record failures and diagnostics; no automatic fault retries.
- [ ] Evaluate learned hold, centering/oscillation and timing separately; refine/train with frozen validation starts as evidence permits. Do not claim robust swing-up from a balance-only actor or from native capture.
- [ ] Independent review, full relevant tests, recorded evidence and local commit; document invocation and remaining measured limits.
