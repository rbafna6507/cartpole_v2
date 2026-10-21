# Policy confidence experiments — 21 October 2026

The original balance actor held the encoder near upright for 7.22 seconds in one trial, but did not repeat that behavior after a fresh reference capture: a full 25-second run lost balance during startup despite uninterrupted control. The stronger-centering actor also failed on hardware, and matched simulations did not reproduce its rapid oscillation. Scoped controller scheduling passed the final timing trials without relaxing the 20 ms lease. The joint swing-up training recipe failed its reserved-pose promotion check. No actor is hardware-qualified and no Colab job was launched in this cycle.

## What was compared

All experiments retain the current 100 Hz policy / 1 kHz executor model, 25 m/s² action ceiling, 150 m/s³ jerk limit, 20 ms anchored command lease, and the measured rail profile. The physical model was not modified to improve policy scores. Encoder errors enter before quantization and the firmware-equivalent observer. Randomization ranges are engineering test ranges, not fitted confidence intervals.

The first stage compared three optimizer seeds (11, 23, 47), each initialized either from scratch or from a supervised feedback teacher. Every run received 20,480 online decisions. Teacher fitting used additional disclosed supervised compute. The teacher law was `clip(x + 2*v + 40*theta + 2*omega, -25, 25)` on observed inputs; it is not a transcription of the native Teensy controller.

The joint stage transferred a previously preserved full-task actor into the current profile and compared ordinary PPO, actor-retention updates, a continuing-objective ablation, and lower initial exploration. There were ten runs at 102,400 decisions each. Matched comparisons use seeds 11 and 23; ordinary PPO and retention also include seed 47. Training episodes lasted 25 seconds. Protocols, launchers, source archives, checkpoints and unsuccessful branches are retained.

## Balance results

Teacher initialization produced 6/6 ten-second development holds, both before and after PPO; scratch initialization produced 0/6. These are repeated outcomes on two poses across three policies, not six independent initial conditions. Mean teacher tail cart RMS worsened from 8.154 to 10.542 mm.

Fresh 60-second confirmation compared initial and final checkpoints across eight shared poses for each of three seeds. Uninterrupted holds changed from 24/24 to 23/24, and mean tail cart RMS barely changed (2.529 to 2.504 mm). Seed 47 retained all eight uninterrupted holds and was exported for the hardware comparison. This supports using it as a development candidate, not a broad PPO improvement claim.

A separate upstream encoder-bias test of that actor exposed poor centering. Zero bias passed both inspected poses; every tested nonzero bias, starting at ±0.25°, lost the final hold through cart displacement. This was reproduced by the original analytic teacher, so it was not merely neural approximation error.

The stronger-centering branch froze the analytic law `(kx, kv, ktheta, komega) = (6, 7, 60, 3)` after a declared development screen. The analytic law passed 20 fresh 30-second tests. One supervised network (seed 47, 1,500 fitting updates, equilibrium projection, zero PPO updates) then passed 10/10 development and 20/20 different fresh 30-second tests at biases 0, ±0.25°, and ±0.5°. At ±0.5° it held with approximately ±91 mm steady cart displacement. Its worst transient displacement was 127.79 mm. It tolerates bias by moving the cart; it does not estimate or remove calibration error.

That network is `training/candidates/balance-20261021-centered/actor.json`. Its strict SDK emission discrepancy was at most 5.71e-6 m/s² and NumPy/SDK disagreement at most 1.78e-14 m/s². All 70,000 saved commands and checkpoint/source bindings were independently checked. See `centered-initialization/final-report.json` and `verification.json`.

## Joint swing-up results and cloud decision

The selected lower-exploration seed-11 checkpoint improved the two inspected development poses. Selection was frozen before reserved-pose evaluation. On eight new 60-second nominal hanging starts, it achieved 6/8 final holds versus its initializer's 8/8. Upright final holds stayed 8/8, but uninterrupted holds declined from 6/8 to 5/8. No alternative candidate was selected after inspecting these results.

Actual SDK evaluation passed the emission tolerance, yet achieved 8/8 hanging final holds where the nominal implementation achieved 6/8. Small numerical action differences led to materially different capture trajectories. Numerical parity and robust closed-loop behavior are separate requirements.

The same selected policy lost all holds in each of four perturbed stress scenarios, including static ±1° encoder bias. All 68 reserved confirmation/control episodes ran and were audited; these were task failures, not discarded evaluator errors. See `joint-result-brief.txt`, `joint-confirmation-summary.json`, `initializer-control-comparison.json`, and their plots.

A longer generic Colab run would not address these demonstrated failures. No cloud training was started. The next recipe should retain the stronger centered balance feedback, explicitly train upstream sensor uncertainty, and preserve initializer controls and unseen long-horizon evaluations. The current small-speed upright friction behavior, camera perspective/calibration, and physical cart tracking remain transfer uncertainties; passive decay fit quality does not validate all of them.

## Hardware evidence

The user subsequently authorized hardware iterations and confirmed the rig clear. Physical two-switch homing passed. An explicitly confirmed upright capture changed the saved encoder reference from 533 to 537. The measured span remained 16,509 steps and usable half-rail 0.3090375 m. Jerk remained 150, bandwidth 10, and I2C errors remained 12 through the first balance and timing trials; the centered-policy trial later incremented the count to 13. No firmware upload or reset occurred.

The first learned trial oscillated physically before an action-expiry fault at approximately 0.51 s. Camera tracking corroborated oscillation; it did not independently resolve the very first encoder jump. A later upright zero-command probe did not reproduce the jump. The enable-disturbance hypothesis is therefore not established.

The longer learned trial (`balance47-run10-gil1-01`) issued 722 actions, all observed accepted. It held raw encoder angle within -0.967° to +0.879° for 7.22 s (0.332° RMS), with counted cart position from -114.0 to +118.16 mm (76.94 mm RMS). It stopped at 7.23 s due to an expired command lease while the last healthy angle was +0.264°. All emitted actions replayed from the saved actor exactly. The subsequent pole fall must not be mistaken for pre-fault loss of balance.

The camera recorded the upright episode, but its angle disagrees with the encoder and varies with cart position. It has no valid cart metric calibration in these recordings. Its image angle is not an independent calibrated vertical reference, and counted cart position is not a physical position measurement. See `hardware/balance47-run10-camera04/signals.png` and `analysis.json`.

Repeated zero-command experiments also timed out. One memory-only, mirror-disabled 25-second run completed, but its repeat failed after about 14 seconds. Reducing the GIL switch interval and changing CPU affinity did not establish reliable scheduling. A detailed two-thread run showed a healthy `notify_all` completing 10.40 ms before the main thread returned from its condition wait, after lease expiry. That wait consumed only 0.068 ms of thread CPU. The last inference took 1.121 ms wall time; the last write took 0.157 ms. This rules out slow final inference and optional logger/mirror work for that instance, while user-space timing alone cannot fully distinguish OS scheduling from interpreter/futex wake handling.

The user granted a temporary RT-priority allowance to one dedicated test shell. Elevating the whole launcher and controller failed on a distinct 47.72 ms read stall. A repeat elevated only the control child, leaving the camera-affinity launcher under ordinary scheduling, and completed 60 seconds of zero commands with no fault. An additional 30-second zero-command check also completed with file logging and encoder publishing restored. Together they retained 8,998 action requests with no dropped records/timing events. This finite success does not guarantee deadlines. The 20 ms lease, hardware parameters, and system-wide limits remain unchanged.

## Reproduction and retention

Run commands from the repository root with `.venv/bin/python`, `PYTHONDONTWRITEBYTECODE=1`, `OMP_NUM_THREADS=1`, and `OPENBLAS_NUM_THREADS=1`. Frozen drivers intentionally refuse overwriting their output directories. Use a new output directory/protocol for a new experiment.

- `run-balance-stage.py`, `run-joint-campaign.py`, and `run-ablation-campaign.py` preserve the training stages.
- `run-confirmation.py` preserves nominal, stress and actual SDK evaluation. Selection and initializer-control declarations are under `runs/policy-confidence-20261021/joint-confirmation/`.
- `centered-initialization/run.py` preserves the supervised centered branch and independent command replay.
- `hardware/trial-timed-v2.py` invokes the actual console policy for up to 60 seconds. `hardware/zero-timing-v2.py` performs full validated actor computation but emits zero acceleration. Both require the sibling `timing_instrumentation.py`; logger/mirror toggles are diagnostic, not a production fix.
- `hardware/analyze-live.py RUN --output NEW_DIRECTORY --actor ACTOR --vision CAMERA_NDJSON` produces finite JSON, CSVs and plots without accessing hardware.

The original `run-joint-stage.py` is preserved unchanged. Independent review found that its early-fault empty-tail metric could produce non-finite JSON. `run-joint-stage-v2.py` fixes this; a regression test exercises the actual early-fault condition. Original nominal runs were audited to have no such faults. Do not silently rewrite frozen experiment source.

`archive-runs.py` packages all completed raw runs, verifies every decompressed payload and original file hash, and splits the archive into Git-sized parts. `archive-manifest.json`, when present, is the authoritative payload/part manifest. Reassemble with `cat runs.tar.gz.part-* > /tmp/cartpole-confidence-runs.tar.gz` from this directory, verify its manifest SHA-256, then extract into a clean directory.

### Longer centered-policy hardware result

`centered-run25-rr10-01` used the scoped controller-only RR10 scheduling and requested 25 seconds. It lost balance early: the encoder exceeded 5° at 0.67 s, and rail braking first occurred at 1.36 s. The raw upright start was 546 against saved reference 537 (about +0.79°). Oscillation grew at roughly 6–7 Hz in the first second; this is a plant/observation/controller mismatch to investigate, not evidence that increased centering gains transferred. Numeric action replay agreed within 7.11e-15 m/s².

The run stopped at approximately 15.92 s on encoder fault 4, with I2C errors increasing 12→13. The later host `mode` rejection followed the board leaving external-control mode; it must not obscure the encoder fault. Balance had been lost long before that fault. Stopped health checks found no continuing errors, then physical two-switch homing passed (epoch 33, same 16,509-step span). A subsequent confirmed upright measurement and a 25-second comparison using the earlier, gentler candidate are recorded below. No hardware acceptance is granted to the centered candidate.


### Refreshed reference and full 25-second original-actor result

The user confirmed a new stationary upright pose. `upright-02` saved raw reference 553 while the motor was disabled; `balance47-run25-rr10-ref553-01` read raw 553, angle zero, counted x zero and healthy status before starting. The change from reference 537 is a difference between user-established poses/readings, not proof of drift at a fixed independently measured true vertical.

The trial completed its full requested 25 seconds, retaining 2,499 action requests and 24.98 seconds between first/last active telemetry samples. Logging and encoder publishing were enabled, all controller threads inherited RR10 on CPUs 4–5, and the launcher remained ordinary priority. No action expiry, encoder fault, or new I2C error occurred. The last action lacks a later active telemetry acceptance sample, so the trace is not a claim that all 2,499 requests were independently observed accepted. Numeric actor replay matched within 7.11e-15 m/s².

Balance failed immediately: the measured encoder angle crossed 5° at 0.05 s, crossed 15° at 0.15 s, and rail braking began at 1.07 s. The camera also shows the ensuing oscillation and fall. At 0.01 s the encoder had changed from −0.088° to −1.494° while counted x was still zero and accepted demand was only −0.070 m/s². This resembles the earlier startup discontinuity, but camera timing/calibration and step-count limitations prevent assigning its cause to encoder error, real mechanical motion, motor enable, or contact release. A zero-command upright probe previously failed to reproduce that jump. No model correction is inferred from it.

The earlier 7.22-second episode had first-quarter-second peak angle only 0.44° and demand RMS 0.20 m/s². The new trial reached 22.06° and 9.67 m/s² over the same interval. It also entered sustained jerk limiting. The 7.22-second episode therefore does not establish reliable startup or disturbance rejection; an unpowered upright pose had also stayed upright during a separate probe. Both successes and failures are retained. `hardware/startup-comparison/startup-comparison.png` and its source script show these starts alongside the centered actor, with independently scaled axes and camera limitations stated.

### What the matched simulation does and does not explain

`hardware-gap-bias0791` evaluates both frozen actors under three explicitly separate hypotheses: exact true upright with +9-count observation bias; actual +0.791° tilt with no bias; and exact upright with no bias. Twelve five-second episodes use the unchanged model and two declared seeds. All 6,000 commands and source/checkpoint bindings were checked; no parameter fitting occurred.

For the centered actor, the bias hypothesis predicts cart displacement (crossing 0.12 m after 1.24 s, peak about 0.183 m), but first-second angle peaks only 1.41–1.49° and never exceeds 5° during five seconds. Actual hardware exceeded 5° after 0.67 s and reached 19.34° within the first second. Treating the same offset as real tilt also settles in this simulator. The current model's static bias alone therefore does not reproduce the observed instability. This establishes a transfer gap, not its unique cause.

The next identification target is the powered small-angle transient: independently measured cart acceleration/startup motion, encoder behavior at enable, observer phase response, and upright friction behavior. The current passive-fit small-speed friction slope is about 32.54/s and has not been independently validated at the upright pose. The camera presently lacks metric cart calibration. Changing friction, delay or acceleration until a policy score improves would be circular; any revised model must predict held-out measured responses before new policy promotion. Further random PPO budget is deferred.

### End state and verification

`rehome-final-01` returned to counted x=0 with mode 0, disabled, fault 0, reference 553 saved, home epoch 33 and I2C counter 13. The temporary priority shell PID 305429 exited; process checks found no remaining trial/launcher or serial owner. The user-level camera service remained active and `/api/clock` responded. Motor supply remains on, with firmware motion disabled. No reset, flash, system-wide scheduler setting or safety-limit change occurred.

The last complete suite passed **2,008 tests, 8 skipped, and 460 subtests**; the separate research timing/polling checks passed **13 tests**. Production source was unchanged after that full run. Reports and plots subsequently added are offline analysis only. The unused periodic-wait diagnostic was never deployed. Unrelated console/runtime working-tree changes are kept out of this task's commit, although exact runtime snapshots are retained with the experiments.
