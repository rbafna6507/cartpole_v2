# Run system identification yourself

Use `scripts/system-id` to collect reproducible records, fit independent training and validation data, and export an explicitly scoped MuJoCo/Gym configuration. It resolves its repository from the script location, so it works from another directory. It uses `uv`: collection selects `hardware` plus `id` (NumPy), fitting selects `id`, plotting selects `id` plus `plots`, and simulation/model commands select `sim`. Hardware collection does not require MuJoCo or Gymnasium, and help needs no optional extra. An installed SDK also provides `cartpole-id`.

```sh
ID=/absolute/path/to/cartpole_v2/scripts/system-id
"$ID" --help
"$ID" collect-passive --help
```

Help and offline commands never open serial. Hardware commands require an explicit port and a **new output directory**. They preserve source hashes, live parameters, saved reference/home identity, raw telemetry, timing, failures and STOP outcomes. Existing outputs are never overwritten. A failed run remains failed evidence; use another directory for the next attempt.

The scripts do not calibrate, home, clear faults, change parameters, flash firmware or change scheduler settings. Resolve preflight failures using the separate trusted rig console. Installed limit switches must remain enabled and released. Only one process may own serial.

## 1. Inspect the stopped rig

Purpose: record readiness, the complete live parameter catalog, and the currently saved reference and home epoch. Inspection connects stopped and sends STOP before completion.

```sh
PORT=/dev/serial/by-id/your-device
"$ID" inspect --port "$PORT" --output runs/inspection-01
```

Collection requires a healthy, homed, disabled executor, saved valid encoder reference, cart within 3 mm of counted home, settled governor, and a quiet hanging pole. It accepts the current saved reference/home rather than hardcoding a particular installation. Add `--expected-reference 330 --expected-home 14` when you intend to pin those exact values; use your inspected values.

## 2. Collect manual passive releases

Purpose: identify passive pole gravity/damping from free motion while the operator physically restrains the cart. The script **never arms**. New passive recordings require the camera and first measure two quiet seconds of hanging encoder/camera data. Keep the pole hanging freely and the cart fixed during `measuring_hanging_baseline`; both markers must be visible. This establishes an **experiment-relative zero**, without sending firmware calibration or changing the saved upright reference or camera service calibration. The release timer starts afterward. Wait for its `"status":"recording","drivers_enabled":false` message, then displace and release the pole. Record several releases with different amplitudes and both directions. Keep hands clear of the pole during each selected free interval and distinguish handling from free motion in your annotations.

```sh
"$ID" collect-passive --port "$PORT" --seconds 180 \
  --dataset-role training --run-label passive-30-60-both-repeat2 \
  --release-angles-deg 30 60 --release-directions left right --repetitions 2 \
  --cart-restraint "cart held stationary by hand" \
  --output runs/passive-train-01
# On a separate recording, collect fresh validation releases after freezing
# the training model and the intended validation procedure.
"$ID" collect-passive --port "$PORT" --seconds 180 \
  --dataset-role validation --run-label fresh-passive-holdout \
  --release-angles-deg 30 60 --release-directions left right --repetitions 2 \
  --cart-restraint "cart held stationary by hand" \
  --output runs/passive-validate-01
```

While recording, a compact `angles` message appears twice per second with `encoder_from_hanging_deg` and `camera_from_hanging_deg`. Use their absolute magnitudes to help aim for the requested pose. A missing camera reading is `null`; it is never filled from the encoder or fusion. These are live relative-angle readings, not final release verification. Hold each intended release pose still for **two seconds with both markers visible**, then release without pushing.

The script prints the sequence after recording starts: 30° left, 30° right, 60° left, 60° right, then repeats. These angles are **requested conditions**, not measurements or automatic fit windows. Conditions, dataset role and restraint are hashed into both the raw log and completion report. The role is descriptive; actual source/session independence is checked during fitting. At most 12 releases fit in one labelled recording, and recording is bounded to 180 seconds. If full settling takes longer, split the procedure across recordings instead of rushing. The collector neither measures nor automatically confirms when each requested release occurred.

Aim for repeatable cart restraint; a rigid clamp is stronger evidence than holding it by hand. If you use your hand, say so. Keep the camera fixed and markers visible. Nominal left/right is the **camera view**, not a hardcoded encoder sign.

### A horizontal (90°) release

The existing collector already accepts 90° from hanging. With the pole hanging vertically down as 0°, 90° is **horizontal**, to either side. This is easier to reproduce visually than 60°. Keep the cart fixed, hold the horizontal pose for two seconds, then release without pushing. The motor stays disabled. Leave enough clearance for the full free swing and keep both markers visible.

Collect a separate large-angle pilot so it does not replace the first batch:

```sh
"$ID" collect-passive --port "$PORT" --seconds 120 \
  --dataset-role development --run-label horizontal-90-pilot \
  --release-angles-deg 90 --release-directions left right --repetitions 2 \
  --cart-restraint "cart held stationary by hand" \
  --output runs/passive-horizontal-90-01
```

The four requested releases are left, right, left, right. Once the procedure is repeatable, collect separate training and validation recordings using the matching dataset role and new output names. Keep smaller-angle data as well; horizontal releases add coverage rather than making lower-amplitude data obsolete. The passive equations use sine/cosine gravity terms and do not require a small-angle approximation, but a fit still has to pass each held-out release. Stronger swings also make independent cart restraint more important.

### Requested angle versus plotted angle

A request for 60° is a label, not a mathematical assumption in the fitter. A clean release actually around 40° is useful for identifying and validating that measured range; it cannot establish 60° or 90° accuracy. Do not change encoder measurements or relabel measured angles to force agreement with the requested pose.

For new recordings containing `passive_baseline`, `raw-observations.png` subtracts the measured initial hanging encoder baseline, so settled hanging starts at **0°**. Raw `theta` remains unchanged in the JSONL; the fitter still uses it and estimates its training-only gravity phase. Camera comparison subtracts its own measured raw image-angle baseline. This removes constant display offsets, not encoder nonlinearity or camera perspective error.

Historical recordings without a measured baseline still plot raw encoder angle minus an integer hanging branch (normally π), **not angle minus the observed settled resting angle**. For example, a resting baseline at −7° and a held pose at +40° are separated by about 47 encoder degrees. Also, the first peak after falling is smaller than the release height because energy has already been lost. Use the pre-release pose and local resting baseline to assess encoder displacement, not just a later peak. This is not an independent physical-angle calibration; the hanging/upright mapping question remains open.

The default raw camera URL is `http://127.0.0.1:3090/api/sensing-stream?max_hz=100`. Camera work runs in a separate process. It inherits the launching process’s CPU affinity: run the integrated collector without `taskset -c 2`, which would pin both camera and control to the same CPU. The package does not change CPU affinity or scheduler settings. A fresh actual camera frame with valid source age is required before serial collection; advancing HTTP heartbeat envelopes alone do not establish camera readiness; camera failure during collection stops the procedure. Use `--camera-url URL` for an explicit endpoint. Passive collection rejects `--no-camera`; the older optional-camera pulse workflow remains available separately. Raw marker geometry can support stationarity assessment, but uncalibrated pixels do not establish metric cart motion or global angle calibration.

Camera-enabled sessions also publish the current encoder session to the portal through the existing read-only UDP mirror. Mirrored or fused values in camera packets are display data. Fitting uses **direct Rig JSONL raw `theta`**, never `angle_hat`, mirrored encoder packets or filtered `omega`. Board `unwrapped_us` and raw camera `vision.t` have different clock meanings. New recordings save local camera receipt timestamps plus bounded `/api/clock` round trips before and after capture. Review interpolates those offsets to collector time and then maps encoder receipt time to board time. Synchronization uncertainty, source gaps and unknown exposure/serial latency stay explicit. No sensor fusion or fitted time shift is used to manufacture agreement. The NDJSON contains raw marker geometry and angles, not a replayable movie.

After all intended releases have settled, type **`done` then Enter** in the collection terminal. `--seconds` is the maximum recording duration after the hanging baseline; reaching it also finishes normally. During the `recording` phase, the first Ctrl-C requests the same graceful finish. The collector validates the last telemetry and camera state, confirms STOP, closes the camera capture, and writes the measured baseline, requested duration, actual elapsed duration and finish reason to the result and raw log. Closing standard input does not count as `done`.

Ctrl-C before `recording` (including the hanging baseline) or during a driven pulse remains an interruption failure. A second interrupt, a disconnected camera, stale/unhealthy telemetry, STOP failure or lost logger records also fails the run. Inspect `report.json` and `vision-report.json`, not just whether files exist. Graceful finish means capture completed; it does not establish that enough independent releases were collected or that the model is valid.

### Batch 2 operator commands

On the Jetson, use the updated staged checkout (earlier recordings remain in the earlier checkout):

```sh
cd ~/cartpole-v2-live/staging/operator-id-20261017-camera-zero
PORT=/dev/serial/by-id/usb-Teensyduino_USB_Serial_20242870-if00
./scripts/system-id collect-passive --port "$PORT" --seconds 180 \
  --dataset-role training --run-label passive-training-2 \
  --release-angles-deg 30 60 90 --release-directions left right --repetitions 1 \
  --cart-restraint "cart held stationary by hand" --output runs/passive-training-2

# Once the first recording has completed, start fresh releases for validation:
./scripts/system-id collect-passive --port "$PORT" --seconds 180 \
  --dataset-role validation --run-label passive-validation-2 \
  --release-angles-deg 30 60 90 --release-directions left right --repetitions 1 \
  --cart-restraint "cart held stationary by hand" --output runs/passive-validation-2
```

Each requests 30° left/right, 60° left/right, then 90° left/right. Keep the console closed and the camera fixed, with full swing and both markers visible. At 90° the pole is horizontal. Hold the cart still throughout, hold each pose for two seconds, release without pushing, and let the motion settle before the next. Start each command with the pole hanging; wait for `recording` before touching it. After the last release settles, type `done` then Enter; you do not need to wait for all 180 seconds. If baseline quality fails, fix the stated condition and choose a new output name. Do not overwrite failed evidence.

For the current collaboration, the operator only collects and reports the directory names. The agent then reviews both raw sources, records held-pose/release/free-motion times before fitting, fits on training, scores independent validation, plots predictions and exports only an accepted model. No new-data fit/export has been performed before those recordings exist.

## 3. Review the raw recording, then annotate free intervals

```sh
"$ID" review-recording --input runs/passive-train-01/rig-EXACT.jsonl \
  --output runs/passive-train-01-review
```

Open `raw-observations.png` or its PDF beside `report.json`. The plot uses board-relative seconds and shows raw angle relative to the hanging branch, counted cart position/commanded velocity, demand and governor acceleration. Check missing samples, handling, repeated releases and actual angle excursions. Completion/STOP and source identity are checked before plotting; this step does not fit a model, certify physical cart stationarity or pick favourable intervals.

Find the `rig-*.jsonl` file in each run directory. Plain JSONL, `.jsonl.gz` and `archive.tar.gz::exact/member.jsonl` are supported. The hash in an annotation is the decompressed exact JSONL content hash. Loading is bounded to 256 MiB of decompressed JSONL, 4 MiB per line and 500,000 records; archive scans additionally cap entries and total declared bytes. Files are streamed and archive members are never extracted.

Keep each newly collected raw log with its sibling `report.json`, including when archiving or compressing it. Fitting requires that report to match the raw basename and decompressed hash, confirm completion and STOP, and record zero logger drops and no camera/collection failure. Raw termination errors and failed STOP records also reject admission. Historical raw-only recordings retain an explicitly labeled compatibility path; they do not acquire a new completion guarantee.

For an older passive recording stopped by the operator's Ctrl-C, keep all original files unchanged. A separate, explicit recovery review can retain usable evidence when the exact interruption, confirmed disabled STOP, logger integrity, measured baseline and camera evidence satisfy its checks:

```sh
"$ID" recover-passive --input runs/passive-train-01/rig-EXACT.jsonl \
  --reason "Pressed Ctrl-C after all intended releases had settled"
```

Use a truthful reason. The command creates a sibling `recovery.json` bound to the original files and refuses to overwrite it. The original `report.json` stays incomplete. Only interruption failures covered by the recovery checks are eligible; hardware, camera, stale-data and logger faults remain rejected. Subsequent review, annotation and fit commands revalidate the recovery decision against the exact source files. Recovery admits evidence for review; release verification, annotation and model acceptance remain separate checks.

```sh
"$ID" annotations-template --input runs/passive-train-01/rig-EXACT.jsonl \
  --output runs/train-annotations.json
"$ID" annotations-template --input runs/passive-validate-01/rig-EXACT.jsonl \
  --output runs/validation-annotations.json
```

**Do not draw on or edit the PNG.** “Mark intervals” means read the start/end times from the plot's horizontal axis and enter those numbers in the annotation JSON. The PNG is a static picture, not an interactive selection tool.

For example, on the Jetson:

```sh
nano runs/train-annotations.json
```

Keep the generated `source_sha256` unchanged. For each release:

1. Find the held pose followed by regular decaying oscillations. Start just after release, when your hand is clear; exclude the preceding lift and hold. If the hand-clear time is uncertain, choose a conservative later start and state that uncertainty.
2. End before you touch/lift the pole again, before the recording ends, or when the motion becomes a flat stationary tail. Keep multiple complete oscillations; very short fragments may fail the required validation-window count.
3. Add a unique `episode_id`, `board_relative_s: [start, end]`, and a truthful `reason`. Use your memory/video of the release to distinguish free motion from handling; an encoder trace alone cannot prove your hand or the cart was clear.
4. Describe how the cart was restrained and how you selected the windows. Once the intervals are fixed **before any fit scoring**, set `selected_before_scoring` to `true`.

In nano, save with Ctrl-O then Enter and exit with Ctrl-X. Repeat for the validation annotation file. The numbers below are illustrative, not timestamps to copy into a different recording. If you already created `train-annotations.json`, edit it; `annotations-template` intentionally refuses to overwrite it.

Edit each new template manually. Its time zero is the first recorded STATE. Supply a truthful restraint description and selection method, then add nonoverlapping hand-clear intervals:

```json
{
  "source_sha256": "keep the generated source hash",
  "selected_before_scoring": true,
  "operator_cart_restraint": "cart base physically restrained by operator",
  "selection_method": "free-motion boundaries read from raw plot and my release observations before scoring",
  "episodes": [
    {"episode_id":"release-1", "board_relative_s":[8.2,11.2], "reason":"hand clear; freely decaying pole"},
    {"episode_id":"release-2", "board_relative_s":[16.1,19.1], "reason":"opposite direction free release"}
  ]
}
```

Do not choose intervals by whichever ones fit best. Static tails cannot validate a dynamic model. Separate recordings and source identities are required for training and validation; renaming a copy does not create a holdout. Exact repeated STATUS snapshots are counted and deduplicated only when every board field agrees; contradictory repeats and reversed clocks fail without rewriting the source.

### Keep batch 1; extend its coverage with batch 2

The [2026-10-17 batch-1 review](../evidence/operator-batch1-20261017/README.md) checks the actual `passive-train-01` and `passive-validate-01` recordings and includes an illustrated annotation example. Both are candidates for annotation and an initial fit; neither has been fitted by that review.

Use the first training and validation recordings for an initial fit if completion/STOP, health, clock integrity, reference consistency, restraint and free-interval selection check out. Requested-angle undershoot alone is not a reason to discard them. A quality review before scoring does not consume the validation set; using its prediction errors to change the model does. If you tune the model after inspecting batch-1 validation errors, that validation recording becomes development evidence, and batch 2 can supply a fresh holdout.

Collect improved 60° and separate 90° releases to cover the missing amplitudes. Validate the same physical model on both lower and higher ranges, rather than replacing every smaller swing with a large one. Preserve every original recording and do not overwrite batch 1. Until the intervals are annotated and the fit is scored, “candidate data” does not mean an accepted model.

### Check measured release poses against the camera

For new baseline-bearing recordings, each annotation also needs `pose_board_relative_s: [held_start, held_end]` and `release_board_s`. The pose window must be stationary, last at least 0.15 s, and end within 0.5 s before the explicitly observed release time. `board_relative_s` still selects **only free motion** for the fit. For example (illustrative times only):

```json
{"episode_id":"release-1", "pose_board_relative_s":[8.0,9.8], "release_board_s":10.0,
 "board_relative_s":[10.1,16.0], "reason":"held pose then hand-clear free oscillation; cart restrained"}
```

Run the separate offline camera review after freezing annotations:

```sh
"$ID" review-releases --input runs/passive-training-2/rig-EXACT.jsonl \
  --annotations runs/train-annotations.json --output runs/passive-training-2-camera-review
```

It creates `release-overlay.png`/PDF and `report.json`: raw encoder and raw camera angles relative to their independently measured hanging baselines, signed held-pose angles, sensor differences, camera gaps and pixel pivot motion. Missing geometry stays missing. Orange denotes the held pose, green free motion, red missing camera coverage. The review never fits zero, scale, sign, timing or a model to make the sensors agree. Geometry/sign follow the existing SDK convention.

Provisional checks are declared before batch 2: at least 70% valid camera coverage, no gap over 0.15 s, at least 10 camera frames per free interval, angular RMS ≤5° and P95 ≤10°, stationary pose spread ≤2°, pose disagreement ≤5°, arm length within 20% of baseline, and apparent pivot radial P95 motion ≤max(4 pixels, 2% of baseline arm length). These are consistency screens, not absolute camera accuracy or metric proof of fixed cart position. Passing the camera check does not override failed dynamics validation. New baseline-bearing training **and** validation must pass camera checks and explicit release-pose verification before a fit can be accepted/exported; historical recordings retain their original conditional path.

## 4. Fit and validate passive dynamics

Declare the model before scoring validation. The default viscous model is directly representable in the current simulator. The optional `viscous_coulomb` model is useful for diagnosis but a nonzero Coulomb term cannot currently be exported.

```sh
"$ID" fit-passive \
  --training runs/passive-train-01/rig-EXACT.jsonl \
  --training-annotations runs/train-annotations.json \
  --validation runs/passive-validate-01/rig-EXACT.jsonl \
  --validation-annotations runs/validation-annotations.json \
  --model viscous --output runs/passive-fit-01.json
```

The copied, reviewed weak-form method retains the frozen numerical gates. Parameters and local gravity phase are estimated from training only. Reports include aggregate and per-episode validation, conditional uncertainty, raw/annotation/source hashes and rejection reasons. Gaps never join integration windows. Exit 0 means the configured scoped checks passed; exit 2 means rejection or invalid input. Rejected fit reports are saved with no recommended model.

Before exporting, plot the **saved** fit against the exact held-out recording:

```sh
"$ID" review-fit --fit runs/passive-fit-01.json \
  --validation runs/passive-validate-01/rig-EXACT.jsonl \
  --validation-annotations runs/validation-annotations.json \
  --output runs/passive-fit-01-review
```

Open `recorded-vs-frozen-ode.png` or its PDF and `report.json`. This works for accepted **or rejected passive fits** with numerical coefficients. It verifies source/annotation provenance and plots measured angle against fixed 0.5 s forecasts and an uninterrupted rollout. It does not refit or change acceptance. These are fitted pendulum ODE predictions, labelled separately from actual MuJoCo trajectories; they diagnose the gravity/damping fit before export. Look for phase drift, systematic amplitude errors, left/right differences and failures at larger angles. A smooth-looking aggregate can hide one poor release; inspect each release and the report's per-episode gates. Review command success means the review was generated, not that the fit passed.

The fixed short-horizon gates include RMS ≤0.08 rad (4.58°), 95th-percentile error ≤0.15 rad (8.59°), integral NRMSE ≤0.15 and sufficient dynamic windows **for each episode**. Uninterrupted rollout error is displayed separately and must also be judged against the intended use. If you alter the model after seeing validation, that recording becomes development data; reserve a fresh recording for the next validation. Do not lower gates just to export.

Even a passed report is **conditional passive-down evidence**: physical cart restraint and angle mapping remain assumptions unless independently established. An inferred hanging-region phase is not a global encoder calibration. A short-horizon validation score does not validate upright, full-swing, motor force, actuator delay or hardware RL transfer. Existing archived training/heldout results are unchanged and do not become newly accepted models merely because this workflow exists.

## 5. Collect a bounded driven pulse

Purpose: excite the cart/pole coupling with a short known reference, return the cart toward counted home, and observe the response under active cart hold. Begin with signed **5 mm**. Inspect real motion, angle excursion, timing, health, camera evidence, clamping and return behavior before choosing a larger trial. The allowlist is not an automatic escalation schedule.

```sh
"$ID" collect-pulse --execute --port "$PORT" --amplitude-mm 5 \
  --pulse-seconds 0.65 --hold-seconds 12 \
  --dataset-role development --run-label plus5-duration065 \
  --output runs/pulse-plus5-01
# A separately chosen opposite-direction trial:
"$ID" collect-pulse --execute --port "$PORT" --amplitude-mm -5 \
  --pulse-seconds 0.65 --hold-seconds 12 \
  --dataset-role development --run-label minus5-duration065 \
  --output runs/pulse-minus5-01
```

The reference is `x=A*sin(pi*t/T)^4`, with zero position, velocity and acceleration at both endpoints. Allowed amplitudes are ±5/10/20/30 mm; `--pulse-seconds T` allows 0.45, 0.65 (unchanged default), 0.8 or 1.0 s. Combinations exceeding 3 m/s² analytic reference acceleration are rejected before opening serial; ±20/30 mm at 0.45 s are rejected. The pre-pulse quiet baseline is 1 second. At 30 mm and 0.65 s the analytic peaks are 0.18836 m/s velocity, 2.80320 m/s² acceleration and 37.0662 m/s³ jerk. These are reference bounds, not measured trajectory guarantees.

After checking the ±5 mm pilot, useful next development trials are interleaved +10/−10 mm at 0.65 s, then +10/−10 mm at 0.45 s and 0.8 s. Run and review them individually. Varying duration changes excitation frequency and helps separate dynamics from the chronological equilibrium shifts seen in the existing data. Retain the static baseline and camera evidence. Do not paste this as an unattended escalation loop. The older evidence-specific `analyze_camera_step_pulses.py` assumes a 0.65 s pulse; do not use it unchanged for new durations.

The 100 Hz policy commands `a_ref + 80*(x_ref-x) + 14*(v_ref-v)`, clamped to ±3 m/s². It retains the MCU's unchanged 20 ms anchored lease, governor, rail and health checks. Runtime guards stop at |x|≥0.05 m, |v|≥0.3 m/s, departure from the initial hanging angle≥1 rad, |omega|≥10 rad/s, replay, or host/board gaps≥20 ms. The pulse is followed by **feedback cart hold** for an explicit `--hold-seconds` value from 3 through 12 s (default 12 s), with a bounded 40 ms deadline allowance; this is not zero-input passive decay or independently proven fixed-cart motion.

Logs distinguish requested acceleration, reference acceleration and sampled MCU governor acceleration. The 100 Hz command steps can reach the existing MCU jerk limit even when analytic reference jerk is lower. Full raw telemetry is still sampled at 100 Hz; fast driven fitting may require replaying the 1 kHz governor between samples. A policy clamp is explicitly recorded as a fitting protocol deviation.

The existing driven fitter is wrapped without changing its numerical fit or original gates:

```sh
"$ID" fit-driven --training runs/pulse-train/rig-EXACT.jsonl \
  --validation runs/pulse-validation/rig-EXACT.jsonl \
  --output runs/driven-fit-01.json
```

It uses direct raw angle and the MCU's jerk-limited `acceleration`, not demand. The CLI additionally requires validation angle span ≥0.15 rad and input standard deviation ≥0.05 m/s², using the existing excitation minima. This prevents a static, zero-error validation recording from certifying dynamics. Reports preserve the untouched `underlying_fit` and the supplemental check; overall rejection blocks model export. A single brief pulse may lack the existing fitter's minimum excitation/window coverage; such a result stays rejected. Plan sufficient distinct forcing before freezing fresh validation, rather than lowering gates after seeing rejection.

## 6. Export a scoped simulation model

Purpose: create a new immutable simulator configuration from an accepted fit, with every remaining assumed quantity visible.

```sh
"$ID" assumptions-template --output runs/assumptions-01.json
# Edit the full config and provide a nonempty rationale for assumed masses,
# rail, force authority, cart damping and other unmeasured dynamics.
"$ID" export-model --report runs/passive-fit-01.json --scope passive-down \
  --assumptions runs/assumptions-01.json --output runs/model-01.json
```

The template explicitly uses 1 ms physics and `control_steps=10`, so Gym operates at 100 Hz. Export changes only effective length and hinge damping:

`hinge_damping = gamma * I_pivot`, with `I_pivot = 0.75 * assumed_pole_mass * L_eff^2` for the simulator's uniform-rod convention.

It preserves the full fit report, its hash, source hashes, scope, assumptions and local-phase limitations. No live reference or default model is changed. Rejected fits cannot export. Unsupported Coulomb friction, non-unit driven input gain or nonzero driven delay also fail, because silently omitting them would misrepresent the model. An export always records `recommended_for_hardware_rl=false`.

## 7. Load in MuJoCo/Gym

```sh
"$ID" gym-smoke --model runs/model-01.json --steps 100 \
  --output runs/gym-smoke-01.json
uv run --project /absolute/path/to/cartpole_v2 --extra sim python \
  /absolute/path/to/cartpole_v2/examples/load_identified_model.py runs/model-01.json
```

The existing example creates the **direct plant** `CartpoleEnv` from the verified export at 100 Hz. It is a loading/physics smoke test; it does not include the MCU governor or host leases and is not the RL training environment.

For RL use the new **`RigCartpoleEnv` and PPO training entry point** described in [RL training and Colab](rl-training.md). They use a 1 kHz executor governor and encoder observer with 100 Hz decisions. Actions are raw acceleration intent in m/s², and policy inputs use the same encoder/commanded-state codec as the real SDK. Requested acceleration goes through the saved jerk, velocity, acceleration and rail limits. The seven state channels are counted cart position, commanded velocity, sine/cosine of encoder angle, estimated angular rate, governed acceleration and brake direction; validity and age channels accompany them. Ground-truth physics is used for diagnostics/reward, not policy observations.

Provide an explicit controller-parameter snapshot and sensor/timing assumptions; simulation loading alone does not establish measured actuator or encoder accuracy. Passive-down exports are still local evidence, so full-swing PPO requires an explicit development-only designation. Checkpoints carry model/config hashes and stay unapproved for hardware deployment.

## What remains before a credible hardware RL candidate

The current physical data is **not yet an accepted full-rig model**. One larger release still fails the fixed tail-error check, and driven fits remain confounded by rest-angle changes. Reconstructing input from cart velocity did not resolve that mismatch. The code and synthetic validation make the workflow runnable; they do not replace physical evidence.

1. Repeat paired 30° and 60° releases with consistent cart restraint, plus independent validation. Keep camera framing and encoder reference fixed. Repeat left/right approaches to expose friction or angle-mapping effects.
2. Vary signed cart-pulse duration and retain pre/post static encoder/camera data. Commanded step counts cannot prove physical cart motion, backlash, missed steps or force capacity; calibrated camera displacement or an independent length measurement is needed for those claims.
3. Validate the angle mapping beyond hanging before full-swing transfer. The fitted local equilibrium phase is not a hanging-to-upright encoder calibration. Use the existing saved upright reference for the working controller; this workflow does not change it.
4. Freeze model structure, fit training data, inspect held-out short and long predictions, then collect a fresh holdout after any model revision. Keep measured quantities separate from assumed masses, force, friction and timing.
5. Train and evaluate in simulation across held-out seeds and explicit parameter/sensor variations. The present PPO script uses a fixed declared model; randomized training should follow defensible uncertainty ranges, not arbitrary ranges invented to hide poor fits. A final policy still needs bounded supervised hardware commissioning.

There is no need to wait to exercise Colab or inspect PPO learning on an explicitly provisional model. There is a need to keep that software test separate from claiming a policy is ready for this rig.
