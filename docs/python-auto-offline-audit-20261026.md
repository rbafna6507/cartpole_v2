# Native AUTO and Python AUTO: offline audit, 2026-10-26

Neither controller is trained. Native AUTO executes the hand-designed energy-shaping, approach, capture and balance equations in firmware. `python-auto` calls `run_host_controller`, reads the complete live parameter catalog while stopped, and constructs `ExecutorFeedbackPolicy`. It does not load a PPO actor, training environment, or separate saved Python gain file. Loading a native controller profile changes the values the next Python run reads; it does not train or replace a learned policy.

## Differences that matter

| Concern | Native AUTO | Python AUTO |
| --- | --- | --- |
| High-level decision cadence | 1 kHz MCU tick | 100 or 250 Hz, selected telemetry cadence |
| State | MCU filtered angle/rate and current counted motion | Snapshots of those same MCU fields, with USB/host delay |
| Observer at start | AUTO requests reset to measured angle and zero rate | External ARM retains the running MCU observer |
| Action execution | Local demand followed by one governor | Raw demand sent with anchored 20 ms expiry; same MCU governor |
| Approach/speed planning interval | 1 ms | Nominal 4 or 10 ms interval |
| Capture forecast | Native float32 feasibility forecast | Optimized Python float64 equivalent, separately checked against actual C++ headers |
| Spin/BAL loss handling | Native spin-center/wait and BAL return states | Spin fault / BAL release stops; not equivalent recovery state machines |
| Runtime risks | MCU deadline/encoder/motion faults | Those faults plus host cadence, scheduling and transport deadlines |

The controller parameter `leff` (0.124 m in the preserved working profile) is part of the hand-designed equations. The fitted simulation plant length (~0.1603 m) is a different quantity in a different layer. Automatically substituting fitted plant values into the controller would change tuned gains and capture forecasts, not merely improve simulation fidelity.

The older `ReferencePolicy` is an offline 1 kHz reference adapter. `HostRatePolicy` is a separate older four-channel example. Neither is the implementation selected by the console's `python-auto`; do not use their default simulations as acceptance evidence for it.

## Verification performed without hardware

Read `rig/console.py`, `rig/policy.py`, `policies/executor_feedback.py`, `control/reference.py`, and the actual firmware AUTO/ARM/observer paths. Existing feedback and diagnostic tests passed (81 tests). Capture forecast/native parity checks also passed (48 tests), compiling and exercising the actual C++ headers.

`evidence/offline-developer-20261026/auto-surrogate-comparison.json` contains six 10-second diagnostic runs with the preserved bw10 parameter file, its default fallback rail geometry, two initial angles and native-reference/Python100/Python250 variants. This is the existing ideal-acceleration diagnostic surrogate: controller leff also defines its plant, damping is assumed, transport delay is zero, and native-reference means Python reproduction, not execution on a Teensy. It is not the unified calibrated Gym environment or a gain recommendation.

From exact hanging, no variant captured within ten seconds. With the initial angle displaced by 0.05 rad, the native-reference captured at 1.442 seconds and held the rest; the two Python variants did not capture. This demonstrates that sampled execution can diverge even without transport faults. It does not isolate the physical failure or establish that either controller is unreliable on the rig.

## Next reliability experiment, after USB repair

First require a stable stopped transport and repeatable homing/reference. Compare native and Python using the same captured live parameter snapshot, reference, home and initial pose. Record capture time, continuous hold, missed captures, rail recovery, requested/applied command difference, observation age and host deadline tail latency. Repeat trials rather than selecting one successful run.

Offline, vary decision rate, command/telemetry delay, observation start state and initial conditions on the versioned calibrated plant. Treat observer-reset and sampled capture changes as counterfactuals first. Tune separately for the sampled host controller only after the failure is reproducible; preserve firmware safety and the successful native profile. No gains, firmware, deployment, or rig state were changed by this audit.
