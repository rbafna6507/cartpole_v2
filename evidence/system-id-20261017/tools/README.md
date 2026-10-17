# Analyze independently collected short pulses

`analyze_pulse_batch.py` combines several completed short pulse recordings for the existing driven weak-form fitter. Each three-second hold remains its own independent segment. This can supply the default minimum of 20 training windows without extending the hardware experiment or weakening any fitting gate.

The declared experimental split is **signed 10/20 mm training and signed 30 mm validation**. Freeze this assignment before scoring validation. Supply only the intended successful runs; failed attempts remain preserved in their original directories and are rejected as inputs. This script never controls hardware, changes parameters, installs a model, or modifies the packaged SDK.

Run from any directory, using exact local paths:

```sh
TOOL=/absolute/path/to/cartpole_v2/evidence/system-id-20261017/tools/analyze_pulse_batch.py
"$TOOL" --help
"$TOOL" \
  --training /runs/plus10/rig-EXACT.jsonl \
  --training /runs/minus10/rig-EXACT.jsonl \
  --training /runs/plus20/rig-EXACT.jsonl \
  --training /runs/minus20/rig-EXACT.jsonl \
  --validation /runs/plus30/rig-EXACT.jsonl \
  --validation /runs/minus30/rig-EXACT.jsonl \
  --output /analysis/NEW-batch.json
```

The executable uses `uv` with its declared NumPy dependency and resolves SDK source relative to its own repository location. An existing environment with the SDK's `id` extra may instead run `python "$TOOL" ...`. No simulation or serial dependency is needed.

Each input must retain its sibling `report.json`. Compressed JSONL and `archive.tar.gz::exact/member.jsonl` work through the packaged bounded loader; a matching archived sibling report is required. Admission checks the raw content hash, report completion, confirmed STOP, zero logger drops and absence of collection/camera failures. Raw termination errors also reject admission. Unlike the historical single-file compatibility path, this new batch tool requires a bound successful modern collection report.

The tool rejects repeated raw content, repeated session or clock identities, and exact copied measurement series even when their metadata and absolute epoch were renamed. It preserves the raw angle, sampled MCU governor acceleration, every invalid row, and every within-run time difference. For analysis only, each role begins at zero and successive runs are separated by one second; all shifts and original endpoints are recorded. Run IDs are raw content hashes. No samples are invented or interpolated across runs, and the fitter keeps invalid rows, identity changes and its existing gap threshold as boundaries.

Exit 0 means the unchanged fitter gates and the supplemental per-validation-run excitation checks accepted the batch. Exit 2 means rejection or invalid input. Statistical rejections produce a full immutable report; invalid sources cannot be fitted, and an existing output is never overwritten. The base fitter checks validation error and coverage but can accept a perfectly static held-out series. This wrapper therefore additionally requires **every** reserved validation run to meet its existing angle-span minimum (0.15 rad) and input standard-deviation minimum (0.05 m/s²). It reports each run separately and rejects the overall batch if any fails, while preserving the complete underlying fitter result unchanged. Dynamic runs cannot hide a static run in an aggregate score.

The output contains:

- Canonical training/validation rows and their SHA256.
- Every source and completion-report hash, original clock range, applied shift, admission counts and independent identity.
- The unchanged fitter configuration, training/held-out metrics, parameters, rejection reasons and conditional uncertainty.
- Tool/SDK source hashes and a canonical content hash for the complete report.

For exact numerical reproduction, verify `content_sha256` after removing that field, verify `canonical_sha256` against `canonical_batches`, then pass those rows to `identify_pendulum` with `source='magnetic'`, `acceleration_kind='commanded'` and `replace(FitConfig(), angle_offset_rad=report['angle_offset']['value_rad'])`. The recorded default configuration pins the remaining gates. Preserve the reported source revisions when reproducing.

The default angle offset is zero. `--angle-offset-rad VALUE` is an explicit comparison, never an estimate made from validation. Use an independently established offset for physical interpretation. Any nonzero run is labeled diagnostic by this tool; a historical fitted hanging-phase value is **not** proof of a global encoder calibration. Preserve zero-offset and offset diagnostics separately instead of selecting whichever validation score is better.

The input acceleration is a sampled MCU governor **command**, not measured physical cart acceleration. The estimated input gain consequently includes actuator, estimation and clock effects; it is not a metric cart calibration. A statistical pass does not establish physical cart motion, full-swing/upright accuracy or RL readiness. Recorded-versus-predicted trajectory plots and independent physical evidence remain necessary.

## Separate exploratory friction comparison

After inspecting the reserved 30 mm scores, `analyze_driven_friction.py` treats that pair as **development**, never fresh validation. It fits only the four original training pulses at the predeclared historical local phase. The original frozen batch analyzer and production fitter are unchanged.

```sh
FRICTION=/absolute/path/to/cartpole_v2/evidence/system-id-20261017/tools/analyze_driven_friction.py
"$FRICTION" --batch /analysis/pulse-batch-secondary-historic-offset.json \
  --output /analysis/NEW-friction-development.json
```

This diagnostic compares constrained viscous and regularized Coulomb-plus-viscous models using identical weak-form windows and delay candidates. It retains the existing length, input-gain and damping bounds, requires nonnegative damping/friction, and bounds Coulomb acceleration at 20 rad/s². The exploratory friction law is `-c*tanh(omega/0.05)`: the fixed 0.05 rad/s smoothing width is an explicit numerical assumption. Seven-point local quadratic derivatives of raw angle construct only the added weak-form friction feature; the original three equation columns are reused exactly. Forecasts retain the original causal initial-rate rule and use at most 2 ms RK4 steps to resolve the smoothing.

The report preserves every training-selected delay score, active constraints, per-run prediction metrics, source hashes and assumptions. It always sets `accepted=false` and installs no model. This approximation omits static stiction and does not establish a calibrated physical input or global angle mapping.

On the recorded batch, adding friction changed training NRMSE from 0.25280 to 0.24766 and development forecast RMS from 0.02737 to 0.02716 rad. The improvement is small and leaves the training residual above the unchanged 0.15 threshold. It does not resolve the identification rejection or justify model promotion.

## Manual-release evaluation and initialization diagnostic

The [manual assessment](../analysis/manual-repeatability/README.md#reproduce-and-audit) gives the complete executable command for `evaluate_manual_repeatability.py`. It scores the preserved new recording against unchanged coefficients and actual MuJoCo, with no later measurement updates during continuous predictions. It also plots direct camera angles separately.

`diagnose_turning_point_initialization.py` tests whether noisy starting velocity explains part of the continuous discrepancy. Run it on the preserved source from the repository root:

```sh
uv run --script evidence/system-id-20261017/tools/diagnose_turning_point_initialization.py \
  --repo "$PWD" \
  --input evidence/system-id-20261017/raw-manual-repeatability/manual-repeatability-01/rig-1792251521290789944-1148199442.jsonl.gz \
  --annotations evidence/system-id-20261017/analysis/manual-repeatability-annotations.json \
  --annotations-sha256 f2ee8d8c478682c8612adccc211386e6f8aac4a236a03376696c57575189f136 \
  --output /tmp/NEW-turning-point-comparison.json
```

The first qualifying extremum is selected from a fixed bounded raw-angle window, never by prediction error. Both initializers are scored on identical samples after that window ends. This is a development diagnostic of the frozen ODE, with no physical parameter refit, new acceptance decision, or model export. The left60 error falls substantially, while right60 worsens; it does not justify replacing the primary scores.
