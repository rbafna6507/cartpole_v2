# Independent passive heldout review — 2026-10-16

Verdict: PASS for the declared aggregate passive statistical assessment, with no substantive scoring, source-split or admission bug found. This is not physical model acceptance, full-episode rollout validation, upright/forced-motion validation, or approval of a full-rig RL environment.

Reviewed the frozen evaluator, six focused tests, source-bound annotations, original compact export, assessment, supplementary diagnostics and final report. No repository source, hardware, SSH, service or calibration change was made during this review.

## Independently verified

- All six evaluator tests passed (0.780 s). The no-refit test replaces fitting with a raising function, compares the original validation math exactly, and checks preserved training parameters. Static heldout, reused recording identity and reversed board timestamps reject.
- Frozen training manifest SHA256 `04befe14b16a54e5288d4326a7ca5d826e8c5a169dc20206dd1108ea160aa744` and all eight artifact hashes match. The three pre-score evaluator/test/annotation pins also match.
- Annotations SHA256 `8d26fa57c18055de73355657584cc3e2bd7b3e176c5dadb8c414691490c40d9b` bind the intervals 31.0–36.4, 44.8–51.2 and 63.0–70.0 seconds to export SHA256 `183dc05f790630640cc22ae8a1e90c469cac9dc92faec26c80436f7b427e1a5f`. Independent root review agreed these intervals before scoring. Raw training/heldout source hashes are disjoint.
- All magnetic and camera parameter dictionaries and gate configurations equal their frozen training versions exactly. No fitted offset, model choice or episode boundary was changed by evaluation.
- Entire export has flags 205, fault 0, mode 0 and last_seq 0; no reversed board or host clocks. One exact duplicate board snapshot is checked before removal. Selected magnetic episodes contain 4700 samples with maximum gap 4 ms.
- Independent evaluator rerun is byte-identical to the packaged assessment, SHA256 `639c95e3544db68a3053227f525a553efc0ac2551f45a832727703a6b40c4dfb`. Supplementary diagnostics also reproduce byte-for-byte.
- Final heldout artifact hashes all match verification.json. Final report SHA256 `a52d551ef159ac9184419b8b607bc42f1a4155306433115f1ae8fcf4dd58b02f` includes the requested explicit forecast reinitialization limitation.

## Interpretation

Frozen magnetic viscous parameters pass the predeclared aggregate gates: forecast RMSE 0.0703792476 rad, p95 absolute error 0.1327684088 rad, integral NRMSE 0.0914158145; 35 forecasts, 51 weak windows and angle span 1.9174753 rad. Each forecast is only 0.5 seconds and starts from measured angle and a past-only angle derivative. The result does not establish accurate full-episode open-loop dynamics.

Errors are uneven across releases. Episode 1 p95 is 0.17418 rad. Episode 3 RMSE is 0.08728 rad and p95 is 0.17550 rad. These exceed the analogous aggregate thresholds when examined per episode. They are correctly disclosed as supplementary limits, without substituting a new post-score gate. The primary viscous+Coulomb model remains rejected because training gamma is negative despite passing heldout residual thresholds.

All three heldout raw-pivot pixel diagnostics pass, but the training episode 2 camera coverage/gap failure remains disclosed. The camera remains an uncalibrated projection with uncertain exposure/transport timing. Quiet pivots and hand restraint support the fixed-cart assumption but do not certify metric or out-of-plane stationarity. Counted cart position with the driver disabled is not independent physical motion evidence. The fitted gravity-phase offset is not proven encoder zero error.

The opt-in MuJoCo profile may be described only as a conditional passive comparison. Effective length and angular damping are identified within the declared sensor/model assumptions; mapping damping to hinge torque still requires assumed inertia. No mass, actuator input gain, physical delay, motor friction or force calibration is established. Existing rejected forced-input characterization remains rejected; no upright or forced dynamics claim follows from these passive hanging-angle trials.

## Independent outputs

- `/tmp/cartpole-python-id-20261016/independent-heldout-assessment.json`
- `/tmp/cartpole-python-id-20261016/independent-heldout-diagnostics.json`

Reproduction commands use the repository `.venv/bin/python`, `PYTHONDONTWRITEBYTECODE=1`, the frozen evaluator/diagnostic scripts under `evidence/system-id-20261016/analysis/heldout/`, the source-bound annotations there, and `/tmp/manual-ringdown-heldout-01-columns.json.gz`. Output destinations above were new files; packaged evidence was not overwritten.
