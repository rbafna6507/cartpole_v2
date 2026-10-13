# Independent Phase 2 final review

Reviewed `/Users/rbafna/projects/cartpole_v2`, base `29bc06a` through HEAD `189a4c8a5f1ee644a1fecc52e6eb9e2c1f934606` on `codex/phase2-controller-simulation`. The checkout was clean at the end of review. This was read-only; no implementation or archive files were changed.

## Result

No actionable correctness or requirements findings in the reviewed scope. No fix wave is requested.

## Review performed

- Read the Phase 2 specification, plan, usage, implementation, native test support, tests, and controller/model/verification evidence. Reviewed the actual change against the base, including CLI and package resource configuration.
- Compared Python control flow and command handling against the preserved original `controlTick`, `handleLine`, swing controller, rail recovery, spin recovery, upright session and motion governor. Checked health faults, host/manual deadlines, unsigned timer differences, recovery command rejection, governor placement, start/capture/loss ordering, and documented binary32 boundaries.
- Verified that the native oracle includes the whole original sketch and original headers, rather than a translated controller. Its four substitutions are exact-match asserted and limited to native interrupt compatibility, decoded angle injection, calibrated cart-position injection and observing demanded acceleration. Inspected reset and peripheral stubs and their documented exclusions.
- Inspected ReferencePolicy session/channel selection, sample effective-age checks, exact observation cadence and sequence enforcement, fault latch/reset behavior, angle observer initialization, and use of commanded velocity rather than simulator velocity truth.
- Checked the acceleration-to-force derivation against both rows of the unconstrained two-DOF equations: the hinge row determines hinge acceleration; the cart row determines the force, with bias/passive compensation and clipping only at the force bound. The model has no hinge actuator or active contacts. Truth and policy sensors remain separate.
- Inspected action validation before lease/state mutation, lease replacement/None retention/substep expiry, seed/reset behavior, delayed acquisition/delivery and sample timestamp retention, numerical failure latch, episode end handling, and Gym observation masks/ages.
- Reviewed installed-wheel evidence, dependency-free core boundaries, optional dependency imports, bundled settings/model metadata, and runner output/provenance semantics. Existing full-suite, wheel, rollout and archive-hash results were reviewed as supplied evidence, not represented as freshly rerun by this reviewer.

## Additional independent execution

These probes were run against the reviewed HEAD using the existing environment, without repository edits or remote/device access:

1. 50,000 deterministic randomized trajectory ticks (seed 155, 50 trajectories of 1,000 ticks), varying measured angle/cart position, commands, manual velocity and intermittent encoder health. Python/native mode, enabled, upright-only and brake-direction outputs matched exactly on every tick.
2. A separate 10,000 deterministic randomized trajectory ticks (seed 524, 10 trajectories of 1,000 ticks), checking numerical outputs against the stated `2e-4 + 2e-5*abs(native)` trajectory tolerance. No violations. Maximum absolute errors were:

| Field | Maximum error |
| --- | ---: |
| angle_hat (circular) | 2.3891296407896334e-7 |
| rate_hat | 5.7240309818684665e-5 |
| velocity | 1.4305165588757163e-6 |
| acceleration | 1.0252026635715339e-4 |
| demand | 1.0216196417234258e-4 |
| energy | 2.227569333435042e-6 |

These maxima supplement the scripted evidence; they are not replacements for its scenario-specific figures.

3. Combined timing probe with 1 ms physics, four physics ticks per control call, sampling every three ticks, delivery delayed two ticks, and a 2.5 ms lease. Exactly three physics ticks used the acceleration request, the fourth used zero demand, and cart velocity was 0.006 m/s for a 2 m/s² request. Sensor effective/receipt times were 0/2 ms at the first returned observation and 6/8 ms at the second, confirming independent sampling/delivery/observation timing.

## Limitations

This is a bounded code review plus supplemental local probes, not proof over all parameter values or trajectories. Native agreement is tolerance-based, not bitwise or whole-board equivalence. Native stubs do not validate the MCU scheduler, pulse ISR, peripheral/electrical behavior, calibration, EEPROM or transport. Existing installed-wheel checks were inspected rather than rebuilt a second time. No hardware, physical system identification, hard real-time behavior or sim-to-real safety claim was assessed. The provisional model and the deferred executor/broker/public-policy isolation scope are described consistently in the reviewed documentation.
