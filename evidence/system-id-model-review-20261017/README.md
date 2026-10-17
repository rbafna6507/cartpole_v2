# Passive system identification — later recordings prioritized

The current experimental candidate is fitted only to the two completed batch-6 recordings: **19 releases**, 355 weak-form windows. It was frozen before reading batch-7 prediction errors. Older recordings informed model selection and serve as secondary comparisons; their coefficients are not blended into the new fit. No coefficients or prediction methods were changed after inspecting batch 7.

**Batch-7 continuous prediction: 2.63° RMS in the ODE and 2.66° in MuJoCo**, versus 7.83° for the earlier viscous model with the same initialization. See [recorded versus MuJoCo, zeroed at recorded hanging](analysis/mujoco-batch7-hanging-zero/recorded-vs-mujoco.png). Predictions use the first 0.5 s to initialize, exclude that history from scoring, then receive no further measurements. Eleven releases are included, including the final partial decay.

This is an experimental fixed-cart replay, not an approved production simulator or full-rig RL validation. Camera/pose qualifications remain unresolved. Firmware, gains, saved encoder reference, production SDK, collection code and Gym defaults are unchanged. No serial port was opened.

## Dataset identity and selection

Recordings are distinguished by raw SHA-256 and board session, not directory labels. The remote inventory found 11 distinct recording reports across the two collection checkouts. Preserved original files and per-file manifests for completed batches 6 and 7 are under `batch6/` and `batch7/`.

| Directory | Internal label | Role in this investigation |
| --- | --- | --- |
| passive-training-6 | passive-training-5 | Primary fit: 8 full releases plus one partial |
| passive-validation-6 | passive-validation-5 | Primary fit: 10 releases; final tiny fragment excluded before scoring |
| passive-training-7 | passive-validation-7 | Final unseen-while-fitting check: 10 full releases plus one partial |
| passive-validation-7 | passive-validation-7 | Failed camera collection; 10 completed interior swing intervals used only for diagnostic replay |
| Batches 2, 3, 5 | Various | Earlier development and secondary checks; not pooled into latest fit |
| passive-validation-4 | Directory says validation, role says training | Found and inventoried; deferred in favor of later recordings |

Annotations were selected from raw encoder/camera curves before prediction scoring. No intervals were selected to minimize residuals. Both batch-6 recordings are development data now, regardless of the word “validation” in one directory. The batch-5 candidate was also scored on batch 7 in a background process, but its output was not read until the latest batch-6 freeze had been written.

Completed batch-7 held poses span approximately **31–35°, 58–64°, and 85–86°** by encoder, in both directions; the camera reaches roughly 89–91° for the larger poses. These are observed apparent angles, not the nominal requested labels or an absolute geometric calibration.

## What changed in the model

Two separate effects mattered:

1. **Initialization:** differentiating 11 raw encoder readings (~40 ms) gave a noisy initial velocity. Fitting the fixed ODE to preceding observations is substantially better. Short forecasts use up to 200 ms of history; the first forecast has about 100 ms available. The current raw angle is retained. No future samples enter initialization. This is an offline analysis method, not a deployed real-time estimator.
2. **Friction:** a simple nonnegative viscous + smooth dry-friction law fits long decays better than viscous damping alone. More elaborate trajectory optimization and quadratic drag did not consistently improve earlier development results, so they were not added to the selected model.

In physical coordinates with zero downward:

`phi_ddot = -(9.81 / L_eff) * sin(phi) - gamma * phi_dot - c * tanh(phi_dot / 0.05)`

Frozen latest coefficients in `candidate-freeze-latest6.json`:

| Parameter | Value |
| --- | ---: |
| Effective length | 0.160303873 m |
| Viscous rate gamma | 0.006891975 /s |
| Smooth dry-friction acceleration c | 1.626894312 rad/s² |
| Local raw-encoder phase offset | −0.112971948 rad |

Dry friction dominates this fit. These are effective parameters inferred through the recorded encoder; measurement distortion can still bias them. This smooth model does not implement exact static sticking. The phase offset is local to these recordings and is **not** a global hanging-to-upright calibration. Passive decays identify ratios, not independent pole mass, center of mass and inertia.

## Frozen batch-7 results

All short comparisons use the same 17,498 future samples and 0.5 s prediction windows. All continuous comparisons below use the same 0.5 s initialization and 17,049 subsequently scored samples.

| Model | Short RMS / P95 | Continuous RMS / P95 |
| --- | ---: | ---: |
| Earlier viscous model, original short initializer | 6.259° / 12.092° | 7.830° / 18.027° |
| Same viscous coefficients, causal short initializer | 2.334° / 4.747° | 7.830° / 18.027° |
| Batch-5 dry-friction candidate, causal initializer | 2.261° / 4.696° | 3.639° / 7.184° |
| **Latest batch-6 dry-friction candidate** | **2.283° / 4.772°** | **2.629° / 5.024°** |

The later fit mainly improves sustained decay prediction; it is not better on every short metric. Its 0.25 s initialization sensitivity check gives continuous RMS 2.712° / P95 5.403°. The short RMS/P95 numeric gates and minimum forecast coverage pass for each of the 11 annotated batch-7 releases. These numerical passes do not override measurement-quality failures.

The separate failed validation-7 prefix gives **3.615° RMS / 6.913° P95** over ten conservatively selected interior free-swing intervals, initialized once for 0.5 s each. It was neither fitted nor treated as a successfully completed validation collection. Its camera error, unsuccessful completion report and lack of confirmed successful STOP report remain preserved. The final held pose had no release before the recording failed. The compact prefix extract preserves source hashes; full original files remain on the Jetson.

### Camera and pose qualifications

Completed training-7 has STOP confirmed and no logger drops. Its camera consistency passes for 10/11 free intervals. The final partial interval exceeds the original 5° RMS / 10° P95 camera/encoder agreement bounds. Nine of eleven held poses pass; release 2 has excessive variation and release 6 has camera/encoder pose disagreement. These failures remain reported in `analysis/batch7-latest6-check/report.json.gz`.

Both batch-6 recordings also retain their original pose/camera flags. The partial ninth training-6 release has only two short prediction windows, below the existing three-window coverage rule. It is usable development data, not evidence of full coverage. `candidate-freeze-coverage-fix.json` adds separate coverage reporting to the older freeze without changing any coefficients, predictions or samples. Original evaluator and reports are retained.

A training-5-only relative camera lag of 17.52 ms reduced camera/encoder RMS on validation-5 from 4.217° to 2.068°. Adding a local periodic mapping reduced it to 1.293°. Those are **sensor agreement errors**, not physics prediction errors. This diagnostic may combine exposure, capture, tracking, USB receipt and encoder timing; it does not establish absolute camera latency or separate projection from encoder distortion. No raw timestamps or calibration were rewritten, and that mapping was not used to generate the latest physics results.

## MuJoCo verification and limits

`tools/mujoco_replay.py` builds a fixed-cart single hinge with equivalent inertia and applies the fitted smooth dry torque every physics tick. Viscous damping is native. It uses the same equivalent uniform-rod convention as the SDK; the 0.02275 kg mass is assumed, not newly identified. The local encoder phase is mapped into the physical angle for replay.

On batch 7, MuJoCo versus encoder is **2.658° RMS / 5.093° P95**. MuJoCo versus the ODE is **0.0773° RMS**, maximum **0.2703°**. Across 117 angle/velocity states, the acceleration equations agree within 2.85e−14 rad/s². The maximum integration step is 1 ms.

The generated MJCF **alone omits dry friction**: the Python replay applies that torque at every tick. Use the script to reproduce the complete model. The current production exporter still rejects nonzero dry friction. The standalone harness does not validate cart actuation, acceleration/jerk limits, command latency, encoder observation distortions, or the full coupled Gym environment.

Earlier evidence remains in `analysis/batch5-development`, `batch6-*-check`, `batch3-historical-check` and `batch2-historical-check`. Those frozen batch-5-candidate checks should not be mistaken for evaluations of the latest batch-6 fit. `mujoco-batch7-latest6` retains an earlier plot coordinate convention; `mujoco-batch7-hanging-zero` repeats the identical numerical result with display zero at recorded hanging.

## Reproduce

Run from the repository root. Original recording directories must include their sibling completion and camera files; annotations bind to raw hashes. Use a new output path. The executable scripts also support direct invocation through their uv shebang.

Evaluate the frozen latest model on another recording without fitting:

```bash
uv run --locked --extra id --with scipy==1.16.3 python \
  evidence/system-id-model-review-20261017/tools/evaluate.py \
  --freeze evidence/system-id-model-review-20261017/candidate-freeze-latest6.json \
  --source runs/passive-batch7-original/passive-training-7/rig-1792268992424581030-2783727930.jsonl \
  --annotations evidence/system-id-model-review-20261017/batch7/training-annotations.json \
  --output runs/latest-passive-check
```

Replay in MuJoCo and produce the recorded-versus-predicted plot:

```bash
MPLCONFIGDIR=/tmp/cartpole-id-matplotlib uv run --locked \
  --extra sim --extra id --extra plots --with scipy==1.16.3 python \
  evidence/system-id-model-review-20261017/tools/mujoco_replay.py \
  --freeze evidence/system-id-model-review-20261017/candidate-freeze-latest6.json \
  --source runs/passive-batch7-original/passive-training-7/rig-1792268992424581030-2783727930.jsonl \
  --annotations evidence/system-id-model-review-20261017/batch7/training-annotations.json \
  --output runs/latest-passive-mujoco
```

`refit_latest.py` accepts repeated `--source`/`--annotations` pairs and a `--prior-freeze`; it deduplicates raw hashes and writes a new candidate. Do not refit on batch 7 and continue calling it independent validation. `compare.py` tests model alternatives on development data. `compare_sensors.py` fits sensor timing/mapping on training data only. `preview.py` makes raw plots before interval selection. `failed_prefix.py` explicitly retains failed-collection status and cannot recover, fit or export a model.

`verify.py` checks analytic sensitivities, synthetic trajectories, no future-data leakage, original-score parity, equal scored samples, and friction dissipation. `verify_bundle.py` additionally checks the archived originals, frozen methods, data separation and reported MuJoCo parity.

## Next steps

These later recordings provide useful passive coverage through roughly ±90°; another broad passive batch is not the immediate priority. Carry the frozen candidate forward, preserve the observed residuals as model uncertainty, and resolve the remaining timing/pose qualifications. Then integrate and test this exact torque law in the production simulator and verify the driven cart/pendulum dynamics against existing cart tests before accepting a full Gym model for hardware-bound RL. No production acceptance gate has been relaxed to lower RMS.
