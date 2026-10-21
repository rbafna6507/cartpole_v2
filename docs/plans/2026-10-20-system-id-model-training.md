# Live system identification and balance deployment, 2026-10-20

User authorization: powered rig is available; run remaining characterization,
update simulation/Gym from evidence, run short training comparisons, and provide
bounded balance-model commands the user can run. No firmware upload is needed.

## Execution plan

1. Inspect camera, exclusive serial ownership, saved reference, measured home,
   firmware and all live gains. Preserve originals; full HOME if needed.
2. Collect short timing and gentle actuator checks before larger signed pulses.
   Retain raw camera geometry, clocks, actions, board telemetry and failure logs.
3. Freeze a training fit before separate validation. Independent physical scales
   and true vertical remain explicit limitations until actually measured.
4. Apply only supported simulator changes; preserve the frozen passive law unless
   new evidence warrants replacement. Run matched short learning comparisons and
   long unseen evaluation of promising candidates.
5. Provide balance-only deployment with shadow default, explicit execution,
   upright/center admission, runtime guards and STOP. Do not claim transfer from
   simulation alone.
6. Review changes and run targeted/full verification before committing.

## Ownership

Parent alone owns all Jetson/serial/motion access. Model-analysis agent owns new
campaign analysis and tests. Training-prep agent owns balance-only hardware
wrapper and tests. Both work locally; no competing serial clients.

## Initial evidence

- Starting commit: 4559d92; branch codex/live-rig-platform.
- Jetson reachable as rbafna@jetson; serial port unowned on initial check.
- Maintained camera service alive at loopback 3090, ~80 processed FPS, but no
  usable pole geometry initially. Inspect framing before motion.
- No new physical data or accepted simulator updates yet.

## Scope correction

User confirms insufficient camera lighting and requests no vision today. Add explicit encoder-only collection; retain default camera requirement for ordinary mode. Physical cart tracking, metric actuator gain and camera/encoder calibration remain unmeasured. Driven pole prediction is conditional on commanded acceleration. Working profile restored and verified (bw=10, jerk=150); saved reference 330 retained. Slow full physical HOME started with switch interlocks.

## Execution outcome

- Completed physical HOME: saved upright 330 retained, home epoch 16, span 16,507 steps, working bw=10 and jerk=150 verified. No firmware changes.
- Recorded successful and failed timing/actuator trials and two independent 25-second native AUTO validation runs. Camera measurements omitted by user request.
- Identified a 53.8 ms cyclic GC pause; implemented tested scoped GC deferral. Later wake/dispatch stalls remain unresolved. No lease or safety limit relaxed. Temporary camera CPU affinity restored.
- Updated the frozen simulation profile to the measured rail and current 41 settings; retained the passive law. Local hanging alignment improves near-hanging prediction, but native prediction fails. No actuator or global angle fit promoted.
- Completed six training runs with equal online budgets, paired heldout evaluations, numeric SDK parity, eleven stress scenarios and a separate teacher centering diagnostic. Nominal balance is promising; ±1° angle bias still fails. Candidate remains development-only.
- Added the reviewed bounded balance wrapper. Actual Jetson numeric shadow completed 25 seconds and 2,501 inferences without ARM. Final state is disabled and healthy at x=0, reference 330, home 16, with no new I2C errors.
- Full suite: 1,717 passed, 7 skipped, 456 subtests. Reports, raw bundles, recipes/checkpoints and commands retained.

See `docs/checkpoint-20261020.md` and `evidence/system-id-20261020/` for results and remaining gaps. Missing independent cart/angle measurements and intermittent host deadlines prevent claiming complete system identification or robust hardware transfer.
