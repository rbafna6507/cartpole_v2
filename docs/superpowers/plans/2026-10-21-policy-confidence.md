# Local policy confidence cycle Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans for the empirical cycle; parallel independent analysis is authorized.

**Goal:** Select and validate a more promising joint swing-up/balance training recipe before committing a large Colab budget.

**Architecture:** Reuse the governed Gym, preserved actor initializers and existing experiment runners. Add only the missing recipe/evaluation interfaces justified by each result. Preserve all stages and immutable source snapshots; no modification of physical fitting to improve scores.

**Tech Stack:** MuJoCo, Gymnasium, PyTorch/SB3 CPU (one thread per worker), NumPy; two local training workers initially.

**Spec:** docs/superpowers/specs/2026-10-21-policy-confidence.md

## Global Constraints

- New encoder profile,100Hz decisions,1kHz governor,jerk150,25m/s² raw ceiling and20ms leases.
- Initial campaign was offline. The later user-authorized hardware follow-up is recorded below; no generic cloud recipe is substituted for an initialized/curriculum winner.
- Independent seeds and equal online budgets; supervised initialization compute disclosed.
- Existing dirty console files remain separate.

## Review Focus

- Initializer success must be distinguished from PPO improvement.
- Upstream encoder randomization must actually reach every training reset.
- Development and final holdout starts must not overlap demonstrations or training.
- Actual exported numeric actor must produce the same actions and task behavior.
- Cloud must preserve exact selected recipe, initialize correctly, and archive complete checkpoints.

### Task1: Matched balance comparisons
- [x] Freeze protocol and runnable two-worker driver: teacher vs scratch, optimizer seeds11/23/47,20480 decisions each, five-second training, initial/final10s development on93000/93001, LR3e-6,std.02, equilibrium projection both arms. Teacher gains1,2,40,2 from saved successful observed-state law.
- [x] Inspect holds, drift and oscillation; evaluate promising checkpoints on longer fresh starts94000+.

### Task2: Joint-task acquisition and robust follow-up
- [x] Audit previous full-task positives/failures and transfer validated weights into the current profile explicitly.
- [x] Run matched nominal acquisition and gradual uncertainty experiments, preserving balance regression and broad heldout metrics. Add TDD tests for new recipe/runner behavior.
- [x] Iterate based on failure mechanism; declare later evaluation seeds before runs, retain unsuccessful branches.

### Task3: Candidate validation and cloud decision
- [x] Evaluate longer unseen nominal and combined-error conditions, then numeric SDK export/inference parity for promising candidates.
- [x] If useful, prepare/launch bounded exact-recipe Colab runs with independent seeds and checkpoint backup. Otherwise record why local work is still preferred.
- [x] Full tests and independent review for code changes; save compact reports/plots and verify the complete raw-run archive. Stage only this task's work for commit.

## Execution ledger

The user explicitly authorized this cycle and Colab as needed. Reuse the existing branch and checkout. Earlier smoke checks were not convergence evidence; this cycle starts from preserved positive controls. Initial comparison is nominal by design; robustness is a separate treatment, not silently omitted.

### Execution update

- Matched balance stage completed: 6 runs,122880 online decisions, teacher6/6 initial and final10s holds; scratch0/6. Mean teacher tail cart RMS worsened8.154→10.542mm; retain initial checkpoints as controls. Fresh60s initial/final confirmation across3optimizer seeds and8pose seeds is running.
- Joint protocol frozen in evidence/policy-confidence-20261021/joint-protocol.json before results: saved anchored actor, PPO-only vs actor-retention, seeds11/23/47,102400 decisions each. Initial/final checkpoints plus halfway development; training and confirmation poses disjoint. Both execution paths passed8-decision smoke checks. These are not quality evidence.
- Ruling: test proven observed-state teacher rather than additionally spending this cycle's first budget on the historically failed native-gain MLP — positive initialization isolates learning retention; cost is no new native-MPL comparison.
- Ruling: retain the pinned original experiment driver and apply the review's early-fault metric fix in run-joint-stage-v2.py — changing active source would invalidate ongoing runs; old nominal results remain usable only if no early faults occurred. The corrected evaluator records unavailable tail metrics as null. Actual early-dropout regression failed with NaN JSON, then passed after the fix.
- Independent review found no other Critical/Important implementation defect. SDK closed-loop execution and same-observation emission parity remain distinct validation steps. Physical transfer, cloud execution, and final quality conclusions await their own evidence.
- Before joint results completed, selection rule made executable: require zero faults and both upright development poses balanced throughout; rank hanging final holds, then earlier mean capture among held episodes, then longer dwell. Initial actor remains eligible. Exact ties use stable iteration order. Reserved96000..96007 remain uninspected until selection freezes.
- Ruling: add one bounded objective ablation (PPO-only, seeds11/23,102400 decisions each) against their matched finite-payoff controls. Remove terminal dwell bonus and bootstrap only normal horizon cutoffs, with unchanged physical safeguards/fault penalties. The original hidden dwell/time creates critic aliasing; terminal-bonus/value-loss association (.907/.835 in seed11) motivates a test, not a causal claim. This jointly changes horizon interpretation and payoff, so cannot distinguish their separate effects. Other settings remain fixed; protocol saved before execution. Preserve future confirmation poses until all candidates are selected.

### Hardware follow-up authorized during the local campaign

The user requested short iterations between learned balance and the physical rig and confirmed motor power on, rig clear, and console closed. Local training continues independently. Hardware preparation read an existing encoder fault4 with current healthy magnetic/configuration status; stopped checks showed no new I2C errors, then explicit CLEAR and slow physical-switch HOME completed. The cart is centered and disabled, reference533 retained, home epoch32, measured span16509steps, rail half0.3090375m. No firmware upload/reset or safety-limit change was performed.

A fresh explicit upright pose is pending. The proposed first live actor is balance teacher-seed47 final20480, which completed8/8 uninterrupted60s simulation confirmations. Its actual SDK/NumPy export checks are separate from physical success. Short1s then conditionally longer trials use the normal console policy, 20ms leases, jerk150, full declared25m/s² action scale and existing physical-switch protections. Camera/control CPU masks are restored after each invocation. Hardware traces are new development evidence and cannot establish global swing-up performance.

The continuing-objective integration review found no blocking defect. One minor CLI issue remains in the frozen research driver: it does not enforce arm membership from the selected protocol; the actual launcher explicitly passes the declared PPO arm, and recipes record it. Do not edit active pinned driver bytes. The separate low-exploration treatment changes only initial standard deviation from.05 to.02 with the original finite objective, seeds11/23 and102400decisions. The frozen-actor noise diagnostic motivated this comparison; it did not establish training improvement.

### Consolidated outcome

All ten joint runs completed. Selection froze lower-exploration seed 11 at 102,400 decisions. Reserved nominal hanging holds regressed from the initializer's 8/8 to 6/8; small sensor-bias stress tests failed. No generic Colab run was launched. The archived selected candidate was not replaced after inspecting holdout results.

The separate stronger-centering supervised network used zero PPO updates and passed 20/20 final-window holds across four new upright poses and five bias settings at 30 seconds. It still offsets the cart by about 91 mm at ±0.5°; this is tolerance, not bias estimation.

The user explicitly requested longer physical balance tests. With the user-confirmed upright reference 537, the original balance candidate held encoder angle within about ±1° for 7.22 seconds, then stopped on an action lease expiry. Cart RMS was 76.94 mm, so centering remains a concern. Repeated zero-command tests reproduced the expiry, including with logging/mirroring disabled. Detailed instrumentation captured a 10.40 ms notification-to-wake delay. A temporary scoped scheduling-priority comparison is prepared; administrator permission is pending. Hardware remains stopped at counted home, with an action-expiry fault latched, and the firmware lease remains 20 ms.

All model/source/checkpoint/trace bindings and tests are retained under evidence/policy-confidence-20261021. The consolidated EXPERIMENTS.md is the current human-readable record; earlier execution entries above are historical, not current rig state.


### Final hardware outcome

Administrator permission was subsequently granted only to the temporary shell. Controller-only RR10 completed60s and30s zero-command trials and the final25s original-actor operation without timing faults. Both learned actors nevertheless failed balance in the later trials. The stronger-centered actor's fast oscillation was not reproduced by matched fixed-bias simulations; the current model is not ready for hardware-confidence promotion. Latest explicit upright capture is553. Final rehome passed and the board is healthy/disabled, with I2C13; temporary shell closed. Full suite2008passed/8skipped/460subtests, research timing checks13passed, independent reviews retained. Complete outcome and limitations: evidence/policy-confidence-20261021/EXPERIMENTS.md.
