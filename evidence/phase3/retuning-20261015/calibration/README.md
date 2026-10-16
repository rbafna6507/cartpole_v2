# Hanging reference conversion: measured model contract

The offline fitter is implemented and tested. **The physical rig model is not validated.** `current-evidence-profile.json` has status `insufficient_data`, no offset, and no approval. It is deliberately unusable by the application API. The direct upright reference 370 remains the reference in the recorded evidence. This work performs no hardware I/O and changes no physical calibration.

The current recordings establish a useful direct upright anchor (370, rechecked at 371) and stopped hanging observations around 2303–2305 before manual movement and 2333 afterward. Ideal half-turn conversion plus an illustrative +113 count correction would map 2305 to 370, but the later hanging observation would require about +85. Those are arithmetic diagnostics, **not fitted/validated calibration values**. The independent camera/encoder difference between almost identical initial/final down poses changes 0.04861 rad (2.79 degrees). Only one complete negative traversal is present. A nominal harmonic angle-map fit is descriptive and unvalidated; it is not used by this model.

The source assessment is copied into `manual-angle-map-assessment.md`. `source-evidence.json` contains exact source hashes and extracted measurement facts, so summary facts cannot be mistaken for native paired windows. Source paths refer to the existing local diagnostic record; no synthetic windows are generated from summary means. `current-evidence-dataset.json` deliberately contains zero eligible pairs. Window IDs, native sampling, acquisition sessions, approach directions, external reference quality, fixture identity and unchanged sensor configuration are not established by the source summaries. The dataset uses explicitly unverified identity labels and cannot pass acceptance.

## Conversion and identity

For a native encoder with `N=4096` counts per revolution:

```text
offset_i = signed_circular_delta(upright_i, hanging_i + N/2)
upright_reference = (new_stable_hanging_raw + N/2 + approved_offset_counts) modulo N
```

`offset_counts` is signed and bounded to ±256 counts, matching the firmware command bound. The fit uses a median of training-pair offsets, then rounds once to a signed integer count, with half ties away from zero. The integer actually sent to firmware is evaluated against validation data. No encoder angle nonlinearity correction is implied.

Every profile contains:

- `schema_version=1`, `fit_version="paired-circular-offset-v1"`, `model_kind="hanging_to_upright_offset"`.
- `hardware_id`, `source_id`, `fixture_id`, `sensor_config_id`, `frame_id`, and `counts_per_turn`. Use a measured fixture revision and sensor configuration ID; an AS5600 source can be named `as5600-raw-12bit`. IDs must match application context exactly. The frame names the physical pole-upright reference shared with separately calibrated vision.
- `offset_counts` (integer or null), `estimate_counts` (unrounded training median or null), `policy`, complete `evidence`, and `validation`.
- `calibration_id`, a SHA-256-derived ID over canonical model, evidence, policy, and validation. Pair ordering is canonicalized for reproducibility.
- `approval=null` until explicit approval. An approval contains `approved_by`, timezone-qualified `approved_at`, and the exact `calibration_id`.

`CalibrationProfile.from_dict()` and `.load()` reconstruct the entire fit and validation from embedded evidence and compare every result. They reject missing/extra profile fields, altered fit output, invented validation status, malformed windows, duplicate JSON keys, and approval for another profile. Application methods repeat that check even if a caller constructed the dataclass directly. This is an integrity/reproduction check, not cryptographic authentication of the operator or physical acquisition.

```python
from cartpole_sdk.sensing.calibration import CalibrationProfile

profile = CalibrationProfile.load("approved.json")
offset = profile.approved_offset_counts(
    hardware_id="YOUR_RIG", source_id="as5600-raw-12bit",
    fixture_id="YOUR_FIXTURE", sensor_config_id="YOUR_SENSOR_CONFIGURATION",
    counts_per_turn=4096, frame_id="pole-upright")
# firmware stable-capture command applies offset after the half-turn.
# For host-only prediction of an already qualified native hanging count:
upright = profile.upright_from_hanging(2305,
    hardware_id="YOUR_RIG", source_id="as5600-raw-12bit",
    fixture_id="YOUR_FIXTURE", sensor_config_id="YOUR_SENSOR_CONFIGURATION")
```

The illustrative count above is not authorization to use the present rig data. The methods require validated and explicitly approved evidence with exact identity. A future capture must meet the same stability and fixture conditions; this reference conversion API does not collect or certify a new live capture.

## Input dataset

Top-level keys are exactly `schema_version`, the six identity/encoder fields above, `provenance`, and `pairs`. `provenance` must contain nonempty `source` and `acquisition_version`; additional source hashes, timestamps and acquisition metadata may be included there.

Each pair has exactly:

```json
{
  "pair_id": "independent-pair-001",
  "session_id": "capture-session-001",
  "split": "train",
  "direction": "positive",
  "reference_uncertainty_counts": 1.0,
  "upright": {
    "window_id": "unique-native-upright-001",
    "sampling": "native",
    "raw_counts": [370, 371, 370],
    "sample_period_s": 0.001
  },
  "hanging": {
    "window_id": "unique-native-hanging-001",
    "sampling": "native",
    "raw_counts": [2305, 2306, 2305],
    "sample_period_s": 0.001
  }
}
```

This abbreviated illustration has too few samples and will be rejected. Supply full native readings, at least 32 samples and at least 0.4 seconds per window. At 1 kHz, 401 readings span exactly 0.4 seconds. Do not count 1 kHz repeated reads of a slower source as independent fresh sensor captures or interpolate/resample telemetry to fill a window. Windows must have distinct IDs, pairs must have distinct IDs, and sampling must be `native`. Reused IDs or explicit resampling fail closed. The acquisition process is responsible for freshness, source identity, truthful timestamps, and honest labels; a JSON declaration cannot prove that the pole was physically placed correctly.

The `direction` describes the common approach direction of the measured hanging/upright pair in increasing (`positive`) or decreasing (`negative`) raw encoder counts. Approach both poses in that direction, and record any reversal as a new acquisition. The external upright reference must be physically supported and independently checked; `reference_uncertainty_counts` is a bound on the physical reference error, not encoder sample noise. Convert an independently established degree bound using `degrees * 4096 / 360`. A claim of zero uncertainty is only justified by independent metrology; a stable hand-held encoder window does not establish it.

## Acceptance and measurement plan

The default policy requires at least six training pairs (three each direction) and four validation pairs (two each direction). Each split must span at least two sessions, and training/validation session IDs must be disjoint. In practice, collect at least eight training pairs to balance both directions across two training sessions, then four held-out pairs across two additional sessions. Designate the split before acquisition and never tune the fitted offset using held-out results.

1. Verify sensor configuration, fixture revision, physical vertical reference, and direct upright alignment. Record the IDs and external reference uncertainty.
2. With the rig disabled and mechanically safe, collect fresh native stable upright and hanging windows for each pair. Do not infer a paired window from a mean or reuse one upright window for several hanging stops.
3. Repeat positive and negative approaches across independent sessions and after the intended normal handling. Record all captures, including failures and history shifts.
4. Fit training pairs, inspect every validation reason, direction gap and session gap, then inspect the independent held-out prediction error. Fitting never approves a profile.
5. If and only if the evidence passes, explicitly approve that exact profile. Any fixture/configuration change requires new evidence; a new stable capture is still needed before firmware saves an upright reference.

Window span must be ≤4 counts, median first-to-last-quarter drift ≤2 counts. The circular median handles 4095→0 wrapping. Unstable, short, or resampled windows are reported and reject the dataset; they are not silently removed to create a passing profile. A robust training median resists isolated bad pairs, but every accepted-window pair still contributes to rejection checks. Reported outliers are not discarded from the validation envelope.

For each pair, the error envelope is the absolute residual of the integer fitted correction plus the full radius of each native window plus one count for quantization (half a count per pose) plus the declared external upright-reference bound. The maximum observed envelope must be ≤0.5 degrees (5.689 counts) on both training and held-out data. No standard-error or square-root-of-sample-count reduction is used, because samples may be correlated. This is an empirical envelope on observed conditions, not a statistical confidence interval or an assurance of future operating states.

Both pooled direction medians and session medians must agree within 3 counts. A direction-dependent or history-dependent offset rejects the scalar model. Policy customization may tighten the limits or increase evidence requirements; it cannot relax the accepted envelope. Missing coverage produces `insufficient_data`; measured contradictions or quality failures produce `rejected`, even when coverage is also insufficient. Neither status is applicable or approvable.

Run the offline `fit`, `report`, `approve`, and `check` commands through `python examples/calibrate_angle.py` or `python -m cartpole_sdk.sensing.calibration`. `fit` exits successfully when it produces a report even if that report rejects the data; `check` is the application gate and exits 2 unless the profile is validated, approved and identity matched. These tools never open hardware or change a reference.

## Separate installation identity

`installation-identity.example.json` is a placeholder schema for a separate current-installation assertion. Replace every `REPLACE_...` value using the actual rig/source/fixture/configuration inventory before application. Do not derive current installation identity by blindly copying the profile identity; a model from another fixture must fail. The optional `frame_id` and `counts_per_turn` fields should be specified to assert the common angle frame and AS5600 count scale. This example is not a calibrated model and cannot authorize calibration.

## Firmware capture compatibility

The explicit model-offset command (including an offset of zero) selects `ModelStillCapture` in `firmware/teensy_executor/model_encoder_reference.h`: 401 native 1 kHz reads spanning 400 ms, a circular whole-window median, span ≤4 counts, and first/last 100-sample median drift ≤2 counts. The bounded 401-byte offset buffer and nine-bin histograms do not allocate memory. Legacy upright and explicitly ideal hanging commands retain their preserved 400-read capture behavior. Cancellation clears both the offset and the model-capture flag, including cancellation immediately before persistence.

The SDK rejects a model that requires more than 401 readings, more than 0.4 seconds, span below 4 counts, or drift below 2 counts, because this firmware cannot guarantee those stricter capture policies. Other stricter validation requirements (more independent pairs or smaller validation error) still apply during fitting. `calibrate_encoder` validates profile evidence, explicit approval, installation identity and capture compatibility before transmitting the bounded offset.

Verification: `python -m pytest -q tests/test_angle_calibration.py tests/test_executor_native.py tests/test_rig_calibration.py tests/test_rig_calibration_model.py` completed with **165 passed and 36 subtests passed**. `validation.log` contains that targeted run. The integrating agent owns the final serial full-repository test run; the earlier concurrent full run was stopped and is not a completion claim.
