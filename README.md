# Cartpole v2

A shared Python interface for simulated and physical cart-pendulum experiments,
with selectable observations and owner-controlled safety enforcement.

**Current status:** architecture and first-milestone design for review. The user
selected the offline measurement foundation on 2026-10-12. Product implementation
has not started. Existing software remains in `../cartpole`.

- [Roadmap and system boundaries](docs/roadmap.md)
- [Assessment of the existing software](docs/assessment.md)
- [First milestone: offline measurement foundation](docs/specs/2026-10-12-measurement-foundation.md)
- [Source fingerprints](evidence/source-inventory.json)
- [Fresh offline replay](evidence/replay-baseline/summary.json)

The intended location is `/Users/rbafna/projects/cartpole_v2`, interpreting
`/projects/cartpole_v2` as a sibling of the existing project.

## Current working boundary

Another session owns the Jetson and rig. This project currently uses local files
and local tests only. Do not launch processes on the Jetson, open its Teensy
connection, send even `stop` or telemetry configuration, claim the camera, change
device controls, flash firmware, or alter the active `cartpole` working tree.
Read-only SSH inspection was permitted, but was unnecessary for this assessment.

The first milestone has no hardware backend. Existing recordings from different
dates are independent datasets, not synchronized encoder/vision ground truth.

## Implementation direction

Preserve useful source and tests with provenance, then port components in small
reviewable slices. The initial package will be `cartpole_v2`, with optional vision
and simulation dependencies. The public policy interface will be separate from
the trusted operator interface that arms, homes, resets, and calibrates the rig.

This directory is a design handoff, not a commissioned hardware release.
