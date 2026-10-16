# Phase 0: portable known-working baseline

Approved in chat on 2026-10-13. Work in /Users/rbafna/projects/cartpole_v2.
Preserve the current controller, firmware, tuning, and vision algorithms. No
Jetson access, flashing, or hardware execution. Owner will test on Jetson.

1. Verify committed source against Git blobs; inventory ignored data. Recover
   committed redundant material from Git, not duplicated originals. Retain unique
   uncommitted measurements; discard generated caches/builds/derived replay video.
2. Produce archive/good_balancing_jetson with unchanged console modules/preset,
   one teensy_firmware/teensy_swingup tree, retained tests and a uv entry point.
3. Move vision2 and vision3 into archive. Add vision3 packaging and repair only
   integration-test path wiring. All pendulum_vision source remains unchanged.
4. Add a foreground loopback SSH tunnel using the previously verified public
   host key, configurable destination/ports, strict checking and failure handling.
5. Replace obsolete active docs/evidence with provenance, instructions, revised
   architecture and verification. No previous-v2-planning or originals directory.
6. Run locked environments, relocation/preset tests against a fake board, console
   and vision suites, JS tests, tunnel checks, source hashes and compile-only
   firmware validation. Review once before delivery. Live checks remain pending.

## Decisions and progress

- Reuse the user's clean v2 checkout on codex/phase0-baseline; a second checkout
  would complicate the explicitly requested directory cleanup.
- Baseline commit: 1d48532c4987e6e12b40ddeb2a78931ff701c3e0. All inventoried tracked
  files match. origin/main locally points to the same commit; no remote fetch.
- Baseline tests: vision fails two imports due to missing console fixture path.
  Preset suite fails its relocation fixture (missing vision_telemetry.py) and an
  outdated assertion that treats a read-only enc poll after stop as motion.
  Fix fixtures/assertion without modifying controller behavior.
- New launch and tunnel tests are run failing before adding the launchers.

## Completed locally

- Moved vision2/vision3 and built the minimal balancing package, retaining one
  firmware tree under `teensy_firmware`. All 70 selected source/config files
  match their baseline hashes; saved tuning matches the final verified preset.
- Kept 353 unique ignored measurements (536.74 MiB), removed 340 verified
  duplicate copies, and discarded generated outputs. These measurements remain
  local and ignored; Git preservation applies to the tracked source.
- Locked Python projects and tested their actual installed commands from fresh
  copied checkouts with spaces in the path. The fake board verified preset
  restoration without changing its existing encoder reference.
- Passed 38 console, 88 vision Python, 16 dashboard JS and 4 tunnel tests; one
  real GStreamer test is skipped locally. The renamed sketch compiles with
  seven existing status-message truncation warnings, without flashing.
- Independent review found one tunnel path-quoting issue. A real offline SSH
  parser regression failed first, then passed after quoting/escaping the option.
  The review's source-only relocation coverage gap is covered by the separate
  fresh uv project integration run. No further review cycle was needed.
- New vision behavior, SDK, executor, limit switches, simulation and live timing
  experiments remain future work. Jetson launch/physical verification is handed
  to the owner in `jetson-testing.md`. Results: `evidence/phase0/verification.json`.
