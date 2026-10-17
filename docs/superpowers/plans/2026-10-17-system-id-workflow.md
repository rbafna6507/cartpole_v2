# Reproducible system identification implementation plan

> **For agentic workers:** Use the existing parallel agent execution authorized by the user. Keep all hardware operations serialized through the primary agent.

**Goal:** Provide operator-runnable collection, analysis, validation and MuJoCo/Gym export tools, and collect stronger physical evidence before RL training.

**Architecture:** Build on the existing Python SDK and bounded experimental procedures. Immutable run directories contain source hashes, actual settings, raw encoder/camera records, timing, health and STOP outcomes. Training, development diagnostics and fresh validation are explicitly distinct. Export model configurations with validation scope and assumptions; preserve live controller settings and archived baselines.

**Tech stack:** Existing Python3.11+, uv, numpy, pyserial, MuJoCo/Gymnasium; existing optional hardware/sim dependency groups.

**Spec:** User request in this thread: continue autonomous identification with powered rig; make every procedure a self-runnable script with purpose/instructions; pipe validated measurements into simulation/Gym for eventual RL. Earlier user explicitly authorized autonomous execution and parallel agents. No additional design approval is required.

## Global constraints

- No firmware flash/reset, calibration, gain change or implicit fault clear. Teensy retains switches, health checks and20ms action leases.
- Only primary controls hardware; other agents work locally. Physical trials serial, small pilot first, inspect before escalation.
- Keep existing frozen training/heldout artifacts unchanged. Old heldout may inform development only; revised models need fresh validation.
- Control collection must STOP in finally; incomplete/failed logs cannot be relabelled successful.
- Defaults/archives/known-good releases unchanged. Fitted gravity-phase is not an established global encoder correction.
- Masses/force authority and unmeasured actuator dynamics remain explicit assumptions. No full-rig or upright claim from passive data.

## Tasks

- [x] Fix the proven near-zero float encoding failure: native parser regression, actual SDK command serialization, explicit numeric error bound, focused tests. No firmware change.
- [x] Add `scripts/system-id` self-runnable uv launcher and `cartpole-id` entry point. Subcommands cover inspect, passive collection, bounded pulse collection, passive fit/validation, driven fit, model export and Gym smoke test. Each must have useful help and recorded provenance; no-argument/help/offline commands never open serial.
- [x] Move reviewed bounded collection and passive-fit behavior into reusable SDK modules, with generic saved-reference/home preflight instead of hardcoded reference330/homeepoch14. Keep exact optional expected-reference/home guards. Required switches, centered/quiet starting state, action bounds and STOP rules stay enforced. Test fault, stale telemetry, output overwrite, missing camera, interval/source split and rejected fit behavior.
- [x] Provide an export schema containing SimulationConfig, source/report hashes, acceptance scope, assumptions and local offset limitations. Accepted passive profile changes only length and mapped damping; other dynamics remain assumed. Rejected fits cannot silently become recommended models. Provide a runnable Gym example loading the exported config.
- [x] Diagnose residuals with training data and historic runs; preserve old validation results as benchmark. Choose new model hypotheses/experiment split before new validation. Record conditional uncertainty and per-episode errors, not aggregate RMS alone.
- [x] Repeat5mm pilot after encoding fix; inspect camera/cart/angle/clock/health before matched negative and10/20/30mm trials. Freeze any final heldout trial identities after the revised training model is fixed. Collect distinct forcing if transient coverage is insufficient.
- [x] Compare the frozen MuJoCo candidate against independent data, including longer open-loop checks. The new manual recording repeats the large-release mismatch; no replacement model is accepted.
- [x] Complete final integrated verification and prepare the reviewed source/data checkpoint for commit without pushing. Full suite: 1040 passed, 8 skipped, 390 subtests passed; plot-enabled independent review: 33 passed.
- [ ] Resolve failed physical-model validation before promoting a plant for RL transfer. This remains open; successful collection/software checks do not complete identification.

## Interfaces and ownership

- Primary: hardware execution, run evidence, overall integration, model-validation comparisons and final documentation.
- Collector/CLI implementer: new `src/cartpole_sdk/identification/{cli,experiments,passive,workflow}.py` as needed; `scripts/system-id`; `pyproject.toml` entry; dedicated tests and user guide. Existing `fit.py` and frozen evidence unchanged. Expose report dictionaries with source identity, immutable output, parameters and acceptance reasons.
- Protocol implementer: minimal existing SDK wire encoding fix and regression tests only.
- Analysis agent: new offline exploration evidence/model proposals only; no hardware or production source changes.

## Review focus

Reject repeated or reversed clocks, static heldout, reused source IDs, missing reference/home and active switch. Explain numerical normalization, degraded camera coverage, force saturation, invalid physical assumptions and per-episode failures. Distinguish requested acceleration, MCU governor output and independent physical cart motion. Launcher must work from another directory and resolve its own repository. Failed exports and interrupted collection must preserve evidence without overwriting earlier runs.

## October 17 execution outcome

The integrated collector completed seven short signed pulses with confirmed STOP and zero logger drops, plus a 180-second disabled manual recording and final stopped inspection. Signed 10/20 mm training and 30 mm validation were frozen before scoring; both primary and historical-phase driven comparisons remain rejected. Actual continuous MuJoCo comparisons identify a repeatable larger-release mismatch. Independent raw hashes, failed attempts, clipped commands, current settings and analysis provenance are preserved under `evidence/system-id-20261017/`. No live gains, reference, firmware or simulator defaults changed.
