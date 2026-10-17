# Batch 2 passive identification and early finish

The operator collected `passive-training-2` and `passive-validation-2` on the Jetson and intentionally ended each with Ctrl-C after finishing. The original collector recorded KeyboardInterrupt in parent and camera reports, although STOP succeeded and logger termination was clean.

## Preserved evidence

`original-recordings.tar.gz` contains all eight original files, byte-for-byte. `original-manifest.json` binds their hashes. Analysis working copies are in ignored `runs/passive-batch2-original/`. Recovery sidecars are separate assertions, copied into `analysis/training-recovery.json` and `analysis/validation-recovery.json`; the original reports still say incomplete/KeyboardInterrupt. Every recovered load reproduces the strict evidence checks.

Training contains 170.03 seconds after baseline; validation 123.03 seconds. Both have zero logger drops, no active-control commands, healthy disabled states, preserved camera clock anchors, and confirmed STOP. Training has a legitimate logging race: serial write occurs before the command event, so a redundant STOP reply appears just before its command log. Recovery retains an earlier ordered STOP/ACK pair, requires disabled telemetry after the final STOP, and prohibits rearm. It never rewrites timestamps.

## Analysis outcome

All six releases per recording were annotated from raw encoder and independently clock-mapped camera geometry before the first fit. There is no replayable movie; exact hand-clear time is an assumption based on operator-reported free releases and observed transitions. Free windows exclude manual lift and static tails. Annotation intervals were not adjusted to improve fit scores.

The viscous model fit is **rejected and was not exported**. Training yields effective length 0.16138 m, angular damping 0.35141/s and local raw-angle phase −0.11393 rad. These are diagnostic fitted values, not new firmware settings or a globally calibrated encoder. Validation short 0.5 s prediction RMS is 5.64° versus the unchanged 4.58° gate, P95 is 10.74° versus 8.59°. Several individual releases and continuous forecasts also fail.

Camera/encoder comparison passes for all six validation free intervals and five training intervals, but not every held release pose qualifies. In both runs, right-side horizontal holds lack camera geometry. Release 02 has excessive encoder variability during the annotated hold (training 5.07° and validation 3.24° P95–P5), while camera variability is about 0.92° and1.13°. This is evidence to investigate, not proof of which sensor or mechanical component is at fault. Verified left-side horizontal poses are about 92°. Nominal 30° releases were closer to 38–43°; measured conditions are retained.

The hanging zero repeats within 0.088° across recordings. Removing this constant offset does not resolve dynamic sensor differences or encoder nonlinearity. More nominally identical free swings alone are not yet the priority: examine initialization sensitivity/angle mapping and restore marker visibility at the right horizontal pose before declaring a simulation model accepted. No simulation model, gains, encoder reference or firmware was changed.

The full forecast arrays are losslessly archived in `analysis/fit-review/report.json.gz`. See `analysis/batch-summary.json`, camera review overlays, and `analysis/fit-review/recorded-vs-frozen-ode.png` (or PDF). Orange predictions in that plot use the saved pendulum ODE; they are not MuJoCo trajectories and do not change the rejection.

## Reproduce

Extract the original archive into a new local working directory (the archive contains two named run directories). For each original `rig-*.jsonl`, run:

```sh
./scripts/system-id recover-passive --input PATH/rig-EXACT.jsonl \
  --reason "Operator confirmed collection finished and used Ctrl-C because no finish command existed"
./scripts/system-id review-releases --input PATH/rig-EXACT.jsonl \
  --annotations evidence/passive-batch2-20261017/analysis/training-annotations.json \
  --output NEW-training-camera-review
```

Use validation annotations for the other run. Review exit 2 means a quality check rejected; artifacts are still saved. Fit with `fit-passive --training TRAIN --training-annotations TRAIN_JSON --validation VALID --validation-annotations VALID_JSON --model viscous --output NEW-fit.json`, then `review-fit --fit NEW-fit.json --validation VALID --validation-annotations VALID_JSON --output NEW-fit-review`. Do not export a rejected report.

## Collector fix

`done` + Enter or first Ctrl-C during passive recording requests controlled early finish; preflight/baseline interrupts and repeated interrupts remain aborts. Requested/elapsed durations and finish reason are recorded. Child camera ignores terminal SIGINT so its parent owns shutdown. Fresh camera and encoder evidence, latched transport/logger errors, and camera-close failures are checked before success. No serial was opened for this fix/analysis.

## Verification

Final full suite with required local socket/process permissions: **1,309 passed, 8 skipped, 390 subtests passed**, in 76.07 seconds. An earlier restricted run failed because localhost TCP/UDP binding and subprocess IPC were blocked; its log is retained alongside the successful authorized run. Independent review found and regression-tested stale camera shutdown, latched error completion, pre-interrupt telemetry freshness, and replayed board snapshot cases. The revised scope had no remaining review findings.

Installed and hash-verified 76 source files in `/home/rbafna/cartpole-v2-live/staging/operator-id-20261017-camera-zero`; locked CLI help succeeds on Jetson. Original recording files were not modified. See `finish-update-manifest.json` and `verification/deployment.json`.
