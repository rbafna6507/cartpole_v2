# Phase 2 Controller and Simulation Implementation Plan

> **For agentic workers:** Use test-driven development for each independent chunk; parent integrates and obtains one independent whole-change review. The owner authorized parallel work and autonomous execution.

**Goal:** Deliver the saved controller in Python and an optional MuJoCo/Gymnasium backend against the existing SDK.
**Architecture:** Independent numerical/controller, native-oracle and physics tracks share pinned interfaces; the parent owns SDK integration, CLI, packaging, docs and end-to-end evidence.
**Tech stack:** Python 3.11+, stdlib control core, native C++17 oracle, optional MuJoCo/numpy/Gymnasium via uv.
**Spec:** docs/specs/phase2-controller-simulation.md

## Global constraints

- No edits to archived algorithms/firmware or remote rig operations.
- Fixed 1 ms reference step, saved tuned parameters, honest float tolerance.
- Simulation parameters remain provisional and sensor data distinct from truth.
- Preserve Phase 1 interfaces and source/clock/validity semantics.
- Keep the core SDK dependency-free; optional packages live in the sim extra.

## Review focus

- A copied/rewritten C++ state machine must not masquerade as independent firmware parity.
- Guard/transition order, timer rollover and command-state reset must preserve baseline behavior.
- Acceleration-to-force conversion must not torque the free pole or hide force saturation.
- Old/delayed/invalid samples or expired/mismatched requests must not become fresh actuation.
- Wheel/resource isolation and seeded episode boundaries must work outside the checkout.

### Task 1: Port the control core

Files: src/cartpole_sdk/control/{__init__,parameters,motion,reference}.py and packaged tuned settings; tests/test_reference.py, tests/test_reference_parity.py; controller provenance.
Interface pinned in /tmp/cartpole-phase2/interfaces.md before implementation.
- [x] Write failing primitive and stateful controller tests against recorded preset/gain values and native oracle scenarios.
- [x] Run tests; expect absent controller modules initially.
- [x] Port estimator, gains, pump/capture, governor and all cart recovery modes from archived headers/controlTick. Validate public inputs and preserve fixed-step timing.
- [x] Compare native primitive and stateful outputs with stated tolerances; report covered modes, maximum errors and any float-sensitive boundaries.
- [x] Run core suite without simulation extra; expected pass.

### Task 2: Build independent native firmware oracle

Files: tests/native/*, tests/oracle_support.py, tests/test_native_oracle.py; evidence/phase2/oracle-provenance.json.
Interface pinned in /tmp/cartpole-phase2/interfaces.md.
- [x] Write failing compile/smoke tests before adding harness/stubs.
- [x] Include a generated native-compatible copy of original .ino plus original headers. Only documented hardware-bound substitutions; retain controlTick/control headers unchanged.
- [x] Expose deterministic text protocol for commands, input samples, state and primitive probes. Test actual native mode/health/fault outcomes.
- [x] Hash source and list every substitution. Compilation failure must fail required parity tests, not silently skip them.

### Task 3: Add MuJoCo and Gymnasium backend

Files: src/cartpole_sdk/sim/* and tests/test_simulation.py, tests/test_gym_env.py; model provenance.
Interface pinned in /tmp/cartpole-phase2/interfaces.md.
- [x] Write failing physics/action/sensor/episode tests; verify absent module failure.
- [x] Implement provisional MJCF, configured acceleration servo with bounded force, seeded sensor pipeline and SDK action lease handling.
- [x] Add continuous-action Gymnasium environment with explicit validity/age metadata and documented reward/termination.
- [x] Run analytic sign/saturation/timing tests and Gym environment checker; expected pass with sim extra.

### Task 4: Integrate SDK policy, examples and evidence

Files: src/cartpole_sdk/control/policy.py, simulation runner/CLI integration, examples, pyproject.toml/uv.lock, docs/phase2-usage.md, README, evidence/phase2.
- [x] Write failing same-policy simulation/record/replay tests, cadence/invalid-source failures and CLI/wheel resource tests.
- [x] Implement strict reference-policy adapter and runnable headless simulation/training examples, with configurable surrogate parameters and saved provenance.
- [x] Run all core/sim/native/tunnel tests, preserved hash checks, wheel install/import/rollout and representative controller scenarios. Record actual failures/limitations without tuning gains to make a demo look good.
- [x] Obtain one independent final review, resolve findings with regressions and leave a clean committed local branch.

## Progress and decisions

- Base 29bc06a; local branch codex/phase2-controller-simulation.
- Original roadmap and owner's kickoff authorize this scope. Separate approval gates are unnecessary under their continuing full-autonomy instruction.
- Parallel work uses disjoint paths and pinned interfaces; no worker commits while parent integrates.
- Current evidence supports effective length and tuned controller settings, but not a complete measured rigid-body/motor model. Surrogate parameters will be labeled rather than guessed as facts.

- Parent integration red stage: both new test modules failed on absent control.policy, then passed after implementation and public float-scalar normalization.
- A real parity failure at rail handoff required binary32 governor arithmetic; no tolerance widening. Exact hard-rail and balance-start threshold behavior was also matched to native float32.
- Integrated suite: 122 tests passed; archive tunnel regressions: 25 passed. External core wheel: 108 discovered, 101 passed, 7 optional skips. External sim wheel completed a 100-step upright rollout.
- Two final 10-second provisional-model rollouts completed without faults or saturation: upright stayed in BALANCE; auto entered BALANCE after 1,275 swing-up ticks. This is local model evidence, not rig identification.
- All 70 preserved source hashes remain unchanged. Independent whole-change review completed with no actionable findings; see evidence/phase2/review.md.
- Final reviewer added 50,000 randomized discrete-parity ticks, 10,000 numerical-parity ticks and a mixed lease/sensor timing probe, all passing. No fix wave was needed. Local branch is retained under the owner's full-autonomy authorization; no push, merge or hardware deployment performed.
