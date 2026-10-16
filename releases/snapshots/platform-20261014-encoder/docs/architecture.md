# Revised v2 architecture

Agreed direction, 2026-10-13: build a Python-accessible path incrementally against
the preserved working controller. The baseline is the saved console, its runtime
preset and `teensy_firmware/teensy_swingup`, not the old deployment prototype.

## Responsibilities

- **Teensy:** step timing, bounded motion, local ceilings, command expiry,
  encoder/health acquisition, latched faults and watchdogs. Limit switches will
  be added later; no current switch enforcement is claimed.
- **Trusted Jetson broker:** sole device owner, timestamped observations, action
  validation, experiment duration and recordings. UI and policies subscribe.
- **Observation providers:** magnetic angle, step-derived cart state, calibrated
  vision, images, and explicit fused estimates. Select sources per quantity.
- **Policy SDK:** a policy resets its own state, receives observations and returns
  an acceleration request. Raw sensor access means broker-provided data, not a
  second serial owner. Operator home/arm/calibrate/fault-clear APIs stay separate.
- **Backends:** recording replay, MuJoCo, and hardware share the policy contract.
  Simulation ground truth remains separate from simulated observations.
- **Public execution, later:** portal/queue hosted away from Jetson; an outbound
  worker runs authorized artifacts locally under tested isolation/resource limits.

Every observation carries source, units/frame, acquisition/effective and receive
times, sequence/epoch, validity, calibration identity and measured/predicted
status. Use named joints and topology for later double/triple pendulums, while
commissioning single-link behavior first.

## Implemented foundation

The root `cartpole_sdk` package supplies immutable scalar observations, explicit
source/frame selection, acceleration intents, validated expiring requests,
versioned recording/import adapters and deterministic replay. The executable
example is local only. See [Phase 1 usage](phase1-usage.md) for commands and the
precise limitations of legacy data. Phase 2 adds the 1 kHz reference controller, native firmware oracle, provisional
MuJoCo physics, simulated sensor timing and Gymnasium interface. See
[Phase 2 usage](phase2-usage.md). Images, live transport and fusion remain backend
work; the single-pole model still requires physical identification.

## Order

1. Phase 0: portable archived baseline, launchers, dependency locks, provenance.
2. Observation/action contracts, recorder adapters and deterministic replay.
3. Python reference-controller port against a C++ oracle, plus initial MuJoCo
   model and Gymnasium wrapper using provisional parameters.
4. New Teensy executor and exclusive Jetson broker; native tests, compile checks,
   motor-disabled bench validation, then bounded supervised motion.
5. Sensor timing/calibration and passive/driven identification, with independent
   cart measurements and held-out model validation. Powered excitation follows
   safety commissioning.
6. Shadow comparisons and progressively tested Python/RL hardware policies.
7. Public sandbox, durable queue, portal, results and viewer.

Reference-controller parity includes filtering, gains, startup/swing-up, capture,
balance, loss and recovery transitions. A host-rate change is a control change
that needs validation. MCU emergency behavior is independent of user-policy
recovery behavior; a dead user policy does not automatically start another run.

## Preserved boundaries

`archive/vision3/pendulum_vision` and the saved control/firmware modules are the
reference implementations. New vision behavior belongs in a different directory,
copying selected components with provenance. Archived display fusion is not yet
an approved actuator input. Source rates, timestamp alignment, valid coverage and
physical error must be measured before upgrading it to a control estimator.

The earlier deployment prototype is recoverable through Git and can contribute
individual protocol, motion-governor, model or identification tests after review.
Do not import its public API, provisional geometry or commissioning limits as
the new defaults without checking them against this rig.

The future executor must consider the current shared enable signal for cart/Z
drivers. Keep public Z operation out of the initial policy contract. Physical
switches and a separately commissioned inhibit/stop path strengthen protection;
software cannot infer actual cart location from steps after slip or external motion.
