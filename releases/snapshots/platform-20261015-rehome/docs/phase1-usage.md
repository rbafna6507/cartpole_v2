# Python SDK: recordings and policy replay

Phase 1 provides an installable `cartpole_sdk` package with no runtime dependencies,
using Python 3.11+. All SDK commands below run locally without opening a camera,
serial port or network connection. The archived applications retain their own uv
projects. Replay checks data flow and policy output against fixed recorded inputs;
it cannot evaluate balance, rewards or how an action would move the rig.

## Try the complete path

From the repository root:

```bash
mkdir -p runs/sdk-demo
uv run --locked cartpole-v2 import-vision tests/fixtures/vision-real.jsonl runs/sdk-demo/vision.jsonl --session-id demo-vision --frame-id vision:demo-calibration
uv run --locked cartpole-v2 inspect runs/sdk-demo/vision.jsonl
uv run --locked python examples/replay_policy.py runs/sdk-demo/vision.jsonl runs/sdk-demo/my-policy.jsonl --frame-id vision:demo-calibration
```

The four genuine recorded vision frames include velocity warm-up and then a usable
velocity. The example writes three `no_request` steps and one bounded acceleration
request. It is an illustrative angular-damping mapping, not a swing-up or balancing
controller. Its sign, gain, 1 m/s² limit, 20 ms lifetime and 100 ms age allowance are
**offline demonstration settings**, not commissioned hardware settings.

Outputs are created exclusively. A repeated command using the same output path
fails without overwriting it; choose another path for another experiment.
Recordings and traces use JSONL, so they can be inspected with a text editor.

The built-in CLI example uses the same policy contract:

```bash
uv run --locked cartpole-v2 replay runs/sdk-demo/vision.jsonl runs/sdk-demo/builtin.jsonl --frame-id vision:demo-calibration
```

To use the SDK from another working directory, install its package there or use
`uv run --project /absolute/path/to/cartpole_v2 cartpole-v2 ...` with absolute input
and output paths. The installed command and the example are tested from outside
the checkout. Run tests with `uv run --locked python -m unittest discover -s tests`.

## Write a policy

Start with `examples/replay_policy.py`. A policy implements only these callbacks:

```python
class MyPolicy:
    def reset(self, session: Session) -> None:
        # Reset model/filter state for this run.
        ...

    def act(self, observation: Observation) -> Acceleration | None:
        # Choose explicit channels and compute an acceleration intent in m/s².
        ...
```

`Session` supplies the clock domain and named topology. `Observation.samples`
contains scalar values with source, entity, quantity, SI unit, coordinate frame,
method, validity, reason and measured/estimated/predicted kind. Named joints allow
multi-link data without changing the callback; only the single-pole rig is
commissioned. The current schema contains scalar state, not raw image tensors.

Use `select_channels` with a `Channel(entity, quantity, source, frame_id)` for every
required input. Sources are `magnetic`, `step`, `vision`, `fused` and `simulation`.
The selector matches exactly and rejects missing, unknown, invalid, stale and
future-effective samples. It preserves the requested channel order and performs
no substitution, frame transform or fusion. Raw samples remain accessible for
analysis or an explicitly designed estimator. A `fused` label describes data;
Phase 1 does not supply a fusion algorithm or approve the archived display fusion
as a control input.

Time is integer nanoseconds in the session's single clock domain:

| Field | Meaning |
| --- | --- |
| `acquired_ns` | Sensor acquisition time, or null when unknown |
| `effective_ns` | Time the value/estimate represents; selection uses this for age |
| `received_ns` | Receipt/read time, or null when unknown |
| `available_ns` | Observation availability, with an explicit `availability_basis` |

Source frames must distinguish calibration epochs and coordinate conventions.
Firmware raw angle, vision hanging-reference angle and a future MuJoCo generalized
coordinate are not automatically interchangeable. Do not merge logs by row number
or assign a shared clock without measuring the relationship.

`Acceleration(0)` is an explicit zero-acceleration intent. `None` means no request;
it is neither a zero command nor a physical stop. A trusted backend wraps intents
in `ActionRequest` with session/clock/observation identity, monotonic action
sequence, issue time and strict expiry. `validate_action` checks these fields,
magnitude, lifetime and observation age. Policies cannot supply their own request
sequence or expiry through `act`. Hardware enforcement belongs in the future
trusted broker and Teensy, independently of Python policy behavior.

## Import existing runs

Vision input must be a single, verified calibration epoch. Inspect its companion
session/calibration/event data first: `states.jsonl` alone does not record every
calibration change. A detected calibrated→uncalibrated transition is rejected;
initial uncalibrated→calibrated startup is allowed, and true→true recalibration
still requires checking companion events. Use a unique session ID and a frame identity that records your
calibration choice:

```bash
uv run --locked cartpole-v2 import-vision /path/to/states.jsonl /path/to/new-recording.jsonl --session-id vision-run-001 --frame-id vision:calibration-001
```

The adapter preserves angle/cart validity independently and retains unusable
numeric remnants as invalid/unknown. Velocity gets its reported effective time;
camera acquisition remains unknown. Availability uses host-read time plus
`host_read_to_result_ms` when present, otherwise an explicit host-read proxy.
Missing older velocity status remains unknown. Spatial extrapolation beyond a cart
calibration segment is labeled; it does not imply a temporal prediction.
Non-increasing sequence/host-read time or decreasing result availability fails
with a line number, requiring segmentation or investigation rather than sorting.

For the baseline twelve-column console CSV:

```bash
uv run --locked cartpole-v2 import-console /path/to/run.csv /path/to/new-output-directory --session-id console-run-001 --frame-id firmware:reference-001
```

This creates `segment-0000.jsonl` and more segments if the board clock resets.
A backward uint32 millisecond jump greater than half the range is treated as wrap;
a smaller backward jump starts a separate session/clock. With emission timestamps
alone, a reset near the wrap boundary is inherently ambiguous. These timestamps
are not sensor acquisition or host receipt, and are not aligned to vision time.
All legacy console values retain **unknown** health/calibration, even when finite.
They are useful for analysis but do not pass valid-channel selection. A future live
broker must expose actual health and calibration metadata before using this path
for control. The import retains four state channels; mode, energy, motor command,
AGC and loop timing remain in the original CSV, not this initial observation schema.

Real snippets and their exact source hashes/line ranges are in
`evidence/phase1/fixture-provenance.json`. Test-only malformed/wrap/reset cases are
explicitly generated and are not rig measurements.

## Recording and replay guarantees

Version 1 recording JSONL has an exact-key session header, observation records and
a required footer counting observations. Unknown versions/fields, duplicate JSON
keys, bool-as-number, non-finite values, inconsistent clocks/topology and bad
ordering are rejected. Truncation is an error; the footer is not an integrity
signature. Writers create new files and remove their partial output on failure.

Replay validates the full input sequence before calling `reset`, then calls `act`
in recorded order using recorded availability time. It models zero policy runtime
and never sleeps. It resets once for each replay invocation, and the example
produces byte-identical traces on repeated runs. A custom policy must itself be
deterministic (seed its random generator; avoid wall-clock and external state) to
get that property. Exceptions and invalid intents fail the run. Trace requests
are offline outputs and are never sent to a device.

This version materializes sessions/replay results in memory. Use bounded session
files for now; a streaming backend and retention policy belong with the recorder
service. Uploaded/untrusted Python is not accepted by these tools.

## Next integration points

The next local milestone can proceed in two parallel tracks after this foundation:

1. Port the preserved controller's filters and state machine to Python, comparing
   outputs and transitions against an executable C++ reference at explicit rates.
   Saved tuned gains must be imported with provenance, not retuned implicitly.
2. Add a MuJoCo plant and training wrapper. Use this same `Policy` and SI intent;
   explicitly convert acceleration intent through actuator dynamics. Keep simulator
   ground truth separate from generated sensor observations, with configurable
   delay, sampling and validity. Initial model parameters remain provisional until
   measured identification and held-out validation.

Then integrate the exclusive Jetson device broker and new Teensy command executor,
with sequence/epoch/expiry enforcement and independently commissioned safety.
Read-only telemetry comes before any external-policy motion. Transport timing and
host scheduling must be measured; replay is not a 1 kHz Python feasibility test.
Raw camera tensors, richer actuator diagnostics, policy configuration/provenance,
clock alignment and real fusion remain explicit future schema/backend work.
