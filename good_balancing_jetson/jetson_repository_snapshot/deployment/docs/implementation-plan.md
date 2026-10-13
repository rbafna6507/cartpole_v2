# Pendulum deployment implementation plan

Goal: deliver a testable commissioning starter for firmware, SDK, simulation and identification in the requested deployment/ directory.
Spec: design.md (including exact shared API and wire format).

The user explicitly requested implementation following the architecture discussion. Work only in the new directory, retaining existing firmware and unrelated checkout changes. No flashing, physical actuation or public deployment.

1. Shared types/configuration: tests for invalid/unknown configuration and serialization; implement documented dataclasses and a source-grounded, provisional rig profile.
2. Firmware: new sketch using baseline cart_motion/cart_mechanics and source-derived pulse I/O; strict v1 parser, owned sessions/fresh actions, hard local caps and fault latch; native adversarial tests and actual Teensy compilation. No Z movement or fabricated IMU.
3. Hardware SDK: frame codec; private TCP and optional USB transports; state/command methods sharing the simulation interface; loopback fragmentation, integrity, stale state, no automatic enable/retry, and close tests.
4. MuJoCo: model geometry/inertia/sign and bounded actuator/governor; SDK backend and Gym wrapper; headless sign/period/timeout/reset checks.
5. Identification: recording/noise/free-decay/drive, nonlinear fit and held-out validation, new-config export; reject invalid/insufficient captures, preserve interrupted runs, synthetic parameter-recovery tests.
6. Integration: runnable examples, CLI, setup and bench checklist, source hashes, Internet/sensorshare design; run all tests and compile; independent review and fix material findings; copy only deployment output to requested location and verify its contents.

Review focus: stale queued TCP commands; wrong units/angle sign; false cart measurement claims; disabled/shared-enable behavior; fitting held or moved-cart data; source geometry vs current assembly confirmation; packaging paths after installation.

Each owned component writes its tests before implementation, reports commands and observed results, and does not edit a neighbor's files. No git commits in the user's already-dirty checkout for this iteration.
