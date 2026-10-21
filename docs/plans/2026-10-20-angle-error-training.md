# Angle-error training and explicit balance refusal diagnostics

User intent: explain the observer-profile refusal, train for angle error, and
clarify remaining identification gaps. During implementation, diagnose a real
70 ms balance trial that stopped on angular rate. Existing autonomous software
work remains authorized. Later user steering explicitly authorizes further autonomous hardware characterization and less restrictive commissioning guards.

## Design and constraints

Keep the current numeric actor, frozen profiles, source-hash admission and all
motion limits unchanged. Work in the existing requested cartpole_v2 checkout.
Add a separate offline experiment that rotates only the actor's valid angle
sin/cos channels by a reproducible per-episode constant bias. Truth physics,
reward, angle-rate feedback, ages, validity and native observer remain unchanged.
This models an actor-input offset after quantization, not a complete calibrated
encoder law. Use raw-angle profiles only. A copied experiment can explicitly
choose bw=6, 8 or 10, without editing the original profile or live board.

## Implementation and validation

- [x] Add tests for reproducible episode bias, unchanged truth/reward and other
  observation fields, invalid inputs, seed separation and output preservation.
- [x] Implement standalone error-training module and runnable CLI, reusing the
  existing teacher/PPO helpers without monkeypatching pinned modules.
- [x] Run matched short baseline/bias trials on bw=8 and independent fixed
  evaluation offsets 0, ±0.5 and ±1 degree. Preserve initial and final results,
  recipes, source identity and checkpoints; do not export a hardware actor.
- [x] Add regression tests requiring explicit variable/value/bound for each
  runtime balance guard. Improve only the refusal message, retaining STOP and
  exact thresholds. Stage that diagnostic update to the isolated Jetson release
  after tests, without serial access or motion.
- [x] Preserve and analyze the user's raw failed run; distinguish the observed
  +1.58 degree start and rate limit from an unproven physical calibration cause.
- [x] Document supported simulation inputs versus unresolved actuator/angle/timing
  measurements, and give reproducible local training commands.

Initial/final comparisons are development evidence. No robust-transfer claim
follows from these small budgets or from testing an already inspected offset.

## Authorized extension after the operator trial

The user requests full learned swing-up/balance, fewer narrow wrapper limits,
and autonomous collection of remaining identification data. Add an explicit
rig guard profile while preserving default commissioning behavior and all native
Teensy switch/rail/health/command-lease authority. Keep balance-only start admission
for the balance-only actor; relaxing runtime guards does not create swing-up.

Collect the previously incomplete standard signed pulse/reversal dataset at the
user-confirmed working bw=8, with separate validation runs and native AUTO
reference trials. Record pre/post settings and restore bw=10 at handoff so the
original pinned actor remains runnable. Preserve reference 330 and home 17 during campaigns; no flash,
no encoder recalibration, no camera measurements (operator ruled them out today).

Run a standalone full-task randomized pilot from the preserved anchored swing
checkpoint, using the latest copied bw8 experiment, angle bias and engineering
dynamics variation. Keep earlier modules/checkpoints/profiles immutable and
report pre/post development results plus fresh held-out tests if warranted.
No independent physical cart gain or angle calibration may be inferred from
commanded/count telemetry alone. Do not select new simulator physics without
identifiable evidence and held-out improvement.

The final separately recorded full-HOME audit intentionally advanced home 17 to
18, repeated the same measured span and preserved all settings/reference.
