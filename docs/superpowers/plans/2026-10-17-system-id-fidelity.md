# System identification and training fidelity plan

> Execute the user-authorized autonomous work in this checkout. Only the primary agent operates hardware; offline analysis, simulation and training interfaces may proceed in parallel.

**Goal:** Distinguish measurement/initialization effects from cart/pole dynamics, collect informative independent data, and make simulation/training consume explicit model and executor assumptions.

**Architecture:** Keep old frozen comparisons and the working controller unchanged. Add bounded pulse durations to the existing collector, a separately named governed Gym environment using the existing 1 kHz executor and firmware observer, and model-bound training admission/provenance. Current rejected physical models remain rejected. Training preparation and synthetic verification do not establish transfer readiness.

**Authorization:** User explicitly requests autonomous collection and iteration until a solid simulation, runnable collection/validation/export examples, and training preparation. They can help with manual swings. Existing authorization permits parallel agents. Do not flash/reset firmware or modify archived baselines.

**Latest steering:** User takes over physical collection. Keep the rig stopped; provide labelled requested release conditions, raw review, frozen-fit plots, validation/export examples and real PPO training for Colab. No new powered batch was run in this turn.

## Tasks

- [x] Add allowlisted pulse durations 0.45, 0.65, 0.8 and 1.0 s; default remains0.65. Reject reference acceleration over3m/s² before serial/ARM. Preserve runtime limits,20ms leases, measured guards, immutable reports and STOP. Increase quiet pre-pulse recording to1s. Tests cover analytic derivatives/endpoints, impossible amplitude-duration pairs, actual runner duration/STOP/lease, CLI forwarding and source metadata.
- [ ] Operator follow-up (not executed after handoff): collect a signed5mm pilot, interleaved signed10mm/.65 repeats, then signed10mm/.45 and/.8 and signed20mm/.8 or1s as justified by earlier outcomes. Inspect each run before the next. Record camera and encoder before/after. Freeze final validation protocol/model before reserved independent captures. No automatic escalation or weakened health/timing limits.
- [x] Quantify rest-angle history, camera corroboration, raw-rate initializer sensitivity and input integration from velocity. Any newly tuned models use previously viewed validation as DEVELOPMENT. Keep original acceptance scores unchanged; new claims require fresh data.
- [x] Add new RigCartpoleEnv reusing ExecutorSimulation and firmware observer. Explicit measured governor settings,100Hz decisions,1kHz physics, raw demand, anchored20ms lease, quantized encoder, causal telemetry/command delay. Preserve old backend/model/config/Gym source because historical model comparisons pin it. Test against existing governor/observer parity and validity/no-truth-leak behavior.
- [ ] Add model-bound training command using metadata-preserving model admission, explicit governor/sensor/prior settings, seed split and immutable artifacts. Passive-down scope cannot authorize full-swing training claims. Implement governed Gym neural PPO, immutable checkpoints/resume/evaluation, a NumPy SDK actor and Colab notebook; do not train a hardware candidate on a rejected model.
- [ ] Review each changed subsystem, run focused and final integrated tests, preserve all raw/failed evidence and plots, document exact operator commands and remaining physical gaps, commit without push.

## Current identified gaps

The new manual recording still fails the existing tail-error gate. A turning-point initializer helps one release and hurts another. Small-pulse fitting is confounded by chronological equilibrium shifts. Sampled acceleration integration has been checked against velocity; it does not explain most fitting residual. General Gym bypasses the existing governor and exposes true omega, whereas hardware bw6 filtering adds substantial phase lag. Mass/force/independent distance and full-angle calibration remain assumptions unless measured.

## Operator additions

- [x] Immutable nominal release angles/directions/repetitions, dataset role and cart-restraint metadata bound into raw records and completion reports; no substitution of requested angles for measurements.
- [x] Raw-recording review PNG/PDF before manual annotation, and explicit collection → annotate → fit → review → export documentation.
- [ ] Frozen-fit review plots on exact held-out sources with unchanged acceptance.
- [ ] Real PPO learn/save/reload/resume and Colab notebook; independent review and final verification.

## Acceptance and review

Require successful source-bound completion/STOP and zero logger loss for fit inputs. Keep source identities and actual applied MCU acceleration; clamped requests remain protocol deviations. Do not replace observed step counts with physical truth or globalize a local gravity offset. Separate short forecast and uninterrupted trajectory errors. Report condition-specific failures, uncertainty and model support rather than selecting a favorable aggregate. No firmware or tuned-gain change is part of this plan.
