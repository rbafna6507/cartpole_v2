# Phase 1 Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Deliver IPv6 discovery and a local, validated policy/replay foundation.
**Architecture:** Preserve archived algorithms. Add a standard-library tunnel helper and an independent root Python SDK with immutable contracts, strict JSONL, legacy importers and deterministic replay.
**Tech Stack:** Python 3.11+, dataclasses, unittest, uv, OpenSSH; no SDK runtime dependencies.
**Spec:** docs/specs/phase1-foundation.md

## Global Constraints

- Work locally in cartpole_v2 on a feature branch; no rig actuation or firmware changes.
- Preserve archived control/firmware/vision source byte-for-byte.
- No automatic cross-clock/source alignment, sensor substitution or claim of hardware safety.
- Follow existing authorization to implement inline without repeated approval gates.

## Review Focus

- Clock/reset/wrap ambiguity must not create apparently fresh observations.
- Partial and hostile JSON input must fail without producing a usable incomplete recording.
- Unavailable health or calibration must not become valid sensor data.
- Expired/mismatched actions must fail, including exact deadline and bool/non-finite inputs.
- IPv6 discovery must preserve SSH identity and reject option injection and unsafe addresses.

### Task 1: Discover the direct tunnel destination

Files: archive/vision_tunnel.py, archive/vision-tunnel.sh, archive/tests/test_tunnel.py, archive/tests/test_tunnel_discovery.py; README and tunnel instructions.
Interfaces: candidates(ip_json) -> list[str]; prepare(argv, env) -> SSH argv; main() execs SSH. Existing destination/port/key-file overrides remain supported.
- [x] Write failing offline tests using captured SSH invocations and real `ssh -G`: stable/temporary ranking, excluded addresses, timeout/unreachable behavior, retained alias/keys, explicit bypass, malformed input and hostile destination.
- [x] Run `python3 -m unittest discover -s archive/tests`; expected missing helper/new default failures.
- [x] Implement bounded read-only discovery, address validation, probing and strict identity reuse behind the Bash wrapper.
- [x] Run tunnel suite and shell syntax; expected all pass. Probe real discovery without opening a camera or issuing hardware commands if authentication permits.
- [x] Commit the tunnel feature and update ledger.

### Task 2: Immutable observation and action contracts

Files: pyproject.toml, .python-version, uv.lock, src/cartpole_sdk/{__init__,contracts}.py, tests/test_contracts.py.
Interfaces: Session, Topology, Sample, Observation, Channel, Acceleration, ActionRequest, ActionLimits, validate_action; select_channels returns explicitly requested usable samples.
- [x] Write tests for valid multi-joint metadata, missing/null/invalid channels, source/frame selection, separate times, non-finite/bool values, expiration/session/clock/sequence and magnitude rejection.
- [x] Run `PYTHONPATH=src python3 -m unittest discover -s tests`; expected missing package failure.
- [x] Implement frozen dataclasses, strict validation and protocol without device imports.
- [x] Run full SDK suite; expected pass. Create locked root uv project; verify import and no hardware dependencies.
- [x] Commit contracts and ledger result.

### Task 3: Strict recording and legacy importers

Files: src/cartpole_sdk/{recording,adapters}.py; tests/test_recording.py, tests/test_adapters.py, tests/fixtures; evidence/phase1 fixture provenance.
Interfaces: write_recording(path, session, observations); read_recording(path) -> (Session, tuple[Observation,...]); import_console(path, session_id, frame_id) yields session segments; import_vision(path, session_id, frame_id) returns session and observations.
- [x] Write round-trip/deterministic tests, footer truncation/order/schema/malformed data tests; import real baseline snippets and assert honest quality/timestamp/source/frame semantics. Cover wrap/reset and invalid vision numeric remnants.
- [x] Run SDK suite; expected missing recording/adapters failures.
- [x] Implement strict JSONL and streaming importers with line-context errors, no clock alignment and exclusive output creation.
- [x] Run complete SDK suite; expected pass. Exercise whole archived CSV and vision recordings to detect assumptions fixtures miss.
- [x] Commit importers and ledger result.

### Task 4: Deterministic replay and runnable examples

Files: src/cartpole_sdk/{replay,cli}.py, examples/replay_policy.py, tests/test_replay.py, tests/test_cli.py, README, docs/phase1-usage.md, evidence/phase1/verification.json.
Interfaces: Policy.reset(Session), Policy.act(Observation) -> Acceleration|None; replay(session, observations, policy, limits) -> trace records; CLI imports and inspects recordings and runs a built-in example.
- [x] Write tests proving repeatability, once-per-session reset, no wall-clock sleep, missing intent vs zero, ordering/action validation and CLI execution from another directory.
- [x] Run SDK suite; expected missing replay/CLI failures.
- [x] Implement replay and a conservative vision damping example that emits no request for unavailable channels. Add import/inspect/replay CLI and documented commands.
- [x] Run all SDK/tunnel suites plus installed CLI smoke tests, archive hash checks and git diff checks; expected pass.
- [x] Obtain one independent whole-change review, fix important findings with regressions, record final evidence and leave local branch for user testing.

## Progress and rulings

- Base: 2c5ebf2. Owner authorized Phase 1 locally and discovery in the existing tunnel.
- Reuse the requested checkout on codex/phase1-foundation; no duplicate worktree.
- Phase 1 scope follows architecture items 2 only; controller port/MuJoCo are Phase 2.
- The earlier blanket remote-code restriction is superseded only for the requested read-only IP discovery; no remote control or camera operations are authorized here.

- Execution update (2026-10-13): owner explicitly authorized chunked parallel work.
  Tunnel and recorder/importers delegated with disjoint file ownership; parent
  implements contracts, runner and CLI. Shared interface pinned before dispatch.
- Task 2: contracts implemented; 22 contract/selection/action tests RED (missing
  package) then GREEN. Frozen SI types and source/frame/timestamp checks in place.
- Pre-flight interfaces: Tasks 2→3 use exact Session/Observation/Sample fields;
  Tasks 2→4 use Policy and validated acceleration requests; Tasks 3→4 use strict
  read_recording returning a session and immutable observation tuple. No conflicts.

- Tasks 1–4 implemented and integrated: 67 SDK tests and 25 tunnel tests pass.
  Wheel/sdist built; isolated wheel entry point and end-to-end example verified.
  All 70 preserved source hashes match; no archived algorithm/firmware edits.
- Tunnel live preflight succeeded using only authenticated IP discovery and bounded
  TCP probing, without opening the final tunnel or touching camera/control.
- Ruling: reject detectable calibrated→uncalibrated transitions in a vision import,
  while allowing initial calibration — protects a single frame identity from a
  known reset; callers must split such files, and true→true recalibration remains
  a caller verification obligation.
- Ruling: parallel ownership supersedes the original inline-only sequencing at
  the owner's request — contracts were pinned before adapter work; integration
  testing and one independent final review cover shared boundaries.

- Task 3 full-file validation: 101 console files / 1,043,366 observations and
  23 vision files / 560,592 observations accepted. One multi-epoch vision file
  intentionally rejected at line 7102, with reason recorded in evidence.
- Original CSV CRLF bytes preserved with scoped .gitattributes; the fixture
  provenance remains byte-exact and Git whitespace checks pass.

- Independent final review: no critical/important findings. Two small findings
  resolved in one pass: deep JSON nesting now yields contextual input errors
  (CLI regression RED→GREEN), and unusual SSH configuration limits are documented.
  Final SDK suite: 68 passed; tunnel suite: 25 passed. See evidence/phase1/review.md.
- Final integration choice: retain the completed local branch for the owner's
  iteration, consistent with the local-only request; no push, merge or deployment.
