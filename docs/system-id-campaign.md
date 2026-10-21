# Collecting the remaining system identification data

Use `./scripts/system-id-campaign` from this checkout. It installs its required
Python dependencies with `uv`; no editable Python scripts or notebook are needed.
Offline tests cover collection orchestration, guards and artifact generation.
Check each live recording's report for its actual completion and STOP outcome;
collection does not automatically update or qualify a simulator or policy.
See [the October 20 live results](checkpoint-20261020.md), including the remaining
host command-deadline failures; a completed trial is not a reliability guarantee.

## What each suite measures

| Suite | Procedure | What the evidence can answer |
| --- | --- | --- |
| `actuator` | Repeated positive/negative smooth cart pulses and direction reversals, then cart feedback hold | Physical camera displacement versus commanded steps, tracking gain, directional asymmetry, slow lag and missed motion |
| `timing` | A quiet cart-position feedback hold at 100 Hz, with 20 ms action leases | Host receipt gaps, policy execution and transport write duration, and when telemetry first reports an action sequence |
| `coupled` | Short preserved **Teensy AUTO** runs using the live gains | Whether the combined cart/pole model predicts driven swings and capture; reserve separate runs for validation |
| `autonomous` | Timing, actuator and coupled trials, repeated in a fixed order | All three powered measurements in one serial session |
| `cart-map` | Six motor-disabled, ruler-measured cart positions, approached in both directions | Independent pixel-to-metre anchors; step counts are not used as physical truth |
| `angle-map` | 32 motor-disabled holds spanning hanging, intermediate angles and upright, approached in both directions | Encoder offset versus angle, approach and repeat; separates a constant zero error from nonlinear mapping/hysteresis |
| `capture-friction` | 12 motor-disabled small releases near upright | Near-zero-speed friction, possible stiction, and whether the fitted hanging-region friction law predicts capture-region motion |

The powered `gentle` level uses six signed 10/20 mm pulse/reversal trials per
repetition. `standard` includes those plus six faster/larger 30–60 mm trials.
These are **position references**, not promises about actual motor movement.
External demands are capped at 8 m/s², further reduced by live acceleration
limits; jerk uses the live setting. The external-motion guards are at most
100 mm from center and 0.6 m/s. Coupled AUTO uses its existing live motion limits.
No collector changes gains, jerk, firmware, encoder zero, switch profile or
watchdogs. In particular, it does not silently replace your working gains.

Camera frames are required by default for every suite. Raw detector geometry is retained
along with encoder data and any published fusion fields. Analysis uses independent
raw camera geometry, not fused values as an independent angle reference. These
files contain tracking records, **not an encoded video recording**.

## Powered collection without the camera

If the camera is unsuitable for a session, explicitly add `--encoder-only` to
`collect` for `timing`, `actuator`, `coupled` or `autonomous`. This mode does not start a camera recorder or read camera measurements and
produces no `vision.ndjson` or `vision-report.json`. The SDK still publishes
encoder telemetry to the loopback vision display. Manual calibration suites
still require the camera.

```sh
./scripts/system-id-campaign collect --suite timing --seconds 5 --repetitions 1 \
  --port "$PORT" --execute --encoder-only --dataset-role training \
  --run-label encoder-timing-001 --output runs/id-encoder-timing-001

./scripts/system-id-campaign collect --suite autonomous --level gentle \
  --port "$PORT" --execute --encoder-only --dataset-role training \
  --run-label encoder-dynamics-001 --output runs/id-encoder-dynamics-001
```

Complete the same healthy, homed, centered and quiet-pole preflight described
below. Encoder-only mode retains the live motion limits, released-switch checks,
reference/home pins, freshness and action-lease guards, STOP behavior and saved
counted-home returns. It changes only the camera prerequisites and recording.

The report and trial events state `sensor_mode: encoder_only`; camera evidence
is explicitly absent. These data support host/transport timing diagnostics,
executor count/command consistency and pole-model replay conditional on recorded
governor input. Counted cart position and governor velocity/acceleration remain
internal executor quantities. They cannot establish physical actuator gain,
latency, slip, independent cart scale or global encoder-angle accuracy.

Run `review` and `bundle` normally. Review retains timing and encoder diagnostics
and adds an explicit missing-independent-camera blocker; `ready_for_fit` and
`hardware_accepted` remain false. A completed encoder-only campaign therefore
does not qualify a physical actuator fit. Reserve a separately labeled validation
recording before comparing predictions. Conditional replay must preserve this
measurement limitation and must not relabel the validation recording as training.

## Rehearse now, without the rig

```sh
./scripts/system-id-campaign --help
./scripts/system-id-campaign plan --suite autonomous --level gentle
./scripts/system-id-campaign rehearse --suite autonomous --output runs/id-rehearsal-001
./scripts/system-id-campaign review \
  --input runs/id-rehearsal-001 --output runs/id-rehearsal-001-review
./scripts/system-id-campaign bundle \
  --input runs/id-rehearsal-001 --output runs/id-rehearsal-001.tar.gz
```

`plan`, `rehearse`, `review` and `bundle` never open serial or contact the camera.
The rehearsal checks file generation, review and packaging with synthetic data;
it does not pretend to execute the live hardware workflow. Its review correctly
reports `synthetic: true`, `ready_for_fit: false` and `hardware_accepted: false`.
All output paths must be new. Review and archive outputs must be outside the
sealed recording directory.

## Prepare the Jetson later

For the default camera mode, keep the camera fixed, showing the entire rail and both pole markers. Start the
maintained vision service as usual; its default raw stream is
`http://127.0.0.1:3090/api/sensing-stream?max_hz=100`.
Override `--camera-url` if your service is elsewhere. The recorder retains camera
clock round trips at the start and end; a local service minimizes uncertainty.

Use the normal console to load the working defaults and complete physical HOME:

```sh
PORT=/dev/serial/by-id/usb-Teensyduino_USB_Serial_20242870-if00
uv run --locked --extra hardware cartpole-console --port "$PORT" --rate 100
# In the console: home; wait for completion; status; stop; quit.
```

Retain a valid saved upright reference. The collector checks reference/home
identity and reads all live motion settings; it never recalibrates them. If you
want a different known profile, load it explicitly in the console first. Close
the console, leave the pole freely hanging and the rig clear before powered
collection. The camera process is a read-only recorder and never opens serial.

The first trial requires healthy firmware, both cart switches enabled and
released, a measured home, disabled motor, and a centered, quiet hanging pole.
Successful powered trials STOP, return to the **saved counted home**, then wait
up to 60 seconds for hanging to settle before the next trial. `--execute`
authorizes these motions. No full HOME or fault clear is attempted automatically.
Any fault, stale source, identity change, log loss or failed STOP aborts the
campaign. Ctrl-C aborts powered collection and attempts STOP; partial evidence
is retained. Inspect the stopped rig before retrying.

## Recommended first collection session

First get the camera distance anchors. This is guided and remains motor-disabled:

```sh
./scripts/system-id-campaign collect --suite cart-map \
  --port "$PORT" --cart-restraint 'Positioned by hand against a ruler referenced to rail midpoint' \
  --dataset-role training --run-label cart-map-001 --output runs/id-cart-map-001
```

At each prompt, position the cart near the requested -100, 0 or +100 mm location,
enter the **actual ruler measurement**, and describe the reference. Positive is
the right side of the rail. Keep the pole markers visible during each two-second
hold. The requested target is not automatically treated as a measurement. If no
independent measurement is available, enter `unknown`; the raw data survives but
that hold is unqualified. Keep this camera position unchanged for subsequent
cart experiments. These anchors cover only the measured region; do not assume
linear image scale elsewhere without checking it.

**Run a fresh full HOME in the console after cart-map**, then stop and quit.
Moving the disabled cart by hand invalidates its physical step-count home even
if the firmware still reports `homed`. REHOME alone cannot repair this.

Then collect the first bounded powered batch:

```sh
./scripts/system-id-campaign collect --suite autonomous --level gentle \
  --port "$PORT" --execute --dataset-role training --run-label dynamics-train-001 \
  --output runs/id-dynamics-train-001
./scripts/system-id-campaign review \
  --input runs/id-dynamics-train-001 --output runs/id-dynamics-train-001-review
```

Review `raw-overview.png` and `review.json`. If collection completed cleanly and
camera tracking covers the motion, collect the larger reference envelope:

```sh
./scripts/system-id-campaign collect --suite autonomous --level standard \
  --port "$PORT" --execute --dataset-role training --run-label dynamics-train-002 \
  --output runs/id-dynamics-train-002
```

Then record a separately labeled validation batch, without changing parameters
or camera framing. Do not tune the fitted model against this batch and still
call it an unseen holdout:

```sh
./scripts/system-id-campaign collect --suite autonomous --level standard \
  --port "$PORT" --execute --dataset-role validation --run-label dynamics-validation-001 \
  --output runs/id-dynamics-validation-001
```

Defaults are two repetitions and 15-second timing/AUTO runs. Use
`--repetitions 3 --seconds 25` for more repetitions/longer coupled observations.
For isolated checks, select `--suite timing`, `actuator` or `coupled`. Every
powered suite requires `--execute`. `--expected-reference COUNTS` and
`--expected-home EPOCH` optionally pin the initial identity; the campaign always
pins the observed identities and settings internally across its trials.

## Guided angular mapping and capture friction

These suites never arm, return home or transition into powered tests. Restrain
the cart independently while moving/releasing the pole. The cart step estimate
cannot establish physical restraint while the driver is off.

```sh
./scripts/system-id-campaign collect --suite angle-map --port "$PORT" \
  --cart-restraint 'Cart held stationary by hand at center' \
  --dataset-role training --run-label angle-map-001 --output runs/id-angle-map-001

./scripts/system-id-campaign collect --suite capture-friction --port "$PORT" \
  --cart-restraint 'Cart held stationary by hand at center' \
  --dataset-role validation --run-label capture-friction-001 --output runs/id-friction-001
```

Angle-map requests hanging, ±45°, ±90°, ±135° and upright from both increasing
and decreasing angular approaches, twice each. Set the pose with an independent
angle gauge, plumb/level fixture or known jig. Enter the actual measured angle
and method. Zero is true hanging/downward vertical; positive follows the raw
encoder's positive rotation direction. A natural resting pose may be recorded
as `unknown`, but is not automatically a measurement of true vertical.

Capture-friction requests ±5°, ±10° and ±20° from upright, twice each. Select
whether the upright basis is `working-upright` or independently measured
`true-vertical`; these are retained as different claims. The actual-angle prompt
still uses hanging-zero degrees, not the small requested upright offset. Release
without pushing, then acknowledge `released`. Continuous raw recording covers
the period before the keypress. A release bracket extends from the held pose to
the acknowledgement; the subsequent six-second window does **not** claim that
the keypress was the physical release time. Analysis will locate the release
inside that bracket using both sensors.

`done` at any manual prompt ends early and retains the incomplete session;
`abort` or Ctrl-C stops it as a failure. The default overall manual-session limit
is 30 minutes; `--manual-timeout-s 3600` permits up to an hour. Low confidence,
missing markers, unknown physical labels or unsteady holds remain in the raw
files and are flagged. Completing every prompt is not automatic calibration
acceptance. Repeat in a separate directory/role if an independent angular-map
validation recording is needed.

## Review and send back the files

```sh
./scripts/system-id-campaign review \
  --input runs/id-dynamics-train-001 --output runs/id-dynamics-train-001-review
./scripts/system-id-campaign bundle \
  --input runs/id-dynamics-train-001 --output runs/id-dynamics-train-001.tar.gz
```

Run these for each directory, including partial/failed recordings. Send the
`.tar.gz` bundles; the review outputs are useful to inspect locally and can be
regenerated from the bundles. Bundling checks hashes, rejects symlinks and refuses
to overwrite. It does not discard failed trials or require a successful run.
Do not modify anything inside a sealed recording; put notes alongside it.
If a writer cannot finish during cleanup, the report says `sealed: false` and no
manifest is created. That directory cannot pass normal review/bundling. Preserve
it after the collector process exits and report the failure; do not treat a
still-growing log as a complete recording.

Each recording contains:

- `plan.json`: exact trial order, preset references and declared operating scope.
- `report.json`: source hashes, dataset role, live settings/reference/home,
  per-trial results, failures, camera summary and final STOP status.
- `rig-*.jsonl`: raw encoder/executor telemetry, action demands, command timing,
  policy timing, trial boundaries, and manual labels/windows.
- `vision.ndjson`, `vision-report.json`: raw source-frame geometry/confidence,
  source and collector clocks, and camera clock anchors; omitted in explicitly
  selected encoder-only collection.
- `analysis-request.json`: explicit remaining questions and model-update boundaries.
- `manifest.json`: relative filenames, byte counts and SHA-256 hashes.

The review produces `review.json`, `encoder-executor.csv`,
`camera-geometry.csv`, and `raw-overview.png` when there are telemetry samples.
The plot uses collector receipt time for inspection and marks the distinct angle
frames. It does not secretly fit a time shift or equate image-up with physical
vertical. CSVs preserve separate source clocks for proper subsequent alignment.
The review checks each excitation, feedback, coupled or manual measurement
phase separately: at least 80% valid camera geometry, at least 16 valid frames/s,
90% time-span coverage and no valid-frame gap above 150 ms. Telemetry requires
at least 70 samples/s, 90% time-span coverage and gaps no larger than 50 ms.
These are collection-screening bounds, not sensor-accuracy or control guarantees.

## How this becomes a better MuJoCo/Gym model

Collection and review deliberately do not overwrite the simulator. Once real
training and validation bundles are available:

1. Check collection/STOP integrity, independent ruler/angle labels, source clocks
   and camera coverage. Build the pixel-to-metre mapping on cart-map anchors and
   check the opposite approach/held-out anchors; reject camera-pose changes.
2. Fit actuator response on training trajectories using independent cart motion.
   Compare predictions on the validation trajectories. Steps, commanded velocity
   and governed acceleration are explanatory signals, not physical motion truth.
3. Fit angular error versus independently referenced angle/approach, and test the
   other repeat/recording. Keep true-vertical uncertainty, hysteresis and the old
   local hanging phase separate. Test the near-upright friction model before
   changing its smoothing width or adding static stiction.
4. Check the assembled plant against **held-out coupled AUTO** recordings, with
   predictions versus measurements for angle and cart motion, and report error
   by region, direction and time horizon.
5. Export a **new versioned training profile**, retaining model, executor and
   observation configurations and their provenance. Run `RigCartpoleEnv` contract
   tests, headless rollouts, and frozen-policy stress checks before new training.

The existing `scripts/system-id fit-passive`, `fit-driven`, `export-model` and
`gym-smoke` commands remain available for their documented supported models in
[the original workflow](system-identification-workflow.md). They are not general
exporters for arbitrary new friction, actuator or encoder laws. If new data
supports motor lag/backlash/stiction that the present simulator cannot represent,
we must implement and validate that term before publishing a candidate profile.
Do not force a successful fit through an exporter that drops its dynamics.

Current training consumes `model.json`, `executor-parameters.json`,
`observation-config.json` and `prior-parameters.json`; see
[training commands](rl-training.md). A future measured profile will replace those
explicit inputs for a new run. Current defaults stay frozen until then.

Two limits remain even with a clean campaign: a roughly 60 Hz camera cannot
identify millisecond physical actuator latency, and the quiet timing policy does
not measure a future neural network's inference cost. The scripts measure host
write/receipt timing honestly; high-rate independent cart sensing and timing the
actual deployed actor may still be necessary if those uncertainties affect the
validated policy. Instrumentation itself also adds overhead. The review never
sets `ready_for_fit` or `hardware_accepted` true just because collection completed.
