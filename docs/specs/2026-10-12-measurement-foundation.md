# Offline measurement foundation design

Date: 2026-10-12. Status: **draft for written review**. The user approved the scope
"offline measurement foundation"; the interfaces below remain reviewable design
choices. This is the first sub-project of the [v2 roadmap](../roadmap.md).

## Purpose and scope

Turn existing vision and encoder recordings into inspectable, reproducible data
that can support vision benchmarking and later system identification. The first
usable command imports a recording, optionally runs the existing detector on its
video, and writes a report that distinguishes what was measured from what is unknown.

Local, file-only operation is mandatory. No camera acquisition, SSH, network service,
serial backend, calibration command, motor command, or firmware upload belongs in
this slice. Importing the package must not open devices or sockets. Do not modify
the existing repository. Python 3.10+ is the initial floor, matching deployment.

Do not implement fusion, a new detector, a live dashboard, automatic parameter
identification, MuJoCo training, public uploads or policy execution in this slice.
The existing green-arm detector is a benchmark baseline, not a declared solution
for all geometries or speeds. All acceptance tests run offline.

## User workflow

The proposed CLI has three small entry points (not implemented yet):

```sh
cartpole-v2 import-vision --states old/states.jsonl --out runs/imported
cartpole-v2 replay-video --video old/raw.avi --timestamps old/raw_times.jsonl \
  --out runs/replayed
cartpole-v2 report runs/replayed --out reports/replayed
```

Encoder import is explicit about format and angle calibration:

```sh
cartpole-v2 import-encoder --format legacy-raw --input old/encoder.jsonl \
  --out runs/encoder
```

These examples operate on one source at a time. A dataset manifest may later join
sources from the **same experiment** with declared clock mappings. The available
October 3 vision and October 12 encoder recordings must never be treated as a pair.
Uncalibrated imports still provide timing, raw counts/pixels and detection metrics.
No automatic hanging-zero selection or unrecorded angle offset is allowed.

## Package layout and responsibilities

The implementation plan should refine these into test-sized commits:

```text
pyproject.toml
src/cartpole_v2/
  contracts.py              # Small immutable schema types and validation
  clocks.py                 # Explicit clock maps and epoch validation
  dataset.py                # Versioned manifests, hashing, streaming JSONL I/O
  adapters/
    vision_legacy.py        # Existing state records and timestamp-sidecar metadata
    encoder_legacy.py       # Legacy raw E captures and legacy telemetry CSV
    deployment.py           # D1 recording files, no transport imports
  vision/
    detector.py            # Provenance-preserved baseline detector
    state.py               # Baseline calibration/derivative logic and adapter
    replay.py              # File decoding and deterministic measurement stream
  report.py                # Coverage/gaps/quality and eligible pair comparisons
  cli.py                   # File-only commands and explicit failure messages
tests/
  fixtures/                # Small source fixtures and generated numerical cases
docs/
  data-format.md
  migration.md
```

Core parsing/reporting should not require OpenCV, Flask, MuJoCo or device libraries.
Use standard-library JSON/dataclasses and NumPy only where numerical work benefits.
OpenCV belongs to an optional vision dependency group. No Flask dependency is needed
for the headless baseline. Keep a source-hash record for each migrated component.

## Data model

Use a versioned JSON manifest plus streaming JSONL samples, preserving original
inputs by path/hash. Large video is referenced, not embedded in observation rows.
No Python pickle or executable configuration is used for datasets.

| Entity | Required meaning |
|---|---|
| `DatasetManifest` | Schema version, dataset/run identity, source file hashes/formats, rig topology, coordinate conventions, stream declarations, available calibrations/clock maps, completeness and processing provenance |
| `SensorSample` | Stream/source ID, sequence, source epoch, time record, named measurements, per-value validity/reason, calibration ID when applicable, original-record index |
| `Measurement` | Value or null, unit, quantity and coordinate frame; raw/derived/estimated kind; valid flag/reason; optional effective time and uncertainty with declared meaning |
| `TimeRecord` | Source timestamp and unit, source clock/epoch ID, timestamp kind; host receipt timestamp and its clock when actually recorded; no invented exposure time |
| `FrameReference` | Relative dataset file reference/hash, decoded frame index, original recording frame number, camera sequence when available, exact time record, resolution/rotation |
| `Calibration` | Immutable identity/hash, source/frame applicability, angle zero/sign, cart scale/direction or geometry transform, method and provenance; unknown entries remain absent |
| `ClockMap` | Source and destination clock/epoch, affine scale/offset, declared valid interval, mapping method and known uncertainty or explicit unknown |

Measurements are named by physical source/link, for example `encoder.joint_1.raw`,
`vision.link_1.angle`, and `vision.cart.position`. A schema-level topology can name
one, two or three links without requiring a detector or importer to fabricate
unsupported values. Reject duplicate identifiers, undefined units/frames and
inconsistent array/topology sizes.

Angles are radians. The canonical single-link world angle is zero upright,
positive toward calibrated cart +x. The legacy image angle has a different origin
and sign; retain it as an image-frame measurement until an explicit transform is
available. Cart A→B can disagree with image-right, so do not infer that transform
from existing documentation alone. Raw encoder count zero is not a saved upright
reference; convert counts only with a declared calibration and count range.

Preserve historical calibrated values in their declared source frame. If the
calibration artifact is missing, mark provenance incomplete and prohibit canonical
cross-source accuracy comparisons. Independent angle/cart/velocity validity is
required. An invalid field is null in the normalized stream; raw source content
is preserved in its immutable input file. Reject nonfinite numbers in valid fields.

## Time and causality

- Preserve absolute source time, unit and origin. A replay-relative time may be
  added for display but cannot replace the source timestamp.
- Epoch boundaries are explicit. Device counter wrap is unwrapped only within an
  established epoch with bounded forward progression; an ambiguous reset/wrap is
  rejected or split with an explicit diagnostic, never guessed into continuity.
- Host wall-clock timestamps and monotonic timestamps are different clocks.
  Receipt time is not sample/exposure time. Missing receipt times remain absent.
- The existing derivative's `omega_effective_t` and cart-velocity effective time
  are preserved separately from the latest position/angle time.
- Clock maps are supplied explicitly in the first slice. Validate finite positive
  scale, finite offset, epoch identity and interval coverage. Do not estimate
  alignment by silently shifting the first sample of each recording to zero.
- Reports can compare data only with compatible frames/calibrations and a known
  shared timeline. Unknown timing uncertainty is reported; it cannot certify a
  latency or accuracy requirement. A supplied map is an assertion with provenance,
  not proof of true exposure synchronization.
- Replaying feeds measurements in source order. Duplicate/reversed times, reset
  boundaries and excessive gaps reset derivative histories. File ingestion reports
  such defects explicitly; it does not silently sort or interpolate them away.

Linux capture will eventually inspect timestamp flags and driver behavior. V4L2
allows driver-selected clocks and timestamp events, which is why this schema does
not label an arbitrary camera timestamp as exposure time.
[V4L2 buffer semantics](https://www.kernel.org/doc/html/latest/userspace-api/media/v4l/buffer.html).

## Import adapters

**Vision states:** normalize the current `states.jsonl` field names, validity,
rejection reasons and effective times. Preserve `seq`, dimensions and source-frame
coordinates. A quality heuristic is stored as such, never converted to covariance.

**Video and sidecar:** require a one-to-one mapping between decoded frames and
sidecar rows for measurement replay. Validate finite strictly increasing times
and camera sequence progression; record skipped sequences separately from invalid
measurements. Preserve original recording frame numbers: the supplied 650-frame
excerpt starts at original frame **4008**, so those numbers cannot be used as
zero-based indices into the excerpt. Explicit sidecar-less preview may be added
later; this slice fails clearly if measurement replay lacks timestamps.

**Legacy raw encoder:** import `encoder.jsonl` records containing board milliseconds,
raw counts, magnet/validity bits, enabled state and host wall time. A sample may
have a valid raw count without a valid calibrated angle. Preserve status/error
fields so sensor quality is auditable. Do not execute `passive_capture.py`.

**Legacy telemetry and D1 files:** adapters declare the format rather than guessing
from common column names. Map units explicitly, retain mode/fault/enable fields
when present, and label cart x/v/a as step-derived command state unless the file
declares an independent measurement. Missing raw angle or validity evidence is
represented as unknown. Do not import the live `HardwareRig` or console.

## Replay and reports

Replay is deterministic for a fixed input, detector configuration and calibration.
Measured wall-clock processing durations are stored separately from deterministic
measurement outputs. Preserve source hashes and detector version in every result.
Outputs are streaming so dataset length does not require retaining every row in
memory. Raw frames and decoder state are bounded in memory. Output directories
must be new; interruption leaves a clearly incomplete dataset, never an apparently
complete one. Reject path traversal or symlink escape when resolving files inside
a dataset bundle; external local source inputs are explicit CLI arguments.

The report contains:

1. Source inventory, calibration/provenance completeness and timestamp semantics.
2. Per-stream sample/frame counts, duration, observed interval distribution, sequence
   gaps, duplicate/reversed timestamps, invalid fractions and rejection reasons.
3. Longest invalid interval and reacquisition intervals where labels establish an
   occlusion end. Bound edge intervals honestly when footage ends during a dropout.
4. Separate metrics for labeled stationary, moving, fast-motion and occlusion
   segments. Without labels report aggregate coverage, not swing-only reliability.
5. Per-value derivative availability and effective lag. Processing p50/p95/p99 is
   runtime-dependent and not an exposure-to-action latency measurement.
6. Optional calibrated cross-source disagreement on compatible synchronized data:
   wrap-aware angular error and cart position error, match counts, excluded counts,
   alignment method and time uncertainty. Use explicit maximum time separation;
   no interpolation across invalidity, gaps, epochs or calibration changes.
7. Ground-truth accuracy and false-positive rates only when independently labeled
   references exist. Otherwise those sections say **unavailable**, with reasons.

Publish machine-readable JSON and a self-contained HTML report with embedded plots
or SVG; it must open without a web server or remote assets. A diagnostic overlay
video is optional, separate from authoritative measurement data. HTML escapes
source labels/paths. Neither processing FPS nor the presence of a report produces
a "ready for control" verdict.

## Acceptance and meaningful tests

| Test class | Required behavior |
|---|---|
| Real source import | Existing vision states, a legacy encoder excerpt and D1/telemetry fixtures preserve counts, units, raw identities, source timing and validity |
| Full rotations | Circular difference across ±π is correct; causal derivatives do not spike at a wrap; sparse ambiguous motion is not certified from unwrap alone |
| Missing/invalid data | Angle/cart/velocity validity is independent; NaN/Inf, stale samples, absent calibration and unknown uncertainty never become valid zeros |
| Frame identity | Excerpt frame 4008 maps to decoded index 0; exact sidecar length required; skipped camera sequences remain visible |
| Clock identity | Offset/drift mapping works on synthetic known clocks; unrelated sessions, resets, backwards time and uncovered intervals cannot be fused |
| Causal replay | Identical source/config yields identical normalized values; no future sample is used for the online observation/derivative stream |
| Comparison eligibility | Unpaired datasets produce no accuracy metric; known synchronized synthetic offsets produce correct circular/linear disagreement and exclusions |
| Reproducibility | Source/config hashes are checked, existing output is refused, malformed/truncated input has explicit diagnostics, interrupted output is incomplete |
| Bounded operation | Long generated JSONL/video input is processed incrementally; optional preview and runtime timing do not change measured values |
| Offline boundary | Importing/running file workflows attempts no serial, network or live-camera access; video source must resolve to a regular file |

Retain and rerun relevant existing vision tests when porting their code. Use
synthetic independent trajectories for mathematical/timebase tests and real fixtures
for detector regression; do not test only outputs generated by the same algorithm.
First run the 650-frame motion excerpt without inventing a calibration. Publish its
coverage/gap report and explicitly unavailable cross-sensor accuracy. Performance
measurements identify the machine and are not promises about Jetson performance.

## Subsequent live measurement protocol

Once the offline pipeline is accepted and the rig is handed over, add capture as
a separate milestone. Start with known stationary poses/travel and passive releases,
then exposure/lighting trials, full rotations, cart travel and occlusion tests.
Establish accuracy and time-delay budgets from the intended control task before
certifying a sensor configuration. This milestone deliberately produces the tools
to measure those budgets; it does not assert them from the current recordings.

## Review and next action

Review the proposed entities, clock/coordinate rules and the acceptance table.
After written-spec approval, produce an implementation plan for (1) contracts and
dataset I/O, (2) file adapters, (3) baseline vision replay, and (4) quality reporting.
Execute locally in those testable slices. Archive source provenance during the
first migration; product code and dependencies are not yet copied into this project.
